import json
from pathlib import Path

import polars as pl
import pytest

from roadsafe.cli import create_parser
from roadsafe.features import FORECAST_FEATURES, FeatureValidationError, build_lagged_feature_panel
from roadsafe.spf import SPF_CATEGORICAL_FEATURES

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluation-lagged-v1.json"


def test_snapshot_covers_every_model_covariate() -> None:
    assert set(FORECAST_FEATURES) == {"annual_vehicle_km", *SPF_CATEGORICAL_FEATURES}


def test_feature_panel_rejects_nonnumeric_exposure(tmp_path: Path) -> None:
    with pytest.raises(FeatureValidationError, match="numeric dtypes"):
        build(evidence().with_columns(pl.col("annual_vehicle_km").cast(pl.String)), tmp_path)


def evidence() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "segment_key": segment,
                "year": year,
                "ksi_count": year - 2019,
                "local_authority_code": "A" if segment == "a" else "B",
                "annual_vehicle_km": float(year * 1000),
                "road_category": f"category-{year}",
                "road_type": "Major",
                "urban_rural": "urban",
                "estimation_method": f"method-{year}",
            }
            for year in range(2019, 2025)
            for segment in ["a", "b"]
        ]
    )


def build(frame: pl.DataFrame, tmp_path: Path, lag: int = 1) -> tuple[dict, pl.DataFrame]:
    source = tmp_path / "source.parquet"
    frame.write_parquet(source)
    report = build_lagged_feature_panel(source, CONTRACT, tmp_path / "out", lag)
    return report, pl.read_parquet(report["output"])


def test_exact_year_snapshots_preserve_targets_and_report_provenance(tmp_path: Path) -> None:
    report, panel = build(evidence(), tmp_path)
    row = panel.filter((pl.col("year") == 2024) & (pl.col("segment_key") == "a")).row(0, named=True)
    assert row["ksi_count"] == 5
    assert row["feature_year"] == 2023
    assert row["annual_vehicle_km"] == 2_023_000
    assert row["observed_annual_vehicle_km"] == 2_024_000
    assert row["road_category"] == "category-2023"
    assert row["estimation_method"] == "method-2023"
    assert report["included_rows"] == 10
    assert report["publication_availability_verified"] is False
    assert report["status"] == "exploratory-benchmark-only"
    assert len(report["output_sha256"]) == 64
    assert json.loads((tmp_path / "out/feature-panel-report.json").read_text()) == report


def test_prediction_year_covariates_do_not_enter_features(tmp_path: Path) -> None:
    _, original = build(evidence(), tmp_path)
    changed = evidence().with_columns(
        pl.when(pl.col("year") == 2024)
        .then(pl.lit(999.0))
        .otherwise(pl.col("annual_vehicle_km"))
        .alias("annual_vehicle_km"),
        pl.when(pl.col("year") == 2024)
        .then(pl.lit("future-value"))
        .otherwise(pl.col("road_category"))
        .alias("road_category"),
    )
    _, altered = build(changed, tmp_path)
    assert (
        original.filter(pl.col("year") == 2024)
        .select(FORECAST_FEATURES)
        .equals(altered.filter(pl.col("year") == 2024).select(FORECAST_FEATURES))
    )


def test_missing_calendar_year_is_not_replaced_with_previous_row(tmp_path: Path) -> None:
    report, panel = build(evidence().filter(pl.col("year") != 2022), tmp_path)
    assert 2023 not in panel["year"].to_list()
    assert report["status"] == "blocked"
    assert report["missing_contract_years"] == [2022, 2023]
    excluded = pl.read_parquet(report["excluded_output"])
    assert excluded["feature_status"].to_list() == ["missing_exact_year_history"] * 2


@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf"), None])
def test_invalid_historical_exposure_is_excluded(tmp_path: Path, value: float | None) -> None:
    frame = evidence().with_columns(
        pl.when(pl.col("year") == 2023)
        .then(pl.lit(value))
        .otherwise(pl.col("annual_vehicle_km"))
        .alias("annual_vehicle_km")
    )
    report, panel = build(frame, tmp_path)
    assert 2024 not in panel["year"].to_list()
    assert report["excluded_rows"] == 2
    assert (
        "invalid_historical_features"
        in pl.read_parquet(report["excluded_output"])["feature_status"].to_list()
    )


def test_duplicate_keys_and_repeated_lagging_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(FeatureValidationError, match="Duplicate segment-year"):
        build(pl.concat([evidence(), evidence().head(1)]), tmp_path)
    _, features = build(evidence(), tmp_path)
    with pytest.raises(FeatureValidationError, match="already lagged"):
        build(features, tmp_path)


@pytest.mark.parametrize("lag", [0, -1, True, 1.5])
def test_lag_must_be_a_positive_integer(tmp_path: Path, lag: int) -> None:
    with pytest.raises(FeatureValidationError, match="positive integer"):
        build(evidence(), tmp_path, lag)


def test_longer_lag_is_explicit_and_reports_unavailable_training_years(tmp_path: Path) -> None:
    report, panel = build(evidence(), tmp_path, 2)
    assert report["lag_years"] == 2
    assert report["missing_contract_years"] == [2020]
    assert (panel["year"] - panel["feature_year"]).unique().to_list() == [2]


def test_cli_accepts_explicit_lag() -> None:
    args = create_parser().parse_args(
        [
            "build-lagged-panel",
            "--panel",
            "input.parquet",
            "--contract",
            str(CONTRACT),
            "--output",
            "output",
            "--lag-years",
            "2",
        ]
    )
    assert args.lag_years == 2
