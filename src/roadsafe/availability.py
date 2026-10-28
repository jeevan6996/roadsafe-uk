"""Conservative source-vintage preflight for fixed-design forecasting experiments."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from roadsafe.evaluation import read_evaluation_contract
from roadsafe.pipeline import sha256_file

SourceKind = Literal["traffic", "network", "urban-rural", "collisions"]
FEATURE_SOURCES: dict[str, tuple[SourceKind, ...]] = {
    "annual_vehicle_km": ("traffic",),
    "road_category": ("traffic",),
    "road_type": ("traffic",),
    "urban_rural": ("urban-rural",),
    "estimation_method": ("traffic",),
}


class SourceVintage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: SourceKind
    year: int = Field(strict=True, ge=1900, le=9998)
    published_on: date
    release_evidence: HttpUrl
    artifact_path: str | None = Field(default=None, min_length=1)
    artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    vintage_available_on: date | None = None
    vintage_evidence: HttpUrl | None = None

    @model_validator(mode="after")
    def validate_vintage(self) -> SourceVintage:
        fields = (
            self.artifact_path,
            self.artifact_sha256,
            self.vintage_available_on,
            self.vintage_evidence,
        )
        if any(value is not None for value in fields) and not all(
            value is not None for value in fields
        ):
            raise ValueError(
                "Artifact path, hash, vintage date and evidence must be provided together"
            )
        if self.vintage_available_on and self.vintage_available_on < self.published_on:
            raise ValueError("Artifact vintage cannot precede its source release")
        return self


class AvailabilityManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    sources: list[SourceVintage]

    @model_validator(mode="after")
    def unique_sources(self) -> AvailabilityManifest:
        keys = [(source.kind, source.year) for source in self.sources]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate source kind/year; select one explicit vintage")
        return self


def audit_availability(
    contract_path: Path, manifest_path: Path, output: Path, lag_years: int = 2
) -> dict[str, Any]:
    if type(lag_years) is not int or lag_years < 1:
        raise ValueError("lag_years must be a positive integer")
    contract = read_evaluation_contract(contract_path)
    years = contract.training_years + contract.validation_years + contract.test_years
    if any(year < 1901 + lag_years or year > 9998 for year in years):
        raise ValueError("Contract years fall outside the supported date range")
    manifest = AvailabilityManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    sources = {(source.kind, source.year): source for source in manifest.sources}
    rows: list[dict[str, Any]] = []
    # Cache verified bytes, not declared checksums; the same vintage can have many uses.
    hashes: dict[Path, str | None] = {}

    def assess(role: str, target_year: int, kind: SourceKind, year: int, cutoff: date) -> None:
        source = sources.get((kind, year))
        reasons = []
        actual_hash = None
        if source is None:
            reasons.append("missing_source")
        else:
            if source.published_on > cutoff:
                reasons.append("release_after_cutoff")
            if source.artifact_path is None:
                reasons.append("unverified_artifact_vintage")
            else:
                path = (manifest_path.parent / source.artifact_path).resolve()
                if path not in hashes:
                    try:
                        hashes[path] = sha256_file(path)
                    except OSError:
                        hashes[path] = None
                actual_hash = hashes[path]
                if actual_hash is None:
                    reasons.append("artifact_unreadable")
                elif actual_hash != source.artifact_sha256:
                    reasons.append("artifact_hash_mismatch")
                if source.vintage_available_on and source.vintage_available_on > cutoff:
                    reasons.append("vintage_after_cutoff")
        rows.append(
            {
                "role": role,
                "prediction_year": target_year,
                "source_kind": kind,
                "source_year": year,
                "cutoff": cutoff.isoformat(),
                "status": "blocked" if reasons else "manifest_supported",
                "reasons": reasons,
                "source": source.model_dump(mode="json") if source else None,
                "actual_artifact_sha256": actual_hash,
            }
        )

    # Geometry defines the segment population even though it is not a model covariate.
    feature_kinds: list[SourceKind] = ["network", "traffic", "urban-rural"]
    for role, sample_years in (
        ("training_features", contract.training_years),
        ("calibration_features", contract.validation_years),
        ("scoring_features", contract.test_years),
    ):
        for year in sorted(set(sample_years)):
            for kind in feature_kinds:
                assess(role, year, kind, year - lag_years, date(year - 1, 12, 31))

    # Outcome labels may follow their measurement year, but must exist before fitting
    # the final forecast. Scoring outcomes are evaluation-only, never a fitting input.
    for prediction_year in sorted(set(contract.test_years)):
        for role, label_years in (
            ("training_labels", contract.training_years),
            ("calibration_labels", contract.validation_years),
        ):
            for year in sorted(set(label_years)):
                assess(role, prediction_year, "collisions", year, date(prediction_year - 1, 12, 31))

    blocked = sum(row["status"] == "blocked" for row in rows)
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "blocked" if blocked else "source-requirements-satisfied",
        "model_promoted": False,
        "lag_years": lag_years,
        "feature_sources": FEATURE_SOURCES,
        "contract_sha256": sha256_file(contract_path),
        "manifest_sha256": sha256_file(manifest_path),
        "implementation_sha256": sha256_file(Path(__file__)),
        "requirements": len(rows),
        "blocked_requirements": blocked,
        "checks": rows,
        "limitations": [
            "Evidence URLs and source-to-artifact semantics require human verification.",
            "This preflight does not prove that a derived panel used these exact artifacts.",
            "Geographic split metadata and network matching lineage need separate audits.",
            "Scoring outcomes are evaluation-only and are not tested against forecast cutoffs.",
            "Passing this audit does not establish calibration, generalisation or model promotion.",
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "availability-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = [
        "# Forecast source availability",
        "",
        f"Status: **{report['status']}**; {blocked}/{len(rows)} requirements blocked.",
        "",
        "| Use | Forecast/sample year | Source | Cutoff | Result |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for row in rows:
        result = ", ".join(row["reasons"]) or "manifest_supported"
        lines.append(
            f"| {row['role']} | {row['prediction_year']} | "
            f"{row['source_kind']} {row['source_year']} | {row['cutoff']} | {result} |"
        )
    lines.extend(["", "## Limits", "", *[f"- {item}" for item in report["limitations"]]])
    (output / "availability-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
