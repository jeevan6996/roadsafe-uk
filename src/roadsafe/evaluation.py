from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
    def years_are_strictly_future_ordered(self) -> "EvaluationContract":
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
