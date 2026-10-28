import json
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from roadsafe.poc import MODELS, calibration_factor, main, predict_counts, run_poc, split_fold

CONTRACT = Path(__file__).resolve().parents[1] / "configs/poc-count-models-v1.json"


def sample_frame() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "segment_key": f"road-{i}",
                "year": year,
                "local_authority_code": "A" if i < 25 else "B",
                "annual_vehicle_km": float(100_000 * (i + 1)),
                "ksi_count": i % 3,
                "road_category": "TA" if i % 2 else "PA",
                "road_type": "Major",
                "urban_rural": "urban",
                "estimation_method": "Counted",
            }
            for year in (2021, 2022, 2023)
            for i in range(50)
        ]
    )


def test_calibration_factor_uses_separate_observations() -> None:
    assert calibration_factor(np.array([1.0, 3.0]), np.array([4.0, 4.0])) == 0.5


@pytest.mark.parametrize(
    "actual,predicted",
    [
        ([], []),
        ([1], [1, 2]),
        ([0], [1]),
        ([1], [0]),
        ([1], [-1]),
        ([1], [np.inf]),
        ([np.nan], [1]),
        ([0.5], [1]),
        ([-1], [1]),
    ],
)
def test_invalid_calibration_is_rejected(actual: list[float], predicted: list[float]) -> None:
    with pytest.raises(ValueError):
        calibration_factor(np.array(actual), np.array(predicted))


def test_geographic_and_identity_exclusion_in_fit_and_calibration() -> None:
    frame = sample_frame().with_columns(
        pl.when((pl.col("segment_key") == "road-0") & (pl.col("year") < 2023))
        .then(pl.lit("B"))
        .otherwise(pl.col("local_authority_code"))
        .alias("local_authority_code")
    )
    training, calibration, scoring = split_fold(frame, "A")
    assert training["year"].unique().to_list() == [2021]
    assert calibration["year"].unique().to_list() == [2022]
    assert scoring["year"].unique().to_list() == [2023]
    for earlier in (training, calibration):
        assert "A" not in earlier["local_authority_code"].to_list()
        assert set(earlier["segment_key"]).isdisjoint(scoring["segment_key"])


@pytest.mark.parametrize("model", MODELS)
def test_predictions_ignore_scoring_outcomes_and_scale_with_exposure(model: str) -> None:
    if model == "poisson-boosting":
        pytest.importorskip("sklearn")
    training, calibration, scoring = split_fold(sample_frame(), "A")
    values = predict_counts(training, scoring, model)
    altered = scoring.with_columns(pl.lit(999).alias("ksi_count"))
    np.testing.assert_allclose(predict_counts(training, altered, model), values)
    doubled = altered.with_columns(pl.col("annual_vehicle_km") * 2)
    np.testing.assert_allclose(predict_counts(training, doubled, model), 2 * values)
    factor = calibration_factor(
        calibration["ksi_count"].to_numpy(), predict_counts(training, calibration, model)
    )
    assert np.isfinite(factor) and factor > 0
    assert np.isfinite(values).all() and (values > 0).all()


@pytest.mark.parametrize("exposure", [0, -1, np.nan, np.inf])
def test_invalid_scoring_exposure_rejected(exposure: float) -> None:
    training, _, scoring = split_fold(sample_frame(), "A")
    with pytest.raises(ValueError):
        predict_counts(
            training,
            scoring.with_columns(pl.lit(exposure).alias("annual_vehicle_km")),
            "exposure-baseline",
        )


