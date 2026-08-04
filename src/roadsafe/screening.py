from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from roadsafe.pipeline import sha256_file

SCREENING_REQUIRED_COLUMNS = {
    "segment_key",
    "count_point_id",
    "year",
    "road_number",
    "road_category",
    "local_authority_code",
    "local_authority_name",
    "annual_vehicle_km",
    "collision_count",
    "ksi_count",
}


class ScreeningValidationError(ValueError):
    """Raised when a panel cannot support descriptive safety screening."""


def build_descriptive_screening(panel_path: Path, output: Path) -> dict[str, Any]:
    panel = pl.read_parquet(panel_path)
    missing = SCREENING_REQUIRED_COLUMNS.difference(panel.columns)
    if missing:
        raise ScreeningValidationError(
            f"{panel_path.name} is missing screening columns: {', '.join(sorted(missing))}"
        )

    invalid_exposure = panel.filter(
        pl.col("annual_vehicle_km").is_null() | (pl.col("annual_vehicle_km") <= 0)
    ).height
    invalid_targets = panel.filter(
        pl.col("collision_count").is_null()
        | pl.col("ksi_count").is_null()
        | (pl.col("collision_count") < 0)
        | (pl.col("ksi_count") < 0)
    ).height
    if invalid_exposure or invalid_targets:
        raise ScreeningValidationError(
            "Panel has invalid exposure or target rows; run the readiness gate before screening"
        )

    output.mkdir(parents=True, exist_ok=True)
    segment_path = output / "segment-descriptive-screening.parquet"
    report_path = output / "descriptive-screening-report.json"
    segment_screening = _segment_screening(panel)
    segment_screening.write_parquet(segment_path)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "panel": str(panel_path),
        "panel_sha256": sha256_file(panel_path),
        "records": panel.height,
        "segments": segment_screening.height,
        "years": sorted(int(year) for year in panel["year"].drop_nulls().unique()),
        "method": "observed exposure-normalized descriptive screening",
        "not_modelled": True,
        "output": str(segment_path),
        "top_ksi_rate_segments": segment_screening.head(10).to_dicts(),
        "subgroup_rates": _subgroup_rates(panel),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _segment_screening(panel: pl.DataFrame) -> pl.DataFrame:
    metadata_columns = [
        column
        for column in [
            "count_point_id",
            "road_number",
            "road_category",
            "local_authority_code",
            "local_authority_name",
            "urban_rural",
        ]
        if column in panel.columns
    ]
    return (
        panel.group_by("segment_key")
        .agg(
            [pl.col(column).drop_nulls().first().alias(column) for column in metadata_columns]
            + [
                pl.col("year").n_unique().alias("years_observed"),
                pl.col("annual_vehicle_km").sum().alias("total_vehicle_km"),
                pl.col("collision_count").sum().alias("observed_collisions"),
                pl.col("ksi_count").sum().alias("observed_ksi"),
            ]
        )
        .with_columns((pl.col("total_vehicle_km") / 1_000_000).alias("total_million_vehicle_km"))
        .with_columns(
            (pl.col("observed_collisions") / pl.col("total_million_vehicle_km")).alias(
                "collision_rate_per_million_vehicle_km"
            ),
            (pl.col("observed_ksi") / pl.col("total_million_vehicle_km")).alias(
                "ksi_rate_per_million_vehicle_km"
            ),
        )
        .sort(
            ["ksi_rate_per_million_vehicle_km", "collision_rate_per_million_vehicle_km"],
            descending=[True, True],
        )
        .with_row_index("screening_rank", offset=1)
    )


def _subgroup_rates(panel: pl.DataFrame) -> dict[str, list[dict[str, Any]]]:
    summaries = {}
    for subgroup in ["road_category", "urban_rural", "local_authority_code"]:
        if subgroup not in panel.columns:
            continue
        frame = (
            panel.drop_nulls(subgroup)
            .group_by(subgroup)
            .agg(
                pl.col("segment_key").n_unique().alias("segments"),
                pl.col("annual_vehicle_km").sum().alias("total_vehicle_km"),
                pl.col("collision_count").sum().alias("observed_collisions"),
                pl.col("ksi_count").sum().alias("observed_ksi"),
            )
            .with_columns(
                (pl.col("total_vehicle_km") / 1_000_000).alias("total_million_vehicle_km")
            )
            .with_columns(
                (pl.col("observed_collisions") / pl.col("total_million_vehicle_km")).alias(
                    "collision_rate_per_million_vehicle_km"
                ),
                (pl.col("observed_ksi") / pl.col("total_million_vehicle_km")).alias(
                    "ksi_rate_per_million_vehicle_km"
                ),
            )
            .sort(subgroup)
        )
        summaries[subgroup] = frame.to_dicts()
    return summaries
