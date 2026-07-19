from pathlib import Path

import polars as pl
import pytest
from pydantic import ValidationError

from roadsafe.evaluation import (
    EvaluationContract,
    PanelValidationError,
    assess_panel_readiness,
    build_segment_year_panel,
    read_evaluation_contract,
)

ROOT = Path(__file__).resolve().parents[1]


def test_published_evaluation_contract_is_future_ordered() -> None:
    contract = read_evaluation_contract(ROOT / "configs" / "evaluation-v1.json")

    assert contract.status == "planned-not-run"
    assert contract.training_years == [2019, 2020, 2021, 2022]
    assert contract.test_years == [2024]
    assert "collision_weather" in contract.excluded_event_features


def test_evaluation_contract_rejects_overlapping_years() -> None:
    with pytest.raises(ValidationError, match="partitions overlap"):
        EvaluationContract(
            schema_version="1.0",
            status="planned-not-run",
            unit="dft-major-road-segment-year",
            target="future_ksi_collision_count",
            training_years=[2022, 2023],
            validation_years=[2023],
            test_years=[2024],
            geographic_split="grouped-local-authority-holdout",
            feature_cutoff="end-of-prior-calendar-year",
            ranking_metrics=["lift_at_k"],
            probabilistic_metrics=["poisson_deviance"],
            required_subgroups=["road_class"],
            excluded_event_features=["collision_weather"],
        )


def panel_frame(year: int, *, include_urban_rural: bool = True) -> pl.DataFrame:
    data: dict[str, list[object]] = {
        "segment_key": ["dft-count-point-1", "dft-count-point-2"],
        "segment_id": [f"dft-mrdb-{year}-1", f"dft-mrdb-{year}-2"],
        "count_point_id": [1, 2],
        "source_year": [year, year],
        "year": [year, year],
        "road_number": ["A1", "M1"],
        "road_category": ["PA", "TM"],
        "road_type": ["Major", "Major"],
        "local_authority_id": [10, 20],
        "local_authority_name": ["Authority A", "Authority B"],
        "local_authority_code": ["E00000001", "E00000002"],
        "estimation_method": ["Counted", "Estimated"],
        "all_motor_vehicles": [10_000, 20_000],
        "link_length_km": [1.0, 2.0],
        "annual_vehicle_km": [3_650_000.0, 14_600_000.0],
        "collision_count": [2, 1],
        "ksi_count": [1, 0],
    }
    if include_urban_rural:
        data["urban_rural"] = ["urban", "rural"]
    return pl.DataFrame(data)


def test_build_segment_year_panel_is_ready_for_complete_contract(tmp_path: Path) -> None:
    paths = []
    for year in range(2019, 2025):
        path = tmp_path / f"evidence-{year}.parquet"
        panel_frame(year).write_parquet(path)
        paths.append(path)

    output = tmp_path / "output"
    report = build_segment_year_panel(paths, ROOT / "configs" / "evaluation-v1.json", output)

    assert report["status"] == "ready-for-evaluation"
    assert report["available_years"] == list(range(2019, 2025))
    assert report["segments_with_complete_history"] == 2
    assert report["blockers"] == []
    assert (output / "segment-year-panel.parquet").exists()
    assert (output / "panel-readiness-report.json").exists()


def test_panel_readiness_reports_missing_years_and_subgroups() -> None:
    contract = read_evaluation_contract(ROOT / "configs" / "evaluation-v1.json")

    readiness = assess_panel_readiness(panel_frame(2024, include_urban_rural=False), contract)

    assert readiness["status"] == "blocked"
    assert readiness["missing_years"] == [2019, 2020, 2021, 2022, 2023]
    assert readiness["missing_subgroups"] == ["urban_rural"]
    assert readiness["blockers"] == ["missing_contract_years", "missing_subgroup_fields"]


def test_panel_readiness_blocks_partial_subgroup_coverage() -> None:
    contract = read_evaluation_contract(ROOT / "configs" / "evaluation-v1.json")
    panel = panel_frame(2024).with_columns(
        pl.when(pl.col("count_point_id") == 2)
        .then(None)
        .otherwise(pl.col("local_authority_code"))
        .alias("local_authority_code")
    )

    readiness = assess_panel_readiness(panel, contract)

    assert readiness["incomplete_subgroup_rows"] == {"local_authority": 1}
    assert "incomplete_subgroup_values" in readiness["blockers"]


def test_panel_readiness_requires_multiple_geographic_groups() -> None:
    contract = read_evaluation_contract(ROOT / "configs" / "evaluation-v1.json")
    panel = panel_frame(2024).with_columns(pl.lit("E00000001").alias("local_authority_code"))

    readiness = assess_panel_readiness(panel, contract)

    assert readiness["geographic_groups"] == 1
    assert "insufficient_geographic_groups" in readiness["blockers"]


def test_panel_readiness_blocks_invalid_exposure_and_target() -> None:
    contract = read_evaluation_contract(ROOT / "configs" / "evaluation-v1.json")
    panel = panel_frame(2024).with_columns(
        pl.when(pl.col("count_point_id") == 1)
        .then(0.0)
        .otherwise(pl.col("annual_vehicle_km"))
        .alias("annual_vehicle_km"),
        pl.when(pl.col("count_point_id") == 2)
        .then(-1)
        .otherwise(pl.col("ksi_count"))
        .alias("ksi_count"),
    )

    readiness = assess_panel_readiness(panel, contract)

    assert readiness["invalid_exposure_rows"] == 1
    assert readiness["invalid_target_rows"] == 1
    assert "invalid_exposure_rows" in readiness["blockers"]
    assert "invalid_target_rows" in readiness["blockers"]


def test_build_segment_year_panel_requires_inputs(tmp_path: Path) -> None:
    with pytest.raises(PanelValidationError, match="At least one annual evidence"):
        build_segment_year_panel([], ROOT / "configs" / "evaluation-v1.json", tmp_path / "output")


def test_build_segment_year_panel_rejects_invalid_annual_schema(tmp_path: Path) -> None:
    missing_column = tmp_path / "missing.parquet"
    panel_frame(2024).drop("segment_key").write_parquet(missing_column)

    with pytest.raises(PanelValidationError, match="missing panel columns: segment_key"):
        build_segment_year_panel(
            [missing_column], ROOT / "configs" / "evaluation-v1.json", tmp_path / "output"
        )

    inconsistent_year = tmp_path / "inconsistent.parquet"
    panel_frame(2024).with_columns(pl.lit(2023).alias("source_year")).write_parquet(
        inconsistent_year
    )
    with pytest.raises(PanelValidationError, match="inconsistent year fields"):
        build_segment_year_panel(
            [inconsistent_year],
            ROOT / "configs" / "evaluation-v1.json",
            tmp_path / "output",
        )


def test_build_segment_year_panel_rejects_duplicate_rows(tmp_path: Path) -> None:
    first = tmp_path / "first.parquet"
    second = tmp_path / "second.parquet"
    panel_frame(2024).write_parquet(first)
    panel_frame(2024).write_parquet(second)

    with pytest.raises(PanelValidationError, match="duplicate segment-year"):
        build_segment_year_panel(
            [first, second], ROOT / "configs" / "evaluation-v1.json", tmp_path / "output"
        )
