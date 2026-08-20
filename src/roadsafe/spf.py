from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import statsmodels.api as sm  # type: ignore[import-untyped]

from roadsafe.baseline import _metrics_by_split
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

    model = sm.NegativeBinomial(
        train_target,
        train_design,
        loglike_method="nb2",
        offset=np.log(train_exposure),
    )
    try:
        result = model.fit(disp=False, maxiter=200)
    except Exception as error:  # statsmodels exposes several fit exception types
        raise SPFValidationError(f"negative-binomial SPF failed to fit: {error}") from error
    if not result.mle_retvals.get("converged", False):
        raise SPFValidationError("negative-binomial SPF did not converge")

    expected = np.asarray(result.predict(score_design, offset=np.log(score_exposure)), dtype=float)
    if not np.isfinite(expected).all() or (expected < 0).any():
        raise SPFValidationError("negative-binomial SPF produced invalid predictions")

    predictions = scoring.with_columns(
        pl.Series("expected_ksi", expected),
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
        "dispersion_alpha": float(result.params[-1]),
        "metrics": {
            "spf": _metrics_by_split(predictions),
            "exposure_rate_baseline": _metrics_by_split(baseline_predictions),
        },
        "unseen_authorities": _unseen_authorities(
            panel, contract.validation_years, contract.test_years
        ),
        "model_promoted": False,
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
