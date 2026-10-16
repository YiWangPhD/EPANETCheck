"""Application service shared by the command-line and graphical interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .checks import check_general_limits, check_performance
from .config import RunConfig
from .exports import export_results
from .model import load_model_and_results
from .report import build_report, write_reports


@dataclass(frozen=True)
class RunOutcome:
    report: dict[str, Any]
    json_report: Path
    text_report: Path
    exports: list[Path]


def run_checks_and_exports(
    config: RunConfig,
    performance: dict[str, Any],
    limits: dict[str, Any],
    log: Callable[[str], None] | None = None,
) -> RunOutcome:
    emit = log or (lambda _message: None)
    emit("Loading EPANET model and binary results...")
    network, results = load_model_and_results(config.inp_file, config.result_file)
    emit(
        f"Loaded {len(network.node_name_list):,} nodes and "
        f"{len(network.link_name_list):,} links."
    )
    emit("Evaluating selected performance criteria...")
    checks = check_performance(network, results, performance)
    emit("Evaluating global limits...")
    checks.extend(check_general_limits(network, results, limits))
    report = build_report(config, checks)
    emit("Writing QA/QC reports...")
    json_report, text_report = write_reports(config, report)
    emit("Exporting CSV files and interactive dashboards...")
    exports = export_results(network, results, config.output_folder, limits)
    return RunOutcome(report, json_report, text_report, exports)
