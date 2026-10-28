import json
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest

from roadsafe import spf
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
    assert report["unseen_authorities"]["available"] is False
    assert report["unseen_authorities"]["unseen_validation"] == []
    assert report["unseen_authorities"]["unseen_test"] == []
    assert report["authority_holdout"]["available"] is True
    assert report["authority_holdout"]["held_out_authorities"] == ["A", "B", "C", "D"]
    assert len(report["authority_holdout"]["folds"]) == 4
    assert report["authority_holdout"]["holdout_rows"] == 16
    assert "no_future_unseen_authorities" in report["promotion_blockers"]
    assert "prior_year_feature_availability_not_verified" in report["promotion_blockers"]
    future = report["future_authority_holdout"]
    assert future["complete"] is True
    assert future["holdout_rows"] == 8
    assert future["metrics_by_split"]["spf"]["test"]["rows"] == 4
    for fold in future["folds"]:
        assert fold["held_out_authority"] not in fold["training_authorities"]
        assert fold["training_years"] == [2019, 2020, 2021, 2022]
        assert fold["scoring_years"] == [2023, 2024]


def future_rows() -> pl.DataFrame:
    return (
        panel_frame()
        .filter(pl.col("year") >= 2023)
        .with_columns(
            pl.when(pl.col("year") == 2023)
            .then(pl.lit("validation"))
            .otherwise(pl.lit("test"))
            .alias("evaluation_split")
        )
    )


def test_future_holdout_excludes_authority_history_and_moved_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    training = (
        panel_frame()
        .filter(pl.col("year") <= 2022)
        .with_columns(
            pl.when(pl.col("segment_key") == "a")
            .then(pl.lit("B"))
            .otherwise(pl.col("local_authority_code"))
            .alias("local_authority_code")
        )
    )
    fitted_frames: list[pl.DataFrame] = []

    def capture_features(frame: pl.DataFrame) -> list[tuple[str, list[str]]]:
        fitted_frames.append(frame)
        return []

    monkeypatch.setattr(spf, "_feature_specs", capture_features)
    monkeypatch.setattr(spf, "_fit_model", lambda target, design, exposure: target.mean())
    monkeypatch.setattr(
        spf, "_predict", lambda result, design, exposure: np.full(len(exposure), result)
    )
    report = spf._authority_holdout(training, future_rows())

    assert report["complete"] is True
    for authority, frame in zip(report["held_out_authorities"], fitted_frames, strict=True):
        assert authority not in frame["local_authority_code"].to_list()
        scoring_keys = (
            future_rows()
            .filter(pl.col("local_authority_code") == authority)["segment_key"]
            .to_list()
        )
        assert set(frame["segment_key"]).isdisjoint(scoring_keys)
        assert frame["year"].max() == 2022
    original = report["metrics_by_split"]["spf"]["test"]["mean_predicted"]
    changed = spf._authority_holdout(
        training, future_rows().with_columns(pl.lit(1000).alias("ksi_count"))
    )
    assert changed["metrics_by_split"]["spf"]["test"]["mean_predicted"] == original


