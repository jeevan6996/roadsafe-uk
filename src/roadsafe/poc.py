"""Exploratory calibration/lag ablation; not a serving or promotion pipeline."""

from __future__ import annotations

import argparse
import json
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from roadsafe.evaluation import read_evaluation_contract
from roadsafe.features import build_lagged_feature_panel
from roadsafe.pipeline import sha256_file
from roadsafe.spf import (
    _design_matrix,
    _detailed_metrics,
    _exposure_rate_predictions,
    _feature_specs,
    _fit_ridge_poisson,
    _predict,
    _validate_rows,
)

MODELS = ("exposure-baseline", "ridge-poisson", "poisson-boosting")
BOOSTING = {
    "loss": "poisson",
    "max_iter": 100,
    "max_leaf_nodes": 7,
    "min_samples_leaf": 20,
    "learning_rate": 0.05,
    "l2_regularization": 1.0,
    "early_stopping": False,
    "random_state": 42,
}


def calibration_factor(actual: np.ndarray, predicted: np.ndarray) -> float:
    if actual.ndim != 1 or actual.shape != predicted.shape or actual.size == 0:
        raise ValueError("Calibration requires aligned nonempty vectors")
    if (
        not np.isfinite(actual).all()
        or not np.isfinite(predicted).all()
        or (actual < 0).any()
        or (actual != np.floor(actual)).any()
        or (predicted <= 0).any()
        or actual.sum() <= 0
    ):
        raise ValueError("Calibration requires valid counts and positive predicted/actual totals")
    factor = float(actual.sum() / predicted.sum())
    if not np.isfinite(factor) or factor <= 0:
        raise ValueError("Invalid calibration factor")
    return factor


def predict_counts(training: pl.DataFrame, scoring: pl.DataFrame, model: str) -> np.ndarray:
    if training.is_empty() or scoring.is_empty():
        raise ValueError("Empty training or scoring cohort")
    _validate_rows(training, "training")
    if training["ksi_count"].sum() <= 0:
        raise ValueError("Training requires positive total counts")
    exposure = scoring["annual_vehicle_km"].to_numpy().astype(float)
    if not np.isfinite(exposure).all() or (exposure <= 0).any():
        raise ValueError("Scoring exposure must be finite and positive")
    specs = _feature_specs(training)
    train_design = _design_matrix(training, specs)
    score_design = _design_matrix(scoring, specs)
    train_exposure = training["annual_vehicle_km"].to_numpy().astype(float)
    target = training["ksi_count"].to_numpy().astype(float)
    if model == "exposure-baseline":
        predicted = _exposure_rate_predictions(training, scoring)
    elif model == "ridge-poisson":
        fitted = _fit_ridge_poisson(target, train_design, train_exposure, alpha=0.01)
        predicted = _predict(fitted, score_design, exposure)
    elif model == "poisson-boosting":
        from sklearn.ensemble import HistGradientBoostingRegressor

        # Exposure-weighted rate loss is proportional to count Poisson loss.
        # Scale exposure units to keep rates and Hessians numerically useful.
        unit = 1_000_000.0
        fitted = HistGradientBoostingRegressor(**BOOSTING)
        fitted.fit(
            train_design, target / (train_exposure / unit), sample_weight=train_exposure / unit
        )
        predicted = np.asarray(fitted.predict(score_design), dtype=float) * exposure / unit
    else:
        raise ValueError(f"Unknown POC model: {model}")
    if not np.isfinite(predicted).all() or (predicted <= 0).any():
        raise ValueError("Model produced invalid counts")
    return predicted


def split_fold(frame: pl.DataFrame, authority: str) -> tuple[pl.DataFrame, ...]:
    scoring = frame.filter((pl.col("year") == 2023) & (pl.col("local_authority_code") == authority))
    held_keys = scoring["segment_key"].to_list()
    others = frame.filter(
        (pl.col("local_authority_code") != authority) & ~pl.col("segment_key").is_in(held_keys)
    )
    return (others.filter(pl.col("year") == 2021), others.filter(pl.col("year") == 2022), scoring)


