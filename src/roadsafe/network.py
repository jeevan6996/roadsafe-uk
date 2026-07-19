from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import polars as pl
import shapefile  # type: ignore[import-untyped]
from pyproj import Transformer
from shapely.geometry import LineString, Point, box, mapping, shape
from shapely.ops import transform
from shapely.strtree import STRtree

from roadsafe.pipeline import PILOT_BOUNDS, read_collisions, sha256_file

MRDB_URL_TEMPLATE = "https://storage.googleapis.com/dft-statistics/road-traffic/mrdb-{year}.zip"
AADF_URL = (
    "https://storage.googleapis.com/dft-statistics/road-traffic/downloads/"
    "data-gov-uk/dft_traffic_counts_aadf.zip"
)
MAX_MATCH_DISTANCE_METRES = 50.0
AMBIGUITY_MARGIN_METRES = 10.0
RATE_SCALE = 100_000_000
AADF_REQUIRED_COLUMNS = {
    "count_point_id",
    "year",
    "region_id",
    "region_name",
    "region_ons_code",
    "local_authority_id",
    "local_authority_name",
    "local_authority_code",
    "road_name",
    "road_category",
    "road_type",
    "estimation_method",
    "estimation_method_detailed",
    "all_motor_vehicles",
    "cars_and_taxis",
    "LGVs",
    "all_HGVs",
    "link_length_km",
}

TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
TO_WGS84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)


class NetworkValidationError(ValueError):
    """Raised when road-network or exposure data violates its contract."""


@dataclass(frozen=True)
class RoadSegment:
    segment_id: str
    count_point_id: int
    road_number: str
    source_year: int
    geometry_bng: LineString
    geometry_wgs84: LineString


def _segment_from_wgs84(feature: dict[str, Any]) -> RoadSegment:
    properties = feature["properties"]
    geometry_wgs84 = cast(LineString, shape(feature["geometry"]))
    geometry_bng = transform(TO_BNG.transform, geometry_wgs84)
    return RoadSegment(
        segment_id=str(properties["segment_id"]),
        count_point_id=int(properties["count_point_id"]),
        road_number=str(properties["road_number"]),
        source_year=int(properties["source_year"]),
        geometry_bng=geometry_bng,
        geometry_wgs84=geometry_wgs84,
    )


def read_road_segments(path: Path, source_year: int = 2024) -> list[RoadSegment]:
    if path.suffix.lower() in {".geojson", ".json"}:
        payload = json.loads(path.read_text(encoding="utf-8"))
        segments = [_segment_from_wgs84(feature) for feature in payload["features"]]
    elif path.suffix.lower() == ".shp":
        reader = shapefile.Reader(str(path))
        fields = [field[0] for field in reader.fields[1:]]
        if not {"CP_Number", "RoadNumber"}.issubset(fields):
            raise NetworkValidationError("Major Roads Database fields are missing")
        segments = []
        pilot_area = box(
            PILOT_BOUNDS["min_longitude"],
            PILOT_BOUNDS["min_latitude"],
            PILOT_BOUNDS["max_longitude"],
            PILOT_BOUNDS["max_latitude"],
        )
        for item in reader.iterShapeRecords():
            properties = dict(zip(fields, item.record, strict=True))
            geometry_bng = cast(LineString, shape(item.shape.__geo_interface__))
            geometry_wgs84 = transform(TO_WGS84.transform, geometry_bng)
            if not geometry_wgs84.intersects(pilot_area):
                continue
            count_point_id = int(properties["CP_Number"])
            segments.append(
                RoadSegment(
                    segment_id=f"dft-mrdb-{source_year}-{count_point_id}",
                    count_point_id=count_point_id,
                    road_number=str(properties["RoadNumber"]),
                    source_year=source_year,
                    geometry_bng=geometry_bng,
                    geometry_wgs84=geometry_wgs84,
                )
            )
    else:
        raise NetworkValidationError(f"Unsupported road-network format: {path.suffix}")

    ids = [segment.segment_id for segment in segments]
    if len(ids) != len(set(ids)):
        raise NetworkValidationError("Road segment identifiers are not unique")
    count_point_ids = [segment.count_point_id for segment in segments]
    if len(count_point_ids) != len(set(count_point_ids)):
        raise NetworkValidationError("Road segment count-point identifiers are not unique")
    if not segments:
        raise NetworkValidationError("No road segments intersect the pilot area")
    return segments


