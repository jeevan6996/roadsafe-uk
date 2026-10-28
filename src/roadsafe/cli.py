import argparse
import json
from pathlib import Path

import polars as pl

from roadsafe.acquisition import (
    SOURCE_KINDS,
    AcquisitionError,
    SourceKind,
    acquire_sources,
)
from roadsafe.availability import audit_availability
from roadsafe.baseline import BaselineValidationError, build_exposure_baseline
from roadsafe.bundle import build_demo_bundle, load_demo_bundle
from roadsafe.empirical_bayes import EmpiricalBayesValidationError, build_empirical_bayes_screening
from roadsafe.evaluation import build_segment_year_panel
from roadsafe.experiments import run_poc_bundle
from roadsafe.features import FeatureValidationError, build_lagged_feature_panel
from roadsafe.network import build_network_evidence
from roadsafe.orchestration import build_contract_evidence
from roadsafe.pipeline import build_pilot
from roadsafe.screening import build_descriptive_screening
from roadsafe.spf import SPFValidationError, build_count_spf


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="roadsafe")
    commands = parser.add_subparsers(dest="command", required=True)
    bundle = commands.add_parser(
        "build-demo-bundle", help="Package verified 2024 serving artifacts"
    )
    bundle.add_argument("--collisions", required=True, type=Path)
    bundle.add_argument("--network", required=True, type=Path)
    bundle.add_argument("--empirical-bayes", type=Path)
    bundle.add_argument("--profile", required=True, choices=["fixture", "pilot"])
    bundle.add_argument("--output", required=True, type=Path)
    verify = commands.add_parser("verify-demo-bundle", help="Verify demo artifact hashes and scope")
    verify.add_argument("--bundle", required=True, type=Path)
    experiment = commands.add_parser(
        "run-poc-bundle", help="Audit source availability before the fixed count-model POC"
    )
    experiment.add_argument("--panel", required=True, type=Path)
    experiment.add_argument("--contract", required=True, type=Path)
    experiment.add_argument("--manifest", required=True, type=Path)
    experiment.add_argument("--output", required=True, type=Path)
    experiment.add_argument(
        "--allow-exploratory", action="store_true", help="Run despite blocked source checks"
    )
    availability = commands.add_parser(
        "audit-availability", help="Check publication and artifact vintages before forecasting"
    )
    availability.add_argument("--contract", required=True, type=Path)
    availability.add_argument("--manifest", required=True, type=Path)
    availability.add_argument("--output", required=True, type=Path)
    availability.add_argument("--lag-years", default=2, type=int)
    fetch = commands.add_parser(
        "fetch-sources", help="Acquire official DfT inputs with provenance manifests"
    )
    fetch.add_argument("--years", required=True, nargs="+", type=int)
    fetch.add_argument("--kinds", nargs="+", choices=SOURCE_KINDS, default=list(SOURCE_KINDS))
    fetch.add_argument("--output", required=True, type=Path)
    fetch.add_argument("--refresh", action="store_true")
    pilot = commands.add_parser("build-pilot", help="Build the West Yorkshire pilot dataset")
    pilot.add_argument("--source", required=True, type=Path)
    pilot.add_argument("--output", required=True, type=Path)
    pilot.add_argument("--year", type=int)
    network = commands.add_parser(
        "build-network", help="Build segment matching and traffic-exposure evidence"
    )
    network.add_argument("--collisions", required=True, type=Path)
    network.add_argument("--roads", required=True, type=Path)
    network.add_argument("--aadf", required=True, type=Path)
    network.add_argument("--urban-rural", type=Path)
    network.add_argument("--output", required=True, type=Path)
    network.add_argument("--year", default=2024, type=int)
    panel = commands.add_parser(
        "build-panel", help="Build and assess a longitudinal segment-year evidence panel"
    )
    panel.add_argument("--evidence", required=True, nargs="+", type=Path)
    panel.add_argument("--contract", required=True, type=Path)
    panel.add_argument("--output", required=True, type=Path)
    features = commands.add_parser(
        "build-lagged-panel", help="Build exact-year historical features for exploratory backtests"
    )
    features.add_argument("--panel", required=True, type=Path)
    features.add_argument("--contract", required=True, type=Path)
    features.add_argument("--output", required=True, type=Path)
    features.add_argument("--lag-years", default=1, type=int)
    screening = commands.add_parser(
        "build-screening",
        help="Build observed exposure-normalized descriptive screening artifacts",
    )
    screening.add_argument("--panel", required=True, type=Path)
    screening.add_argument("--output", required=True, type=Path)
    baseline = commands.add_parser(
        "build-baseline", help="Evaluate the transparent exposure-rate baseline"
    )
    baseline.add_argument("--panel", required=True, type=Path)
    baseline.add_argument("--contract", required=True, type=Path)
    baseline.add_argument("--output", required=True, type=Path)
    spf = commands.add_parser(
        "build-spf", help="Evaluate the negative-binomial Safety Performance Function"
    )
    spf.add_argument("--panel", required=True, type=Path)
    spf.add_argument("--contract", required=True, type=Path)
    spf.add_argument("--output", required=True, type=Path)
    spf.add_argument(
        "--model", choices=["negative-binomial", "ridge-poisson"], default="negative-binomial"
    )
    spf.add_argument("--ridge-alpha", default=0.01, type=float)
    empirical_bayes = commands.add_parser(
        "build-empirical-bayes",
        help="Build retrospective Poisson-gamma Empirical Bayes screening artifacts",
    )
    empirical_bayes.add_argument("--panel", required=True, type=Path)
    empirical_bayes.add_argument("--contract", required=True, type=Path)
    empirical_bayes.add_argument("--output", required=True, type=Path)
    contract = commands.add_parser(
        "build-contract", help="Build annual evidence for every year in an evaluation contract"
    )
    contract.add_argument("--collision-template", required=True)
    contract.add_argument("--historical-collision-source", type=Path)
    contract.add_argument("--road-template", required=True)
    contract.add_argument("--aadf", required=True, type=Path)
    contract.add_argument("--urban-rural", type=Path)
    contract.add_argument("--contract", required=True, type=Path)
    contract.add_argument("--output", required=True, type=Path)
    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()
    if args.command in {"build-demo-bundle", "verify-demo-bundle"}:
        try:
            bundle = (
                load_demo_bundle(args.bundle)
                if args.command == "verify-demo-bundle"
                else build_demo_bundle(
                    args.collisions, args.network, args.output, args.profile, args.empirical_bayes
                )
            )
        except (ValueError, OSError, pl.exceptions.PolarsError) as error:
            parser.error(str(error))
        print(bundle.model_dump_json(indent=2))
    elif args.command == "run-poc-bundle":
        try:
            report = run_poc_bundle(
                args.panel,
                args.contract,
                args.manifest,
                args.output,
                allow_exploratory=args.allow_exploratory,
            )
        except (ValueError, OSError, RuntimeError, ImportError) as error:
            parser.error(str(error))
        print(json.dumps(report, indent=2, sort_keys=True))
        if report["status"] != "completed-exploratory":
            raise SystemExit(1)
    elif args.command == "audit-availability":
        try:
            report = audit_availability(args.contract, args.manifest, args.output, args.lag_years)
        except (ValueError, OSError) as error:
            parser.error(str(error))
        print(json.dumps(report, indent=2, sort_keys=True))
        if report["status"] == "blocked":
            raise SystemExit(1)
    elif args.command == "fetch-sources":
        try:
            report = acquire_sources(
                args.years, args.output, set[SourceKind](args.kinds), args.refresh
            )
        except AcquisitionError as error:
            parser.error(str(error))
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "build-pilot":
        report = build_pilot(args.source, args.output, args.year)
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "build-network":
        report = build_network_evidence(
            args.collisions, args.roads, args.aadf, args.output, args.year, args.urban_rural
        )
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "build-panel":
        report = build_segment_year_panel(args.evidence, args.contract, args.output)
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "build-screening":
        report = build_descriptive_screening(args.panel, args.output)
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "build-lagged-panel":
        try:
            report = build_lagged_feature_panel(
                args.panel, args.contract, args.output, args.lag_years
            )
        except FeatureValidationError as error:
            parser.error(str(error))
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "build-baseline":
        try:
            report = build_exposure_baseline(args.panel, args.contract, args.output)
        except BaselineValidationError as error:
            parser.error(str(error))
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "build-spf":
        try:
            report = build_count_spf(
                args.panel,
                args.contract,
                args.output,
                model_kind=args.model,
                ridge_alpha=args.ridge_alpha,
            )
        except SPFValidationError as error:
            parser.error(str(error))
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "build-empirical-bayes":
        try:
            report = build_empirical_bayes_screening(args.panel, args.contract, args.output)
        except EmpiricalBayesValidationError as error:
            parser.error(str(error))
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "build-contract":
        report = build_contract_evidence(
            args.collision_template,
            args.road_template,
            args.aadf,
            args.contract,
            args.output,
            args.historical_collision_source,
            args.urban_rural,
        )
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
