"""Portable, validated serving artifacts for the bounded 2024 demonstration."""

import json
import math
import shutil
from pathlib import Path
from typing import Any, Literal

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from roadsafe.domain import CollisionPoint, NetworkFeature, NetworkProperties, RetrospectiveRecord
from roadsafe.network import RATE_SCALE
from roadsafe.pipeline import REQUIRED_COLUMNS, sha256_file

Profile = Literal["fixture", "pilot"]
PROFILES: dict[Profile, tuple[int, int, str]] = {
    "fixture": (12, 6, "Traceable West Yorkshire fixture"),
    "pilot": (1791, 256, "West Yorkshire 2024 pilot"),
}


class Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DemoBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    profile: Profile
    year: Literal[2024] = 2024
    records: int = Field(gt=0)
    segments: int = Field(gt=0)
    collisions: Artifact
    network: Artifact
    empirical_bayes: Artifact | None = None
    not_future_prediction: Literal[True] = True
    model_promoted: Literal[False] = False
    attribution: Literal["Contains DfT information under Open Government Licence v3.0"] = (
        "Contains DfT information under Open Government Licence v3.0"
    )


def artifact_path(root: Path, artifact: Artifact) -> Path:
    if Path(artifact.filename).name != artifact.filename:
        raise ValueError("Bundle artifacts must use plain filenames")
    path = (root / artifact.filename).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Bundle artifact is missing or outside the bundle")
    if sha256_file(path) != artifact.sha256:
        raise ValueError(f"Bundle checksum mismatch: {artifact.filename}")
    return path


def inspect_artifacts(
    collisions: Path, network: Path, empirical_bayes: Path | None, profile: Profile
) -> tuple[int, int]:
    frame = (
        pl.read_parquet(collisions) if collisions.suffix == ".parquet" else pl.read_csv(collisions)
    )
    collection: Any = json.loads(network.read_text(encoding="utf-8"))
    retrospective = pl.read_parquet(empirical_bayes) if empirical_bayes is not None else None
    records, segments = validate_serving_data(frame, collection, retrospective)
    expected_records, expected_segments, _ = PROFILES[profile]
    if (records, segments) != (expected_records, expected_segments):
        raise ValueError(f"Artifact counts do not match the declared {profile} demo profile")
    return records, segments


def _validate_network_exposure(properties: NetworkProperties, source: dict[str, Any]) -> None:
    try:
        # Preserve the producer's 365-day convention and four-decimal fixture rates.
        exposure = properties.all_motor_vehicles * 365 * properties.link_length_km
        if not math.isfinite(exposure) or exposure <= 0:
            raise ValueError("Network exposure must be finite and positive")
        if "annual_vehicle_km" in source:
            declared = source["annual_vehicle_km"]
            if (
                type(declared) not in (int, float)
                or not math.isfinite(declared)
                or not math.isclose(declared, exposure, rel_tol=1e-12, abs_tol=0)
            ):
                raise ValueError("Network annual vehicle-km differs from its exposure inputs")
        rate = properties.collision_count / exposure * RATE_SCALE
        if not math.isfinite(rate) or not math.isclose(
            properties.collision_rate_per_100m_vehicle_km,
            rate,
            rel_tol=1e-12,
            abs_tol=0.00005 + math.ulp(rate),
        ):
            raise ValueError("Network collision rate differs from its count and exposure")
    except (OverflowError, ZeroDivisionError) as error:
        raise ValueError("Network exposure and rate must be finite") from error


