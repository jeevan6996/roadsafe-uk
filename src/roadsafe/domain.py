from enum import IntEnum

from pydantic import BaseModel, Field


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


class DataMetadata(BaseModel):
    dataset: str
    source: str
    source_year: int
    status: str
    licence: str
    records: int
    scope: str
    caveat: str


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