def test_future_holdout_reports_failed_fold_without_claiming_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_fit = spf._fit_model
    calls = 0

    def fail_first(*args: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise SPFValidationError("test nonconvergence")
        return original_fit(*args)

    monkeypatch.setattr(spf, "_fit_model", fail_first)
    report = spf._authority_holdout(panel_frame().filter(pl.col("year") <= 2022), future_rows())
    assert report["available"] is True
    assert report["complete"] is False
    assert report["holdout_rows"] == 6
    assert report["expected_holdout_rows"] == 8
    assert report["row_coverage"] == 0.75
    assert report["failed_folds"] == [{"held_out_authority": "A", "reason": "test nonconvergence"}]


@pytest.mark.parametrize("authority", [None, "", " "])
def test_future_holdout_rejects_missing_authority_identity(authority: str | None) -> None:
    report = spf._authority_holdout(
        panel_frame().filter(pl.col("year") <= 2022),
        future_rows().with_columns(pl.lit(authority).alias("local_authority_code")),
    )
    assert report == {"available": False, "reason": "incomplete_local_authority_code"}


def test_future_holdout_rejects_overlapping_periods() -> None:
    report = spf._authority_holdout(panel_frame(), future_rows())
    assert report == {"available": False, "reason": "scoring_period_not_strictly_future"}


def test_ranking_precision_is_a_fraction_not_a_collision_count() -> None:
    rows = pl.DataFrame({"ksi_count": [4, 0, 1], "expected_ksi": [3.0, 2.0, 1.0]})
    metrics = spf._detailed_metrics(rows)
    assert metrics["precision_at_10_percent"] == 1.0
    assert metrics["mean_ksi_at_10_percent"] == 4.0
    assert metrics["recall_at_10_percent"] == 0.8


def test_ranking_precision_for_zero_events_is_zero() -> None:
    metrics = spf._detailed_metrics(pl.DataFrame({"ksi_count": [0, 0], "expected_ksi": [1.0, 1.0]}))
    assert metrics["precision_at_10_percent"] == 0.0
    assert metrics["mean_ksi_at_10_percent"] == 0.0
    assert metrics["recall_at_10_percent"] == 0.0


def test_future_holdout_can_score_one_authority() -> None:
    report = spf._authority_holdout(
        panel_frame().filter(pl.col("year") <= 2022),
        future_rows().filter(pl.col("local_authority_code") == "A"),
    )
    assert report["complete"] is True
    assert report["holdout_rows"] == 2


def test_future_holdout_handles_no_remaining_training_rows() -> None:
    report = spf._authority_holdout(
        panel_frame().filter((pl.col("year") <= 2022) & (pl.col("local_authority_code") == "A")),
        future_rows().filter(pl.col("local_authority_code") == "A"),
    )
    assert report["available"] is False
    assert report["complete"] is False
    assert report["holdout_rows"] == 0
    assert report["failed_folds"][0]["reason"] == "no training rows after geographic exclusions"


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


def test_spf_rejects_missing_test_year(tmp_path: Path) -> None:
    path = tmp_path / "panel.parquet"
    panel_frame().filter(pl.col("year") != 2024).write_parquet(path)
    with pytest.raises(SPFValidationError, match="Missing contract years:.*2024"):
        build_negative_binomial_spf(path, contract_path(tmp_path), tmp_path / "out")


@pytest.mark.parametrize("feature_year", [2024, None, 2023.5])
def test_spf_rejects_invalid_or_future_feature_year(
    tmp_path: Path, feature_year: int | float | None
) -> None:
    path = tmp_path / "panel.parquet"
    panel_frame().with_columns(pl.lit(feature_year).alias("feature_year")).write_parquet(path)
    with pytest.raises(SPFValidationError, match="feature_year must"):
        build_negative_binomial_spf(path, contract_path(tmp_path), tmp_path / "out")


def test_ridge_poisson_intercept_matches_exposure_rate() -> None:
    exposure = np.array([1.0, 2.0, 3.0])
    design = np.ones((3, 1))
    result = spf._fit_ridge_poisson(np.array([1.0, 0.0, 3.0]), design, exposure, alpha=0.01)
    np.testing.assert_allclose(spf._predict(result, design, exposure), exposure * 4 / 6, rtol=1e-5)


def test_ridge_poisson_handles_a_zero_event_category() -> None:
    design = np.column_stack([np.ones(12), np.array([0.0] * 6 + [1.0] * 6)])
    target = np.array([0.0] * 6 + [1.0, 2.0, 1.0, 2.0, 1.0, 2.0])
    result = spf._fit_ridge_poisson(target, design, np.ones(12), alpha=0.01)
    predictions = spf._predict(result, design, np.ones(12))
    assert np.isfinite(result.params).all()
    assert 0 < predictions[0] < predictions[-1]


def test_ridge_poisson_has_distinct_artifacts_and_does_not_train_on_future_targets(
    tmp_path: Path,
) -> None:
    path = tmp_path / "panel.parquet"
    panel = panel_frame().with_columns((pl.col("year") - 1).alias("feature_year"))
    panel.write_parquet(path)
    report = spf.build_count_spf(
        path, contract_path(tmp_path), tmp_path / "out", model_kind="ridge-poisson"
    )
    original = pl.read_parquet(report["output"])
    assert report["model_kind"] == "ridge-poisson"
    assert report["dispersion_alpha"] is None
    assert report["model_promoted"] is False
    assert report["feature_timing"]["mode"] == "historical-exposure-proxy"
    assert report["future_authority_holdout"]["complete"] is True
    assert Path(report["output"]).name == "ridge-poisson-spf-predictions.parquet"
    panel.with_columns(
        pl.when(pl.col("year") >= 2023)
        .then(pl.lit(999))
        .otherwise(pl.col("ksi_count"))
        .alias("ksi_count")
    ).write_parquet(path)
    updated = spf.build_count_spf(
        path, contract_path(tmp_path), tmp_path / "changed", model_kind="ridge-poisson"
    )
    np.testing.assert_allclose(
        original["expected_ksi"], pl.read_parquet(updated["output"])["expected_ksi"]
    )
    assert report["future_authority_holdout"]["spf"]["mean_predicted"] == pytest.approx(
        updated["future_authority_holdout"]["spf"]["mean_predicted"]
    )


@pytest.mark.parametrize("alpha", [0.0, -1.0, float("nan"), float("inf")])
def test_ridge_poisson_rejects_invalid_penalties(tmp_path: Path, alpha: float) -> None:
    with pytest.raises(SPFValidationError, match="finite and positive"):
        spf.build_count_spf(tmp_path / "unused", tmp_path / "unused", tmp_path, ridge_alpha=alpha)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 1.5])
def test_count_model_rejects_nonfinite_or_fractional_counts(tmp_path: Path, value: float) -> None:
    path = tmp_path / "panel.parquet"
    panel_frame().with_columns(pl.lit(value).alias("ksi_count")).write_parquet(path)
    with pytest.raises(SPFValidationError, match="invalid rows"):
        spf.build_count_spf(
            path, contract_path(tmp_path), tmp_path / "out", model_kind="ridge-poisson"
        )
