import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from roadsafe.bundle import build_demo_bundle, load_demo_bundle
from roadsafe.pipeline import sha256_file

FIXTURES = Path(__file__).parent / "fixtures"
COLLISIONS = FIXTURES / "dft-collisions-west-yorkshire-2024.csv"
NETWORK = FIXTURES / "segment-evidence-west-yorkshire-2024.geojson"


def retrospective_rows() -> list[dict[str, Any]]:
    rows = []
    for feature in json.loads(NETWORK.read_text())["features"]:
        props = feature["properties"]
        expected = (1 + props["ksi_count"]) / 2
        rows.append(
            {
                "segment_key": props["segment_key"],
                "year": 2024,
                "ksi_count": props["ksi_count"],
                "prior_expected_ksi": 1.0,
                "expected_ksi": expected,
                "expected_ksi_std": math.sqrt(expected + expected**2),
                "excess_ksi": max(props["ksi_count"] - expected, 0.0),
            }
        )
    return rows


def test_portable_bundle_and_deterministic_manifest(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    bundle = build_demo_bundle(COLLISIONS, NETWORK, first, "fixture")
    build_demo_bundle(COLLISIONS, NETWORK, second, "fixture")
    assert (first / "bundle.json").read_bytes() == (second / "bundle.json").read_bytes()
    moved = tmp_path / "moved"
    first.rename(moved)
    assert load_demo_bundle(moved) == bundle
    assert bundle.records == 12 and bundle.segments == 6
    assert bundle.collisions.sha256 == sha256_file(COLLISIONS)
    assert bundle.not_future_prediction and not bundle.model_promoted


def test_refuses_existing_output_and_wrong_profile(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    build_demo_bundle(COLLISIONS, NETWORK, output, "fixture")
    with pytest.raises(FileExistsError):
        build_demo_bundle(COLLISIONS, NETWORK, output, "fixture")
    with pytest.raises(ValueError, match="counts"):
        build_demo_bundle(COLLISIONS, NETWORK, tmp_path / "pilot", "pilot")
    assert not (tmp_path / "pilot").exists()


@pytest.mark.parametrize("change", ["bytes", "path", "records", "promotion", "missing"])
def test_rejects_changed_bundle(tmp_path: Path, change: str) -> None:
    output = tmp_path / "bundle"
    bundle = build_demo_bundle(COLLISIONS, NETWORK, output, "fixture")
    path = output / "bundle.json"
    manifest = json.loads(path.read_text())
    if change == "bytes":
        (output / bundle.collisions.filename).write_text("changed")
    elif change == "missing":
        (output / bundle.network.filename).unlink()
    elif change == "path":
        manifest["collisions"]["filename"] = "../outside.csv"
    elif change == "records":
        manifest["records"] = 13
    else:
        manifest["model_promoted"] = True
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        load_demo_bundle(output)


@pytest.mark.parametrize("change", ["year", "duplicate", "properties", "counts"])
def test_rejects_mismatched_network(tmp_path: Path, change: str) -> None:
    content = json.loads(NETWORK.read_text())
    props = content["features"][0]["properties"]
    if change == "year":
        props["source_year"] = 2023
    elif change == "duplicate":
        props["segment_key"] = content["features"][1]["properties"]["segment_key"]
    elif change == "properties":
        content["features"][0]["properties"] = None
    else:
        props["ksi_count"] = -1
    network = tmp_path / "network.geojson"
    network.write_text(json.dumps(content))
    with pytest.raises(ValueError):
        build_demo_bundle(COLLISIONS, network, tmp_path / "output", "fixture")
    assert not (tmp_path / "output").exists()


def test_retrospective_identity_and_counts_are_checked(tmp_path: Path) -> None:
    rows = retrospective_rows()
    retrospective = tmp_path / "retrospective.parquet"
    pl.DataFrame(rows).write_parquet(retrospective)
    output = tmp_path / "valid"
    build_demo_bundle(COLLISIONS, NETWORK, output, "fixture", retrospective)
    assert load_demo_bundle(output).empirical_bayes is not None
    rows[0]["ksi_count"] = 999
    rows[0]["expected_ksi"] = 500.0
    rows[0]["expected_ksi_std"] = math.sqrt(500.0 + 500.0**2)
    rows[0]["excess_ksi"] = 499.0
    pl.DataFrame(rows).write_parquet(retrospective)
    with pytest.raises(ValueError, match="observed counts do not match the network"):
        build_demo_bundle(COLLISIONS, NETWORK, tmp_path / "bad", "fixture", retrospective)


def test_changed_source_does_not_publish_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copy = shutil.copyfile

    def corrupt_copy(source: Path, destination: Path) -> None:
        copy(source, destination)
        destination.write_bytes(b"changed")

    monkeypatch.setattr("roadsafe.bundle.shutil.copyfile", corrupt_copy)
    output = tmp_path / "bundle"
    with pytest.raises(ValueError, match="changed"):
        build_demo_bundle(COLLISIONS, NETWORK, output, "fixture")
    assert not (output / "bundle.json").exists()


def test_api_loads_bundle_and_refuses_mixed_configuration(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    build_demo_bundle(COLLISIONS, NETWORK, output, "fixture")
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("ROADSAFE_")
    }
    environment["ROADSAFE_BUNDLE_PATH"] = str(output)
    code = (
        "from fastapi.testclient import TestClient; from roadsafe.api.app import app; "
        "c=TestClient(app); print(c.get('/api/v1/release').json()['verified_bundle']); "
        "print(c.get('/api/v1/metadata').json()['scope'])"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert result.stdout.splitlines() == ["True", "Traceable West Yorkshire fixture"]
    environment["ROADSAFE_DATA_PATH"] = str(COLLISIONS)
    rejected = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert rejected.returncode != 0 and "not both" in rejected.stderr


def test_api_freezes_served_data_with_verified_provenance(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    bundle = build_demo_bundle(COLLISIONS, NETWORK, output, "fixture")
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("ROADSAFE_")
    }
    environment["ROADSAFE_BUNDLE_PATH"] = str(output)
    code = (
        "from fastapi.testclient import TestClient; from roadsafe.api.app import app; "
        "from pathlib import Path; import os; c=TestClient(app); "
        "before=c.get('/api/v1/release').json(); "
        "root=Path(os.environ['ROADSAFE_BUNDLE_PATH']); "
        "(root/'collisions.csv').write_text('changed'); "
        "(root/'bundle.json').write_text('{}'); "
        "assert c.get('/api/v1/release').json()==before; "
        "assert c.get('/api/v1/summary').json()['collisions']==12; "
        "print(c.get('/api/v1/metadata').json()['collision_sha256'])"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert result.stdout.strip() == bundle.collisions.sha256
    with pytest.raises(ValueError):
        load_demo_bundle(output)


@pytest.mark.parametrize(
    "change",
    [
        "spf",
        "missing_std",
        "nan",
        "infinity",
        "negative",
        "excess",
        "shrinkage",
        "std",
    ],
)
def test_rejects_non_eb_retrospective_artifacts(tmp_path: Path, change: str) -> None:
    rows = retrospective_rows()
    if change == "spf":
        for row in rows:
            del row["prior_expected_ksi"]
            del row["excess_ksi"]
            row["expected_ksi_lower_95"] = 0.0
            row["expected_ksi_upper_95"] = 5.0
    elif change == "missing_std":
        for row in rows:
            del row["expected_ksi_std"]
    else:
        field, value = {
            "nan": ("expected_ksi", float("nan")),
            "infinity": ("expected_ksi_std", float("inf")),
            "negative": ("prior_expected_ksi", -1.0),
            "excess": ("excess_ksi", 999.0),
            "shrinkage": ("expected_ksi", 100.0),
            "std": ("expected_ksi_std", 0.0),
        }[change]
        rows[0][field] = value
    retrospective = tmp_path / "retrospective.parquet"
    pl.DataFrame(rows).write_parquet(retrospective)
    with pytest.raises(ValueError):
        build_demo_bundle(COLLISIONS, NETWORK, tmp_path / "bundle", "fixture", retrospective)
    assert not (tmp_path / "bundle" / "bundle.json").exists()


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("collision_severity", 99),
        ("collision_severity", None),
        ("longitude", 200.0),
        ("latitude", float("nan")),
        ("number_of_vehicles", 0),
        ("number_of_casualties", None),
        ("speed_limit", "invalid"),
    ],
)
def test_rejects_unservable_collisions(tmp_path: Path, column: str, value: Any) -> None:
    collisions = tmp_path / "collisions.parquet"
    pl.read_csv(COLLISIONS).with_columns(pl.lit(value).alias(column)).write_parquet(collisions)
    with pytest.raises(ValueError):
        build_demo_bundle(collisions, NETWORK, tmp_path / "bundle", "fixture")


@pytest.mark.parametrize(
    "change",
    [
        "missing_exposure",
        "null_exposure",
        "method",
        "road",
        "rate",
        "geometry",
        "forecast",
        "string_coordinates",
        "extra_nan",
    ],
)
def test_rejects_unservable_network(tmp_path: Path, change: str) -> None:
    content = json.loads(NETWORK.read_text())
    feature = content["features"][0]
    props = feature["properties"]
    if change == "missing_exposure":
        del props["all_motor_vehicles"]
    elif change == "null_exposure":
        props["all_motor_vehicles"] = None
    elif change == "method":
        props["estimation_method"] = "Unknown"
    elif change == "road":
        props["road_number"] = None
    elif change == "rate":
        props["collision_rate_per_100m_vehicle_km"] = float("inf")
    elif change == "geometry":
        feature["geometry"] = {"type": "LineString", "coordinates": [[0, 0]]}
    elif change == "string_coordinates":
        feature["geometry"]["coordinates"][0][0] = "-1.5"
    elif change == "extra_nan":
        props["geometry_length_km"] = float("nan")
    else:
        props["expected_ksi"] = 2.5
    network = tmp_path / "network.geojson"
    network.write_text(json.dumps(content))
    with pytest.raises(ValueError):
        build_demo_bundle(COLLISIONS, network, tmp_path / "bundle", "fixture")


@pytest.mark.parametrize("first_request", [None, "/api/v1/collisions", "/api/v1/metadata"])
def test_legacy_snapshot_binds_all_hashes_at_startup(
    tmp_path: Path, first_request: str | None
) -> None:
    collisions = tmp_path / "collisions.csv"
    network = tmp_path / "network.geojson"
    retrospective = tmp_path / "retrospective.parquet"
    shutil.copyfile(COLLISIONS, collisions)
    shutil.copyfile(NETWORK, network)
    pl.DataFrame(retrospective_rows()).write_parquet(retrospective)
    expected_hashes = [sha256_file(p) for p in (collisions, network, retrospective)]
    environment = {k: v for k, v in os.environ.items() if not k.startswith("ROADSAFE_")}
    environment.update(
        ROADSAFE_DATA_PATH=str(collisions),
        ROADSAFE_NETWORK_PATH=str(network),
        ROADSAFE_EMPIRICAL_BAYES_PATH=str(retrospective),
    )
    code = f"""
from fastapi.testclient import TestClient
from roadsafe.api.app import app
from pathlib import Path
import os
c = TestClient(app)
first = {first_request!r}
if first:
    assert c.get(first).status_code == 200
for name in ('ROADSAFE_DATA_PATH', 'ROADSAFE_NETWORK_PATH', 'ROADSAFE_EMPIRICAL_BAYES_PATH'):
    Path(os.environ[name]).unlink()
metadata = c.get('/api/v1/metadata').json()
hashes = [metadata[k] for k in ('collision_sha256', 'network_sha256', 'empirical_bayes_sha256')]
assert hashes == {expected_hashes!r}
assert c.get('/api/v1/summary').json()['collisions'] == 12
assert len(c.get('/api/v1/segments').json()['features']) == 6
assert len(c.get('/api/v1/empirical-bayes').json()['records']) == 6
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_legacy_rejects_spf_and_projects_only_eb_fields(tmp_path: Path) -> None:
    retrospective = tmp_path / "retrospective.parquet"
    rows = retrospective_rows()
    for row in rows:
        row["experimental_future_prediction"] = 99.0
    pl.DataFrame(rows).write_parquet(retrospective)
    environment = {k: v for k, v in os.environ.items() if not k.startswith("ROADSAFE_")}
    environment["ROADSAFE_EMPIRICAL_BAYES_PATH"] = str(retrospective)
    code = """
from fastapi.testclient import TestClient
from roadsafe.api.app import app
record = TestClient(app).get('/api/v1/empirical-bayes').json()['records'][0]
assert set(record) == {'segment_key', 'year', 'ksi_count', 'prior_expected_ksi',
                       'expected_ksi', 'expected_ksi_std', 'excess_ksi'}
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    for row in rows:
        del row["prior_expected_ksi"]
        del row["excess_ksi"]
    pl.DataFrame(rows).write_parquet(retrospective)
    rejected = subprocess.run(
        [sys.executable, "-c", "import roadsafe.api.app"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert rejected.returncode != 0
