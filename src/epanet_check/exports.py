"""Export EPANET statistics, time series, and interactive dashboards."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from .checks import FEET_TO_METRE, MAX_REASONABLE_ABSOLUTE_RESULT, MLD_TO_CMS, PSI_TO_METRE


def _clean(frame: pd.DataFrame | pd.Series):
    """Replace non-finite and EPANET sentinel values with missing values."""
    return frame.mask(~np.isfinite(frame) | (frame.abs() > MAX_REASONABLE_ABSOLUTE_RESULT))


def _dashboard_html(
    stats: pd.DataFrame,
    time_series: pd.DataFrame,
    *,
    title: str,
    asset_column: str,
    sort_column: str,
    y_axis_title: str,
    top_n: int = 20,
) -> str:
    table = stats.copy()
    table["Group"] = table[asset_column].astype(str).map(
        lambda asset: asset.split("-", 1)[0] if "-" in asset else asset
    )
    stats_data = json.loads(table.round(3).to_json(orient="records"))
    series_data = {
        str(column): [None if pd.isna(value) else float(value) for value in time_series[column]]
        for column in time_series.columns
    }
    time_values = [float(value) if isinstance(value, (int, float, np.number)) else str(value)
                   for value in time_series.index]
    groups = sorted(table["Group"].astype(str).unique().tolist())

    def js(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }}
h1 {{ margin-bottom: 6px; }}
.note {{ color: #6b7280; margin-top: 0; }}
.controls {{ display: flex; gap: 10px; margin: 20px 0; }}
select, button {{ padding: 7px 10px; }}
.table-wrap {{ max-height: 420px; overflow: auto; border: 1px solid #d1d5db; }}
table {{ border-collapse: collapse; width: 100%; }}
th {{ position: sticky; top: 0; background: #f3f4f6; }}
th, td {{ border-bottom: 1px solid #e5e7eb; padding: 7px; text-align: left; }}
#chart {{ width: 100%; height: 700px; margin-top: 24px; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="note">Select an asset group or show the highest-ranked assets.</p>
<div class="controls">
  <select id="group"></select>
  <button id="top">Show top {top_n}</button>
</div>
<div class="table-wrap"><table id="stats"></table></div>
<div id="chart"></div>
<script>
const stats = {js(stats_data)};
const series = {js(series_data)};
const times = {js(time_values)};
const groups = {js(groups)};
const assetField = {js(asset_column)};
const sortField = {js(sort_column)};
const groupSelect = document.getElementById("group");

groups.forEach(group => {{
  const option = document.createElement("option");
  option.value = group;
  option.textContent = group;
  groupSelect.appendChild(option);
}});

function drawTable(rows) {{
  if (!rows.length) {{ document.getElementById("stats").innerHTML = ""; return; }}
  const columns = Object.keys(rows[0]);
  const head = `<tr>${{columns.map(c => `<th>${{c}}</th>`).join("")}}</tr>`;
  const body = rows.map(row => `<tr>${{columns.map(c => `<td>${{row[c] ?? ""}}</td>`).join("")}}</tr>`).join("");
  document.getElementById("stats").innerHTML = head + body;
}}

function drawChart(rows, chartTitle) {{
  const traces = rows.filter(row => series[row[assetField]]).map(row => ({{
    x: times, y: series[row[assetField]], mode: "lines", name: row[assetField]
  }}));
  Plotly.newPlot("chart", traces, {{
    title: chartTitle,
    xaxis: {{ title: {js(time_series.index.name or "Time")} }},
    yaxis: {{ title: {js(y_axis_title)} }},
    hovermode: "x unified"
  }}, {{ responsive: true }});
}}

function showGroup() {{
  const group = groupSelect.value;
  const rows = stats.filter(row => row.Group === group);
  drawTable(rows);
  drawChart(rows, `${{group}} group`);
}}

document.getElementById("top").addEventListener("click", () => {{
  const rows = [...stats].sort((a, b) => Number(b[sortField]) - Number(a[sortField])).slice(0, {top_n});
  drawTable(stats);
  drawChart(rows, `Top {top_n} assets by ${{sortField}}`);
}});
groupSelect.addEventListener("change", showGroup);
if (groups.length) showGroup();
</script>
</body>
</html>
"""


