import argparse
import json
from pathlib import Path

from roadsafe.acquisition import (
    SOURCE_KINDS,
    AcquisitionError,
    SourceKind,
    acquire_sources,
)
from roadsafe.evaluation import build_segment_year_panel
from roadsafe.network import build_network_evidence
from roadsafe.orchestration import build_contract_evidence
from roadsafe.pipeline import build_pilot


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="roadsafe")
    commands = parser.add_subparsers(dest="command", required=True)
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
    network.add_argument("--output", required=True, type=Path)
    network.add_argument("--year", default=2024, type=int)
    panel = commands.add_parser(
        "build-panel", help="Build and assess a longitudinal segment-year evidence panel"
    )
    panel.add_argument("--evidence", required=True, nargs="+", type=Path)
    panel.add_argument("--contract", required=True, type=Path)
    panel.add_argument("--output", required=True, type=Path)
    contract = commands.add_parser(
        "build-contract", help="Build annual evidence for every year in an evaluation contract"
    )
    contract.add_argument("--collision-template", required=True)
    contract.add_argument("--historical-collision-source", type=Path)
    contract.add_argument("--road-template", required=True)
    contract.add_argument("--aadf", required=True, type=Path)
    contract.add_argument("--contract", required=True, type=Path)
    contract.add_argument("--output", required=True, type=Path)
    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()
    if args.command == "fetch-sources":
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
            args.collisions, args.roads, args.aadf, args.output, args.year
        )
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "build-panel":
        report = build_segment_year_panel(args.evidence, args.contract, args.output)
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "build-contract":
        report = build_contract_evidence(
            args.collision_template,
            args.road_template,
            args.aadf,
            args.contract,
            args.output,
            args.historical_collision_source,
        )
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
