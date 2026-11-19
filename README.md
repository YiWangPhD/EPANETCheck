# EPANET Check

`epanet-check` evaluates an existing EPANET binary result file against two sets
of JSON criteria. It provides a PyQt6 desktop application and a command-line
interface that share the same checking and export engine. It reads an existing
simulation result; it does not run a new EPANET simulation.

## Installation

Requires Python 3.13 or later. The package depends on PyQt6 and WNTR.

From the repository folder, install the project dependencies:

```powershell
uv sync --locked
```

To install a built wheel into an existing compatible Python environment, activate
that environment and run:

```powershell
python -m pip install dist/epanet_check-0.1.0-py3-none-any.whl
```

For an ArcGIS Pro Python environment, use a cloned environment with a compatible
Python version. The desktop application runs as an independent window.

## Desktop application

Launch from the repository:

```powershell
uv run epanet-check-gui
```

After installing the wheel, launch with `epanet-check-gui` from the activated
environment.

1. Select a project folder for the outputs, an EPANET input file (`.inp`), and
   its matching binary result file (`.tmp`, `.bin`, or `.out`).
2. Review the Performance Criteria and Global Limits dialogs.
3. Click Run Checks and Export. Progress and the result summary appear in the log.
4. Use Open Output Folder or the Tank, Pump, and Valve dashboard buttons to
   inspect the outputs.

Analysis runs in a background thread so the interface can remain responsive.

### Performance Criteria

The GUI automatically loads **71 checks: 23 junction checks and 48 tank checks**,
based on the supplied `pressure_checklist.csv`. These are hydraulic **head**
thresholds in **feet**, including the tank checks. The defaults are bundled in
`src/epanet_check/defaults/performance_criteria.json` and included in the wheel,
so loading them does not require the example folder or CSV.

- Select one table row to populate the editor above the table.
- Edit the asset type, ID, measurement, unit, minimum/maximum, or limit in the
  editor to update that row immediately.
- Click New Criterion to clear the selection, fill in the editor, then click Add
  to create a separate check. New checks require an asset ID from the selected
  input model.
- Select one or more rows and click Remove Selected to delete them.
- Use Load JSON to replace the current criteria, or Save JSON to keep your edits.

Edits take effect for the current run immediately; saving JSON makes them
persistent. The bundled default file is not overwritten when saving your first
copy. Loading a run configuration replaces the current criteria with those in
its referenced file.

### Global Limits

The limits are arranged in two rows of compact category boxes:

| First row | Second row |
| --- | --- |
| Junction, Pipe, Pump | Tank, Valve |

Type values directly into the numeric fields; the up/down spinner arrows are
hidden. Each box is approximately 170 pixels tall, expanding if its contents
require more space. Use Load JSON and Save JSON to manage the limits file.

### Save and load a run configuration

The main window loads and saves `run_config.json`. Loading a configuration fills
in the model and output paths and loads both supporting JSON files. The referenced
paths are checked independently. Missing paths are left empty and errors appear
in the Log; missing or unreadable supporting JSON files reset their editors to
built-in defaults. Correct missing model paths before running. CLI path validation
remains strict.

Save the Performance Criteria and Global Limits JSON files in their dialogs
before saving a run configuration. Runs can also use the current in-memory
criteria and limits without saving a configuration first.

## Configuration files

The CLI uses three JSON files:

- `run_config.json` contains file locations and the output report name.
- `performance_criteria.json` identifies selected tanks or junctions and their
  required head, pressure, or level range.
- `general_limits.json` contains network-wide operating limits.

Paths in the run configuration may be absolute or relative to the run
configuration file. Local example files may be available in `examples`; this
folder is not included in the wheel. A run configuration has this structure:

```json
{
  "output_folder": "output",
  "inp_file": "model.inp",
  "result_file": "model.out",
  "performance_criteria_file": "performance_criteria.json",
  "limits_file": "general_limits.json",
  "report_name": "epanet_check_report"
}
```

Performance measurements are `head`, `pressure`, and `level`. Head and level
can use `m` or `ft`; pressure can use `m`, `psi`, or `kpa`. A criterion can
define `min`, `max`, or both. Remove a key from `general_limits.json` when that
network-wide check should be disabled for a CLI run. The Global Limits editor
populates all supported fields with values when loading a file, so saving from
that dialog restores any omitted fields with their defaults.

For example, a performance criteria file can contain:

```json
{
  "criteria": [
    {
      "asset_type": "junction",
      "asset_id": "44AM-1020",
      "metric": "head",
      "unit": "ft",
      "min": 560.0
    }
  ]
}
```

## Command-line usage

The CLI uses the criteria file referenced by the run configuration; it does not
automatically substitute the GUI's bundled defaults.

Validate the JSON and load the EPANET model without requiring a result file:

```powershell
uv run epanet-check run_config.json --validate-only
```

Run all checks after setting a matching result file in `run_config.json`:

```powershell
uv run epanet-check run_config.json
```

After installing the wheel, use `epanet-check` without the `uv run` prefix.

## Reports and exports

Both interfaces write a full JSON report and a concise text report containing
issues. A successful CLI run returns exit code 0; failed, missing, or invalid
checks return 1; configuration or input errors return 2.
Extreme EPANET sentinel values and non-finite results are reported as `INVALID`
rather than being treated as ordinary minimum or maximum failures.

Each run also exports ten CSV files containing junction, pipe, tank, pump, and
valve statistics or time series. Interactive `tanks.html`, `pumps.html`, and
`valves.html` dashboards are written to the same output folder. The dashboards
use Plotly from its public CDN, so chart rendering requires an internet
connection when an HTML file is opened.

## Build a wheel

From the repository folder:

```powershell
uv build --wheel
```

The wheel is written to `dist/` and includes the default performance criteria.


## Release notes

### 0.1.0 - 2026-11-19

- GUI configuration loading continues when referenced files or folders are missing.
  Valid paths load normally; missing paths are cleared and reported in the Log.
  Missing or unreadable supporting files reset to built-in defaults, clearing old
  file references. Previous model asset IDs are cleared when loading a new config.
- Invalid main configuration JSON is reported in the Log without replacing the
  current project. Command-line validation remains strict.
- `tanks.html` now offers individual tank checkboxes, Select all, and Clear all.
  The statistics table and level graph both follow the selection. Initially only
  the first tank is selected; Show top 30 selects tanks by NumCycles.
- Pump and valve dashboard controls and CSV export formats are unchanged.
