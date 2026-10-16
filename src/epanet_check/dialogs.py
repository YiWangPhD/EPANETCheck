"""Configuration dialogs for the PyQt application."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("The top level must be a JSON object.")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class PerformanceCriteriaDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Performance Criteria")
        self.resize(850, 580)
        self.criteria: list[dict[str, Any]] = []
        self.current_path: Path | None = None
        self.asset_ids: dict[str, list[str]] = {"junction": [], "tank": []}

        layout = QVBoxLayout(self)
        file_row = QHBoxLayout()
        self.path_label = QLabel("No performance criteria file loaded")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        load_button = QPushButton("Load JSON")
        save_button = QPushButton("Save JSON")
        load_button.clicked.connect(self.load_json)
        save_button.clicked.connect(self.save_json)
        file_row.addWidget(self.path_label, 1)
        file_row.addWidget(load_button)
        file_row.addWidget(save_button)
        layout.addLayout(file_row)

        editor = QGroupBox("Add criterion")
        form = QGridLayout(editor)
        self.type_combo = QComboBox()
        self.type_combo.addItem("Junction", "junction")
        self.type_combo.addItem("Tank", "tank")
        self.id_combo = QComboBox()
        self.id_combo.setEditable(True)
        self.id_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.id_combo.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.id_combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.metric_combo = QComboBox()
        self.unit_combo = QComboBox()
        self.bound_combo = QComboBox()
        self.bound_combo.addItem("Minimum", "min")
        self.bound_combo.addItem("Maximum", "max")
        self.limit_spin = QDoubleSpinBox()
        self.limit_spin.setRange(-1_000_000_000, 1_000_000_000)
        self.limit_spin.setDecimals(4)
        add_button = QPushButton("Add")
        add_button.clicked.connect(self.add_criterion)

        widgets = [
            ("Asset type", self.type_combo),
            ("Asset ID", self.id_combo),
            ("Measurement", self.metric_combo),
            ("Unit", self.unit_combo),
            ("Limit type", self.bound_combo),
            ("Limit", self.limit_spin),
        ]
        for row, (label, widget) in enumerate(widgets):
            form.addWidget(QLabel(label), row, 0)
            form.addWidget(widget, row, 1)
        form.addWidget(add_button, len(widgets) - 1, 2)
        form.setColumnStretch(1, 1)
        layout.addWidget(editor)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Type", "ID", "Measurement", "Min/Max", "Limit", "Unit"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self.remove_selected)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(remove_button)
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self.type_combo.currentIndexChanged.connect(self._update_type)
        self.metric_combo.currentIndexChanged.connect(self._update_units)
        self._update_type()

    def set_assets(self, junctions: list[str], tanks: list[str]) -> None:
        self.asset_ids = {"junction": junctions, "tank": tanks}
        self._update_ids()

    def _update_type(self) -> None:
        asset_type = self.type_combo.currentData()
        self.metric_combo.blockSignals(True)
        self.metric_combo.clear()
        if asset_type == "junction":
            self.metric_combo.addItem("Hydraulic head", "head")
            self.metric_combo.addItem("Pressure", "pressure")
        else:
            self.metric_combo.addItem("Hydraulic head", "head")
            self.metric_combo.addItem("Water level", "level")
        self.metric_combo.blockSignals(False)
        self._update_ids()
        self._update_units()

    def _update_ids(self) -> None:
        current = self.id_combo.currentText()
        self.id_combo.clear()
        self.id_combo.addItems(self.asset_ids.get(self.type_combo.currentData(), []))
        if current:
            self.id_combo.setCurrentText(current)

    def _update_units(self) -> None:
        metric = self.metric_combo.currentData()
        self.unit_combo.clear()
        if metric == "pressure":
            self.unit_combo.addItem("psi", "psi")
            self.unit_combo.addItem("kPa", "kpa")
            self.unit_combo.addItem("metres of head", "m")
        else:
            self.unit_combo.addItem("ft", "ft")
            self.unit_combo.addItem("m", "m")

    def add_criterion(self) -> None:
        asset_id = self.id_combo.currentText().strip()
        asset_type = self.type_combo.currentData()
        if not asset_id:
            QMessageBox.warning(self, "Missing asset", "Select an asset ID.")
            return
        if asset_id not in self.asset_ids.get(asset_type, []):
            QMessageBox.warning(self, "Unknown asset", "The selected ID is not present in the model.")
            return
        item = {
            "asset_type": asset_type,
            "asset_id": asset_id,
            "metric": self.metric_combo.currentData(),
            "unit": self.unit_combo.currentData(),
            self.bound_combo.currentData(): self.limit_spin.value(),
        }
        self.criteria.append(item)
        self._refresh()

    def remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.criteria.pop(row)
        self._refresh()

    def _refresh(self) -> None:
        self.table.setRowCount(len(self.criteria))
        metric_names = {"head": "Hydraulic head", "pressure": "Pressure", "level": "Water level"}
        for row, item in enumerate(self.criteria):
            bound = "min" if "min" in item else "max"
            values = [
                str(item.get("asset_type", "")).title(),
                str(item.get("asset_id", "")),
                metric_names.get(str(item.get("metric", "")), str(item.get("metric", ""))),
                bound.title(),
                f"{float(item[bound]):g}",
                str(item.get("unit", "")),
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))

    def set_data(self, value: dict[str, Any], path: Path | None = None) -> None:
        criteria = value.get("criteria")
        if not isinstance(criteria, list):
            raise ValueError("Performance JSON must contain a 'criteria' array.")
        normalized: list[dict[str, Any]] = []
        legacy = {"head_ft": ("head", "ft"), "pressure_psi": ("pressure", "psi"), "level_ft": ("level", "ft")}
        for raw in criteria:
            item = dict(raw)
            if item.get("metric") in legacy:
                item["metric"], item["unit"] = legacy[item["metric"]]
            if "min" in item and "max" in item:
                minimum = dict(item)
                maximum = dict(item)
                minimum.pop("max")
                maximum.pop("min")
                normalized.extend([minimum, maximum])
            else:
                normalized.append(item)
        self.criteria = normalized
        self.current_path = path
        self.path_label.setText(str(path) if path else "Unsaved performance criteria")
        self._refresh()

    def data(self) -> dict[str, Any]:
        return {"criteria": deepcopy(self.criteria)}

    def load_path(self, path: Path) -> None:
        self.set_data(_read_json(path), path)

    def load_json(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Load performance criteria", filter="JSON files (*.json)")
        if not filename:
            return
        try:
            self.load_path(Path(filename))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Unable to load JSON", str(exc))

    def save_json(self) -> None:
        initial = str(self.current_path or Path("performance_criteria.json"))
        filename, _ = QFileDialog.getSaveFileName(self, "Save performance criteria", initial, "JSON files (*.json)")
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        try:
            _write_json(path, self.data())
            self.current_path = path
            self.path_label.setText(str(path))
        except OSError as exc:
            QMessageBox.critical(self, "Unable to save JSON", str(exc))


class GlobalLimitsDialog(QDialog):
    FIELD_DEFINITIONS = [
        ("Junction", "Minimum pressure", "junction_pressure_psi", "min", "psi", 10.0),
        ("Junction", "Maximum pressure", "junction_pressure_psi", "max", "psi", 300.0),
        ("Pipe", "Maximum absolute flow", "pipe_max_abs_flow_mld", "max", "MLD", 500.0),
        ("Pipe", "Maximum velocity", "pipe_max_abs_velocity_fps", "max", "ft/s", 10.0),
        ("Pipe", "Maximum reversals per day", "pipe_flow_reversals_per_day", "max", "", 10.0),
        ("Pump", "Maximum absolute flow", "pump_max_abs_flow_mld", "max", "MLD", 500.0),
        ("Pump", "Maximum starts per day", "pump_starts_per_day", "max", "", 10.0),
        ("Tank", "Minimum level", "tank_level_ft", "min", "ft", 0.0),
        ("Tank", "Maximum level", "tank_level_ft", "max", "ft", 20.0),
        ("Tank", "Maximum cycles per day", "tank_cycles_per_day", "max", "", 2.0),
        ("Tank", "Cycle prominence", "tank_cycles_per_day", "prominence", "", 0.5),
        ("Valve", "Maximum absolute flow", "valve_max_abs_flow_mld", "max", "MLD", 500.0),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Global Limits")
        self.resize(920, 480)
        self.current_path: Path | None = None
        self.fields: dict[tuple[str, str], QDoubleSpinBox] = {}

        layout = QVBoxLayout(self)
        file_row = QHBoxLayout()
        self.path_label = QLabel("No global limits file loaded")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        load_button = QPushButton("Load JSON")
        save_button = QPushButton("Save JSON")
        load_button.clicked.connect(self.load_json)
        save_button.clicked.connect(self.save_json)
        file_row.addWidget(self.path_label, 1)
        file_row.addWidget(load_button)
        file_row.addWidget(save_button)
        layout.addLayout(file_row)

        groups_row = QHBoxLayout()
        categories = ["Junction", "Pipe", "Pump", "Tank", "Valve"]
        for category in categories:
            group = QGroupBox(category)
            form = QFormLayout(group)
            for cat, label, key, subkey, unit, default in self.FIELD_DEFINITIONS:
                if cat != category:
                    continue
                spin = QDoubleSpinBox()
                spin.setRange(-1_000_000_000, 1_000_000_000)
                spin.setDecimals(4)
                spin.setValue(default)
                self.fields[(key, subkey)] = spin
                row = QHBoxLayout()
                row.addWidget(spin)
                if unit:
                    row.addWidget(QLabel(unit))
                form.addRow(label, row)
            groups_row.addWidget(group)
        layout.addLayout(groups_row, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        self.set_data({"limits": {}})

    def set_data(self, value: dict[str, Any], path: Path | None = None) -> None:
        limits = value.get("limits")
        if not isinstance(limits, dict):
            raise ValueError("Global limits JSON must contain a 'limits' object.")
        for _category, _label, key, subkey, _unit, default in self.FIELD_DEFINITIONS:
            source = limits.get(key, {})
            if subkey == "prominence":
                selected = source.get("prominence", source.get("prominence_ft", default))
            else:
                selected = source.get(subkey, default)
            self.fields[(key, subkey)].setValue(float(selected))
        self.current_path = path
        self.path_label.setText(str(path) if path else "Unsaved global limits")

    def data(self) -> dict[str, Any]:
        limits: dict[str, dict[str, float]] = {}
        for _category, _label, key, subkey, _unit, _default in self.FIELD_DEFINITIONS:
            limits.setdefault(key, {})[subkey] = self.fields[(key, subkey)].value()
        return {"limits": limits}

    def load_path(self, path: Path) -> None:
        self.set_data(_read_json(path), path)

    def load_json(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Load global limits", filter="JSON files (*.json)")
        if not filename:
            return
        try:
            self.load_path(Path(filename))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Unable to load JSON", str(exc))

    def save_json(self) -> None:
        initial = str(self.current_path or Path("general_limits.json"))
        filename, _ = QFileDialog.getSaveFileName(self, "Save global limits", initial, "JSON files (*.json)")
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        try:
            _write_json(path, self.data())
            self.current_path = path
            self.path_label.setText(str(path))
        except OSError as exc:
            QMessageBox.critical(self, "Unable to save JSON", str(exc))
