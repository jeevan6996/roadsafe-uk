import io
import json
import zipfile
from pathlib import Path
from urllib import request

import pytest

from roadsafe import acquisition
from roadsafe.acquisition import (
    AcquisitionError,
    SourceSpec,
    acquire_source,
    acquire_sources,
    source_specs,
)


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.stream = io.BytesIO(content)

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.stream.read(size)


def collision_csv(year: int) -> bytes:
    return f"collision_index,collision_year\nA,{year}\nB,{year}\n".encode()


def archive_bytes(names: list[str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name in names:
            archive.writestr(name, b"fixture")
    return output.getvalue()


def test_source_catalog_is_explicit_and_deduplicates_shared_aadf() -> None:
    specs = source_specs([2024, 2019, 2024])

    assert [spec.requested_year for spec in specs if spec.kind == "collision"] == [2019, 2024]
    assert [spec.requested_year for spec in specs if spec.kind == "roads"] == [2019, 2024]
    assert sum(spec.kind == "aadf" for spec in specs) == 1
    assert all(spec.url.startswith("https://") for spec in specs)
    historical = next(
        spec for spec in specs if spec.requested_year == 2019 and spec.kind == "collision"
    )
    assert historical.reporting_period == "1979-latest-published-year"
    assert historical.year_validation == "contains"


@pytest.mark.parametrize("years", [[], [2018], [2025]])
def test_source_catalog_rejects_missing_or_non_final_years(years: list[int]) -> None:
    with pytest.raises(AcquisitionError):
        source_specs(years)


def test_source_catalog_requires_a_source_kind() -> None:
    with pytest.raises(AcquisitionError, match="source kind"):
        source_specs([2024], set())


def test_acquisition_writes_manifest_and_uses_verified_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def open_fixture(source_request: request.Request, timeout: int) -> FakeResponse:
        calls.append(source_request.full_url)
        assert timeout == 60
        return FakeResponse(collision_csv(2023))

    monkeypatch.setattr(acquisition.request, "urlopen", open_fixture)
    spec = source_specs([2023], {"collision"})[0]

    first = acquire_source(spec, tmp_path)
    second = acquire_source(spec, tmp_path)

    assert first["status"] == "downloaded"
    assert first["validation"] == {
        "available_year_max": 2023,
        "available_year_min": 2023,
        "collision_records": 2,
        "requested_year": 2023,
        "year_validation": "exact",
    }
    assert second["status"] == "cached"
    assert len(calls) == 1
    manifest = json.loads((tmp_path / f"{spec.filename}.manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"]["publication_status"] == "final"
    assert manifest["artifact"]["sha256"] == first["artifact"]["sha256"]


def test_acquisition_refreshes_a_tampered_cached_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def open_fixture(source_request: request.Request, timeout: int) -> FakeResponse:
        nonlocal calls
        calls += 1
        return FakeResponse(collision_csv(2022))

    monkeypatch.setattr(acquisition.request, "urlopen", open_fixture)
    spec = source_specs([2022], {"collision"})[0]
    acquire_source(spec, tmp_path)
    (tmp_path / spec.filename).write_bytes(collision_csv(2021))

    result = acquire_source(spec, tmp_path)

    assert result["status"] == "downloaded"
    assert calls == 2


def test_acquisition_rejects_wrong_collision_year_without_partial_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        acquisition.request,
        "urlopen",
        lambda source_request, timeout: FakeResponse(collision_csv(2022)),
    )
    spec = source_specs([2023], {"collision"})[0]

    with pytest.raises(AcquisitionError, match="do not contain the requested year"):
        acquire_source(spec, tmp_path)

    assert not (tmp_path / spec.filename).exists()
    assert not (tmp_path / f"{spec.filename}.manifest.json").exists()
    assert list(tmp_path.glob("*.part")) == []


def test_historical_collision_source_accepts_requested_year_among_multiple_years(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"collision_index,collision_year\nA,2018\nB,2019\nC,2020\n"
    monkeypatch.setattr(
        acquisition.request,
        "urlopen",
        lambda source_request, timeout: FakeResponse(content),
    )
    spec = source_specs([2019], {"collision"})[0]

    result = acquire_source(spec, tmp_path)

    assert result["validation"]["requested_year"] == 2019
    assert result["validation"]["available_year_min"] == 2018
    assert result["validation"]["available_year_max"] == 2020


def test_acquisition_validates_road_and_aadf_archive_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payloads = {
        "roads": archive_bytes(["roads.shp", "roads.shx", "roads.dbf", "roads.prj"]),
        "aadf": archive_bytes(["dft_traffic_counts_aadf.csv"]),
    }

    def open_fixture(source_request: request.Request, timeout: int) -> FakeResponse:
        kind = "aadf" if "aadf" in source_request.full_url else "roads"
        return FakeResponse(payloads[kind])

    monkeypatch.setattr(acquisition.request, "urlopen", open_fixture)

    report = acquire_sources([2024], tmp_path, {"roads", "aadf"})

    assert [artifact["status"] for artifact in report["artifacts"]] == [
        "downloaded",
        "downloaded",
    ]
    assert (tmp_path / "acquisition-report.json").exists()


def test_acquisition_rejects_incomplete_road_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        acquisition.request,
        "urlopen",
        lambda source_request, timeout: FakeResponse(archive_bytes(["roads.shp"])),
    )
    spec = SourceSpec(
        source_id="roads-test",
        kind="roads",
        url="https://example.test/roads.zip",
        source_page="https://example.test",
        filename="roads.zip",
        reporting_period="2024",
        requested_year=2024,
    )

    with pytest.raises(AcquisitionError, match="missing required members"):
        acquire_source(spec, tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_acquisition_cleans_up_after_transfer_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailedResponse(FakeResponse):
        def read(self, size: int = -1) -> bytes:
            raise OSError("connection reset")

    monkeypatch.setattr(
        acquisition.request,
        "urlopen",
        lambda source_request, timeout: FailedResponse(b"partial"),
    )
    spec = source_specs([2024], {"collision"})[0]

    with pytest.raises(AcquisitionError, match="connection reset"):
        acquire_source(spec, tmp_path)

    assert list(tmp_path.iterdir()) == []
