from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path
from typing import override
from xml.sax import ContentHandler, make_parser

from pyproj import Transformer
from shapely.geometry import shape
from shapely.strtree import STRtree

from roadsafe.network import read_road_segments
from roadsafe.pipeline import PILOT_BOUNDS

TABLE_NS = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"


class OaLookupHandler(ContentHandler):
    def __init__(self) -> None:
        super().__init__()
        self.in_oa = False
        self.in_row = False
        self.in_cell = False
        self.in_paragraph = False
        self.row: list[str] = []
        self.header: list[str] | None = None
        self.classification: dict[str, str] = {}
        self.cell_text = ""
        self.repeat = 1

    @override
    def startElementNS(self, name: tuple[str, str], _qname: str, attrs: object) -> None:  # noqa: N802
        namespace, local = name
        if namespace == TABLE_NS and local == "table":
            self.in_oa = attrs.get((TABLE_NS, "name")) == "OA11"  # type: ignore[union-attr]
        elif self.in_oa and namespace == TABLE_NS and local == "table-row":
            self.in_row = True
            self.row = []
        elif self.in_row and namespace == TABLE_NS and local == "table-cell":
            self.in_cell = True
            self.cell_text = ""
            self.repeat = int(
                attrs.get((TABLE_NS, "number-columns-repeated"), "1")  # type: ignore[union-attr]
            )
        elif self.in_cell and namespace == TEXT_NS and local == "p":
            self.in_paragraph = True

    def characters(self, content: str) -> None:
        if self.in_paragraph:
            self.cell_text += content

    @override
    def endElementNS(self, name: tuple[str, str], _qname: str) -> None:  # noqa: N802
        namespace, local = name
        if namespace == TEXT_NS and local == "p":
            self.in_paragraph = False
        elif namespace == TABLE_NS and local == "table-cell" and self.in_cell:
            self.row.extend([self.cell_text.strip()] * self.repeat)
            self.in_cell = False
        elif namespace == TABLE_NS and local == "table-row" and self.in_row:
            if self.row and self.row[0] == "Output Area 2011 Code":
                self.header = self.row
            elif self.header is not None:
                code_index = self.header.index("Output Area 2011 Code")
                class_index = self.header.index("Rural Urban Classification 2011 (2 fold)")
                if len(self.row) > class_index and self.row[code_index]:
                    self.classification[self.row[code_index]] = self.row[class_index].lower()
            self.in_row = False
        elif namespace == TABLE_NS and local == "table":
            self.in_oa = False


def read_oa_classification(path: Path) -> dict[str, str]:
    handler = OaLookupHandler()
    parser = make_parser()
    parser.setFeature("http://xml.org/sax/features/namespaces", True)
    parser.setContentHandler(handler)
    with zipfile.ZipFile(path) as archive, archive.open("content.xml") as stream:
        parser.parse(stream)
    return handler.classification


def main() -> None:
    root = Path(__file__).parents[1]
    classification = read_oa_classification(
        root / "data/raw/rural-urban-classification-2011-small-area.ods"
    )
    geo = json.loads((root / "data/raw/oa11-west-yorkshire.geojson").read_text())
    polygons = [shape(feature["geometry"]) for feature in geo["features"]]
    codes = [feature["properties"]["OA11CD"] for feature in geo["features"]]
    tree = STRtree(polygons)
    to_bng = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
    pilot_box = shape(
        {
            "type": "Polygon",
            "coordinates": [
                [
                    to_bng.transform(PILOT_BOUNDS["min_longitude"], PILOT_BOUNDS["min_latitude"]),
                    to_bng.transform(PILOT_BOUNDS["max_longitude"], PILOT_BOUNDS["min_latitude"]),
                    to_bng.transform(PILOT_BOUNDS["max_longitude"], PILOT_BOUNDS["max_latitude"]),
                    to_bng.transform(PILOT_BOUNDS["min_longitude"], PILOT_BOUNDS["max_latitude"]),
                    to_bng.transform(PILOT_BOUNDS["min_longitude"], PILOT_BOUNDS["min_latitude"]),
                ]
            ],
        }
    )

    def classify(point: object) -> str | None:
        for index in tree.query(point):  # type: ignore[arg-type]
            index = int(index)
            if polygons[index].covers(point):  # type: ignore[arg-type]
                value = classification.get(codes[index])
                if value in {"urban", "rural"}:
                    return value
        nearest = int(tree.nearest(point))  # type: ignore[arg-type]
        if polygons[nearest].distance(point) <= 500:  # type: ignore[arg-type]
            value = classification.get(codes[nearest])
            if value in {"urban", "rural"}:
                return value
        return None

    rows: set[tuple[int, int, str]] = set()
    missing: list[tuple[int, int]] = []
    for year in range(2019, 2025):
        road_path = root / f"data/raw/extracted/mrdb-{year}/MRDB_{year}_published.shp"
        for segment in read_road_segments(road_path, source_year=year):
            count_point_id = segment.count_point_id
            value = classify(segment.geometry_bng.intersection(pilot_box).representative_point())
            if value is None:
                missing.append((year, count_point_id))
            rows.add((count_point_id, year, value or ""))
    if missing:
        raise RuntimeError(f"{len(missing)} road points have no output-area class: {missing[:10]}")

    output = root / "data/processed/urban-rural-2019-2024.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["count_point_id", "year", "urban_rural"])
        writer.writerows(sorted(rows, key=lambda row: (row[1], row[0])))
    print(f"parsed_oa_classifications={len(classification)}")
    print(f"road_point_year_rows={len(rows)}")
    print(f"output={output}")


if __name__ == "__main__":
    main()
