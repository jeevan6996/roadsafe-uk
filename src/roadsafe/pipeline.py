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

    frame = frame.filter(pl.col("collision_index").is_not_null())

    duplicate_ids = frame.select(pl.col("collision_index").is_duplicated().sum()).item()
    if duplicate_ids:
        raise DataValidationError(f"Found {duplicate_ids} duplicate collision identifiers")

    invalid_severity = frame.filter(~pl.col("collision_severity").is_in([1, 2, 3])).height
    if invalid_severity:
        raise DataValidationError(f"Found {invalid_severity} invalid severity values")

    return frame


def build_pilot(source: Path, output: Path) -> dict[str, Any]:
    frame = read_collisions(source)
    missing_coordinates = frame.filter(
        pl.col("longitude").is_null() | pl.col("latitude").is_null()
    ).height

    pilot = (
        frame.filter(
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
    pilot_path = output / "pilot-collisions-2024.parquet"
    pilot.write_parquet(pilot_path)

    severity_counts = {
        str(row["collision_severity"]): row["len"]
        for row in pilot.group_by("collision_severity").len().to_dicts()
    }
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": SOURCE_URL,
        "source_sha256": sha256_file(source),
        "source_records": frame.height,
        "pilot_records": pilot.height,
        "missing_source_coordinates": missing_coordinates,
        "severity_counts": severity_counts,
        "bounds": PILOT_BOUNDS,
        "output": str(pilot_path),
        "status": "observed-evidence-only",
    }
    (output / "data-quality-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report
