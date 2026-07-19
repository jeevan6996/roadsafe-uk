import json
from pathlib import Path

import polars as pl
import pytest

from roadsafe.pipeline import (
    DataValidationError,
    build_pilot,
    collision_source_year,
    read_collisions,
)

FIXTURE = Path(__file__).parent / "fixtures" / "dft-collisions-west-yorkshire-2024.csv"


def test_read_collisions_validates_fixture() -> None:
    frame = read_collisions(FIXTURE)
    assert frame.height == 12
    assert frame["collision_index"].n_unique() == 12


def test_read_collisions_rejects_missing_contract_column(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.csv"
    pl.DataFrame({"collision_index": ["one"]}).write_csv(invalid)

    with pytest.raises(DataValidationError, match="Missing required columns"):
        read_collisions(invalid)


def test_build_pilot_writes_parquet_and_quality_report(tmp_path: Path) -> None:
    report = build_pilot(FIXTURE, tmp_path)

    assert report["pilot_records"] == 12
    assert report["severity_counts"] == {"2": 3, "3": 9}
    assert (tmp_path / "pilot-collisions-2024.parquet").exists()
    saved_report = json.loads((tmp_path / "data-quality-report-2024.json").read_text())
    assert saved_report["source_sha256"] == report["source_sha256"]
    assert saved_report["source_year"] == 2024


def test_collision_source_year_rejects_mixed_annual_data() -> None:
    with pytest.raises(DataValidationError, match="exactly one reporting year"):
        collision_source_year(pl.DataFrame({"collision_year": [2023, 2024]}))
