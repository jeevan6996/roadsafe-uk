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


@pytest.mark.parametrize("suffix", ["csv", "parquet"])
@pytest.mark.parametrize("severity", [None, 0, 4])
def test_read_collisions_rejects_missing_or_invalid_severity(
    tmp_path: Path, suffix: str, severity: int | None
) -> None:
    frame = pl.read_csv(FIXTURE).with_columns(
        pl.when(pl.int_range(pl.len()) == 0)
        .then(pl.lit(severity, dtype=pl.Int64))
        .otherwise(pl.col("collision_severity"))
        .alias("collision_severity")
    )
    source = tmp_path / f"invalid.{suffix}"
    if suffix == "csv":
        frame.write_csv(source)
    else:
        frame.write_parquet(source)
    with pytest.raises(DataValidationError, match="invalid severity"):
        read_collisions(source)


@pytest.mark.parametrize("suffix", ["csv", "parquet"])
def test_read_collisions_rejects_duplicate_identifiers(tmp_path: Path, suffix: str) -> None:
    frame = pl.read_csv(FIXTURE)
    duplicate = pl.concat([frame, frame.head(1)])
    source = tmp_path / f"duplicates.{suffix}"
    if suffix == "csv":
        duplicate.write_csv(source)
    else:
        duplicate.write_parquet(source)
    with pytest.raises(DataValidationError, match="duplicate collision identifiers"):
        read_collisions(source)


def test_read_collisions_accepts_equivalent_parquet(tmp_path: Path) -> None:
    source = tmp_path / "collisions.parquet"
    pl.read_csv(FIXTURE).write_parquet(source)
    assert read_collisions(source).equals(read_collisions(FIXTURE))


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


def test_build_pilot_preserves_dates_from_its_parquet_output(tmp_path: Path) -> None:
    build_pilot(FIXTURE, tmp_path / "first")
    source = tmp_path / "first" / "pilot-collisions-2024.parquet"
    build_pilot(source, tmp_path / "second")
    original = pl.read_parquet(source)
    repeated = pl.read_parquet(tmp_path / "second" / "pilot-collisions-2024.parquet")
    assert original.schema["date"] == pl.Date
    assert original["date"].null_count() == 0
    assert repeated.equals(original)


def test_build_pilot_rejects_unsupported_date_dtype_cleanly(tmp_path: Path) -> None:
    source = tmp_path / "dates.parquet"
    read_collisions(FIXTURE).with_columns(pl.lit(20240101).alias("date")).write_parquet(source)
    output = tmp_path / "out"
    with pytest.raises(DataValidationError, match="date.*String or Date"):
        build_pilot(source, output)
    assert not output.exists()


def test_build_pilot_extracts_requested_year_from_historical_source(tmp_path: Path) -> None:
    historical = tmp_path / "historical.csv"
    frame = pl.concat(
        [
            pl.read_csv(FIXTURE).with_columns(pl.lit(2019).alias("collision_year")),
            pl.read_csv(FIXTURE).with_columns(pl.lit(2020).alias("collision_year")),
        ]
    ).with_columns(
        (
            pl.col("collision_index").cast(pl.String)
            + "-"
            + pl.col("collision_year").cast(pl.String)
        ).alias("collision_index")
    )
    frame.write_csv(historical)

    report = build_pilot(historical, tmp_path, year=2019)

    assert report["source_records"] == 24
    assert report["selected_source_records"] == 12
    assert report["source_year"] == 2019
    assert (tmp_path / "pilot-collisions-2019.parquet").exists()


def test_collision_source_year_rejects_mixed_annual_data() -> None:
    with pytest.raises(DataValidationError, match="exactly one reporting year"):
        collision_source_year(pl.DataFrame({"collision_year": [2023, 2024]}))
