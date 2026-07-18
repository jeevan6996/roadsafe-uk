import argparse
import json
from pathlib import Path

from roadsafe.pipeline import build_pilot


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="roadsafe")
    commands = parser.add_subparsers(dest="command", required=True)
    pilot = commands.add_parser("build-pilot", help="Build the West Yorkshire pilot dataset")
    pilot.add_argument("--source", required=True, type=Path)
    pilot.add_argument("--output", required=True, type=Path)
    return parser


def main() -> None:
    args = create_parser().parse_args()
    if args.command == "build-pilot":
        report = build_pilot(args.source, args.output)
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
