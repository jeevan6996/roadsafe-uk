import argparse
import json
from pathlib import Path

from roadsafe.network import build_network_evidence
from roadsafe.pipeline import build_pilot


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="roadsafe")
    commands = parser.add_subparsers(dest="command", required=True)
    pilot = commands.add_parser("build-pilot", help="Build the West Yorkshire pilot dataset")
    pilot.add_argument("--source", required=True, type=Path)
    pilot.add_argument("--output", required=True, type=Path)
    network = commands.add_parser(
        "build-network", help="Build segment matching and traffic-exposure evidence"
    )
    network.add_argument("--collisions", required=True, type=Path)
    network.add_argument("--roads", required=True, type=Path)
    network.add_argument("--aadf", required=True, type=Path)
    network.add_argument("--output", required=True, type=Path)
    network.add_argument("--year", default=2024, type=int)
    return parser


def main() -> None:
    args = create_parser().parse_args()
    if args.command == "build-pilot":
        report = build_pilot(args.source, args.output)
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.command == "build-network":
        report = build_network_evidence(
            args.collisions, args.roads, args.aadf, args.output, args.year
        )
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
