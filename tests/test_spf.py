import json
from pathlib import Path

import polars as pl
import pytest

from roadsafe.spf import SPFValidationError, build_negative_binomial_spf


def panel_frame() -> pl.DataFrame:
    rows = []
    for year in range(2019, 2025):
        for segment, authority, category, exposure, count in [
            ("a", "A", "A", 1_000_000.0, 1),
            ("b", "B", "A", 2_000_000.0, 2),
            ("c", "C", "B", 3_000_000.0, 4),
            ("d", "D", "B", 4_000_000.0, 6),
        ]:
            rows.append(
                {
                    "segment_key": segment,
                    "year": year,
                    "annual_vehicle_km": exposure,
                    "ksi_count": count + (year - 2019) % 2,
                    "road_category": category,
                    "road_type": "Major",
                    "urban_rural": "urban" if segment in {"a", "c"} else "rural",
                    "estimation_method": "Counted",
                    "local_authority_code": authority,
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


def test_spf_writes_future_predictions_and_baseline_comparison(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.parquet"
    panel_frame().write_parquet(panel_path)

    report = build_negative_binomial_spf(panel_path, contract_path(tmp_path), tmp_path / "out")
    predictions = pl.read_parquet(tmp_path / "out" / "negative-binomial-spf-predictions.parquet")

    assert report["status"] == "evaluated-benchmark"
    assert report["model_promoted"] is False
    assert report["metrics"]["spf"]["validation"]["rows"] == 4.0
    assert "poisson_deviance" in report["metrics"]["spf"]["test"]
    assert "recall_at_10_percent" in report["metrics"]["spf"]["test"]
    assert report["metrics"]["exposure_rate_baseline"]["test"]["rows"] == 4.0
    assert predictions.height == 8
    assert predictions["expected_ksi"].is_not_null().all()
    assert {"expected_ksi_lower_95", "expected_ksi_upper_95"}.issubset(predictions.columns)
    assert report["unseen_authorities"]["available"] is True
    assert report["authority_holdout"]["available"] is True
    assert "no_future_unseen_authorities" in report["promotion_blockers"]


def test_spf_rejects_invalid_exposure(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.parquet"
    panel_frame().with_columns(
        pl.when(pl.col("year") == 2023)
        .then(pl.lit(0.0))
        .otherwise(pl.col("annual_vehicle_km"))
        .alias("annual_vehicle_km")
    ).write_parquet(panel_path)

    with pytest.raises(
        SPFValidationError,
        match="validation and test years contain 4 invalid rows",
    ):
        build_negative_binomial_spf(panel_path, contract_path(tmp_path), tmp_path / "out")
