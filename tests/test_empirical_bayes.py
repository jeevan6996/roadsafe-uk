import json
from pathlib import Path

import polars as pl
import pytest

from roadsafe.domain import RetrospectiveRecord
from roadsafe.empirical_bayes import (
    EmpiricalBayesValidationError,
    build_empirical_bayes_screening,
)


def panel_frame() -> pl.DataFrame:
    rows = []
    for year in range(2019, 2025):
        for segment, exposure, count in [
            ("a", 1_000_000.0, 1),
            ("b", 2_000_000.0, 2),
            ("c", 4_000_000.0, 5),
        ]:
            rows.append(
                {
                    "segment_key": segment,
                    "year": year,
                    "annual_vehicle_km": exposure,
                    "ksi_count": count + (year - 2019) % 2,
                }
            )
    return pl.DataFrame(rows)


def contract_path(tmp_path: Path) -> Path:
    path = tmp_path / "contract.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "status": "completed",
                "unit": "dft-major-road-segment-year",
                "target": "future_ksi_collision_count",
                "training_years": [2019, 2020, 2021, 2022],
                "validation_years": [2023],
                "test_years": [2024],
                "geographic_split": "grouped-local-authority-holdout",
                "feature_cutoff": "end-of-prior-calendar-year",
                "ranking_metrics": ["precision_at_k"],
                "probabilistic_metrics": ["poisson_deviance"],
                "required_subgroups": ["road_class"],
                "excluded_event_features": ["collision_weather"],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_empirical_bayes_writes_screening_artifact(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.parquet"
    panel_frame().write_parquet(panel_path)

    report = build_empirical_bayes_screening(panel_path, contract_path(tmp_path), tmp_path / "out")
    predictions = pl.read_parquet(tmp_path / "out" / "empirical-bayes-screening.parquet")

    assert report["status"] == "evaluated-screening"
    assert report["not_future_prediction"] is True
    assert report["metrics"]["test"]["rows"] == 3.0
    assert predictions.height == 6
    assert {"prior_expected_ksi", "expected_ksi", "expected_ksi_std", "excess_ksi"}.issubset(
        predictions.columns
    )
    assert (predictions["expected_ksi"] > 0).all()
    assert (
        predictions["expected_ksi"] <= predictions["prior_expected_ksi"] + predictions["ksi_count"]
    ).all()


def test_empirical_bayes_rejects_invalid_scoring_rows(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.parquet"
    panel_frame().with_columns(
        pl.when(pl.col("year") == 2023)
        .then(pl.lit(0.0))
        .otherwise(pl.col("annual_vehicle_km"))
        .alias("annual_vehicle_km")
    ).write_parquet(panel_path)

    with pytest.raises(
        EmpiricalBayesValidationError,
        match="validation and test years contain 3 invalid rows",
    ):
        build_empirical_bayes_screening(panel_path, contract_path(tmp_path), tmp_path / "out")


@pytest.mark.parametrize("year", [2019, 2023])
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
def test_empirical_bayes_rejects_invalid_values_before_writing(
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
    with pytest.raises(EmpiricalBayesValidationError, match="contain 1 invalid rows"):
        build_empirical_bayes_screening(source, contract_path(tmp_path), output)
    assert not output.exists()


@pytest.mark.parametrize("column", ["annual_vehicle_km", "ksi_count"])
@pytest.mark.parametrize("dtype", [pl.String, pl.Boolean])
def test_empirical_bayes_rejects_non_numeric_columns(
    tmp_path: Path, column: str, dtype: pl.DataType
) -> None:
    source = tmp_path / "panel.parquet"
    panel_frame().with_columns(pl.col(column).cast(dtype)).write_parquet(source)
    output = tmp_path / "out"
    with pytest.raises(EmpiricalBayesValidationError, match="invalid rows"):
        build_empirical_bayes_screening(source, contract_path(tmp_path), output)
    assert not output.exists()


def test_empirical_bayes_rejects_finite_input_overflow_before_writing(tmp_path: Path) -> None:
    source = tmp_path / "panel.parquet"
    panel_frame().with_columns(
        pl.when(pl.col("year") == 2023)
        .then(1e308)
        .otherwise(pl.col("annual_vehicle_km"))
        .alias("annual_vehicle_km")
    ).write_parquet(source)
    output = tmp_path / "out"
    with pytest.raises(EmpiricalBayesValidationError, match="non-finite|overflow"):
        build_empirical_bayes_screening(source, contract_path(tmp_path), output)
    assert not output.exists()


def test_empirical_bayes_accepts_zero_scoring_and_integral_float_counts(tmp_path: Path) -> None:
    source = tmp_path / "panel.parquet"
    panel_frame().with_columns(
        pl.when(pl.col("year") >= 2023)
        .then(0.0)
        .otherwise(pl.col("ksi_count").cast(pl.Float64))
        .alias("ksi_count")
    ).write_parquet(source)
    report = build_empirical_bayes_screening(source, contract_path(tmp_path), tmp_path / "out")
    assert report["status"] == "evaluated-screening"
    assert report["metrics"]["test"]["observed_ksi"] == 0
    assert report["metrics"]["test"]["expected_ksi"] > 0
    predictions = pl.read_parquet(tmp_path / "out" / "empirical-bayes-screening.parquet")
    for row in predictions.to_dicts():
        RetrospectiveRecord.model_validate(row)


@pytest.mark.parametrize("column", ["annual_vehicle_km", "ksi_count"])
def test_empirical_bayes_preserves_valid_decimal_support(tmp_path: Path, column: str) -> None:
    source = tmp_path / "panel.parquet"
    panel_frame().with_columns(pl.col(column).cast(pl.Decimal(20, 2))).write_parquet(source)
    build_empirical_bayes_screening(source, contract_path(tmp_path), tmp_path / "out")
    predictions = pl.read_parquet(tmp_path / "out" / "empirical-bayes-screening.parquet")
    for row in predictions.to_dicts():
        RetrospectiveRecord.model_validate(row)


def test_empirical_bayes_ignores_numeric_corruption_outside_contract(tmp_path: Path) -> None:
    source = tmp_path / "panel.parquet"
    panel = panel_frame().with_columns(pl.col("ksi_count").cast(pl.Float64))
    unrelated = panel.head(1).with_columns(
        pl.lit(2018, dtype=panel.schema["year"]).alias("year"),
        pl.lit(float("nan")).alias("ksi_count"),
    )
    pl.concat([unrelated, panel]).write_parquet(source)
    report = build_empirical_bayes_screening(source, contract_path(tmp_path), tmp_path / "out")
    assert report["scoring_rows"] == 6
