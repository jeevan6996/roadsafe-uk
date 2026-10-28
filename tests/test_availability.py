import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from roadsafe.availability import FEATURE_SOURCES, AvailabilityManifest, audit_availability
from roadsafe.cli import main
from roadsafe.features import FORECAST_FEATURES
from roadsafe.pipeline import sha256_file

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/poc-count-models-v1.json"


def manifest(tmp_path: Path) -> Path:
    artifact = tmp_path / "source.csv"
    artifact.write_text("synthetic test bytes\n")
    sources = []
    for kind, years in (
        ("traffic", [2019, 2020, 2021]),
        ("network", [2019, 2020, 2021]),
        ("urban-rural", [2019, 2020, 2021]),
        ("collisions", [2021, 2022]),
    ):
        for year in years:
            sources.append(
                {
                    "kind": kind,
                    "year": year,
                    "published_on": f"{year}-12-31",
                    "release_evidence": "https://example.org/release",
                    "artifact_path": "source.csv",
                    "artifact_sha256": sha256_file(artifact),
                    "vintage_available_on": f"{year}-12-31",
                    "vintage_evidence": "https://example.org/archive",
                }
            )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema_version": "1.0", "sources": sources}))
    return path


def test_every_model_feature_has_explicit_source_requirements() -> None:
    assert set(FEATURE_SOURCES) == set(FORECAST_FEATURES)


def test_verified_fixture_boundary_dates_and_repeatability(tmp_path: Path) -> None:
    path = manifest(tmp_path)
    report = audit_availability(CONTRACT, path, tmp_path / "out")
    assert report["status"] == "source-requirements-satisfied"
    assert report["requirements"] == 11
    assert report["model_promoted"] is False
    assert report == audit_availability(CONTRACT, path, tmp_path / "out")
    stored = json.loads((tmp_path / "out/availability-report.json").read_text())
    assert stored["manifest_sha256"] == sha256_file(path)
    assert "0/11 requirements blocked" in (tmp_path / "out/availability-report.md").read_text()


def test_historical_features_use_their_own_cutoff(tmp_path: Path) -> None:
    path = manifest(tmp_path)
    data = json.loads(path.read_text())
    data["sources"][0]["vintage_available_on"] = "2021-01-01"
    path.write_text(json.dumps(data))
    report = audit_availability(CONTRACT, path, tmp_path / "out")
    row = report["checks"][1]
    assert row["role"] == "training_features"
    assert row["cutoff"] == "2020-12-31"
    assert row["reasons"] == ["vintage_after_cutoff"]


def test_calibration_labels_must_exist_before_forecast(tmp_path: Path) -> None:
    path = manifest(tmp_path)
    data = json.loads(path.read_text())
    data["sources"][-1]["published_on"] = "2023-09-28"
    data["sources"][-1]["vintage_available_on"] = "2023-09-28"
    path.write_text(json.dumps(data))
    report = audit_availability(CONTRACT, path, tmp_path / "out")
    row = report["checks"][-1]
    assert row["role"] == "calibration_labels"
    assert row["cutoff"] == "2022-12-31"
    assert row["reasons"] == ["release_after_cutoff", "vintage_after_cutoff"]


@pytest.mark.parametrize(
    "change,reason", [("changed", "artifact_hash_mismatch"), ("missing", "artifact_unreadable")]
)
def test_exact_bytes_are_required(tmp_path: Path, change: str, reason: str) -> None:
    path = manifest(tmp_path)
    if change == "changed":
        (tmp_path / "source.csv").write_text("revised data")
    else:
        (tmp_path / "source.csv").unlink()
    report = audit_availability(CONTRACT, path, tmp_path / "out")
    assert report["blocked_requirements"] == 11
    assert all(reason in row["reasons"] for row in report["checks"])


def test_release_dates_alone_cannot_pass(tmp_path: Path) -> None:
    report = audit_availability(CONTRACT, ROOT / "configs/source-availability-v1.json", tmp_path)
    assert report["status"] == "blocked"
    assert report["blocked_requirements"] == report["requirements"]
    assert "release_after_cutoff" in report["checks"][-1]["reasons"]
    assert any("missing_source" in row["reasons"] for row in report["checks"])


@pytest.mark.parametrize("lag", [True, 0, -1, 1.5])
def test_invalid_lag_is_rejected(tmp_path: Path, lag: int) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        audit_availability(CONTRACT, manifest(tmp_path), tmp_path / "out", lag)


@pytest.mark.parametrize("mutation", ["duplicate", "partial", "early", "unknown", "bool_year"])
def test_invalid_manifest_is_rejected(tmp_path: Path, mutation: str) -> None:
    data = json.loads(manifest(tmp_path).read_text())
    if mutation == "duplicate":
        data["sources"].append(data["sources"][0])
    elif mutation == "partial":
        del data["sources"][0]["artifact_sha256"]
    elif mutation == "early":
        data["sources"][0]["vintage_available_on"] = "2000-01-01"
    elif mutation == "bool_year":
        data["sources"][0]["year"] = True
    else:
        data["unexpected"] = True
    with pytest.raises(ValidationError):
        AvailabilityManifest.model_validate(data)


def test_cli_exits_nonzero_and_still_writes_blockers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "roadsafe",
            "audit-availability",
            "--contract",
            str(CONTRACT),
            "--manifest",
            str(ROOT / "configs/source-availability-v1.json"),
            "--output",
            str(tmp_path),
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
    assert (tmp_path / "availability-report.md").is_file()
