import json
from pathlib import Path

import polars as pl
import pytest
from pyproj import Transformer
from shapely.geometry import LineString

from roadsafe.network import (
    NetworkValidationError,
    RoadSegment,
    build_network_evidence,
    match_collisions,
    read_aadf,
    read_road_segments,
)
from roadsafe.pipeline import read_collisions

FIXTURES = Path(__file__).parent / "fixtures"
COLLISIONS = FIXTURES / "dft-collisions-west-yorkshire-2024.csv"
ROADS = FIXTURES / "dft-major-roads-west-yorkshire-2024.geojson"
AADF = FIXTURES / "dft-aadf-west-yorkshire-2024.csv"


def test_collision_matching_rejects_distant_events() -> None:
    collisions = read_collisions(COLLISIONS)
    segments = read_road_segments(ROADS)

    matches = match_collisions(collisions, segments)
    status_counts = {
        row["match_status"]: row["len"] for row in matches.group_by("match_status").len().to_dicts()
    }

    assert status_counts == {"accepted": 2, "out_of_range": 10}
    assert matches.filter(pl.col("match_status") == "accepted")["distance_m"].max() < 25


def test_aadf_links_exactly_to_count_point_ids() -> None:
    segments = read_road_segments(ROADS)
    aadf = read_aadf(AADF, {segment.count_point_id for segment in segments})

    assert aadf.height == 6
    assert aadf.filter(pl.col("estimation_method") == "Counted").height == 1
    assert aadf["all_motor_vehicles"].min() == 7877


def test_build_network_writes_evidence_and_diagnostics(tmp_path: Path) -> None:
    report = build_network_evidence(COLLISIONS, ROADS, AADF, tmp_path)

    assert report["road_segments"] == 6
    assert report["segments_with_exposure"] == 6
    assert report["accepted_match_rate"] == 0.1667
    assert report["match_status_counts"] == {"accepted": 2, "out_of_range": 10}
    assert report["road_source_sha256"][ROADS.name]
    assert report["exposure_source_sha256"]
    assert (tmp_path / "collision-segment-matches-2024.parquet").exists()
    assert (tmp_path / "segment-evidence-2024.parquet").exists()
    geojson = json.loads((tmp_path / "segment-evidence-2024.geojson").read_text())
    assert len(geojson["features"]) == 6
    assert sum(feature["properties"]["collision_count"] for feature in geojson["features"]) == 2


def test_matching_marks_near_equal_candidates_ambiguous() -> None:
    collision = pl.DataFrame(
        {"collision_index": ["test"], "longitude": [-1.73], "latitude": [53.8]}
    )
    x, y = Transformer.from_crs(4326, 27700, always_xy=True).transform(-1.73, 53.8)
    line = LineString([(x - 100, y), (x + 100, y)])
    segments = [RoadSegment(f"segment-{index}", index, "A1", 2024, line, line) for index in (1, 2)]

    match = match_collisions(collision, segments).row(0, named=True)

    assert match["match_status"] == "ambiguous"
    assert match["segment_id"] is None
    assert match["candidate_count"] == 2


def test_aadf_rejects_missing_contract_columns(tmp_path: Path) -> None:
    invalid = tmp_path / "aadf.csv"
    pl.DataFrame({"count_point_id": [1], "year": [2024]}).write_csv(invalid)

    with pytest.raises(NetworkValidationError, match="Missing AADF columns"):
        read_aadf(invalid, {1})