def export_results(
    network,
    results,
    output_folder: Path,
    limits_config: dict[str, Any] | None = None,
) -> list[Path]:
    """Write the CSV files and HTML dashboards used by the CLI and future GUI."""
    output_folder.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    pressure = _clean(results.node["pressure"] / PSI_TO_METRE)
    junction_stats = pd.DataFrame({
        "Junction": network.junction_name_list,
        "MinPressure(psi)": [pressure[name].min() for name in network.junction_name_list],
        "MaxPressure(psi)": [pressure[name].max() for name in network.junction_name_list],
    })

    pipe_names = network.pipe_name_list
    headloss = _clean(results.link["headloss"] * 1000)
    flow = _clean(results.link["flowrate"] / MLD_TO_CMS)
    velocity = _clean(results.link["velocity"] / FEET_TO_METRE)
    pipe_stats = pd.DataFrame({
        "Pipe": pipe_names,
        "MaxHeadLoss(m/km)": [headloss[name].max() for name in pipe_names],
        "MaxAbsFlow(MLD)": [flow[name].abs().max() for name in pipe_names],
        "MaxAbsVelocity(fps)": [velocity[name].abs().max() for name in pipe_names],
    })

    prominence = 0.5
    if limits_config:
        prominence = float(
            limits_config.get("limits", {}).get("tank_cycles_per_day", {}).get(
                "prominence",
                limits_config.get("limits", {}).get("tank_cycles_per_day", {}).get(
                    "prominence_ft", prominence
                ),
            )
        )
    tank_levels = pd.DataFrame(index=results.node["head"].index)
    tank_rows: list[dict[str, Any]] = []
    for name in network.tank_name_list:
        level = _clean((results.node["head"][name] - network.get_node(name).elevation) / FEET_TO_METRE)
        tank_levels[name] = level
        valid = level.dropna().to_numpy()
        peaks, _ = find_peaks(valid, prominence=prominence)
        valleys, _ = find_peaks(-valid, prominence=prominence)
        tank_rows.append({
            "Tank": name,
            "NumCycles": min(len(peaks), len(valleys)),
            "NumPeaks": len(peaks),
            "NumValleys": len(valleys),
            "MinLevel(ft)": level.min(),
            "MaxLevel(ft)": level.max(),
            "LevelRange(ft)": level.max() - level.min(),
        })
    tank_stats = pd.DataFrame(tank_rows)
    tank_levels.index = tank_levels.index / 3600
    tank_levels.index.name = "Time_hr"

    pump_names = network.pump_name_list
    pump_flow = flow[pump_names].copy()
    pump_status = results.link["status"][pump_names].copy()
    pump_rows: list[dict[str, Any]] = []
    for name in pump_names:
        is_on = pump_status[name] > 0
        series = pump_flow[name]
        pump_rows.append({
            "Pump": name,
            "MinFlow(MLD)": series.min(),
            "MaxFlow(MLD)": series.max(),
            "AvgFlow(MLD)": series.mean(),
            "AvgFlow_When_On(MLD)": series[is_on].mean() if is_on.any() else 0.0,
            "FlowRange(MLD)": series.max() - series.min(),
            "Percent_ON": 100 * is_on.mean(),
        })
    pump_stats = pd.DataFrame(pump_rows)
    pump_flow.index = pump_flow.index / 3600
    pump_flow.index.name = "Time_hr"
    pump_status.index = pump_status.index / 3600
    pump_status.index.name = "Time_hr"

    valve_names = network.valve_name_list
    valve_flow = flow[valve_names].copy()
    valve_status = results.link["status"][valve_names].copy()
    valve_rows: list[dict[str, Any]] = []
    for name in valve_names:
        is_open = valve_status[name] > 0
        series = valve_flow[name]
        valve_rows.append({
            "Valve": name,
            "MinFlow(MLD)": series.min(),
            "MaxFlow(MLD)": series.max(),
            "AvgFlow(MLD)": series.mean(),
            "MaxAbsFlow(MLD)": series.abs().max(),
            "Percent_Open": 100 * is_open.mean(),
        })
    valve_stats = pd.DataFrame(valve_rows)
    valve_flow.index = valve_flow.index / 3600
    valve_flow.index.name = "Time_hr"
    valve_status.index = valve_status.index / 3600
    valve_status.index.name = "Time_hr"

    csv_exports = {
        "junction_stats.csv": (junction_stats, False),
        "pipe_stats.csv": (pipe_stats, False),
        "tank_stats.csv": (tank_stats, False),
        "tank_levels.csv": (tank_levels, True),
        "pump_stats.csv": (pump_stats, False),
        "pump_status.csv": (pump_status, True),
        "pump_discharges.csv": (pump_flow, True),
        "valve_stats.csv": (valve_stats, False),
        "valve_status.csv": (valve_status, True),
        "valve_discharges.csv": (valve_flow, True),
    }
    for filename, (frame, include_index) in csv_exports.items():
        path = output_folder / filename
        frame.to_csv(path, index=include_index)
        created.append(path)

    dashboards = [
        ("tanks.html", tank_stats, tank_levels, "Tank Results", "Tank", "NumCycles", "Level (ft)", 30),
        ("pumps.html", pump_stats, pump_flow, "Pump Results", "Pump", "AvgFlow(MLD)", "Flow (MLD)", 20),
        ("valves.html", valve_stats, valve_flow, "Valve Results", "Valve", "AvgFlow(MLD)", "Flow (MLD)", 20),
    ]
    for filename, stats, series, title, asset, sort, axis, top_n in dashboards:
        path = output_folder / filename
        path.write_text(
            _dashboard_html(
                stats, series, title=title, asset_column=asset,
                sort_column=sort, y_axis_title=axis, top_n=top_n,
            ),
            encoding="utf-8",
        )
        created.append(path)
    return created
