from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, Literal

import numpy as np
import polars as pl
import statsmodels.api as sm  # type: ignore[import-untyped]

from roadsafe.evaluation import assess_geographic_holdout, read_evaluation_contract
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
    return build_count_spf(panel_path, contract_path, output)


def build_count_spf(
    panel_path: Path,
    contract_path: Path,
    output: Path,
    *,
    model_kind: Literal["negative-binomial", "ridge-poisson"] = "negative-binomial",
    ridge_alpha: float = 0.01,
) -> dict[str, Any]:
    if model_kind not in {"negative-binomial", "ridge-poisson"}:
        raise SPFValidationError("Unsupported count model")
    if not np.isfinite(ridge_alpha) or ridge_alpha <= 0:
        raise SPFValidationError("ridge_alpha must be finite and positive")
    fit_model = (
        _fit_model
        if model_kind == "negative-binomial"
        else partial(_fit_ridge_poisson, alpha=ridge_alpha)
    )
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
    available_years = set(training["year"].to_list() + scoring["year"].to_list())
    missing_years = sorted(set(training_years + scoring_years).difference(available_years))
    if missing_years:
        raise SPFValidationError(f"Missing contract years: {missing_years}")
    feature_timing: dict[str, Any] = {
        "mode": "same-year-observed",
        "publication_availability_verified": False,
    }
    if "feature_year" in panel.columns:
        relevant = pl.concat([training, scoring])
        if (
            not relevant.schema["feature_year"].is_integer()
            or relevant.filter(
                pl.col("feature_year").is_null() | (pl.col("feature_year") >= pl.col("year"))
            ).height
        ):
            raise SPFValidationError("feature_year must be an integer strictly before target year")
        feature_timing["mode"] = "historical-exposure-proxy"
        feature_timing["lags_in_years"] = sorted(
            relevant.select(pl.col("year") - pl.col("feature_year")).to_series().unique().to_list()
        )
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

    result = fit_model(train_target, train_design, train_exposure)
    expected = _predict(result, score_design, score_exposure)
    alpha = float(result.params[-1]) if model_kind == "negative-binomial" else 0.0
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
    prediction_path = output / f"{model_kind}-spf-predictions.parquet"
    report_path = output / f"{model_kind}-spf-report.json"
    predictions.write_parquet(prediction_path)
    temporal_unseen = assess_geographic_holdout(panel, contract)
    authority_holdout = _authority_holdout(training, fit_model=fit_model)
    future_authority_holdout = _authority_holdout(
        training,
        predictions.drop(
            "expected_ksi", "expected_ksi_std", "expected_ksi_lower_95", "expected_ksi_upper_95"
        ),
        fit_model=fit_model,
    )
    metrics = {
        "spf": _detailed_metrics_by_split(predictions),
        "exposure_rate_baseline": _detailed_metrics_by_split(baseline_predictions),
    }
    promotion_blockers = [
        "prior_year_feature_availability_not_verified",
        "calibration_and_uncertainty_acceptance_gates_not_defined",
        "future_authority_holdout_incomplete"
        if not future_authority_holdout.get("complete", False)
        else None,
        "no_future_unseen_authorities"
        if not temporal_unseen["unseen_validation"] and not temporal_unseen["unseen_test"]
        else None,
        "authority_holdout_unavailable" if not authority_holdout["available"] else None,
        "authority_holdout_incomplete"
        if authority_holdout.get("available") and not authority_holdout.get("complete", False)
        else None,
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
            if model_kind == "negative-binomial"
            else "ridge-regularized Poisson Safety Performance Function with log exposure offset"
        ),
        "model_kind": model_kind,
        "ridge_alpha": ridge_alpha if model_kind == "ridge-poisson" else None,
        "interval_note": "Normal process-variance approximation; excludes parameter uncertainty",
        "status": "evaluated-benchmark",
        "training_years": training_years,
        "validation_years": contract.validation_years,
        "test_years": contract.test_years,
        "features": [spec[0] for spec in feature_specs],
        "feature_timing": feature_timing,
        "training_rows": training.height,
        "scoring_rows": scoring.height,
        "dispersion_alpha": alpha if model_kind == "negative-binomial" else None,
        "metrics": metrics,
        "subgroup_metrics": {
            "spf": _subgroup_metrics(predictions),
            "exposure_rate_baseline": _subgroup_metrics(baseline_predictions),
        },
        "unseen_authorities": temporal_unseen,
        "authority_holdout": authority_holdout,
        "future_authority_holdout": future_authority_holdout,
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


