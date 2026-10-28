import json
import os
from dataclasses import dataclass
from functools import cached_property, lru_cache
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import polars as pl
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from roadsafe import __version__
from roadsafe.bundle import PROFILES, artifact_path, load_demo_bundle, validate_serving_data
from roadsafe.domain import (
    CollisionPoint,
    CollisionSeverity,
    CollisionSummary,
    DataMetadata,
    NetworkSummary,
    RetrospectiveRecord,
)
from roadsafe.pipeline import SOURCE_URL, sha256_file
from roadsafe.segment_collisions import (
    CollisionAssignments,
    SegmentCollisions,
    derive_assignments,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "dft-collisions-west-yorkshire-2024.csv"
DATA_PATH = Path(os.environ.get("ROADSAFE_DATA_PATH", FIXTURE_PATH))
NETWORK_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "segment-evidence-west-yorkshire-2024.geojson"
NETWORK_PATH = Path(os.environ.get("ROADSAFE_NETWORK_PATH", NETWORK_FIXTURE_PATH))
EMPIRICAL_BAYES_PATH = os.environ.get("ROADSAFE_EMPIRICAL_BAYES_PATH")
BUNDLE_PATH = os.environ.get("ROADSAFE_BUNDLE_PATH")
BUNDLE = None
BUNDLE_SHA256 = None
if BUNDLE_PATH:
    if any(
        os.environ.get(name)
        for name in ("ROADSAFE_DATA_PATH", "ROADSAFE_NETWORK_PATH", "ROADSAFE_EMPIRICAL_BAYES_PATH")
    ):
        raise ValueError("Use ROADSAFE_BUNDLE_PATH or individual artifact paths, not both")
    bundle_root = Path(BUNDLE_PATH)
    BUNDLE_SHA256 = sha256_file(bundle_root / "bundle.json")
    BUNDLE = load_demo_bundle(bundle_root)
    if sha256_file(bundle_root / "bundle.json") != BUNDLE_SHA256:
        raise ValueError("Bundle manifest changed during startup")
    DATA_PATH = artifact_path(bundle_root, BUNDLE.collisions)
    NETWORK_PATH = artifact_path(bundle_root, BUNDLE.network)
    EMPIRICAL_BAYES_PATH = (
        str(artifact_path(bundle_root, BUNDLE.empirical_bayes)) if BUNDLE.empirical_bayes else None
    )

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
    expose_headers=["X-RoadSafe-Snapshot"],
)


@dataclass(frozen=True)
class ServingSnapshot:
    collisions: pl.DataFrame
    network: dict[str, Any]
    empirical_bayes: pl.DataFrame | None
    collision_sha256: str
    network_sha256: str
    empirical_bayes_sha256: str | None

    @cached_property
    def identity(self) -> str:
        sources = [
            __version__,
            self.collision_sha256,
            self.network_sha256,
            self.empirical_bayes_sha256,
        ]
        return sha256(json.dumps(sources, separators=(",", ":")).encode()).hexdigest()

    @cached_property
    def collision_assignments(self) -> CollisionAssignments:
        return derive_assignments(self.collisions, self.network)


@lru_cache
def serving_snapshot() -> ServingSnapshot:
    collision_bytes = DATA_PATH.read_bytes()
    network_bytes = NETWORK_PATH.read_bytes()
    eb_path = Path(EMPIRICAL_BAYES_PATH) if EMPIRICAL_BAYES_PATH else None
    eb_bytes = eb_path.read_bytes() if eb_path and eb_path.is_file() else None
    frame = (
        pl.read_parquet(BytesIO(collision_bytes))
        if DATA_PATH.suffix == ".parquet"
        else pl.read_csv(BytesIO(collision_bytes))
    )
    network = cast(dict[str, Any], json.loads(network_bytes))
    retrospective = pl.read_parquet(BytesIO(eb_bytes)) if eb_bytes is not None else None
    validate_serving_data(frame, network, retrospective)
    snapshot = ServingSnapshot(
        frame,
        network,
        retrospective,
        sha256(collision_bytes).hexdigest(),
        sha256(network_bytes).hexdigest(),
        sha256(eb_bytes).hexdigest() if eb_bytes is not None else None,
    )
    if BUNDLE is not None and (
        snapshot.collision_sha256 != BUNDLE.collisions.sha256
        or snapshot.network_sha256 != BUNDLE.network.sha256
        or snapshot.empirical_bayes_sha256
        != (BUNDLE.empirical_bayes.sha256 if BUNDLE.empirical_bayes else None)
    ):
        raise ValueError("Bundle checksum mismatch while loading serving snapshot")
    return snapshot


