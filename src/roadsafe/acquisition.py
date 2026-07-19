from __future__ import annotations

import json
import os
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast
from urllib import request

import polars as pl

from roadsafe.pipeline import collision_source_year, sha256_file

SOURCE_PAGE_URL = "https://www.gov.uk/government/statistical-data-sets/road-safety-open-data"
TRAFFIC_DOWNLOADS_URL = "https://roadtraffic.dft.gov.uk/downloads"
OGL_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
COLLISION_URL_TEMPLATE = (
    "https://data.dft.gov.uk/road-accidents-safety-data/"
    "dft-road-casualty-statistics-collision-{year}.csv"
)
COLLISION_HISTORY_URL = (
    "https://data.dft.gov.uk/road-accidents-safety-data/"
    "dft-road-casualty-statistics-collision-1979-latest-published-year.csv"
)
MRDB_URL_TEMPLATE = "https://storage.googleapis.com/dft-statistics/road-traffic/mrdb-{year}.zip"
AADF_URL = (
    "https://storage.googleapis.com/dft-statistics/road-traffic/downloads/"
    "data-gov-uk/dft_traffic_counts_aadf.zip"
)
SUPPORTED_YEARS = tuple(range(2019, 2025))
SOURCE_KINDS = ("collision", "roads", "aadf")
DOWNLOAD_CHUNK_BYTES = 1024 * 1024

SourceKind = Literal["collision", "roads", "aadf"]
YearValidation = Literal["exact", "contains"]


class AcquisitionError(RuntimeError):
    """Raised when an official source cannot be acquired or validated."""


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    kind: SourceKind
    url: str
    source_page: str
    filename: str
    reporting_period: str
    publication_status: str = "published"
    licence: str = "Open Government Licence v3.0"
    licence_url: str = OGL_URL
    requested_year: int | None = None
    year_validation: YearValidation | None = None


def source_specs(years: list[int], kinds: set[SourceKind] | None = None) -> list[SourceSpec]:
    selected_kinds = set(SOURCE_KINDS) if kinds is None else kinds
    unsupported_kinds = selected_kinds.difference(SOURCE_KINDS)
    if unsupported_kinds:
        raise AcquisitionError(f"Unsupported source kinds: {', '.join(sorted(unsupported_kinds))}")
    if not selected_kinds:
        raise AcquisitionError("At least one source kind is required")
    requested_years = sorted(set(years))
    unsupported_years = set(requested_years).difference(SUPPORTED_YEARS)
    if not requested_years:
        raise AcquisitionError("At least one reporting year is required")
    if unsupported_years:
        values = ", ".join(str(year) for year in sorted(unsupported_years))
        raise AcquisitionError(f"Unsupported or non-final reporting years: {values}")

    specs: list[SourceSpec] = []
    for year in requested_years:
        if "collision" in selected_kinds:
            is_historical_source = year == 2019
            specs.append(
                SourceSpec(
                    source_id=(
                        "dft-stats19-collision-history"
                        if is_historical_source
                        else f"dft-stats19-collision-{year}"
                    ),
                    kind="collision",
                    url=(
                        COLLISION_HISTORY_URL
                        if is_historical_source
                        else COLLISION_URL_TEMPLATE.format(year=year)
                    ),
                    source_page=SOURCE_PAGE_URL,
                    filename=(
                        "dft-road-casualty-statistics-collision-1979-latest-published-year.csv"
                        if is_historical_source
                        else f"dft-road-casualty-statistics-collision-{year}.csv"
                    ),
                    reporting_period=(
                        "1979-latest-published-year" if is_historical_source else str(year)
                    ),
                    publication_status="final",
                    requested_year=year,
                    year_validation="contains" if is_historical_source else "exact",
                )
            )
        if "roads" in selected_kinds:
            specs.append(
                SourceSpec(
                    source_id=f"dft-major-roads-database-{year}",
                    kind="roads",
                    url=MRDB_URL_TEMPLATE.format(year=year),
                    source_page=TRAFFIC_DOWNLOADS_URL,
                    filename=f"mrdb-{year}.zip",
                    reporting_period=str(year),
                    requested_year=year,
                )
            )
    if "aadf" in selected_kinds:
        specs.append(
            SourceSpec(
                source_id="dft-aadf-bulk",
                kind="aadf",
                url=AADF_URL,
                source_page=TRAFFIC_DOWNLOADS_URL,
                filename="dft_traffic_counts_aadf.zip",
                reporting_period="2000-latest-published-year",
            )
        )
    return specs


def _manifest_path(target: Path) -> Path:
    return target.with_name(f"{target.name}.manifest.json")


