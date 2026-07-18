from fastapi.testclient import TestClient

from roadsafe.api.app import app

client = TestClient(app)


def test_health_exposes_version() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.2.0"}


def test_summary_matches_fixture() -> None:
    response = client.get("/api/v1/summary")
    assert response.status_code == 200
    assert response.json() == {
        "collisions": 12,
        "killed_or_seriously_injured": 3,
        "casualties": 17,
        "fatal": 0,
        "serious": 3,
        "slight": 9,
    }


def test_collision_filter_uses_dft_severity_codes() -> None:
    response = client.get("/api/v1/collisions", params={"severity": 2})
    assert response.status_code == 200
    points = response.json()
    assert len(points) == 3
    assert {point["severity_label"] for point in points} == {"Serious"}


def test_metadata_discloses_scope_and_caveat() -> None:
    response = client.get("/api/v1/metadata")
    assert response.status_code == 200
    assert response.json()["records"] == 12
    assert "not a measure of causal risk" in response.json()["caveat"]


def test_segments_expose_traffic_method_and_geometry() -> None:
    response = client.get("/api/v1/segments")
    assert response.status_code == 200
    features = response.json()["features"]
    assert len(features) == 6
    assert {feature["geometry"]["type"] for feature in features} == {"LineString"}
    assert {feature["properties"]["estimation_method"] for feature in features} == {
        "Counted",
        "Estimated",
    }


def test_network_summary_keeps_exposure_scope_explicit() -> None:
    response = client.get("/api/v1/network-summary")
    assert response.status_code == 200
    assert response.json() == {
        "segments": 6,
        "segments_with_exposure": 6,
        "counted_exposure": 1,
        "estimated_exposure": 5,
        "matched_collisions": 2,
        "matched_ksi": 1,
        "scope": "DfT major-road links only",
        "caveat": "AADF link estimates are descriptive exposure, not expected collision risk.",
    }
