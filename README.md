# EPANET Check

`epanet-check` evaluates an existing EPANET binary result file against two sets
of JSON criteria. The checking code is independent of the command-line layer so
the same files and engine can be reused by a future PyQt interface.

## Configuration files

The CLI uses three JSON files:

- `run_config.json` contains file locations and the output report name.
- `performance_criteria.json` identifies selected tanks or junctions and their
  required head, pressure, or level range.
- `general_limits.json` contains network-wide operating limits.

Paths in the run configuration may be absolute or relative to the run
configuration file. See the files in `examples` for the complete format.

Performance measurements are `head`, `pressure`, and `level`. Head and level
can use `m` or `ft`; pressure can use `m`, `psi`, or `kpa`. A criterion can
define `min`, `max`, or both. Remove a key from `general_limits.json` when that
network-wide check should be disabled.

## Commands

Launch the PyQt application:

```powershell
uv run epanet-check-gui
```

The main window loads and saves `run_config.json`. Performance criteria and
global limits are loaded and saved inside their respective dialogs. Loading a
run configuration automatically loads both referenced supporting files.

Validate the JSON and load the EPANET model without requiring a result file:

```powershell
uv run epanet-check examples/run_config.json --validate-only
```

Run all checks after setting a matching result file in `run_config.json`:

```powershell
uv run epanet-check examples/run_config.json
```

The command writes a full JSON report for the future GUI and a concise text
report containing failures and missing assets. A successful run returns exit
code 0; failed or missing checks return 1; configuration errors return 2.
Extreme EPANET sentinel values and non-finite results are reported as `INVALID`
rather than being treated as ordinary minimum or maximum failures.

Each run also exports ten CSV files containing junction, pipe, tank, pump, and
valve statistics or time series. Interactive `tanks.html`, `pumps.html`, and
`valves.html` dashboards are written to the same output folder. The dashboards
use Plotly from its public CDN, so chart rendering requires an internet
connection when an HTML file is opened.