def collision_frame() -> pl.DataFrame:
    return serving_snapshot().collisions


def network_features() -> dict[str, Any]:
    return serving_snapshot().network


def empirical_bayes_frame() -> pl.DataFrame | None:
    return serving_snapshot().empirical_bayes


@app.middleware("http")
async def bind_snapshot_identity(request: Request, call_next: RequestResponseEndpoint) -> Response:
    snapshot = serving_snapshot() if request.url.path.startswith("/api/v1/") else None
    response = await call_next(request)
    if snapshot is not None and 200 <= response.status_code < 300:
        response.headers["X-RoadSafe-Snapshot"] = snapshot.identity
    return response


def to_point(row: dict[str, object]) -> CollisionPoint:
    return CollisionPoint.from_dft(row)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/api/v1/release")
def release() -> dict[str, Any]:
    if BUNDLE is None:
        return {"verified_bundle": False, "reason": "No demo bundle configured."}
    return {
        "verified_bundle": True,
        "bundle_sha256": BUNDLE_SHA256,
        "application_version": __version__,
        "bundle": BUNDLE.model_dump(),
    }


@app.get("/api/v1/metadata", response_model=DataMetadata)
@lru_cache
def metadata() -> DataMetadata:
    return DataMetadata(
        dataset="DfT STATS19 collision records",
        source=SOURCE_URL,
        source_year=2024,
        status="final validated data",
        licence="Open Government Licence v3.0",
        records=collision_frame().height,
        scope=(
            PROFILES[BUNDLE.profile][2]
            if BUNDLE
            else (
                "West Yorkshire 2024 pilot"
                if DATA_PATH.suffix == ".parquet"
                else "Traceable West Yorkshire fixture"
            )
        ),
        caveat="Police-reported personal-injury collisions only; not a measure of causal risk.",
        collision_sha256=serving_snapshot().collision_sha256,
        network_sha256=serving_snapshot().network_sha256,
        empirical_bayes_sha256=serving_snapshot().empirical_bayes_sha256,
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


@app.get("/api/v1/segments/{segment_key}/collisions", response_model=SegmentCollisions)
def segment_collisions(segment_key: str) -> SegmentCollisions:
    snapshot = serving_snapshot()
    properties = next(
        (
            feature["properties"]
            for feature in snapshot.network["features"]
            if feature["properties"]["segment_key"] == segment_key
        ),
        None,
    )
    if properties is None:
        raise HTTPException(status_code=404, detail="Unknown segment key")
    assignments = snapshot.collision_assignments
    return SegmentCollisions(
        segment_key=segment_key,
        source_year=properties["source_year"],
        available=assignments.reason is None,
        reason=assignments.reason,
        collisions=assignments.points.get(segment_key, []),
        collision_sha256=snapshot.collision_sha256,
        network_sha256=snapshot.network_sha256,
    )


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


@app.get("/api/v1/empirical-bayes")
def empirical_bayes(year: int = Query(default=2024, ge=2000, le=2_100)) -> dict[str, Any]:
    if BUNDLE is not None and year != BUNDLE.year:
        return {"available": False, "reason": "Year is outside this serving bundle's scope."}
    frame = empirical_bayes_frame()
    if frame is None:
        return {
            "available": False,
            "reason": "Empirical Bayes artifact is not configured for this server.",
        }
    if "year" not in frame.columns:
        return {"available": False, "reason": "Empirical Bayes artifact has no year column."}
    records = [
        RetrospectiveRecord.model_validate(row).model_dump()
        for row in frame.filter(pl.col("year") == year).to_dicts()
    ]
    return {
        "available": True,
        "year": year,
        "method": "Poisson-gamma Empirical Bayes retrospective frequency screening",
        "not_future_prediction": True,
        "records": records,
    }


# Freeze data and provenance together for bundle and legacy configurations alike.
serving_snapshot()
metadata()
if BUNDLE is not None and BUNDLE_PATH:
    for artifact in (BUNDLE.collisions, BUNDLE.network, BUNDLE.empirical_bayes):
        if artifact:
            artifact_path(Path(BUNDLE_PATH), artifact)
    if sha256_file(Path(BUNDLE_PATH) / "bundle.json") != BUNDLE_SHA256:
        raise ValueError("Bundle manifest changed while loading serving data")
