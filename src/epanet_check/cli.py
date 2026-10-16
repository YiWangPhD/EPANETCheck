"""Command-line interface for EPANET checks."""

from __future__ import annotations

import argparse
import sys

from .config import ConfigError, RunConfig, load_supporting_json
from .model import load_network
from .service import run_checks_and_exports


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="epanet-check",
        description="Check an existing EPANET binary result against JSON criteria.",
    )
    parser.add_argument("config", help="Path to the run configuration JSON file")
    parser.add_argument(
        "--validate-only", action="store_true",
        help="Validate JSON files and load the INP model without reading results",
    )
    return parser


def run(config_path: str, validate_only: bool = False) -> int:
    config = RunConfig.load(config_path)
    config.validate_paths(require_result=not validate_only)
    performance, limits = load_supporting_json(config)

    if validate_only:
        network = load_network(config.inp_file)
        print(
            "Configuration is valid. "
            f"Loaded {len(network.node_name_list)} nodes and "
            f"{len(network.link_name_list)} links."
        )
        return 0

    outcome = run_checks_and_exports(config, performance, limits)
    summary = outcome.report["summary"]
    print(
        f"Completed {summary['total']} checks: {summary['PASS']} passed, "
        f"{summary['FAIL']} failed, {summary['MISSING']} missing, "
        f"{summary['INVALID']} invalid."
    )
    print(f"JSON report: {outcome.json_report}")
    print(f"Text report: {outcome.text_report}")
    print(f"Data exports: {len(outcome.exports)} files in {config.output_folder}")
    return 1 if summary["FAIL"] or summary["MISSING"] or summary["INVALID"] else 0


def main() -> None:
    args = _parser().parse_args()
    try:
        raise SystemExit(run(args.config, args.validate_only))
    except (ConfigError, ValueError, KeyError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
