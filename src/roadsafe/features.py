from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from roadsafe.evaluation import read_evaluation_contract
from roadsafe.pipeline import sha256_file

FORECAST_FEATURES = (
    "annual_vehicle_km",
    "road_category",
    "road_type",
    "urban_rural",
    "estimation_method",
)
TARGET_COLUMNS = ("segment_key", "year", "ksi_count", "local_authority_code")


class FeatureValidationError(ValueError):
    """Raised when evidence cannot support exact-year feature snapshots."""


def build_lagged_feature_panel(
    panel_path: Path, contract_path: Path, output: Path, lag_years: int = 1
) -> dict[str, Any]:
    if isinstance(lag_years, bool) or not isinstance(lag_years, int) or lag_years < 1:
        raise FeatureValidationError("lag_years must be a positive integer")
    panel = pl.read_parquet(panel_path)
    missing = set(TARGET_COLUMNS + FORECAST_FEATURES).difference(panel.columns)
    if missing:
        raise FeatureValidationError(f"Missing feature-panel columns: {', '.join(sorted(missing))}")
    if "feature_year" in panel.columns:
        raise FeatureValidationError("Input must be observed evidence, not an already lagged panel")
    if not panel.schema["year"].is_integer():
        raise FeatureValidationError("year must have an integer dtype")
    if any(not panel.schema[column].is_numeric() for column in ("annual_vehicle_km", "ksi_count")):
        raise FeatureValidationError("Exposure and KSI count must have numeric dtypes")
    if panel.filter(
        pl.col("year").is_null()
        | pl.col("segment_key").is_null()
        | (pl.col("segment_key").cast(pl.String).str.strip_chars() == "")
    ).height:
        raise FeatureValidationError("Segment-year keys must be complete")
    if panel.select(pl.struct("segment_key", "year").is_duplicated().any()).item():
        raise FeatureValidationError("Duplicate segment-year keys")

    contract = read_evaluation_contract(contract_path)
    years = sorted(contract.training_years + contract.validation_years + contract.test_years)
    targets = panel.filter(pl.col("year").is_in(years)).select(
        *TARGET_COLUMNS,
        pl.col("annual_vehicle_km").alias("observed_annual_vehicle_km"),
        (pl.col("year") - lag_years).alias("feature_year"),
    )
    snapshots = panel.select(
        "segment_key",
        pl.col("year").alias("feature_year"),
        *FORECAST_FEATURES,
        pl.lit(True).alias("snapshot_found"),
    )
    joined = targets.join(snapshots, on=["segment_key", "feature_year"], how="left", validate="m:1")
    valid_features = (
        pl.col("annual_vehicle_km").is_finite()
        & (pl.col("annual_vehicle_km") > 0)
        & pl.all_horizontal(
            pl.col(column).is_not_null() & (pl.col(column).cast(pl.String).str.strip_chars() != "")
            for column in FORECAST_FEATURES[1:]
        )
    ).fill_null(False)
    valid_targets = (
        pl.col("ksi_count").is_finite()
        & (pl.col("ksi_count") >= 0)
        & (pl.col("ksi_count") == pl.col("ksi_count").floor())
        & pl.col("local_authority_code").is_not_null()
        & (pl.col("local_authority_code").cast(pl.String).str.strip_chars() != "")
    ).fill_null(False)
    assessed = joined.with_columns(
        pl.when(pl.col("snapshot_found").is_null())
        .then(pl.lit("missing_exact_year_history"))
        .when(~valid_features)
        .then(pl.lit("invalid_historical_features"))
        .when(~valid_targets)
        .then(pl.lit("invalid_target_or_authority"))
        .otherwise(pl.lit("included"))
        .alias("feature_status")
    )
    features = (
        assessed.filter(pl.col("feature_status") == "included")
        .drop("snapshot_found", "feature_status")
        .sort(["year", "segment_key"])
    )
    excluded = (
        assessed.filter(pl.col("feature_status") != "included")
        .select("segment_key", "year", "feature_year", "feature_status")
        .sort(["year", "segment_key"])
    )
    missing_years = sorted(set(years).difference(features["year"].to_list()))
    output.mkdir(parents=True, exist_ok=True)
    feature_path = output / "lagged-feature-panel.parquet"
    excluded_path = output / "excluded-feature-rows.parquet"
    features.write_parquet(feature_path)
    excluded.write_parquet(excluded_path)
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "blocked" if missing_years else "exploratory-benchmark-only",
        "lag_years": lag_years,
        "features": list(FORECAST_FEATURES),
        "exposure_semantics": "historical annual vehicle-km used as a future exposure proxy",
        "publication_availability_verified": False,
        "promotion_blockers": ["source_publication_dates_not_verified"],
        "missing_contract_years": missing_years,
        "candidate_rows": targets.height,
        "included_rows": features.height,
        "excluded_rows": excluded.height,
        "rows_by_year_and_status": assessed.group_by("year", "feature_status")
        .len()
        .sort(["year", "feature_status"])
        .to_dicts(),
        "panel_sha256": sha256_file(panel_path),
        "contract_sha256": sha256_file(contract_path),
        "output": str(feature_path),
        "output_sha256": sha256_file(feature_path),
        "excluded_output": str(excluded_path),
    }
    (output / "feature-panel-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report
