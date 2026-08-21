from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import statsmodels.api as sm  # type: ignore[import-untyped]

from roadsafe.evaluation import read_evaluation_contract
from roadsafe.pipeline import sha256_file

SPF_REQUIRED_COLUMNS = {"segment_key", "year", "annual_vehicle_km", "ksi_count"}
SPF_CATEGORICAL_FEATURES = (
    "road_category",
    "road_type",
    "urban_rural",
    "estimation_method",
)


class SPFValidationError(ValueError):
    """Raised when a panel cannot support the negative-binomial SPF."""


def build_negative_binomial_spf(
    panel_path: Path,
    contract_path: Path,
    output: Path,
) -> dict[str, Any]:
    panel = pl.read_parquet(panel_path)
    missing = SPF_REQUIRED_COLUMNS.difference(panel.columns)
    if missing:
        raise SPFValidationError(
            f"{panel_path.name} is missing SPF columns: {', '.join(sorted(missing))}"
        )

    contract = read_evaluation_contract(contract_path)
    training_years = contract.training_years
    scoring_years = contract.validation_years + contract.test_years
    training = panel.filter(pl.col("year").is_in(training_years))
    scoring = panel.filter(pl.col("year").is_in(scoring_years))
    if training.is_empty():
        raise SPFValidationError("training years contain no panel rows")
    if scoring.is_empty():
        raise SPFValidationError("validation and test years contain no panel rows")

    _validate_rows(training, "training")
    _validate_rows(scoring, "validation and test")

    feature_specs = _feature_specs(training)
    train_design = _design_matrix(training, feature_specs)
    score_design = _design_matrix(scoring, feature_specs)
    train_exposure = training["annual_vehicle_km"].to_numpy().astype(float)
    score_exposure = scoring["annual_vehicle_km"].to_numpy().astype(float)
    train_target = training["ksi_count"].to_numpy().astype(float)

    result = _fit_model(train_target, train_design, train_exposure)
    expected = _predict(result, score_design, score_exposure)
    alpha = float(result.params[-1])
    prediction_std = np.sqrt(expected + alpha * expected**2)

    predictions = scoring.with_columns(
        pl.Series("expected_ksi", expected),
        pl.Series("expected_ksi_std", prediction_std),
        pl.Series("expected_ksi_lower_95", np.maximum(0, expected - 1.96 * prediction_std)),
        pl.Series("expected_ksi_upper_95", expected + 1.96 * prediction_std),
        pl.when(pl.col("year").is_in(contract.validation_years))
        .then(pl.lit("validation"))
        .otherwise(pl.lit("test"))
        .alias("evaluation_split"),
    )
    baseline_expected = _exposure_rate_predictions(training, scoring)
    baseline_predictions = scoring.with_columns(
        pl.Series("expected_ksi", baseline_expected),
        pl.when(pl.col("year").is_in(contract.validation_years))
        .then(pl.lit("validation"))
        .otherwise(pl.lit("test"))
        .alias("evaluation_split"),
    )

    output.mkdir(parents=True, exist_ok=True)
    prediction_path = output / "negative-binomial-spf-predictions.parquet"
    report_path = output / "negative-binomial-spf-report.json"
    predictions.write_parquet(prediction_path)
    temporal_unseen = _unseen_authorities(panel, contract.validation_years, contract.test_years)
    authority_holdout = _authority_holdout(training)
    metrics = {
        "spf": _detailed_metrics_by_split(predictions),
        "exposure_rate_baseline": _detailed_metrics_by_split(baseline_predictions),
    }
    promotion_blockers = [
        "no_future_unseen_authorities"
        if not temporal_unseen["validation"] and not temporal_unseen["test"]
        else None,
        "authority_holdout_unavailable" if not authority_holdout["available"] else None,
        "no_future_test_mae_improvement"
        if metrics["spf"].get("test", {}).get("mae", float("inf"))
        >= metrics["exposure_rate_baseline"].get("test", {}).get("mae", float("inf"))
        else None,
        "authority_holdout_does_not_beat_baseline"
        if authority_holdout.get("available")
        and authority_holdout["spf"]["mae"] >= authority_holdout["exposure_rate_baseline"]["mae"]
        else None,
    ]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "method": (
            "negative-binomial NB2 Safety Performance Function with log annual vehicle-km offset"
        ),
        "status": "evaluated-benchmark",
        "training_years": training_years,
        "validation_years": contract.validation_years,
        "test_years": contract.test_years,
        "features": [spec[0] for spec in feature_specs],
        "training_rows": training.height,
        "scoring_rows": scoring.height,
        "dispersion_alpha": alpha,
        "metrics": metrics,
        "subgroup_metrics": {
            "spf": _subgroup_metrics(predictions),
            "exposure_rate_baseline": _subgroup_metrics(baseline_predictions),
        },
        "unseen_authorities": temporal_unseen,
        "authority_holdout": authority_holdout,
        "promotion_blockers": [blocker for blocker in promotion_blockers if blocker],
        "model_promoted": not any(promotion_blockers),
        "promotion_note": (
            "Promote only after the SPF beats the baseline on declared future and authority "
            "holdouts with acceptable calibration."
        ),
        "panel": str(panel_path),
        "panel_sha256": sha256_file(panel_path),
        "contract": str(contract_path),
        "contract_sha256": sha256_file(contract_path),
        "output": str(prediction_path),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _fit_model(target: np.ndarray, design: np.ndarray, exposure: np.ndarray) -> Any:
    model = sm.NegativeBinomial(
        target,
        design,
        loglike_method="nb2",
        offset=np.log(exposure),
    )
    try:
        # The benchmark reports predictions, not coefficient standard errors;
        # skipping Hessian inversion avoids an unnecessary small-fixture warning.
        result = model.fit(disp=False, maxiter=200, skip_hessian=True)
    except Exception as error:  # statsmodels exposes several fit exception types
        raise SPFValidationError(f"negative-binomial SPF failed to fit: {error}") from error
    if not result.mle_retvals.get("converged", False):
        raise SPFValidationError("negative-binomial SPF did not converge")
    return result