def test_full_poc_is_repeatable_and_ignores_2024_outcomes(tmp_path: Path) -> None:
    pytest.importorskip("sklearn")
    template = sample_frame().filter(pl.col("year") == 2021)
    source = pl.concat(
        [template.with_columns(pl.lit(year).alias("year")) for year in range(2019, 2025)]
    )
    panel = tmp_path / "panel.parquet"
    source.write_parquet(panel)
    contract = Path(__file__).resolve().parents[1] / "configs/poc-count-models-v1.json"
    first = run_poc(panel, contract, tmp_path / "first")
    repeat = run_poc(panel, contract, tmp_path / "repeat")
    assert first["results"] == repeat["results"]
    assert first["prediction_sha256"] == repeat["prediction_sha256"]
    source.with_columns(
        pl.when(pl.col("year") == 2024)
        .then(pl.lit(999))
        .otherwise(pl.col("ksi_count"))
        .alias("ksi_count")
    ).write_parquet(panel)
    altered = run_poc(panel, contract, tmp_path / "altered")
    assert first["results"] == altered["results"]
    assert first["prediction_sha256"] == altered["prediction_sha256"]
    assert first["panel_sha256"] != altered["panel_sha256"]
    assert len(first["results"]) == 6
    assert all(item["complete"] for item in first["results"])
    assert first["lag_coverage"]["1"]["after_pairing"] == 150


@pytest.fixture
def poc_panel(tmp_path: Path) -> Path:
    template = sample_frame().filter(pl.col("year") == 2021)
    source = pl.concat(
        [template.with_columns(pl.lit(year).alias("year")) for year in range(2019, 2024)]
    )
    panel = tmp_path / "panel.parquet"
    source.write_parquet(panel)
    return panel


@pytest.mark.parametrize("populated", [False, True])
def test_poc_rejects_existing_output_without_writing(
    poc_panel: Path, tmp_path: Path, populated: bool
) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    if populated:
        (output / "lag-1").mkdir()
        (output / "lag-1/feature-panel-report.json").write_bytes(b"prior feature report")
        (output / "poc-report.json").write_bytes(b"prior run report")
        (output / "poc-predictions.parquet").write_bytes(b"prior predictions")
    before = {
        path.relative_to(output): path.read_bytes() if path.is_file() else None
        for path in output.rglob("*")
    }

    with pytest.raises(FileExistsError):
        run_poc(poc_panel, CONTRACT, output)

    after = {
        path.relative_to(output): path.read_bytes() if path.is_file() else None
        for path in output.rglob("*")
    }
    assert after == before


@pytest.mark.parametrize("failure", ["none", "partial", "all"])
def test_poc_cli_reports_completion_and_exits_nonzero_for_incomplete_folds(
    poc_panel: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    pytest.importorskip("sklearn")
    if failure != "none":
        source = pl.read_parquet(poc_panel)
        zero_calibration = pl.col("year") == 2022
        if failure == "partial":
            zero_calibration &= pl.col("local_authority_code") == "A"
        source.with_columns(
            pl.when(zero_calibration)
            .then(pl.lit(0))
            .otherwise(pl.col("ksi_count"))
            .alias("ksi_count")
        ).write_parquet(poc_panel)
    output = tmp_path / "run"
    monkeypatch.setattr(
        "sys.argv",
        ["poc", "--panel", str(poc_panel), "--contract", str(CONTRACT), "--output", str(output)],
    )

    if failure == "none":
        main()
    else:
        with pytest.raises(SystemExit) as error:
            main()
        assert error.value.code == 1

    summary = json.loads(capsys.readouterr().out)
    report = json.loads((output / "poc-report.json").read_text())
    expected_status = "completed-exploratory" if failure == "none" else "partial-exploratory"
    assert summary["status"] == report["status"] == expected_status
    assert summary["experiments"] == 6
    assert report["model_promoted"] is False
    folds = [fold for result in report["results"] for fold in result["folds"]]
    expected_failures = {"none": 0, "partial": 6, "all": 12}[failure]
    assert sum(fold["status"] == "failed" for fold in folds) == expected_failures
    if failure != "none":
        assert all(not result["complete"] for result in report["results"])
        assert all("reason" in fold for fold in folds if fold["status"] == "failed")
    if failure == "all":
        assert report["prediction_sha256"] is None
        assert not (output / "poc-predictions.parquet").exists()
    else:
        assert (output / "poc-predictions.parquet").is_file()
