"""Source-audited bundles for the fixed-design count-model experiment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from roadsafe.availability import audit_availability
from roadsafe.evaluation import read_evaluation_contract
from roadsafe.pipeline import sha256_file
from roadsafe.poc import run_poc


def run_poc_bundle(
    panel: Path,
    contract: Path,
    manifest: Path,
    output: Path,
    *,
    allow_exploratory: bool = False,
) -> dict[str, Any]:
    """Audit both lag designs before fitting; never certify panel lineage or promotion."""
    if type(allow_exploratory) is not bool:
        raise ValueError("allow_exploratory must be a boolean")
    spec = read_evaluation_contract(contract)
    if (spec.training_years, spec.validation_years, spec.test_years) != ([2021], [2022], [2023]):
        raise ValueError("This fixed POC requires 2021 fit / 2022 calibration / 2023 evaluation")
    inputs = {"panel": panel, "contract": contract, "manifest": manifest}
    fingerprints = {name: sha256_file(path) for name, path in inputs.items()}
    # A fresh directory prevents stale predictions from resembling a blocked run's output.
    output.mkdir(parents=True, exist_ok=False)
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "running",
        "allow_exploratory": allow_exploratory,
        "model_promoted": False,
        "panel_lineage_verified": False,
        "input_sha256": fingerprints,
        "implementation_sha256": sha256_file(Path(__file__)),
        "source_audits": {},
        "model_run": None,
        "artifacts": {},
        "limitations": [
            "Source checks do not prove this panel was built from the declared vintages.",
            "Evidence citations and source semantics require human verification.",
            "This fixed-design POC remains exploratory even when source checks pass.",
            "Calibration, fresh holdout evaluation and uncertainty gates remain outstanding.",
        ],
    }

    def save() -> None:
        (output / "run-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )

    save()
    try:
        for lag in (1, 2):
            audit = audit_availability(contract, manifest, output / f"availability-lag-{lag}", lag)
            report["source_audits"][str(lag)] = {
                "status": audit["status"],
                "requirements": audit["requirements"],
                "blocked_requirements": audit["blocked_requirements"],
            }
        blocked = any(row["status"] == "blocked" for row in report["source_audits"].values())
        if blocked and not allow_exploratory:
            report["status"] = "blocked"
        else:
            model = run_poc(panel, contract, output / "experiment")
            complete = bool(model["results"]) and all(row["complete"] for row in model["results"])
            report["status"] = "completed-exploratory" if complete else "partial-exploratory"
            report["model_run"] = {
                "status": model["status"],
                "experiments": len(model["results"]),
                "complete": complete,
            }
        if fingerprints != {name: sha256_file(path) for name, path in inputs.items()}:
            raise ValueError("Run inputs changed during execution; discard this bundle")
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        report["artifacts"] = {
            str(path.relative_to(output)): sha256_file(path)
            for path in sorted(output.rglob("*"))
            if path.is_file() and path != output / "run-report.json"
        }
        save()
    return report
