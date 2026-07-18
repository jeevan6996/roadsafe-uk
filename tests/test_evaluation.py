from pathlib import Path

import pytest
from pydantic import ValidationError

from roadsafe.evaluation import EvaluationContract, read_evaluation_contract

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
