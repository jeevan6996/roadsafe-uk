from pathlib import Path

import polars as pl
import pytest

from roadsafe.screening import ScreeningValidationError, build_descriptive_screening


def panel_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "segment_key": ["dft-count-point-1", "dft-count-point-1", "dft-count-point-2"],
            "count_point_id": [1, 1, 2],
            "year": [2022, 2023, 2023],
            "road_number": ["A1", "A1", "M1"],
            "road_category": ["PA", "PA", "TM"],
            "local_authority_code": ["E00000001", "E00000001", "E00000002"],
            "local_authority_name": ["Authority A", "Authority A", "Authority B"],
            "urban_rural": ["urban", "urban", "rural"],
            "annual_vehicle_km": [1_000_000.0, 1_000_000.0, 500_000.0],
            "collision_count": [1, 2, 2],
            "ksi_count": [0, 1, 1],
        }
    )


def test_descriptive_screening_exports_ranked_observed_rates(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.parquet"
    panel_frame().write_parquet(panel_path)

    report = build_descriptive_screening(panel_path, tmp_path / "out")
    screening = pl.read_parquet(tmp_path / "out" / "segment-descriptive-screening.parquet")

    assert report["not_modelled"] is True
    assert report["segments"] == 2
    assert report["years"] == [2022, 2023]
    assert screening["segment_key"].to_list() == ["dft-count-point-2", "dft-count-point-1"]
    assert screening["ksi_rate_per_million_vehicle_km"].to_list() == [2.0, 0.5]
    assert (tmp_path / "out" / "descriptive-screening-report.json").exists()
    assert "urban_rural" in report["subgroup_rates"]


def test_descriptive_screening_rejects_invalid_panel_schema(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.parquet"
    panel_frame().drop("ksi_count").write_parquet(panel_path)

    with pytest.raises(ScreeningValidationError, match="missing screening columns: ksi_count"):
        build_descriptive_screening(panel_path, tmp_path / "out")


def test_descriptive_screening_rejects_invalid_exposure(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.parquet"
    panel_frame().with_columns(pl.lit(0.0).alias("annual_vehicle_km")).write_parquet(panel_path)

    with pytest.raises(ScreeningValidationError, match="invalid exposure or target rows"):
        build_descriptive_screening(panel_path, tmp_path / "out")
