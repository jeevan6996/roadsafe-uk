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
