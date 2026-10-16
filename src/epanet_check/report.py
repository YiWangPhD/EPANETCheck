"""Write machine-readable and human-readable check reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .checks import CheckResult
from .config import RunConfig


def build_report(config: RunConfig, checks: list[CheckResult]) -> dict:
    counts = {
        status: sum(item.status == status for item in checks)
        for status in ("PASS", "FAIL", "MISSING", "INVALID")
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "inp_file": str(config.inp_file),
            "result_file": str(config.result_file),
            "performance_criteria_file": str(config.performance_criteria_file),
            "limits_file": str(config.limits_file),
        },
        "summary": {"total": len(checks), **counts},
        "checks": [item.to_dict() for item in checks],
    }


def write_reports(config: RunConfig, report: dict) -> tuple[Path, Path]:
    config.output_folder.mkdir(parents=True, exist_ok=True)
    json_path = config.output_folder / f"{config.report_name}.json"
    text_path = config.output_folder / f"{config.report_name}.txt"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    summary = report["summary"]
    lines = [
        "EPANET CHECK REPORT",
        "=" * 60,
        f"Checks: {summary['total']}  Passed: {summary['PASS']}  "
        f"Failed: {summary['FAIL']}  Missing: {summary['MISSING']}  "
        f"Invalid: {summary['INVALID']}",
        "",
        "ISSUES",
        "=" * 60,
    ]
    issues = [item for item in report["checks"] if item["status"] != "PASS"]
    if not issues:
        lines.append("No issues found.")
    for item in issues:
        lines.append(
            f"{item['status']:7} | {item['scope']:11} | {item['asset_type']:8} | "
            f"{item['asset_id']:20} | {item['metric']}: {item['message']}"
        )
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, text_path