def _predict(result: Any, design: np.ndarray, exposure: np.ndarray) -> np.ndarray:
    expected = np.asarray(result.predict(design, offset=np.log(exposure)), dtype=float)
    if not np.isfinite(expected).all() or (expected < 0).any():
        raise SPFValidationError("negative-binomial SPF produced invalid predictions")
    return expected


def _detailed_metrics_by_split(frame: pl.DataFrame) -> dict[str, dict[str, float]]:
    metrics: dict[str, dict[str, float]] = {}
    for split in ["validation", "test"]:
        rows = frame.filter(pl.col("evaluation_split") == split)
        if not rows.is_empty():
            metrics[split] = _detailed_metrics(rows)
    return metrics


def _detailed_metrics(frame: pl.DataFrame) -> dict[str, float]:
    actual = frame["ksi_count"].to_numpy().astype(float)
    predicted = np.maximum(frame["expected_ksi"].to_numpy().astype(float), 1e-12)
    errors = actual - predicted
    deviance_terms = np.empty_like(actual)
    positive = actual > 0
    deviance_terms[~positive] = predicted[~positive]
    deviance_terms[positive] = actual[positive] * np.log(actual[positive] / predicted[positive]) - (
        actual[positive] - predicted[positive]
    )
    ranking_count = max(1, int(np.ceil(frame.height * 0.1)))
    order = np.argsort(-predicted)[:ranking_count]
    total_actual = float(actual.sum())
    top_actual = float(actual[order].sum())
    recall = top_actual / total_actual if total_actual else 0.0
    return {
        "rows": float(frame.height),
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "poisson_deviance": float(2 * np.sum(deviance_terms)),
        "mean_actual": float(np.mean(actual)),
        "mean_predicted": float(np.mean(predicted)),
        "calibration_ratio": float(actual.sum() / predicted.sum()) if predicted.sum() else 0.0,
        "precision_at_10_percent": float(top_actual / ranking_count),
        "recall_at_10_percent": float(recall),
        "lift_at_10_percent": float(recall / (ranking_count / frame.height)),
    }


def _subgroup_metrics(frame: pl.DataFrame) -> dict[str, dict[str, dict[str, float]]]:
    metrics: dict[str, dict[str, dict[str, float]]] = {}
    for column in ["road_category", "urban_rural", "estimation_method"]:
        if column not in frame.columns:
            continue
        metrics[column] = {}
        for value in frame[column].drop_nulls().cast(pl.String).unique().sort().to_list():
            subset = frame.filter(pl.col(column).cast(pl.String) == value)
            metrics[column][str(value)] = _detailed_metrics(subset)
    return metrics