def run_poc(panel: Path, contract: Path, output: Path) -> dict[str, Any]:
    spec = read_evaluation_contract(contract)
    if (spec.training_years, spec.validation_years, spec.test_years) != ([2021], [2022], [2023]):
        raise ValueError("This fixed POC requires 2021 fit / 2022 calibration / 2023 evaluation")
    output.mkdir(parents=True, exist_ok=False)
    reports = {
        lag: build_lagged_feature_panel(panel, contract, output / f"lag-{lag}", lag)
        for lag in (1, 2)
    }
    frames = {lag: pl.read_parquet(report["output"]) for lag, report in reports.items()}
    keys = ["segment_key", "year"]
    common = frames[1].select(keys).join(frames[2].select(keys), on=keys, how="inner")
    frames = {
        lag: frame.join(common, on=keys, how="semi").sort(keys) for lag, frame in frames.items()
    }
    if any(set(frame["year"].to_list()) != {2021, 2022, 2023} for frame in frames.values()):
        raise ValueError("Common cohort does not cover all POC years")
    results: list[dict[str, Any]] = []
    predictions: list[pl.DataFrame] = []
    for lag, frame in frames.items():
        authorities = sorted(
            frame.filter(pl.col("year") == 2023)["local_authority_code"].unique().to_list()
        )
        for model in MODELS:
            folds = []
            raw_frames, scaled_frames = [], []
            for authority in authorities:
                training, calibration, scoring = split_fold(frame, authority)
                try:
                    combined = pl.concat([calibration, scoring])
                    values = predict_counts(training, combined, model)
                    factor = calibration_factor(
                        calibration["ksi_count"].to_numpy(), values[: calibration.height]
                    )
                    raw = scoring.with_columns(
                        pl.Series("expected_ksi", values[calibration.height :])
                    )
                    scaled = raw.with_columns(pl.col("expected_ksi") * factor)
                    raw_frames.append(raw)
                    scaled_frames.append(scaled)
                    folds.append(
                        {
                            "authority": authority,
                            "status": "completed",
                            "factor": factor,
                            "training_rows": training.height,
                            "calibration_rows": calibration.height,
                            "raw": _detailed_metrics(raw),
                            "scaled": _detailed_metrics(scaled),
                        }
                    )
                except (ValueError, RuntimeError) as error:
                    folds.append({"authority": authority, "status": "failed", "reason": str(error)})
            complete = len(raw_frames) == len(authorities) and bool(authorities)
            result: dict[str, Any] = {
                "lag": lag,
                "model": model,
                "complete": complete,
                "folds": folds,
            }
            for name, parts in (("raw", raw_frames), ("scaled", scaled_frames)):
                if parts:
                    scored = pl.concat(parts).sort(keys)
                    result[name] = _detailed_metrics(scored) if complete else None
                    predictions.append(
                        scored.with_columns(
                            pl.lit(lag).alias("lag"),
                            pl.lit(model).alias("model"),
                            pl.lit(name).alias("variant"),
                        )
                    )
            results.append(result)
    prediction_path = output / "poc-predictions.parquet"
    if predictions:
        pl.concat(predictions).write_parquet(prediction_path)
    report = {
        "status": "completed-exploratory"
        if results and all(result["complete"] for result in results)
        else "partial-exploratory",
        "model_promoted": False,
        "fit_year": 2021,
        "calibration_year": 2022,
        "evaluation_year": 2023,
        "uses_2024_outcomes": False,
        "publication_availability_verified": False,
        "calibration_label_availability_verified": False,
        "code_sha256": {
            name: sha256_file(Path(__file__).with_name(name))
            for name in ("poc.py", "spf.py", "features.py")
        },
        "panel_sha256": sha256_file(panel),
        "contract_sha256": sha256_file(contract),
        "versions": {
            name: version(name) for name in ("numpy", "polars", "statsmodels", "scikit-learn")
        },
        "parameters": {"ridge_alpha": 0.01, "boosting": BOOSTING},
        "lag_coverage": {
            str(lag): {
                "before_pairing": reports[lag]["included_rows"],
                "after_pairing": frame.height,
                "by_year": frame.group_by("year").len().sort("year").to_dicts(),
            }
            for lag, frame in frames.items()
        },
        "results": results,
        "prediction_sha256": sha256_file(prediction_path) if predictions else None,
        "limitations": [
            "One fitting year; no hyperparameter search or confirmatory holdout",
            "Publication timing and historical revisions not verified",
            "2022 calibration labels were published after the end-2022 forecast cutoff",
            "2023 evaluation is exploratory; no uncertainty or promotion claim",
        ],
    }
    (output / "poc-report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=Path("configs/poc-count-models-v1.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_poc(args.panel, args.contract, args.output)
    print(json.dumps({"status": report["status"], "experiments": len(report["results"])}))
    if report["status"] != "completed-exploratory":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
