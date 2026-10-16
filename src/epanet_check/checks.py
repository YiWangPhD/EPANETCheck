"""Reusable EPANET QA/QC checking engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from scipy.signal import find_peaks

FEET_TO_METRE = 0.3048
MLD_TO_CMS = 1_000_000 / 86_400 / 1_000
PSI_TO_METRE = 0.70307
MAX_REASONABLE_ABSOLUTE_RESULT = 1_000_000.0


@dataclass
class CheckResult:
    scope: str
    asset_type: str
    asset_id: str
    metric: str
    unit: str
    status: str
    observed_min: float | None = None
    observed_max: float | None = None
    observed_value: float | None = None
    limit_min: float | None = None
    limit_max: float | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(value: object, name: str, optional: bool = True) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"'{name}' must be a number.")
    return float(value)


def _range_result(
    *, scope: str, asset_type: str, asset_id: str, metric: str, unit: str,
    observed_min: float, observed_max: float, limit_min: float | None,
    limit_max: float | None,
) -> CheckResult:
    failures: list[str] = []
    if limit_min is not None and observed_min < limit_min:
        failures.append(f"minimum {observed_min:.3f} is below {limit_min:.3f}")
    if limit_max is not None and observed_max > limit_max:
        failures.append(f"maximum {observed_max:.3f} is above {limit_max:.3f}")
    return CheckResult(
        scope, asset_type, asset_id, metric, unit,
        "FAIL" if failures else "PASS",
        observed_min=observed_min, observed_max=observed_max,
        limit_min=limit_min, limit_max=limit_max,
        message="; ".join(failures) if failures else "Within limits",
    )


def _series_range_result(
    *, scope: str, asset_type: str, asset_id: str, metric: str, unit: str,
    series, limit_min: float | None, limit_max: float | None,
) -> CheckResult:
    values = np.asarray(series, dtype=float)
    invalid = ~np.isfinite(values) | (np.abs(values) > MAX_REASONABLE_ABSOLUTE_RESULT)
    if invalid.any():
        return CheckResult(
            scope, asset_type, asset_id, metric, unit, "INVALID",
            limit_min=limit_min, limit_max=limit_max,
            message=f"Result contains {int(invalid.sum())} missing or invalid value(s)",
        )
    return _range_result(
        scope=scope, asset_type=asset_type, asset_id=asset_id, metric=metric,
        unit=unit, observed_min=float(values.min()), observed_max=float(values.max()),
        limit_min=limit_min, limit_max=limit_max,
    )


def _maximum_result(
    *, scope: str, asset_type: str, asset_id: str, metric: str, unit: str,
    value: float, maximum: float,
) -> CheckResult:
    failed = value > maximum
    return CheckResult(
        scope, asset_type, asset_id, metric, unit, "FAIL" if failed else "PASS",
        observed_value=value, limit_max=maximum,
        message=(f"{value:.3f} is above {maximum:.3f}" if failed else "Within limit"),
    )


def _series_for_metric(network, results, asset_id: str, metric: str, unit: str | None):
    # Backward compatibility with the first JSON format, where the unit was
    # embedded in the metric name.
    legacy = {
        "head_ft": ("head", "ft"),
        "pressure_psi": ("pressure", "psi"),
        "level_ft": ("level", "ft"),
    }
    metric, unit = legacy.get(metric, (metric, unit))
    if metric == "head":
        values = results.node["head"][asset_id]
        allowed = {"m": values, "ft": values / FEET_TO_METRE}
    elif metric == "pressure":
        values = results.node["pressure"][asset_id]
        allowed = {
            "m": values,
            "psi": values / PSI_TO_METRE,
            "kpa": values * 9.80665,
        }
    elif metric == "level":
        values = results.node["head"][asset_id] - network.get_node(asset_id).elevation
        allowed = {"m": values, "ft": values / FEET_TO_METRE}
    else:
        raise ValueError(f"Unknown performance metric '{metric}'.")
    normalized_unit = (unit or "m").lower()
    if normalized_unit not in allowed:
        raise ValueError(f"Unit '{unit}' is not valid for performance metric '{metric}'.")
    return allowed[normalized_unit], normalized_unit


def check_performance(network, results, config: dict[str, Any]) -> list[CheckResult]:
    output: list[CheckResult] = []
    node_names = set(network.node_name_list)
    for index, item in enumerate(config["criteria"]):
        if not isinstance(item, dict):
            raise ValueError(f"criteria[{index}] must be an object.")
        asset_id = str(item.get("asset_id", "")).strip()
        asset_type = str(item.get("asset_type", "node")).strip().lower()
        metric = str(item.get("metric", "head_ft")).strip().lower()
        unit = str(item.get("unit", "")).strip().lower() or None
        minimum = _number(item.get("min"), f"criteria[{index}].min")
        maximum = _number(item.get("max"), f"criteria[{index}].max")
        if not asset_id:
            raise ValueError(f"criteria[{index}].asset_id cannot be empty.")
        if minimum is None and maximum is None:
            raise ValueError(f"criteria[{index}] must define 'min', 'max', or both.")
        if asset_id not in node_names:
            output.append(CheckResult(
                "performance", asset_type, asset_id, metric, "", "MISSING",
                limit_min=minimum, limit_max=maximum,
                message="Asset is not present in the model",
            ))
            continue
        series, unit = _series_for_metric(network, results, asset_id, metric, unit)
        output.append(_series_range_result(
            scope="performance", asset_type=asset_type, asset_id=asset_id,
            metric=metric, unit=unit, series=series,
            limit_min=minimum, limit_max=maximum,
        ))
    return output


def check_general_limits(network, results, config: dict[str, Any]) -> list[CheckResult]:
    limits = config["limits"]
    output: list[CheckResult] = []
    duration_hours = float(results.node["head"].index.max()) / 3600
    simulation_days = duration_hours / 24 if duration_hours > 0 else 1.0

    pressure_limit = limits.get("junction_pressure_psi")
    if pressure_limit is not None:
        pressure = results.node["pressure"] / PSI_TO_METRE
        low = _number(pressure_limit.get("min"), "junction_pressure_psi.min")
        high = _number(pressure_limit.get("max"), "junction_pressure_psi.max")
        for asset_id in network.junction_name_list:
            series = pressure[asset_id]
            output.append(_series_range_result(
                scope="general", asset_type="junction", asset_id=asset_id,
                metric="pressure_psi", unit="psi", series=series,
                limit_min=low, limit_max=high,
            ))

    tank_limit = limits.get("tank_level_ft")
    cycle_limit = limits.get("tank_cycles_per_day")
    for asset_id in network.tank_name_list:
        level = (results.node["head"][asset_id] - network.get_node(asset_id).elevation) / FEET_TO_METRE
        if tank_limit is not None:
            output.append(_series_range_result(
                scope="general", asset_type="tank", asset_id=asset_id,
                metric="level_ft", unit="ft", series=level,
                limit_min=_number(tank_limit.get("min"), "tank_level_ft.min"),
                limit_max=_number(tank_limit.get("max"), "tank_level_ft.max"),
            ))
        if cycle_limit is not None:
            prominence = _number(
                cycle_limit.get("prominence", cycle_limit.get("prominence_ft", 0.5)),
                "tank_cycles_per_day.prominence", optional=False,
            )
            maximum = _number(cycle_limit.get("max"), "tank_cycles_per_day.max", optional=False)
            peaks, _ = find_peaks(level.to_numpy(), prominence=prominence)
            valleys, _ = find_peaks(-level.to_numpy(), prominence=prominence)
            cycles_per_day = min(len(peaks), len(valleys)) / simulation_days
            output.append(_maximum_result(
                scope="general", asset_type="tank", asset_id=asset_id,
                metric="cycles_per_day", unit="cycles/day",
                value=float(cycles_per_day), maximum=maximum,
            ))

    flow = results.link["flowrate"] / MLD_TO_CMS
    status = results.link["status"]
    velocity = results.link["velocity"] / FEET_TO_METRE

    pump_flow_limit = limits.get("pump_max_abs_flow_mld")
    pump_start_limit = limits.get("pump_starts_per_day")
    for asset_id in network.pump_name_list:
        if pump_flow_limit is not None:
            output.append(_maximum_result(
                scope="general", asset_type="pump", asset_id=asset_id,
                metric="max_abs_flow_mld", unit="MLD",
                value=float(flow[asset_id].abs().max()),
                maximum=_number(pump_flow_limit.get("max"), "pump_max_abs_flow_mld.max", optional=False),
            ))
        if pump_start_limit is not None:
            binary = (status[asset_id] > 0).astype(int)
            starts_per_day = float((binary.diff() == 1).sum()) / simulation_days
            output.append(_maximum_result(
                scope="general", asset_type="pump", asset_id=asset_id,
                metric="starts_per_day", unit="starts/day", value=starts_per_day,
                maximum=_number(pump_start_limit.get("max"), "pump_starts_per_day.max", optional=False),
            ))

    valve_limit = limits.get("valve_max_abs_flow_mld")
    if valve_limit is not None:
        maximum = _number(valve_limit.get("max"), "valve_max_abs_flow_mld.max", optional=False)
        for asset_id in network.valve_name_list:
            output.append(_maximum_result(
                scope="general", asset_type="valve", asset_id=asset_id,
                metric="max_abs_flow_mld", unit="MLD",
                value=float(flow[asset_id].abs().max()), maximum=maximum,
            ))

    pipe_flow_limit = limits.get("pipe_max_abs_flow_mld")
    pipe_velocity_limit = limits.get("pipe_max_abs_velocity_fps")
    reversal_limit = limits.get("pipe_flow_reversals_per_day")
    for asset_id in network.pipe_name_list:
        if pipe_flow_limit is not None:
            output.append(_maximum_result(
                scope="general", asset_type="pipe", asset_id=asset_id,
                metric="max_abs_flow_mld", unit="MLD",
                value=float(flow[asset_id].abs().max()),
                maximum=_number(pipe_flow_limit.get("max"), "pipe_max_abs_flow_mld.max", optional=False),
            ))
        if pipe_velocity_limit is not None:
            output.append(_maximum_result(
                scope="general", asset_type="pipe", asset_id=asset_id,
                metric="max_abs_velocity_fps", unit="ft/s",
                value=float(velocity[asset_id].abs().max()),
                maximum=_number(pipe_velocity_limit.get("max"), "pipe_max_abs_velocity_fps.max", optional=False),
            ))
        if reversal_limit is not None:
            signs = np.sign(flow[asset_id]).replace(0, np.nan).ffill().bfill()
            reversals_per_day = float((signs.diff().abs() == 2).sum()) / simulation_days
            output.append(_maximum_result(
                scope="general", asset_type="pipe", asset_id=asset_id,
                metric="flow_reversals_per_day", unit="reversals/day",
                value=reversals_per_day,
                maximum=_number(reversal_limit.get("max"), "pipe_flow_reversals_per_day.max", optional=False),
            ))
    return output
