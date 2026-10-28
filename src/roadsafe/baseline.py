from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from roadsafe.evaluation import read_evaluation_contract
from roadsafe.pipeline import sha256_file


class BaselineValidationError(ValueError):
    """Raised when a panel cannot support the exposure baseline."""


BASELINE_REQUIRED_COLUMNS = {"segment_key", "year", "annual_vehicle_km", "ksi_count"}


def build_exposure_baseline(panel_path: Path, contract_path: Path, output: Path) -> dict[str, Any]:
    panel = pl.read_parquet(panel_path)
    missing = BASELINE_REQUIRED_COLUMNS.difference(panel.columns)
    if missing:
        raise BaselineValidationError(
            f"{panel_path.name} is missing baseline columns: {', '.join(sorted(missing))}"
        )

    contract = read_evaluation_contract(contract_path)
    training_years = contract.training_years
    scoring_years = contract.validation_years + contract.test_years
    training = panel.filter(pl.col("year").is_in(training_years))
    scoring = panel.filter(pl.col("year").is_in(scoring_years))
    if training.is_empty():
        raise BaselineValidationError("training years contain no panel rows")
    if scoring.is_empty():
        raise BaselineValidationError("validation and test years contain no panel rows")

    _validate_rows(training, "training")
    _validate_rows(scoring, "validation and test")
    scoring = scoring.with_columns(pl.col("ksi_count").cast(pl.UInt64))

    total_exposure_mvk = float(training["annual_vehicle_km"].cast(pl.Float64).sum()) / 1_000_000
    total_ksi = float(training["ksi_count"].cast(pl.Float64).sum())
    if not math.isfinite(total_exposure_mvk) or total_exposure_mvk <= 0:
        raise BaselineValidationError("training exposure must be finite and positive")
    if not math.isfinite(total_ksi) or total_ksi < 0:
        raise BaselineValidationError("training KSI total must be finite and nonnegative")
    training_rate = total_ksi / total_exposure_mvk
    if not math.isfinite(training_rate):
        raise BaselineValidationError("training rate must be finite")

    predictions = scoring.with_columns(
        (pl.col("annual_vehicle_km") / 1_000_000 * training_rate).alias("expected_ksi")
    ).with_columns(
        pl.when(pl.col("year").is_in(contract.validation_years))
        .then(pl.lit("validation"))
        .otherwise(pl.lit("test"))
        .alias("evaluation_split")
    )
    if not predictions["expected_ksi"].is_finite().all() or (predictions["expected_ksi"] < 0).any():
        raise BaselineValidationError("Baseline predictions must be finite and nonnegative")
    prediction_path = output / "exposure-baseline-predictions.parquet"
    report_path = output / "exposure-baseline-report.json"
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "method": "global training KSI rate with annual vehicle-km exposure offset",
        "not_modelled": False,
        "training_years": training_years,
        "scoring_years": scoring_years,
        "training_ksi": total_ksi,
        "training_million_vehicle_km": total_exposure_mvk,
        "training_rate_per_million_vehicle_km": training_rate,
        "metrics": _metrics_by_split(predictions),
        "panel": str(panel_path),
        "panel_sha256": sha256_file(panel_path),
        "contract": str(contract_path),
        "contract_sha256": sha256_file(contract_path),
        "output": str(prediction_path),
    }
    try:
        report_json = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    except ValueError as error:
        raise BaselineValidationError("Baseline report contains non-finite values") from error
    output.mkdir(parents=True, exist_ok=True)
    predictions.write_parquet(prediction_path)
    report_path.write_text(report_json, encoding="utf-8")
    return report


def _validate_rows(frame: pl.DataFrame, label: str) -> None:
    if any(not frame.schema[column].is_numeric() for column in ("annual_vehicle_km", "ksi_count")):
        raise BaselineValidationError(f"{label} years contain {frame.height} invalid rows")
    invalid = frame.filter(
        pl.col("annual_vehicle_km").is_null()
        | ~pl.col("annual_vehicle_km").cast(pl.Float64).is_finite()
        | (pl.col("annual_vehicle_km") <= 0)
        | pl.col("ksi_count").is_null()
        | ~pl.col("ksi_count").cast(pl.Float64).is_finite()
        | (pl.col("ksi_count") < 0)
        | (pl.col("ksi_count") != pl.col("ksi_count").floor())
        | pl.col("ksi_count").cast(pl.UInt64, strict=False).is_null()
    ).height
    if invalid:
        raise BaselineValidationError(f"{label} years contain {invalid} invalid rows")


def _metrics_by_split(predictions: pl.DataFrame) -> dict[str, dict[str, float]]:
    metrics: dict[str, dict[str, float]] = {}
    for split in ["validation", "test"]:
        frame = predictions.filter(pl.col("evaluation_split") == split)
        if frame.is_empty():
            continue
        errors = [
            float(actual) - float(expected)
            for actual, expected in frame.select(["ksi_count", "expected_ksi"]).iter_rows()
        ]
        metrics[split] = {
            "rows": float(frame.height),
            "mae": sum(abs(error) for error in errors) / len(errors),
            "rmse": math.sqrt(sum(error * error for error in errors) / len(errors)),
        }
    return metrics
