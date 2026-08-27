from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from roadsafe.evaluation import read_evaluation_contract
from roadsafe.pipeline import sha256_file

EB_REQUIRED_COLUMNS = {"segment_key", "year", "annual_vehicle_km", "ksi_count"}


class EmpiricalBayesValidationError(ValueError):
    """Raised when a panel cannot support Empirical Bayes screening."""


def build_empirical_bayes_screening(
    panel_path: Path,
    contract_path: Path,
    output: Path,
) -> dict[str, Any]:
    """Build a Poisson-gamma Empirical Bayes screening artifact.

    The prior is estimated from training years only. Counts in each scoring
    period are then shrunk toward the exposure-scaled prior mean, producing a
    retrospective expected frequency and excess-frequency signal.
    """
    panel = pl.read_parquet(panel_path)
    missing = EB_REQUIRED_COLUMNS.difference(panel.columns)
    if missing:
        raise EmpiricalBayesValidationError(
            f"{panel_path.name} is missing Empirical Bayes columns: {', '.join(sorted(missing))}"
        )

    contract = read_evaluation_contract(contract_path)
    training = panel.filter(pl.col("year").is_in(contract.training_years))
    scoring_years = contract.validation_years + contract.test_years
    scoring = panel.filter(pl.col("year").is_in(scoring_years))
    if training.is_empty():
        raise EmpiricalBayesValidationError("training years contain no panel rows")
    if scoring.is_empty():
        raise EmpiricalBayesValidationError("validation and test years contain no panel rows")

    _validate_rows(training, "training")
    _validate_rows(scoring, "validation and test")
    prior_rate, shape = _fit_prior(training)
    exposure = scoring["annual_vehicle_km"].to_numpy().astype(float)
    observed = scoring["ksi_count"].to_numpy().astype(float)
    prior_mean = exposure * prior_rate
    posterior_mean = exposure * (shape + observed) / (shape / prior_rate + exposure)
    posterior_variance = posterior_mean + posterior_mean**2 / shape
    excess = np.maximum(observed - posterior_mean, 0.0)

    predictions = scoring.with_columns(
        pl.Series("prior_expected_ksi", prior_mean),
        pl.Series("expected_ksi", posterior_mean),
        pl.Series("expected_ksi_std", np.sqrt(posterior_variance)),
        pl.Series("excess_ksi", excess),
        pl.when(pl.col("year").is_in(contract.validation_years))
        .then(pl.lit("validation"))
        .otherwise(pl.lit("test"))
        .alias("evaluation_split"),
    )

    output.mkdir(parents=True, exist_ok=True)
    prediction_path = output / "empirical-bayes-screening.parquet"
    report_path = output / "empirical-bayes-screening-report.json"
    predictions.write_parquet(prediction_path)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "method": "Poisson-gamma Empirical Bayes retrospective frequency screening",
        "status": "evaluated-screening",
        "not_future_prediction": True,
        "training_years": contract.training_years,
        "scoring_years": scoring_years,
        "training_rows": training.height,
        "scoring_rows": scoring.height,
        "prior_rate_per_vehicle_km": prior_rate,
        "prior_shape": shape,
        "metrics": _screening_metrics(predictions),
        "panel": str(panel_path),
        "panel_sha256": sha256_file(panel_path),
        "contract": str(contract_path),
        "contract_sha256": sha256_file(contract_path),
        "output": str(prediction_path),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _fit_prior(training: pl.DataFrame) -> tuple[float, float]:
    exposure = training["annual_vehicle_km"].to_numpy().astype(float)
    observed = training["ksi_count"].to_numpy().astype(float)
    total_exposure = float(exposure.sum())
    prior_rate = float(observed.sum() / total_exposure)
    if not np.isfinite(prior_rate) or prior_rate <= 0:
        raise EmpiricalBayesValidationError("training data must contain a positive KSI rate")

    mean = exposure * prior_rate
    excess_variance = float(np.sum((observed - mean) ** 2 - mean))
    denominator = float(np.sum(mean**2))
    shape = denominator / excess_variance if excess_variance > 0 else 1_000_000_000.0
    return prior_rate, float(max(shape, 1.0))


def _validate_rows(frame: pl.DataFrame, label: str) -> None:
    invalid = frame.filter(
        pl.col("annual_vehicle_km").is_null()
        | (pl.col("annual_vehicle_km") <= 0)
        | pl.col("ksi_count").is_null()
        | (pl.col("ksi_count") < 0)
    ).height
    if invalid:
        raise EmpiricalBayesValidationError(f"{label} years contain {invalid} invalid rows")


def _screening_metrics(frame: pl.DataFrame) -> dict[str, dict[str, float]]:
    metrics: dict[str, dict[str, float]] = {}
    for split in ["validation", "test"]:
        subset = frame.filter(pl.col("evaluation_split") == split)
        if subset.is_empty():
            continue
        observed = subset["ksi_count"].to_numpy().astype(float)
        expected = subset["expected_ksi"].to_numpy().astype(float)
        metrics[split] = {
            "rows": float(subset.height),
            "observed_ksi": float(observed.sum()),
            "expected_ksi": float(expected.sum()),
            "excess_ksi": float(subset["excess_ksi"].sum()),
            "calibration_ratio": float(observed.sum() / expected.sum()) if expected.sum() else 0.0,
        }
    return metrics
