import json
from pathlib import Path

import polars as pl
import pytest

from roadsafe.baseline import BaselineValidationError, build_exposure_baseline


def panel_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "segment_key": ["a", "a", "b", "b", "a", "b"],
            "year": [2019, 2020, 2019, 2020, 2021, 2021],
            "annual_vehicle_km": [1_000_000.0] * 6,
            "ksi_count": [1, 2, 3, 4, 0, 2],
        }
    )


def contract_path(tmp_path: Path) -> Path:
    path = tmp_path / "contract.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "status": "completed",
                "unit": "dft-major-road-segment-year",
                "target": "future_ksi_collision_count",
                "training_years": [2019, 2020],
                "validation_years": [2021],
                "test_years": [2022],
                "geographic_split": "grouped-local-authority-holdout",
                "feature_cutoff": "end-of-prior-calendar-year",
                "ranking_metrics": ["recall_at_k"],
                "probabilistic_metrics": ["poisson_deviance"],
                "required_subgroups": ["road_class"],
                "excluded_event_features": ["collision_count"],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_build_exposure_baseline_scores_future_split(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.parquet"
    panel_frame().write_parquet(panel_path)

    report = build_exposure_baseline(panel_path, contract_path(tmp_path), tmp_path / "out")
    predictions = pl.read_parquet(tmp_path / "out" / "exposure-baseline-predictions.parquet")

    assert report["training_rate_per_million_vehicle_km"] == 2.5
    assert report["metrics"]["validation"]["rows"] == 2.0
    assert predictions["expected_ksi"].to_list() == [2.5, 2.5]
    assert predictions["evaluation_split"].to_list() == ["validation", "validation"]


def test_build_exposure_baseline_rejects_missing_training_rows(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.parquet"
    panel_frame().filter(pl.col("year") == 2021).write_parquet(panel_path)

    with pytest.raises(BaselineValidationError, match="training years contain no panel rows"):
        build_exposure_baseline(panel_path, contract_path(tmp_path), tmp_path / "out")


def test_build_exposure_baseline_rejects_invalid_scoring_rows(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.parquet"
    panel_frame().with_columns(
        pl.when(pl.col("year") == 2021)
        .then(0.0)
        .otherwise(pl.col("annual_vehicle_km"))
        .alias("annual_vehicle_km")
    ).write_parquet(panel_path)

    with pytest.raises(
        BaselineValidationError,
        match="validation and test years contain 2 invalid rows",
    ):
        build_exposure_baseline(panel_path, contract_path(tmp_path), tmp_path / "out")


@pytest.mark.parametrize("year", [2019, 2021])
@pytest.mark.parametrize(
    "column,value",
    [
        ("annual_vehicle_km", value)
        for value in [None, float("nan"), float("inf"), -float("inf"), 0.0, -1.0]
    ]
    + [
        ("ksi_count", value)
        for value in [None, float("nan"), float("inf"), -float("inf"), -1.0, 0.5, float(2**64)]
    ],
)
def test_baseline_rejects_invalid_numeric_values_before_writing(
    tmp_path: Path, year: int, column: str, value: float | None
) -> None:
    source = tmp_path / "panel.parquet"
    panel_frame().with_columns(
        pl.when((pl.col("year") == year) & (pl.col("segment_key") == "a"))
        .then(pl.lit(value, dtype=pl.Float64))
        .otherwise(pl.col(column).cast(pl.Float64))
        .alias(column)
    ).write_parquet(source)
    output = tmp_path / "out"
    with pytest.raises(BaselineValidationError, match="contain 1 invalid rows"):
        build_exposure_baseline(source, contract_path(tmp_path), output)
    assert not output.exists()


@pytest.mark.parametrize("column", ["annual_vehicle_km", "ksi_count"])
@pytest.mark.parametrize("dtype", [pl.String, pl.Boolean])
def test_baseline_rejects_non_numeric_columns(
    tmp_path: Path, column: str, dtype: pl.DataType
) -> None:
    source = tmp_path / "panel.parquet"
    panel_frame().with_columns(pl.col(column).cast(dtype)).write_parquet(source)
    output = tmp_path / "out"
    with pytest.raises(BaselineValidationError, match="invalid rows"):
        build_exposure_baseline(source, contract_path(tmp_path), output)
    assert not output.exists()


@pytest.mark.parametrize("year,column", [(2019, "annual_vehicle_km"), (2021, "annual_vehicle_km")])
def test_baseline_rejects_non_finite_derived_values(tmp_path: Path, year: int, column: str) -> None:
    source = tmp_path / "panel.parquet"
    panel_frame().with_columns(
        pl.when(pl.col("year") == year)
        .then(1e308)
        .otherwise(pl.col(column).cast(pl.Float64))
        .alias(column)
    ).write_parquet(source)
    output = tmp_path / "out"
    with pytest.raises(BaselineValidationError, match="finite"):
        build_exposure_baseline(source, contract_path(tmp_path), output)
    assert not output.exists()


@pytest.mark.parametrize("column", ["annual_vehicle_km", "ksi_count"])
def test_baseline_accepts_valid_decimal_columns(tmp_path: Path, column: str) -> None:
    source = tmp_path / "panel.parquet"
    panel_frame().with_columns(pl.col(column).cast(pl.Decimal(20, 2))).write_parquet(source)
    report = build_exposure_baseline(source, contract_path(tmp_path), tmp_path / "out")
    assert report["training_rate_per_million_vehicle_km"] == 2.5
