from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

SOURCE_URL = (
    "https://data.dft.gov.uk/road-accidents-safety-data/"
    "dft-road-casualty-statistics-collision-2024.csv"
)
SOURCE_PAGE_URL = "https://www.gov.uk/government/statistical-data-sets/road-safety-open-data"

REQUIRED_COLUMNS = {
    "collision_index",
    "collision_year",
    "longitude",
    "latitude",
    "collision_severity",
    "number_of_vehicles",
    "number_of_casualties",
    "date",
    "time",
    "speed_limit",
    "local_authority_highway_current",
}

PILOT_BOUNDS = {
    "min_longitude": -1.75,
    "max_longitude": -1.35,
    "min_latitude": 53.72,
    "max_latitude": 53.90,
}


class DataValidationError(ValueError):
    """Raised when a source file cannot satisfy the published data contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_collisions(path: Path) -> pl.DataFrame:
    frame = pl.read_csv(path, infer_schema_length=10_000, null_values=["", "-1"])
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise DataValidationError(f"Missing required columns: {', '.join(sorted(missing))}")

    frame = frame.filter(pl.col("collision_index").is_not_null()).with_columns(
        pl.col("collision_index").cast(pl.String)
    )

    duplicate_ids = frame.select(pl.col("collision_index").is_duplicated().sum()).item()
    if duplicate_ids:
        raise DataValidationError(f"Found {duplicate_ids} duplicate collision identifiers")

    invalid_severity = frame.filter(~pl.col("collision_severity").is_in([1, 2, 3])).height
    if invalid_severity:
        raise DataValidationError(f"Found {invalid_severity} invalid severity values")

    return frame


def collision_source_year(frame: pl.DataFrame) -> int:
    years = frame["collision_year"].drop_nulls().unique().to_list()
    if len(years) != 1:
        raise DataValidationError("Collision source must contain exactly one reporting year")
    return int(years[0])


def build_pilot(source: Path, output: Path, year: int | None = None) -> dict[str, Any]:
    frame = read_collisions(source)
    if year is None:
        source_year = collision_source_year(frame)
        source_frame = frame
    else:
        source_year = year
        source_frame = frame.filter(pl.col("collision_year") == year)
        if source_frame.is_empty():
            raise DataValidationError(f"Collision source does not contain reporting year {year}")

    missing_coordinates = frame.filter(
        pl.col("longitude").is_null() | pl.col("latitude").is_null()
    ).height

    pilot = (
        source_frame.filter(
            pl.col("longitude").is_between(
                PILOT_BOUNDS["min_longitude"], PILOT_BOUNDS["max_longitude"]
            )
            & pl.col("latitude").is_between(
                PILOT_BOUNDS["min_latitude"], PILOT_BOUNDS["max_latitude"]
            )
        )
        .select(sorted(REQUIRED_COLUMNS))
        .with_columns(
            pl.col("date").str.strptime(pl.Date, "%d/%m/%Y", strict=False),
            pl.col("collision_index").cast(pl.String),
        )
        .sort(["date", "collision_index"])
    )

    output.mkdir(parents=True, exist_ok=True)
    pilot_path = output / f"pilot-collisions-{source_year}.parquet"
    pilot.write_parquet(pilot_path)

    severity_counts = {
        str(row["collision_severity"]): row["len"]
        for row in pilot.group_by("collision_severity").len().to_dicts()
    }
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": SOURCE_URL if source_year == 2024 else SOURCE_PAGE_URL,
        "source_file": source.name,
        "source_year": source_year,
        "source_sha256": sha256_file(source),
        "source_records": frame.height,
        "selected_source_records": source_frame.height,
        "pilot_records": pilot.height,
        "missing_source_coordinates": missing_coordinates,
        "severity_counts": severity_counts,
        "bounds": PILOT_BOUNDS,
        "output": str(pilot_path),
        "status": "observed-evidence-only",
    }
    (output / f"data-quality-report-{source_year}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report
