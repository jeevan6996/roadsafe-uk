import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import polars as pl
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from roadsafe import __version__
from roadsafe.domain import (
    CollisionPoint,
    CollisionSeverity,
    CollisionSummary,
    DataMetadata,
    NetworkSummary,
)
from roadsafe.pipeline import SOURCE_URL

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "dft-collisions-west-yorkshire-2024.csv"
DATA_PATH = Path(os.environ.get("ROADSAFE_DATA_PATH", FIXTURE_PATH))
NETWORK_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "segment-evidence-west-yorkshire-2024.geojson"
NETWORK_PATH = Path(os.environ.get("ROADSAFE_NETWORK_PATH", NETWORK_FIXTURE_PATH))

app = FastAPI(
    title="RoadSafe UK API",
    version=__version__,
    description="Versioned evidence API for road safety investigation.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@lru_cache
def collision_frame() -> pl.DataFrame:
    if DATA_PATH.suffix == ".parquet":
        return pl.read_parquet(DATA_PATH)
    return pl.read_csv(DATA_PATH)


@lru_cache
def network_features() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(NETWORK_PATH.read_text(encoding="utf-8")))


def to_point(row: dict[str, object]) -> CollisionPoint:
    severity = CollisionSeverity(int(str(row["collision_severity"])))
    return CollisionPoint(
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/api/v1/metadata", response_model=DataMetadata)
def metadata() -> DataMetadata:
    return DataMetadata(
        dataset="DfT STATS19 collision records",
        source=SOURCE_URL,
        source_year=2024,
        status="final validated data",
        licence="Open Government Licence v3.0",
        records=collision_frame().height,
        scope=(
            "West Yorkshire 2024 pilot"
            if DATA_PATH.suffix == ".parquet"
            else "Traceable West Yorkshire fixture"
        ),
        caveat="Police-reported personal-injury collisions only; not a measure of causal risk.",
    )


@app.get("/api/v1/collisions", response_model=list[CollisionPoint])
def collisions(
    severity: CollisionSeverity | None = None,
    limit: int = Query(default=500, ge=1, le=5_000),
) -> list[CollisionPoint]:
    frame = collision_frame()
    if severity is not None:
        frame = frame.filter(pl.col("collision_severity") == int(severity))
    return [to_point(row) for row in frame.head(limit).to_dicts()]


@app.get("/api/v1/summary", response_model=CollisionSummary)
def summary() -> CollisionSummary:
    frame = collision_frame()
    severity = frame["collision_severity"]
    return CollisionSummary(
        collisions=frame.height,
        killed_or_seriously_injured=int(severity.is_in([1, 2]).sum()),
        casualties=int(frame["number_of_casualties"].sum()),
        fatal=int((severity == 1).sum()),
        serious=int((severity == 2).sum()),
        slight=int((severity == 3).sum()),
    )


@app.get("/api/v1/segments")
def segments() -> dict[str, Any]:
    return network_features()


@app.get("/api/v1/network-summary", response_model=NetworkSummary)
def network_summary() -> NetworkSummary:
    properties = [feature["properties"] for feature in network_features()["features"]]
    return NetworkSummary(
        segments=len(properties),
        segments_with_exposure=sum(item["all_motor_vehicles"] is not None for item in properties),
        counted_exposure=sum(item["estimation_method"] == "Counted" for item in properties),
        estimated_exposure=sum(item["estimation_method"] == "Estimated" for item in properties),
        matched_collisions=sum(item["collision_count"] for item in properties),
        matched_ksi=sum(item["ksi_count"] for item in properties),
        scope="DfT major-road links only",
        caveat="AADF link estimates are descriptive exposure, not expected collision risk.",
    )