def read_aadf(path: Path, count_point_ids: set[int], year: int = 2024) -> pl.DataFrame:
    columns = pl.read_csv(path, n_rows=0).columns
    missing = AADF_REQUIRED_COLUMNS.difference(columns)
    if missing:
        raise NetworkValidationError(f"Missing AADF columns: {', '.join(sorted(missing))}")
    frame = pl.read_csv(
        path,
        columns=sorted(AADF_REQUIRED_COLUMNS),
        infer_schema_length=10_000,
        null_values=["", "NA"],
    )
    frame = (
        frame.filter((pl.col("year") == year) & pl.col("count_point_id").is_in(count_point_ids))
        .select(sorted(AADF_REQUIRED_COLUMNS))
        .rename({"LGVs": "lgvs", "all_HGVs": "all_hgvs"})
    )
    if frame.select(pl.struct(["count_point_id", "year"]).is_duplicated().sum()).item():
        raise NetworkValidationError("AADF has duplicate count-point/year records")
    return frame


def match_collisions(
    collisions: pl.DataFrame,
    segments: list[RoadSegment],
    max_distance_metres: float = MAX_MATCH_DISTANCE_METRES,
    ambiguity_margin_metres: float = AMBIGUITY_MARGIN_METRES,
) -> pl.DataFrame:
    geometries = [segment.geometry_bng for segment in segments]
    tree = STRtree(geometries)
    rows: list[dict[str, Any]] = []

    for collision in collisions.to_dicts():
        point = Point(
            *TO_BNG.transform(float(collision["longitude"]), float(collision["latitude"]))
        )
        nearby = [int(index) for index in tree.query(point.buffer(max_distance_metres))]
        distances = sorted(
            (
                (point.distance(geometries[index]), index)
                for index in nearby
                if point.distance(geometries[index]) <= max_distance_metres
            ),
            key=lambda item: item[0],
        )
        if not distances:
            nearest_index = int(tree.nearest(point))
            rows.append(
                {
                    "collision_index": str(collision["collision_index"]),
                    "match_status": "out_of_range",
                    "segment_id": None,
                    "nearest_segment_id": segments[nearest_index].segment_id,
                    "distance_m": round(point.distance(geometries[nearest_index]), 2),
                    "second_distance_m": None,
                    "candidate_count": 0,
                }
            )
            continue

        nearest_distance, nearest_index = distances[0]
        second_distance = distances[1][0] if len(distances) > 1 else None
        status: Literal["accepted", "ambiguous"] = "accepted"
        segment_id: str | None = segments[nearest_index].segment_id
        if (
            second_distance is not None
            and second_distance - nearest_distance <= ambiguity_margin_metres
        ):
            status = "ambiguous"
            segment_id = None
        rows.append(
            {
                "collision_index": str(collision["collision_index"]),
                "match_status": status,
                "segment_id": segment_id,
                "nearest_segment_id": segments[nearest_index].segment_id,
                "distance_m": round(nearest_distance, 2),
                "second_distance_m": (
                    round(second_distance, 2) if second_distance is not None else None
                ),
                "candidate_count": len(distances),
            }
        )

    return pl.DataFrame(rows)


def _segment_frame(segments: list[RoadSegment]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "segment_key": [f"dft-count-point-{segment.count_point_id}" for segment in segments],
            "segment_id": [segment.segment_id for segment in segments],
            "count_point_id": [segment.count_point_id for segment in segments],
            "road_number": [segment.road_number for segment in segments],
            "source_year": [segment.source_year for segment in segments],
            "geometry_length_km": [segment.geometry_bng.length / 1_000 for segment in segments],
        }
    )


def _road_source_hashes(path: Path) -> dict[str, str]:
    if path.suffix.lower() != ".shp":
        return {path.name: sha256_file(path)}
    return {
        component.name: sha256_file(component)
        for suffix in (".shp", ".shx", ".dbf", ".prj")
        if (component := path.with_suffix(suffix)).exists()
    }


