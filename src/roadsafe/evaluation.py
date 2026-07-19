from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import polars as pl
from pydantic import BaseModel, Field, model_validator

from roadsafe.pipeline import sha256_file

PANEL_REQUIRED_COLUMNS = {
    "segment_key",
    "segment_id",
    "count_point_id",
    "source_year",
    "year",
    "road_number",
    "road_category",
    "road_type",
    "local_authority_id",
    "local_authority_name",
    "local_authority_code",
    "estimation_method",
    "all_motor_vehicles",
    "link_length_km",
    "annual_vehicle_km",
    "collision_count",
    "ksi_count",
}

SUBGROUP_COLUMNS = {
    "road_class": "road_category",
    "urban_rural": "urban_rural",
    "traffic_estimation_method": "estimation_method",
    "local_authority": "local_authority_code",
}


class PanelValidationError(ValueError):
    """Raised when annual evidence cannot form an auditable segment-year panel."""


class EvaluationContract(BaseModel):
    schema_version: str
    status: Literal["planned-not-run", "completed"]
    unit: Literal["dft-major-road-segment-year"]
    target: Literal["future_ksi_collision_count"]
    training_years: list[int] = Field(min_length=1)
    validation_years: list[int] = Field(min_length=1)
    test_years: list[int] = Field(min_length=1)
    geographic_split: Literal["grouped-local-authority-holdout"]
    feature_cutoff: Literal["end-of-prior-calendar-year"]
    ranking_metrics: list[str] = Field(min_length=1)
    probabilistic_metrics: list[str] = Field(min_length=1)
    required_subgroups: list[str] = Field(min_length=1)
    excluded_event_features: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def years_are_strictly_future_ordered(self) -> EvaluationContract:
        train = set(self.training_years)
        validation = set(self.validation_years)
        test = set(self.test_years)
        if train & validation or train & test or validation & test:
            raise ValueError("Evaluation year partitions overlap")
        if max(train) >= min(validation) or max(validation) >= min(test):
            raise ValueError("Validation and test periods must follow training")
        return self


def read_evaluation_contract(path: Path) -> EvaluationContract:
    return EvaluationContract.model_validate_json(path.read_text(encoding="utf-8"))


def assess_panel_readiness(panel: pl.DataFrame, contract: EvaluationContract) -> dict[str, Any]:
    required_years = sorted(
        contract.training_years + contract.validation_years + contract.test_years
    )
    available_years = sorted(int(year) for year in panel["year"].drop_nulls().unique())
    missing_years = sorted(set(required_years).difference(available_years))
    contract_panel = panel.filter(pl.col("year").is_in(required_years))
    missing_subgroups = []
    incomplete_subgroup_rows = {}
    for subgroup in contract.required_subgroups:
        column = SUBGROUP_COLUMNS.get(subgroup)
        if column is None or column not in panel.columns:
            missing_subgroups.append(subgroup)
            continue
        incomplete = contract_panel.filter(
            pl.col(column).is_null() | (pl.col(column).cast(pl.String).str.strip_chars() == "")
        ).height
        if incomplete:
            incomplete_subgroup_rows[subgroup] = incomplete

    invalid_exposure = contract_panel.filter(
        pl.col("annual_vehicle_km").is_null() | (pl.col("annual_vehicle_km") <= 0)
    ).height
    invalid_target = contract_panel.filter(
        pl.col("ksi_count").is_null() | (pl.col("ksi_count") < 0)
    ).height
    complete_history = (
        contract_panel.group_by("segment_key")
        .agg(pl.col("year").n_unique().alias("years"))
        .filter(pl.col("years") == len(required_years))
        .height
    )
    geographic_groups = (
        contract_panel["local_authority_code"].drop_nulls().n_unique()
        if "local_authority_code" in contract_panel.columns
        else 0
    )
    blockers = []
    if missing_years:
        blockers.append("missing_contract_years")
    if missing_subgroups:
        blockers.append("missing_subgroup_fields")
    if incomplete_subgroup_rows:
        blockers.append("incomplete_subgroup_values")
    if geographic_groups < 2:
        blockers.append("insufficient_geographic_groups")
    if invalid_exposure:
        blockers.append("invalid_exposure_rows")
    if invalid_target:
        blockers.append("invalid_target_rows")
    return {
        "status": "ready-for-evaluation" if not blockers else "blocked",
        "blockers": blockers,
        "required_years": required_years,
        "available_years": available_years,
        "missing_years": missing_years,
        "missing_subgroups": missing_subgroups,
        "incomplete_subgroup_rows": incomplete_subgroup_rows,
        "invalid_exposure_rows": invalid_exposure,
        "invalid_target_rows": invalid_target,
        "geographic_groups": geographic_groups,
        "segments_with_complete_history": complete_history,
    }


def build_segment_year_panel(
    evidence_paths: list[Path], contract_path: Path, output: Path
) -> dict[str, Any]:
    if not evidence_paths:
        raise PanelValidationError("At least one annual evidence file is required")

    frames = []
    for path in evidence_paths:
        frame = pl.read_parquet(path)
        missing = PANEL_REQUIRED_COLUMNS.difference(frame.columns)
        if missing:
            raise PanelValidationError(
                f"{path.name} is missing panel columns: {', '.join(sorted(missing))}"
            )
        if frame.filter(pl.col("year") != pl.col("source_year")).height:
            raise PanelValidationError(f"{path.name} has inconsistent year fields")
        frames.append(frame)

    panel = pl.concat(frames, how="diagonal_relaxed").sort(["year", "segment_key"])
    duplicate_rows = panel.select(pl.struct(["segment_key", "year"]).is_duplicated().sum()).item()
    if duplicate_rows:
        raise PanelValidationError(f"Found {duplicate_rows} duplicate segment-year rows")

    contract = read_evaluation_contract(contract_path)
    readiness = assess_panel_readiness(panel, contract)
    output.mkdir(parents=True, exist_ok=True)
    panel_path = output / "segment-year-panel.parquet"
    report_path = output / "panel-readiness-report.json"
    panel.write_parquet(panel_path)
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "contract": str(contract_path),
        "contract_sha256": sha256_file(contract_path),
        "contract_schema_version": contract.schema_version,
        "contract_status": contract.status,
        "unit": contract.unit,
        "target": contract.target,
        "feature_cutoff": contract.feature_cutoff,
        "inputs": [{"path": str(path), "sha256": sha256_file(path)} for path in evidence_paths],
        "records": panel.height,
        "records_by_year": {
            str(row["year"]): row["len"]
            for row in panel.group_by("year").len().sort("year").to_dicts()
        },
        "segments": panel["segment_key"].n_unique(),
        "output": str(panel_path),
        **readiness,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
