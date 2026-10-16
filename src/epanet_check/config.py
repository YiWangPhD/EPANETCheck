"""Configuration loading and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when a configuration file is incomplete or invalid."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except FileNotFoundError as exc:
        raise ConfigError(f"JSON file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Invalid JSON in {path} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(value, dict):
        raise ConfigError(f"The top level of {path} must be a JSON object.")
    return value


def _resolve(base: Path, value: object, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"'{field}' must be a non-empty path string.")
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


@dataclass(frozen=True)
class RunConfig:
    config_path: Path
    output_folder: Path
    inp_file: Path
    result_file: Path
    performance_criteria_file: Path
    limits_file: Path
    report_name: str

    @classmethod
    def load(cls, config_path: str | Path) -> "RunConfig":
        path = Path(config_path).expanduser().resolve()
        data = _read_json(path)
        base = path.parent
        report_name = data.get("report_name", "epanet_check_report")
        if not isinstance(report_name, str) or not report_name.strip():
            raise ConfigError("'report_name' must be a non-empty string.")
        if Path(report_name).name != report_name:
            raise ConfigError("'report_name' must be a filename stem, not a path.")

        return cls(
            config_path=path,
            output_folder=_resolve(base, data.get("output_folder"), "output_folder"),
            inp_file=_resolve(base, data.get("inp_file"), "inp_file"),
            result_file=_resolve(base, data.get("result_file"), "result_file"),
            performance_criteria_file=_resolve(
                base, data.get("performance_criteria_file"), "performance_criteria_file"
            ),
            limits_file=_resolve(base, data.get("limits_file"), "limits_file"),
            report_name=report_name,
        )

    def validate_paths(self, require_result: bool = True) -> None:
        required = [
            ("inp_file", self.inp_file),
            ("performance_criteria_file", self.performance_criteria_file),
            ("limits_file", self.limits_file),
        ]
        if require_result:
            required.append(("result_file", self.result_file))
        missing = [f"{name}: {path}" for name, path in required if not path.is_file()]
        if missing:
            raise ConfigError("Missing required file(s):\n  " + "\n  ".join(missing))


def load_supporting_json(config: RunConfig) -> tuple[dict[str, Any], dict[str, Any]]:
    performance = _read_json(config.performance_criteria_file)
    limits = _read_json(config.limits_file)
    criteria = performance.get("criteria")
    if not isinstance(criteria, list):
        raise ConfigError("Performance criteria JSON must contain a 'criteria' array.")
    if not isinstance(limits.get("limits"), dict):
        raise ConfigError("Limits JSON must contain a 'limits' object.")
    return performance, limits
