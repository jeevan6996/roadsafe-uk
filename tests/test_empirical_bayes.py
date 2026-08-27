import json
from pathlib import Path

import polars as pl
import pytest

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
