from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from roadsafe.evaluation import build_segment_year_panel
from roadsafe.network import build_network_evidence
from roadsafe.pipeline import build_pilot


def contract_years(contract: Path) -> list[int]:
    payload = json.loads(contract.read_text(encoding="utf-8"))
    return sorted(
        {
            int(year)
            for key in ("training_years", "validation_years", "test_years")
            for year in payload[key]
        }
    )


def format_year_path(template: str, year: int) -> Path:
    return Path(template.format(year=year))


def build_contract_evidence(
    collision_template: str,
    road_template: str,
    aadf: Path,
    contract: Path,
    output: Path,
    historical_collision_source: Path | None = None,
) -> dict[str, Any]:
    years = contract_years(contract)
    annual_reports: list[dict[str, Any]] = []
    evidence_paths: list[Path] = []
    for year in years:
        collision_source = (
            historical_collision_source
            if historical_collision_source is not None and year == 2019
            else format_year_path(collision_template, year)
        )
        pilot_report = build_pilot(collision_source, output, year)
        pilot_path = Path(str(pilot_report["output"]))
        network_report = build_network_evidence(
            pilot_path, format_year_path(road_template, year), aadf, output, year
        )
        outputs = network_report["outputs"]
        evidence_path = Path(str(outputs["evidence"]))
        evidence_paths.append(evidence_path)
        annual_reports.append(
            {
                "year": year,
                "collision_source": str(collision_source),
                "pilot": pilot_report,
                "network": network_report,
            }
        )

    panel_report = build_segment_year_panel(evidence_paths, contract, output)
    report: dict[str, Any] = {
        "years": years,
        "annual_reports": annual_reports,
        "panel": panel_report,
    }
    (output / "contract-build-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report