def _authority_holdout(training: pl.DataFrame) -> dict[str, Any]:
    if "local_authority_code" not in training.columns:
        return {"available": False, "reason": "missing_local_authority_code"}
    authorities = sorted(
        str(value) for value in training["local_authority_code"].drop_nulls().unique().to_list()
    )
    if len(authorities) < 2:
        return {"available": False, "reason": "fewer_than_two_training_authorities"}

    held_out = authorities[-1]
    fit_frame = training.filter(pl.col("local_authority_code").cast(pl.String) != held_out)
    holdout = training.filter(pl.col("local_authority_code").cast(pl.String) == held_out)
    _validate_rows(fit_frame, "authority-holdout training")
    _validate_rows(holdout, "authority holdout")
    specs = _feature_specs(fit_frame)
    result = _fit_model(
        fit_frame["ksi_count"].to_numpy().astype(float),
        _design_matrix(fit_frame, specs),
        fit_frame["annual_vehicle_km"].to_numpy().astype(float),
    )
    expected = _predict(
        result,
        _design_matrix(holdout, specs),
        holdout["annual_vehicle_km"].to_numpy().astype(float),
    )
    holdout_predictions = holdout.with_columns(
        pl.Series("expected_ksi", expected), pl.lit("authority_holdout").alias("evaluation_split")
    )
    baseline = holdout.with_columns(
        pl.Series("expected_ksi", _exposure_rate_predictions(fit_frame, holdout)),
        pl.lit("authority_holdout").alias("evaluation_split"),
    )
    return {
        "available": True,
        "held_out_authority": held_out,
        "training_rows": fit_frame.height,
        "holdout_rows": holdout.height,
        "spf": _detailed_metrics(holdout_predictions),
        "exposure_rate_baseline": _detailed_metrics(baseline),
    }


def _validate_rows(frame: pl.DataFrame, label: str) -> None:
    invalid = frame.filter(
        pl.col("annual_vehicle_km").is_null()
        | (pl.col("annual_vehicle_km") <= 0)
        | pl.col("ksi_count").is_null()
        | (pl.col("ksi_count") < 0)
    ).height
    if invalid:
        raise SPFValidationError(f"{label} years contain {invalid} invalid rows")


def _feature_specs(frame: pl.DataFrame) -> list[tuple[str, list[str]]]:
    specs: list[tuple[str, list[str]]] = []
    for column in SPF_CATEGORICAL_FEATURES:
        if column not in frame.columns:
            continue
        values = frame[column].cast(pl.String).fill_null("__missing__").unique().sort().to_list()
        if len(values) > 1:
            specs.append((column, [str(value) for value in values[1:]]))
    return specs


def _design_matrix(frame: pl.DataFrame, specs: list[tuple[str, list[str]]]) -> np.ndarray:
    columns: list[np.ndarray] = [np.ones(frame.height, dtype=float)]
    for column, levels in specs:
        values = frame[column].cast(pl.String).fill_null("__missing__").to_list()
        for level in levels:
            columns.append(np.asarray([float(value == level) for value in values]))
    return np.column_stack(columns)


def _exposure_rate_predictions(training: pl.DataFrame, scoring: pl.DataFrame) -> np.ndarray:
    total_exposure = float(training["annual_vehicle_km"].sum())
    total_target = float(training["ksi_count"].sum())
    return scoring["annual_vehicle_km"].to_numpy().astype(float) * total_target / total_exposure


def _unseen_authorities(
    panel: pl.DataFrame,
    validation_years: list[int],
    test_years: list[int],
) -> dict[str, Any]:
    if "local_authority_code" not in panel.columns:
        return {"available": False, "validation": [], "test": []}
    training_authorities = set(
        panel.filter(~pl.col("year").is_in(validation_years + test_years))["local_authority_code"]
        .drop_nulls()
        .cast(pl.String)
        .to_list()
    )
    result: dict[str, Any] = {"available": True}
    for label, years in [("validation", validation_years), ("test", test_years)]:
        authorities = set(
            panel.filter(pl.col("year").is_in(years))["local_authority_code"]
            .drop_nulls()
            .cast(pl.String)
            .to_list()
        )
        result[label] = sorted(authorities.difference(training_authorities))
    return result
