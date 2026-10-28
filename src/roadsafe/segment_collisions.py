"""Count-verified collision assignments derived only from frozen serving geometry."""

from dataclasses import dataclass
from typing import Any, Literal, Self

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, model_validator
from shapely.errors import GEOSException

from roadsafe.bundle import validate_serving_data
from roadsafe.domain import CollisionPoint
from roadsafe.network import (
    AMBIGUITY_MARGIN_METRES,
    MAX_MATCH_DISTANCE_METRES,
    _segment_from_wgs84,
    match_collisions,
)


class CollisionMatching(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    method: Literal["nearest_unambiguous_bng"] = "nearest_unambiguous_bng"
    max_distance_m: float = MAX_MATCH_DISTANCE_METRES
    ambiguity_margin_m: float = AMBIGUITY_MARGIN_METRES


class SegmentCollisions(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    segment_key: str = Field(min_length=1)
    source_year: int
    available: bool
    reason: str | None
    collisions: list[CollisionPoint]
    collision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    network_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    matching: CollisionMatching = Field(default_factory=CollisionMatching)

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        if self.available:
            if self.reason is not None:
                raise ValueError("Available evidence must not have an unavailable reason")
        elif not self.reason or self.collisions:
            raise ValueError("Unavailable evidence requires a reason and no collision points")
        return self


@dataclass(frozen=True)
class CollisionAssignments:
    points: dict[str, list[CollisionPoint]]
    reason: str | None = None


def derive_assignments(frame: pl.DataFrame, network: dict[str, Any]) -> CollisionAssignments:
    try:
        validate_serving_data(frame, network, None)
        properties = [feature["properties"] for feature in network["features"]]
        for field in ("segment_id", "count_point_id"):
            values = [props[field] for props in properties]
            if len(set(values)) != len(values):
                raise ValueError("Road matching identities are not unique")
        # The matcher emits string identities, including for numerically inferred CSV IDs.
        frame = frame.with_columns(pl.col("collision_index").cast(pl.String))
        if frame["collision_index"].n_unique() != frame.height:
            raise ValueError("Collision matching identities are not unique")
        segments = [
            _segment_from_wgs84(feature, feature["properties"]["source_year"])
            for feature in network["features"]
        ]
        matches = match_collisions(frame, segments)
        accepted = matches.filter(pl.col("match_status") == "accepted")
        rows = {row["collision_index"]: row for row in frame.to_dicts()}
        points: dict[str, list[CollisionPoint]] = {props["segment_key"]: [] for props in properties}
        keys = {props["segment_id"]: props["segment_key"] for props in properties}
        for match in accepted.to_dicts():
            points[keys[match["segment_id"]]].append(
                CollisionPoint.from_dft(rows[match["collision_index"]])
            )
        for props in properties:
            assigned = points[props["segment_key"]]
            if (
                len(assigned) != props["collision_count"]
                or sum(point.severity in (1, 2) for point in assigned) != props["ksi_count"]
            ):
                return CollisionAssignments(
                    {},
                    "Canonical-geometry assignments do not reproduce network collision/KSI counts.",
                )
        return CollisionAssignments(points)
    except (ValueError, KeyError, TypeError, GEOSException, pl.exceptions.PolarsError):
        return CollisionAssignments({}, "Frozen artifacts do not support verified road matching.")