def _cached_manifest(spec: SourceSpec, target: Path) -> dict[str, Any] | None:
    manifest_path = _manifest_path(target)
    if not target.is_file() or not manifest_path.is_file():
        return None
    try:
        payload: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    manifest = cast(dict[str, Any], payload)
    source = manifest.get("source")
    artifact = manifest.get("artifact")
    if not isinstance(source, dict) or not isinstance(artifact, dict):
        return None
    if manifest.get("schema_version") != 1 or source != asdict(spec):
        return None
    if artifact.get("bytes") != target.stat().st_size:
        return None
    if artifact.get("sha256") != sha256_file(target):
        return None
    return manifest


def _validate_archive(path: Path, kind: SourceKind) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if not name.endswith("/")]
            corrupt_member = archive.testzip()
    except zipfile.BadZipFile as error:
        raise AcquisitionError(f"Downloaded {kind} source is not a valid ZIP archive") from error
    if corrupt_member is not None:
        raise AcquisitionError(f"Downloaded {kind} archive has a corrupt member: {corrupt_member}")
    suffixes = {Path(name).suffix.lower() for name in names}
    required = {".shp", ".shx", ".dbf"} if kind == "roads" else {".csv"}
    missing = required.difference(suffixes)
    if missing:
        raise AcquisitionError(
            f"Downloaded {kind} archive is missing required members: {', '.join(sorted(missing))}"
        )
    return {"archive_members": len(names), "required_suffixes": sorted(required)}


def _validate_source(spec: SourceSpec, path: Path) -> dict[str, Any]:
    if path.stat().st_size == 0:
        raise AcquisitionError(f"Downloaded {spec.source_id} source is empty")
    if spec.kind == "collision":
        try:
            years = pl.read_csv(path, columns=["collision_year"])
        except (pl.exceptions.PolarsError, ValueError) as error:
            message = f"Downloaded collision source failed schema validation: {error}"
            raise AcquisitionError(message) from error
        available_years = sorted(
            int(year) for year in years["collision_year"].drop_nulls().unique()
        )
        if not available_years:
            raise AcquisitionError("Downloaded collision source has no reporting years")
        if spec.year_validation == "exact":
            try:
                actual_year = collision_source_year(years)
            except ValueError as error:
                raise AcquisitionError(str(error)) from error
            valid_year = actual_year == spec.requested_year
        else:
            valid_year = spec.requested_year in available_years
        if not valid_year:
            message = (
                "Downloaded collision years do not contain the requested year "
                f"{spec.requested_year}"
            )
            raise AcquisitionError(message)
        return {
            "collision_records": years.height,
            "available_year_min": min(available_years),
            "available_year_max": max(available_years),
            "requested_year": spec.requested_year,
            "year_validation": spec.year_validation,
        }
    return _validate_archive(path, spec.kind)


def _download(spec: SourceSpec, temporary_path: Path) -> None:
    download_request = request.Request(
        spec.url,
        headers={"User-Agent": "roadsafe-uk (+https://github.com/jeevan6996/roadsafe-uk)"},
    )
    try:
        with (
            request.urlopen(download_request, timeout=60) as response,
            temporary_path.open("wb") as destination,
        ):
            while chunk := response.read(DOWNLOAD_CHUNK_BYTES):
                destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())
    except OSError as error:
        raise AcquisitionError(f"Failed to download {spec.source_id}: {error}") from error


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def acquire_source(spec: SourceSpec, output: Path, refresh: bool = False) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    target = output / spec.filename
    cached = None if refresh else _cached_manifest(spec, target)
    if cached is not None:
        return {"source_id": spec.source_id, "status": "cached", "path": str(target), **cached}

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output, prefix=f".{spec.filename}.", suffix=".part", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        _download(spec, temporary_path)
        validation = _validate_source(spec, temporary_path)
        artifact = {
            "filename": spec.filename,
            "bytes": temporary_path.stat().st_size,
            "sha256": sha256_file(temporary_path),
        }
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "source": asdict(spec),
            "artifact": artifact,
            "validation": validation,
        }
        temporary_path.replace(target)
        temporary_path = None
        try:
            _write_json_atomic(_manifest_path(target), manifest)
        except OSError:
            target.unlink(missing_ok=True)
            raise
        return {
            "source_id": spec.source_id,
            "status": "downloaded",
            "path": str(target),
            **manifest,
        }
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def acquire_sources(
    years: list[int],
    output: Path,
    kinds: set[SourceKind] | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    specs = source_specs(years, kinds)
    artifacts = [acquire_source(spec, output, refresh) for spec in specs]
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "requested_years": sorted(set(years)),
        "requested_kinds": sorted(set(SOURCE_KINDS) if kinds is None else kinds),
        "artifacts": artifacts,
    }
    _write_json_atomic(output / "acquisition-report.json", report)
    return report
