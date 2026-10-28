import json
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from roadsafe.cli import main
from roadsafe.experiments import run_poc_bundle
from roadsafe.pipeline import sha256_file

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/poc-count-models-v1.json"
BLOCKED = ROOT / "configs/source-availability-v1.json"


@pytest.fixture
def panel(tmp_path: Path) -> Path:
    path = tmp_path / "panel.parquet"
    pl.DataFrame(
        [
            {
                "segment_key": f"road-{i}",
                "year": year,
                "local_authority_code": "A" if i < 12 else "B",
                "annual_vehicle_km": float(100_000 * (i + 1)),
                "ksi_count": i % 3,
                "road_category": "PA",
                "road_type": "Major",
                "urban_rural": "urban",
                "estimation_method": "Counted",
            }
            for year in range(2019, 2024)
            for i in range(24)
        ]
    ).write_parquet(path)
    return path


def supported_manifest(tmp_path: Path) -> Path:
    artifact = tmp_path / "source.csv"
    artifact.write_text("synthetic availability fixture, not real historical evidence\n")
    sources = [
        {
            "kind": kind,
            "year": year,
            "published_on": f"{year}-12-31",
            "release_evidence": "https://example.org/release",
            "artifact_path": artifact.name,
            "artifact_sha256": sha256_file(artifact),
            "vintage_available_on": f"{year}-12-31",
            "vintage_evidence": "https://example.org/vintage",
        }
        for kind in ("traffic", "network", "urban-rural", "collisions")
        for year in range(2019, 2023)
    ]
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema_version": "1.0", "sources": sources}))
    return path


def test_blocked_bundle_does_not_call_model(
    panel: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: Any) -> None:
        pytest.fail("Blocked source evidence must prevent fitting")

    monkeypatch.setattr("roadsafe.experiments.run_poc", forbidden)
    out = tmp_path / "blocked"
    report = run_poc_bundle(panel, CONTRACT, BLOCKED, out)
    assert report["status"] == "blocked"
    assert report["model_run"] is None
    assert not (out / "experiment").exists()
    assert len(report["artifacts"]) == 4
    assert set(report["source_audits"]) == {"1", "2"}
    assert all(row["blocked_requirements"] == 11 for row in report["source_audits"].values())
    assert report == json.loads((out / "run-report.json").read_text())
    for relative, fingerprint in report["artifacts"].items():
        assert sha256_file(out / relative) == fingerprint
    repeated = run_poc_bundle(panel, CONTRACT, BLOCKED, tmp_path / "repeat")
    assert repeated == report


@pytest.mark.parametrize("supported", [False, True])
def test_real_experiment_stays_exploratory(panel: Path, tmp_path: Path, supported: bool) -> None:
    pytest.importorskip("sklearn")
    manifest = supported_manifest(tmp_path) if supported else BLOCKED
    out = tmp_path / "run"
    report = run_poc_bundle(panel, CONTRACT, manifest, out, allow_exploratory=not supported)
    assert report["status"] == "completed-exploratory"
    assert report["model_promoted"] is False
    assert report["panel_lineage_verified"] is False
    assert report["model_run"]["experiments"] == 6
    assert "experiment/poc-predictions.parquet" in report["artifacts"]
    assert report["input_sha256"]["panel"] == sha256_file(panel)
    expected = "source-requirements-satisfied" if supported else "blocked"
    assert all(row["status"] == expected for row in report["source_audits"].values())


def test_existing_output_is_never_reused(panel: Path, tmp_path: Path) -> None:
    out = tmp_path / "old"
    out.mkdir()
    marker = out / "poc-predictions.parquet"
    marker.write_bytes(b"preserve previous results")
    with pytest.raises(FileExistsError):
        run_poc_bundle(panel, CONTRACT, BLOCKED, out)
    assert marker.read_bytes() == b"preserve previous results"
    assert not (out / "run-report.json").exists()


@pytest.mark.parametrize("failure", ["exception", "mutation", "partial"])
def test_failed_and_partial_runs_are_not_successes(
    panel: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    def fake_model(*args: Any) -> dict[str, Any]:
        if failure == "exception":
            raise RuntimeError("synthetic fit failure")
        if failure == "mutation":
            panel.write_bytes(b"changed during fitting")
        return {"status": "exploratory-only", "results": [{"complete": failure != "partial"}]}

    monkeypatch.setattr("roadsafe.experiments.run_poc", fake_model)
    out = tmp_path / "run"
    if failure == "partial":
        report = run_poc_bundle(panel, CONTRACT, BLOCKED, out, allow_exploratory=True)
        assert report["status"] == "partial-exploratory"
    else:
        with pytest.raises((ValueError, RuntimeError)):
            run_poc_bundle(panel, CONTRACT, BLOCKED, out, allow_exploratory=True)
        report = json.loads((out / "run-report.json").read_text())
        assert report["status"] == "failed"
        assert "error" in report
    assert report["model_promoted"] is False


def test_invalid_manifest_records_failure(panel: Path, tmp_path: Path) -> None:
    manifest = tmp_path / "bad.json"
    manifest.write_text("not json")
    out = tmp_path / "failed"
    with pytest.raises(ValueError):
        run_poc_bundle(panel, CONTRACT, manifest, out)
    assert json.loads((out / "run-report.json").read_text())["status"] == "failed"


def test_cli_blocked_exit(
    panel: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "roadsafe",
            "run-poc-bundle",
            "--panel",
            str(panel),
            "--contract",
            str(CONTRACT),
            "--manifest",
            str(BLOCKED),
            "--output",
            str(tmp_path / "cli"),
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