def _fit_ridge_poisson(
    target: np.ndarray, design: np.ndarray, exposure: np.ndarray, *, alpha: float
) -> Any:
    if target.sum() <= 0:
        raise SPFValidationError("Poisson training requires at least one positive count")
    model = sm.GLM(target, design, family=sm.families.Poisson(), offset=np.log(exposure))
    penalties = np.full(design.shape[1], alpha)
    penalties[0] = 0.0
    start = np.zeros(design.shape[1])
    start[0] = np.log(target.sum() / exposure.sum())
    try:
        result = model.fit_regularized(alpha=penalties, L1_wt=0.0, start_params=start, maxiter=500)
    except Exception as error:
        raise SPFValidationError(f"ridge Poisson failed to fit: {error}") from error
    # GLM's ridge result does not expose optimizer convergence; verify stationarity.
    gradient = -model.score(result.params) / len(target) + penalties * result.params
    if (
        not np.isfinite(result.params).all()
        or not np.isfinite(gradient).all()
        or (np.max(np.abs(gradient)) > 1e-5)
    ):
        raise SPFValidationError("ridge Poisson did not reach the gradient tolerance")
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
    order = np.argsort(-predicted, kind="stable")[:ranking_count]
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
        "precision_at_10_percent": float(np.mean(actual[order] > 0)),
        "mean_ksi_at_10_percent": float(top_actual / ranking_count),
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


