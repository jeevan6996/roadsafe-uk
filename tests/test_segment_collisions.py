import copy
from dataclasses import replace
from typing import Any

import polars as pl
import pytest
from fastapi.testclient import TestClient

import roadsafe.api.app as api
from roadsafe.network import TO_WGS84


@pytest.fixture
def snapshot(monkeypatch: pytest.MonkeyPatch) -> api.ServingSnapshot:
    original = api.serving_snapshot()
    template = original.collisions.row(0, named=True)
    rows = []
    # Parallel roads 20m apart: the midpoint is ambiguous; the remote point is excluded.
    for identity, x, y, severity in [
        ("accepted", 430000, 430000, 2),
        ("ambiguous", 430010, 430000, 1),
        ("remote", 431000, 430000, 3),
    ]:
        lon, lat = TO_WGS84.transform(x, y)
        rows.append(
            dict(
                template,
                collision_index=identity,
                longitude=lon,
                latitude=lat,
                collision_severity=severity,
            )
        )
    features = []
    for i, x in enumerate([430000, 430020, 432000]):
        feature = copy.deepcopy(original.network["features"][0])
        feature["properties"].update(
            segment_key=f"road-{i}",
            segment_id=f"id-{i}",
            count_point_id=i + 1,
            collision_count=int(i == 0),
            ksi_count=int(i == 0),
        )
        props = feature["properties"]
        props["collision_rate_per_100m_vehicle_km"] = (
            props["collision_count"]
            / (props["all_motor_vehicles"] * 365 * props["link_length_km"])
            * 100_000_000
        )
        feature["geometry"]["coordinates"] = [
            list(TO_WGS84.transform(x, y)) for y in [429900, 430100]
        ]
        features.append(feature)
    frozen = replace(
        original,
        collisions=pl.DataFrame(rows),
        network={"type": "FeatureCollection", "features": features},
        collision_sha256="a" * 64,
        network_sha256="b" * 64,
    )
    monkeypatch.setattr(api, "serving_snapshot", lambda: frozen)
    return frozen


def get(key: str) -> dict[str, Any]:
    response = TestClient(api.app).get(f"/api/v1/segments/{key}/collisions")
    assert response.status_code == 200
    return response.json()  # type: ignore[no-any-return]


def test_only_accepted_points_with_source_identity(snapshot: api.ServingSnapshot) -> None:
    result = get("road-0")
    assert result["available"] is True
    assert result["reason"] is None
    assert result["segment_key"] == "road-0"
    assert result["source_year"] == 2024
    assert [point["collision_id"] for point in result["collisions"]] == ["accepted"]
    assert result["collisions"][0]["severity"] == 2
    raw = snapshot.collisions.row(0, named=True)
    assert result["collisions"][0]["longitude"] == raw["longitude"]
    assert result["collisions"][0]["latitude"] == raw["latitude"]
    assert result["collision_sha256"] == "a" * 64
    assert result["network_sha256"] == "b" * 64
    assert result["matching"]["max_distance_m"] == 50.0
    assert result["matching"]["ambiguity_margin_m"] == 10.0
    assert result["matching"]["method"]


def test_zero_count_roads_are_available_and_empty(snapshot: api.ServingSnapshot) -> None:
    for key in ["road-1", "road-2"]:
        result = get(key)
        assert result["available"] is True
        assert result["collisions"] == []


def test_unknown_segment_is_404(snapshot: api.ServingSnapshot) -> None:
    assert TestClient(api.app).get("/api/v1/segments/missing/collisions").status_code == 404


@pytest.mark.parametrize(
    "field,value",
    [
        ("collision_count", 2),
        ("ksi_count", 0),
        ("source_year", 2023),
        ("segment_id", "id-1"),
        ("count_point_id", 2),
        ("segment_key", "road-1"),
    ],
)
def test_inconsistent_network_fails_closed(
    snapshot: api.ServingSnapshot,
    field: str,
    value: object,
) -> None:
    snapshot.network["features"][0]["properties"][field] = value
    if field == "collision_count":
        props = snapshot.network["features"][0]["properties"]
        props["collision_rate_per_100m_vehicle_km"] = (
            props["collision_count"]
            / (props["all_motor_vehicles"] * 365 * props["link_length_km"])
            * 100_000_000
        )
    result = get("road-1")
    assert result["available"] is False
    assert result["reason"]
    assert result["collisions"] == []


def test_unsupported_geometry_fails_closed(snapshot: api.ServingSnapshot) -> None:
    snapshot.network["features"][0]["geometry"] = {"type": "Point", "coordinates": [0, 0]}
    assert get("road-1")["available"] is False


@pytest.mark.parametrize("network_hash", ["b" * 64, "c" * 64])
def test_cache_is_snapshot_local(
    snapshot: api.ServingSnapshot,
    monkeypatch: pytest.MonkeyPatch,
    network_hash: str,
) -> None:
    assert get("road-0")["available"] is True
    network = copy.deepcopy(snapshot.network)
    network["features"][0]["properties"]["collision_count"] = 2
    props = network["features"][0]["properties"]
    props["collision_rate_per_100m_vehicle_km"] = (
        props["collision_count"]
        / (props["all_motor_vehicles"] * 365 * props["link_length_km"])
        * 100_000_000
    )
    updated = replace(snapshot, network=network, network_sha256=network_hash)
    monkeypatch.setattr(api, "serving_snapshot", lambda: updated)
    result = get("road-0")
    assert result["available"] is False
    assert "Canonical-geometry assignments" in result["reason"]
    assert result["network_sha256"] == network_hash


@pytest.mark.parametrize(
    "column,values",
    [
        ("collision_index", ["duplicate", "duplicate", "remote"]),
        ("collision_year", [2023, 2024, 2024]),
    ],
)
def test_invalid_collision_identity_or_year_fails_closed(
    snapshot: api.ServingSnapshot,
    monkeypatch: pytest.MonkeyPatch,
    column: str,
    values: list[Any],
) -> None:
    frame = snapshot.collisions.with_columns(pl.Series(column, values))
    monkeypatch.setattr(api, "serving_snapshot", lambda: replace(snapshot, collisions=frame))
    result = get("road-0")
    assert result["available"] is False
    assert result["collisions"] == []
    assert result["reason"]


def test_fixture_counts_agree_for_every_road() -> None:
    for feature in api.serving_snapshot().network["features"]:
        props = feature["properties"]
        result = get(props["segment_key"])
        assert result["available"] is True
        assert len(result["collisions"]) == props["collision_count"]
        assert sum(p["severity"] in [1, 2] for p in result["collisions"]) == props["ksi_count"]