def build_network_evidence(
    collision_path: Path,
    road_path: Path,
    aadf_path: Path,
    output: Path,
    year: int = 2024,
) -> dict[str, Any]:
    collisions = (
        pl.read_parquet(collision_path)
        if collision_path.suffix == ".parquet"
        else read_collisions(collision_path)
    )
    collision_years = collisions["collision_year"].drop_nulls().unique().to_list()
    if collision_years != [year]:
        raise NetworkValidationError(
            f"Collision reporting years {sorted(collision_years)} do not match network year {year}"
        )
    segments = read_road_segments(road_path, source_year=year)
    aadf = read_aadf(aadf_path, {segment.count_point_id for segment in segments}, year)
    matches = match_collisions(collisions, segments)

    accepted = (
        matches.filter(pl.col("match_status") == "accepted")
        .join(
            collisions.select(["collision_index", "collision_severity"]),
            on="collision_index",
            how="left",
        )
        .group_by("segment_id")
        .agg(
            pl.len().alias("collision_count"),
            pl.col("collision_severity").is_in([1, 2]).sum().alias("ksi_count"),
        )
    )
    evidence = (
        _segment_frame(segments)
        .join(aadf, on="count_point_id", how="left")
        .join(accepted, on="segment_id", how="left")
        .with_columns(
            pl.col("collision_count").fill_null(0),
            pl.col("ksi_count").fill_null(0),
            (pl.col("all_motor_vehicles") * 365 * pl.col("link_length_km")).alias(
                "annual_vehicle_km"
            ),
        )
        .with_columns(
            pl.when(pl.col("annual_vehicle_km") > 0)
            .then(pl.col("collision_count") / pl.col("annual_vehicle_km") * RATE_SCALE)
            .otherwise(None)
            .alias("collision_rate_per_100m_vehicle_km")
        )
        .sort("segment_id")
    )

    output.mkdir(parents=True, exist_ok=True)
    match_path = output / f"collision-segment-matches-{year}.parquet"
    evidence_path = output / f"segment-evidence-{year}.parquet"
    geojson_path = output / f"segment-evidence-{year}.geojson"
    report_path = output / f"network-quality-report-{year}.json"
    matches.write_parquet(match_path)
    evidence.write_parquet(evidence_path)

    evidence_by_id = {row["segment_id"]: row for row in evidence.to_dicts()}
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": evidence_by_id[segment.segment_id],
                "geometry": mapping(segment.geometry_wgs84),
            }
            for segment in segments
        ],
    }
    geojson_path.write_text(json.dumps(geojson, indent=2) + "\n", encoding="utf-8")

    statuses = {
        row["match_status"]: row["len"] for row in matches.group_by("match_status").len().to_dicts()
    }
    method_counts = {
        row["estimation_method"]: row["len"]
        for row in aadf.group_by("estimation_method").len().to_dicts()
    }
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_year": year,
        "road_source": MRDB_URL_TEMPLATE.format(year=year),
        "road_source_sha256": _road_source_hashes(road_path),
        "exposure_source": AADF_URL,
        "exposure_source_sha256": sha256_file(aadf_path),
        "road_segments": len(segments),
        "segments_with_exposure": aadf.height,
        "exposure_coverage": round(aadf.height / len(segments), 4),
        "collision_records": collisions.height,
        "match_status_counts": statuses,
        "accepted_match_rate": round(statuses.get("accepted", 0) / collisions.height, 4),
        "max_match_distance_metres": MAX_MATCH_DISTANCE_METRES,
        "ambiguity_margin_metres": AMBIGUITY_MARGIN_METRES,
        "aadf_estimation_methods": method_counts,
        "local_authorities": sorted(evidence["local_authority_code"].drop_nulls().unique()),
        "rate_scale_vehicle_km": RATE_SCALE,
        "outputs": {
            "matches": str(match_path),
            "evidence": str(evidence_path),
            "geojson": str(geojson_path),
        },
        "status": "descriptive-exposure-only",
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