def _authority_holdout(
    training: pl.DataFrame,
    scoring: pl.DataFrame | None = None,
    *,
    fit_model: Callable[[np.ndarray, np.ndarray, np.ndarray], Any] | None = None,
) -> dict[str, Any]:
    fit_model = _fit_model if fit_model is None else fit_model
    future = scoring is not None
    scoring = training if scoring is None else scoring
    if any("local_authority_code" not in frame.columns for frame in (training, scoring)):
        return {"available": False, "reason": "missing_local_authority_code"}
    if any(
        frame.filter(
            pl.col("local_authority_code").is_null()
            | (pl.col("local_authority_code").cast(pl.String).str.strip_chars() == "")
        ).height
        for frame in (training, scoring)
    ):
        return {"available": False, "reason": "incomplete_local_authority_code"}
    if future:
        last_training_year = training["year"].max()
        first_scoring_year = scoring["year"].min()
        if (
            not isinstance(last_training_year, int)
            or not isinstance(first_scoring_year, int)
            or training["year"].null_count()
            or scoring["year"].null_count()
            or last_training_year >= first_scoring_year
        ):
            return {"available": False, "reason": "scoring_period_not_strictly_future"}
    authorities = sorted(str(value) for value in scoring["local_authority_code"].unique().to_list())
    if not future and len(authorities) < 2:
        return {"available": False, "reason": "fewer_than_two_training_authorities"}

    fold_predictions: list[pl.DataFrame] = []
    baseline_predictions: list[pl.DataFrame] = []
    folds: list[dict[str, Any]] = []
    failed_folds: list[dict[str, str]] = []
    for held_out in authorities:
        fit_frame = training.filter(pl.col("local_authority_code").cast(pl.String) != held_out)
        holdout = scoring.filter(pl.col("local_authority_code").cast(pl.String) == held_out)
        # Exclude stable segment identities too, including authority-boundary changes.
        if future:
            fit_frame = fit_frame.filter(
                ~pl.col("segment_key").is_in(holdout["segment_key"].unique().implode())
            )
        try:
            if fit_frame.is_empty():
                raise SPFValidationError("no training rows after geographic exclusions")
            _validate_rows(fit_frame, "authority-holdout training")
            _validate_rows(holdout, "authority holdout")
            specs = _feature_specs(fit_frame)
            result = fit_model(
                fit_frame["ksi_count"].to_numpy().astype(float),
                _design_matrix(fit_frame, specs),
                fit_frame["annual_vehicle_km"].to_numpy().astype(float),
            )
            expected = _predict(
                result,
                _design_matrix(holdout, specs),
                holdout["annual_vehicle_km"].to_numpy().astype(float),
            )
        except SPFValidationError as error:
            failure = {"held_out_authority": held_out, "reason": str(error)}
            failed_folds.append(failure)
            folds.append({**failure, "status": "failed"})
            continue
        fold = holdout.with_columns(pl.Series("expected_ksi", expected))
        baseline = holdout.with_columns(
            pl.Series("expected_ksi", _exposure_rate_predictions(fit_frame, holdout))
        )
        if not future:
            fold = fold.with_columns(pl.lit("authority_holdout").alias("evaluation_split"))
            baseline = baseline.with_columns(pl.lit("authority_holdout").alias("evaluation_split"))
        fold_predictions.append(fold)
        baseline_predictions.append(baseline)
        folds.append(
            {
                "held_out_authority": held_out,
                "training_rows": fit_frame.height,
                "holdout_rows": holdout.height,
                "training_authorities": sorted(
                    fit_frame["local_authority_code"].cast(pl.String).unique().to_list()
                ),
                "training_years": sorted(fit_frame["year"].unique().to_list()),
                "scoring_years": sorted(holdout["year"].unique().to_list()),
                "spf": _detailed_metrics(fold),
                "exposure_rate_baseline": _detailed_metrics(baseline),
                "metrics_by_split": {
                    "spf": _detailed_metrics_by_split(fold),
                    "exposure_rate_baseline": _detailed_metrics_by_split(baseline),
                }
                if future
                else {},
                "status": "completed",
            }
        )
    if not fold_predictions:
        return {
            "available": False,
            "complete": False,
            "expected_holdout_rows": scoring.height,
            "holdout_rows": 0,
            "reason": "all_authority_holdout_folds_failed",
            "held_out_authorities": authorities,
            "folds": folds,
            "failed_folds": failed_folds,
        }
    holdout_predictions = pl.concat(fold_predictions)
    baseline = pl.concat(baseline_predictions)
    completed_folds = [fold for fold in folds if fold["status"] == "completed"]
    return {
        "available": True,
        "complete": not failed_folds,
        "evaluation": "future-authority-holdout" if future else "historical-authority-holdout",
        "held_out_authorities": authorities,
        "folds": folds,
        "failed_folds": failed_folds,
        "training_rows": sum(fold["training_rows"] for fold in completed_folds),
        "holdout_rows": sum(fold["holdout_rows"] for fold in completed_folds),
        "expected_holdout_rows": scoring.height,
        "row_coverage": holdout_predictions.height / scoring.height,
        "spf": _detailed_metrics(holdout_predictions),
        "exposure_rate_baseline": _detailed_metrics(baseline),
        "metrics_by_split": {
            "spf": _detailed_metrics_by_split(holdout_predictions),
            "exposure_rate_baseline": _detailed_metrics_by_split(baseline),
        }
        if future
        else {},
    }


def _validate_rows(frame: pl.DataFrame, label: str) -> None:
    invalid = frame.filter(
        pl.col("annual_vehicle_km").is_null()
        | ~pl.col("annual_vehicle_km").is_finite()
        | (pl.col("annual_vehicle_km") <= 0)
        | pl.col("ksi_count").is_null()
        | ~pl.col("ksi_count").is_finite()
        | (pl.col("ksi_count") < 0)
        | (pl.col("ksi_count") != pl.col("ksi_count").floor())
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
