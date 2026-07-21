import json
from pathlib import Path

import polars as pl

from roadsafe.orchestration import build_contract_evidence

FIXTURES = Path(__file__).parent / "fixtures"
COLLISIONS = FIXTURES / "dft-collisions-west-yorkshire-2024.csv"
ROADS = FIXTURES / "dft-major-roads-west-yorkshire-2024.geojson"
AADF = FIXTURES / "dft-aadf-west-yorkshire-2024.csv"


def write_collision_source(path: Path, year: int) -> None:
    frame = pl.read_csv(COLLISIONS).with_columns(pl.lit(year).alias("collision_year"))
    frame.write_csv(path)


def write_aadf_source(path: Path, years: list[int]) -> None:
    frame = pl.read_csv(AADF)
    pl.concat([frame.with_columns(pl.lit(year).alias("year")) for year in years]).write_csv(path)


def write_contract(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "test",
                "status": "planned-not-run",
                "unit": "dft-major-road-segment-year",
                "target": "future_ksi_collision_count",
                "training_years": [2022],
                "validation_years": [2023],
                "test_years": [2024],
                "geographic_split": "grouped-local-authority-holdout",
                "feature_cutoff": "end-of-prior-calendar-year",
                "ranking_metrics": ["lift_at_k"],
                "probabilistic_metrics": ["poisson_deviance"],
                "required_subgroups": [
                    "road_class",
                    "traffic_estimation_method",
                    "local_authority",
                ],
                "excluded_event_features": ["collision_weather"],
            }
        ),
        encoding="utf-8",
    )


def test_build_contract_evidence_builds_annual_artifacts_and_panel(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    for year in (2022, 2023, 2024):
        write_collision_source(raw / f"collision-{year}.csv", year)
        (raw / f"roads-{year}.geojson").write_text(ROADS.read_text(encoding="utf-8"))
    aadf = raw / "aadf.csv"
    write_aadf_source(aadf, [2022, 2023, 2024])
    contract = raw / "contract.json"
    write_contract(contract)
    output = tmp_path / "processed"

    report = build_contract_evidence(
        str(raw / "collision-{year}.csv"),
        str(raw / "roads-{year}.geojson"),
        aadf,
        contract,
        output,
    )

    assert report["years"] == [2022, 2023, 2024]
    assert len(report["annual_reports"]) == 3
    assert (output / "pilot-collisions-2022.parquet").exists()
    assert (output / "segment-evidence-2023.parquet").exists()
    assert (output / "segment-year-panel.parquet").exists()
    assert (output / "contract-build-report.json").exists()
    assert report["panel"]["available_years"] == [2022, 2023, 2024]


def test_build_contract_evidence_uses_historical_source_for_2019(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    history = raw / "collision-history.csv"
    history_frame = pl.concat(
        [
            pl.read_csv(COLLISIONS).with_columns(pl.lit(2018).alias("collision_year")),
            pl.read_csv(COLLISIONS).with_columns(pl.lit(2019).alias("collision_year")),
        ]
    ).with_columns(
        (
            pl.col("collision_index").cast(pl.String)
            + "-"
            + pl.col("collision_year").cast(pl.String)
        ).alias("collision_index")
    )
    history_frame.write_csv(history)
    for year in (2019, 2020, 2021):
        if year != 2019:
            write_collision_source(raw / f"collision-{year}.csv", year)
        (raw / f"roads-{year}.geojson").write_text(ROADS.read_text(encoding="utf-8"))
    aadf = raw / "aadf.csv"
    write_aadf_source(aadf, [2019, 2020, 2021])
    contract = raw / "contract.json"
    contract.write_text(
        json.dumps(
            {
                "schema_version": "test",
                "status": "planned-not-run",
                "unit": "dft-major-road-segment-year",
                "target": "future_ksi_collision_count",
                "training_years": [2019],
                "validation_years": [2020],
                "test_years": [2021],
                "geographic_split": "grouped-local-authority-holdout",
                "feature_cutoff": "end-of-prior-calendar-year",
                "ranking_metrics": ["lift_at_k"],
                "probabilistic_metrics": ["poisson_deviance"],
                "required_subgroups": ["road_class", "local_authority"],
                "excluded_event_features": ["collision_weather"],
            }
        ),
        encoding="utf-8",
    )

    report = build_contract_evidence(
        str(raw / "collision-{year}.csv"),
        str(raw / "roads-{year}.geojson"),
        aadf,
        contract,
        tmp_path / "processed",
        history,
    )

    first = report["annual_reports"][0]
    assert first["year"] == 2019
    assert first["collision_source"] == str(history)
    assert first["pilot"]["selected_source_records"] == 12