def validate_serving_data(
    frame: pl.DataFrame, collection: Any, retrospective: pl.DataFrame | None
) -> tuple[int, int]:
    if not REQUIRED_COLUMNS.issubset(frame.columns):
        raise ValueError("Collision artifact is missing required columns")
    if frame["collision_year"].unique().to_list() != [2024]:
        raise ValueError("The demo requires 2024 collisions")
    if frame["collision_index"].null_count() or frame["collision_index"].n_unique() != frame.height:
        raise ValueError("Collision identities must be non-null and unique")
    if any(frame[column].null_count() for column in REQUIRED_COLUMNS):
        raise ValueError("Collision serving fields must not be null")
    for column in (
        "collision_severity",
        "number_of_vehicles",
        "number_of_casualties",
        "speed_limit",
    ):
        if not frame.schema[column].is_integer():
            raise ValueError(f"Collision {column} must contain integers")
    for row in frame.to_dicts():
        CollisionPoint.from_dft(row)
    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        raise ValueError("Network artifact must be a GeoJSON FeatureCollection")
    # Extra source properties are served unchanged, so they must also be JSON-safe.
    json.dumps(collection, allow_nan=False)
    features = collection.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("Network artifact has no features")
    keys: list[str] = []
    observed: dict[str, int] = {}
    matched_collisions = 0
    matched_ksi = 0
    for feature in features:
        if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
            raise ValueError("Network features must contain a properties object")
        props = feature["properties"]
        properties = NetworkFeature.model_validate(feature).properties
        if {
            "expected_ksi",
            "expected_ksi_std",
            "prior_expected_ksi",
            "excess_ksi",
            "expected_ksi_lower_95",
            "expected_ksi_upper_95",
        }.intersection(props):
            raise ValueError("Network must contain observed evidence, not model predictions")
        key = props.get("segment_key")
        if not isinstance(key, str) or not key or props.get("source_year") != 2024:
            raise ValueError("Network requires stable identities and the 2024 source year")
        keys.append(key)
        ksi = props.get("ksi_count")
        count = props.get("collision_count")
        if type(ksi) is not int or type(count) is not int or not 0 <= ksi <= count:
            raise ValueError("Network observed counts must be nonnegative integers")
        _validate_network_exposure(properties, props)
        observed[key] = ksi
        matched_collisions += count
        matched_ksi += ksi
    if len(set(keys)) != len(keys):
        raise ValueError("Network identities must be unique")
    source_ksi = int(frame["collision_severity"].is_in([1, 2]).sum())
    if matched_collisions > frame.height:
        raise ValueError("Matched network counts exceed source collisions")
    if matched_ksi > source_ksi:
        raise ValueError("Matched network counts exceed source KSI collisions")
    if matched_collisions - matched_ksi > frame.height - source_ksi:
        raise ValueError("Matched network counts exceed source non-KSI collisions")
    if retrospective is not None:
        if not {"year", "segment_key", "ksi_count"}.issubset(retrospective.columns):
            raise ValueError("Retrospective artifact is missing identity, year or observed counts")
        for row in retrospective.to_dicts():
            RetrospectiveRecord.model_validate(row)
        rows = retrospective.filter(pl.col("year") == 2024)
        if rows.height != len(keys) or rows["segment_key"].n_unique() != rows.height:
            raise ValueError("Retrospective evidence must cover each 2024 segment exactly once")
        if set(rows["segment_key"].to_list()) != set(keys):
            raise ValueError("Retrospective segment identities do not match the network")
        for row in rows.select("segment_key", "ksi_count").to_dicts():
            if row["ksi_count"] != observed[row["segment_key"]]:
                raise ValueError("Retrospective observed counts do not match the network")
    return frame.height, len(keys)


def load_demo_bundle(root: Path) -> DemoBundle:
    bundle = DemoBundle.model_validate_json((root / "bundle.json").read_text(encoding="utf-8"))
    records, segments = inspect_artifacts(
        artifact_path(root, bundle.collisions),
        artifact_path(root, bundle.network),
        artifact_path(root, bundle.empirical_bayes) if bundle.empirical_bayes else None,
        bundle.profile,
    )
    if (records, segments) != (bundle.records, bundle.segments):
        raise ValueError("Bundle declared counts differ from its artifacts")
    return bundle


def build_demo_bundle(
    collisions: Path,
    network: Path,
    output: Path,
    profile: Profile,
    empirical_bayes: Path | None = None,
) -> DemoBundle:
    if collisions.suffix not in {".csv", ".parquet"}:
        raise ValueError("Collision artifact must be CSV or Parquet")
    records, segments = inspect_artifacts(collisions, network, empirical_bayes, profile)
    sources = {"collisions": collisions, "network": network}
    if empirical_bayes is not None:
        sources["empirical_bayes"] = empirical_bayes
    hashes = {name: sha256_file(path) for name, path in sources.items()}
    output.mkdir(parents=True, exist_ok=False)
    artifacts: dict[str, Artifact] = {}
    for name, path in sources.items():
        filename = f"{name}{path.suffix}"
        destination = output / filename
        shutil.copyfile(path, destination)
        if sha256_file(destination) != hashes[name] or sha256_file(path) != hashes[name]:
            raise ValueError("Source artifact changed while building the bundle")
        artifacts[name] = Artifact(filename=filename, sha256=hashes[name])
    bundle = DemoBundle(
        profile=profile,
        records=records,
        segments=segments,
        collisions=artifacts["collisions"],
        network=artifacts["network"],
        empirical_bayes=artifacts.get("empirical_bayes"),
    )
    inspect_artifacts(
        output / bundle.collisions.filename,
        output / bundle.network.filename,
        output / bundle.empirical_bayes.filename if bundle.empirical_bayes else None,
        profile,
    )
    # Publish the completion manifest only after the copied artifacts validate.
    (output / "bundle.json").write_text(bundle.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return bundle
