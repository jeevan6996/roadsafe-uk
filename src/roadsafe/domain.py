from enum import IntEnum
from math import isclose
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CollisionSeverity(IntEnum):
    FATAL = 1
    SERIOUS = 2
    SLIGHT = 3

    @property
    def label(self) -> str:
        return self.name.title()


class CollisionPoint(BaseModel):
    collision_id: str
    longitude: float = Field(ge=-8.7, le=2.1)
    latitude: float = Field(ge=49.8, le=60.9)
    severity: CollisionSeverity
    severity_label: str
    date: str
    time: str
    speed_limit: int
    vehicles: int = Field(ge=1)
    casualties: int = Field(ge=1)
    local_authority_code: str

    @classmethod
    def from_dft(cls, row: dict[str, Any]) -> Self:
        severity = CollisionSeverity(int(str(row["collision_severity"])))
        return cls(
            collision_id=str(row["collision_index"]),
            longitude=float(str(row["longitude"])),
            latitude=float(str(row["latitude"])),
            severity=severity,
            severity_label=severity.label,
            date=str(row["date"]),
            time=str(row["time"]),
            speed_limit=int(str(row["speed_limit"])),
            vehicles=int(str(row["number_of_vehicles"])),
            casualties=int(str(row["number_of_casualties"])),
            local_authority_code=str(row["local_authority_highway_current"]),
        )


class NetworkProperties(BaseModel):
    model_config = ConfigDict(strict=True, allow_inf_nan=False)
    segment_key: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    count_point_id: int = Field(gt=0)
    road_number: str = Field(min_length=1)
    source_year: Literal[2024]
    all_motor_vehicles: int = Field(ge=0)
    estimation_method: Literal["Counted", "Estimated"]
    estimation_method_detailed: str = Field(min_length=1)
    link_length_km: float = Field(gt=0)
    collision_count: int = Field(ge=0)
    ksi_count: int = Field(ge=0)
    collision_rate_per_100m_vehicle_km: float = Field(ge=0)


class NetworkGeometry(BaseModel):
    type: Literal["LineString"]
    coordinates: list[
        tuple[
            Annotated[float, Field(ge=-8.7, le=2.1, allow_inf_nan=False, strict=True)],
            Annotated[float, Field(ge=49.8, le=60.9, allow_inf_nan=False, strict=True)],
        ]
    ] = Field(min_length=2)


class NetworkFeature(BaseModel):
    type: Literal["Feature"]
    properties: NetworkProperties
    geometry: NetworkGeometry


class RetrospectiveRecord(BaseModel):
    model_config = ConfigDict(strict=True, allow_inf_nan=False)
    segment_key: str = Field(min_length=1)
    year: int = Field(ge=2000, le=2100)
    ksi_count: int = Field(ge=0)
    prior_expected_ksi: float = Field(gt=0)
    expected_ksi: float = Field(ge=0)
    expected_ksi_std: float = Field(ge=0)
    excess_ksi: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_retrospective_semantics(self) -> Self:
        # The producer shrinks the observed count toward a positive prior mean.
        low, high = sorted((self.prior_expected_ksi, self.ksi_count))
        if (self.expected_ksi < low and not isclose(self.expected_ksi, low, abs_tol=1e-12)) or (
            self.expected_ksi > high and not isclose(self.expected_ksi, high, abs_tol=1e-12)
        ):
            raise ValueError(
                "Retrospective expected KSI must lie between prior and observed counts"
            )
        if not isclose(self.excess_ksi, max(self.ksi_count - self.expected_ksi, 0), abs_tol=1e-12):
            raise ValueError("Retrospective excess KSI is inconsistent with observed counts")
        variance = self.expected_ksi_std**2
        if variance < self.expected_ksi and not isclose(variance, self.expected_ksi, abs_tol=1e-12):
            raise ValueError("Retrospective variance proxy must be at least the expected count")
        return self


class DataMetadata(BaseModel):
    dataset: str
    source: str
    source_year: int
    status: str
    licence: str
    records: int
    scope: str
    caveat: str
    collision_sha256: str
    network_sha256: str
    empirical_bayes_sha256: str | None = None


class CollisionSummary(BaseModel):
    collisions: int
    killed_or_seriously_injured: int
    casualties: int
    fatal: int
    serious: int
    slight: int


class NetworkSummary(BaseModel):
    segments: int
    segments_with_exposure: int
    counted_exposure: int
    estimated_exposure: int
    matched_collisions: int
    matched_ksi: int
    scope: str
    caveat: str
