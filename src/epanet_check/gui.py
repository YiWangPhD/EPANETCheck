"""PyQt graphical interface for EPANET Check."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .config import RunConfig
from .dialogs import GlobalLimitsDialog, PerformanceCriteriaDialog
from .service import RunOutcome, run_checks_and_exports


def read_asset_ids(inp_file: Path) -> tuple[list[str], list[str]]:
    """Read junction and tank IDs directly from INP sections."""
    sections: dict[str, list[str]] = {"JUNCTIONS": [], "TANKS": []}
    current = ""
    for raw_line in inp_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.split(";", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip().upper()
            continue
        if current in sections:
            sections[current].append(line.split()[0])
    return sections["JUNCTIONS"], sections["TANKS"]


class AnalysisWorker(QObject):
    log = pyqtSignal(str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, config: RunConfig, performance: dict, limits: dict) -> None:
        super().__init__()
        self.config = config
        self.performance = performance
        self.limits = limits

    @pyqtSlot()
    def run(self) -> None:
        try:
            outcome = run_checks_and_exports(
                self.config, self.performance, self.limits, self.log.emit
            )
        except Exception as exc:  # presented as a friendly GUI error
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.finished.emit(outcome)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("EPANET Check")
        self.resize(1000, 700)
        self.performance_dialog = PerformanceCriteriaDialog(self)
        self.limits_dialog = GlobalLimitsDialog(self)
        self.run_config_path: Path | None = None
        self.last_outcome: RunOutcome | None = None
        self.thread: QThread | None = None
        self.worker: AnalysisWorker | None = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        inputs = QGroupBox("Project and model files")
        grid = QGridLayout(inputs)
        self.output_edit = QLineEdit()
        self.inp_edit = QLineEdit()
        self.result_edit = QLineEdit()
        self.config_edit = QLineEdit()
        self.config_edit.setReadOnly(True)
        self._add_path_row(grid, 0, "Project folder", self.output_edit, "folder")
        self._add_path_row(grid, 1, "Input file", self.inp_edit, "inp")
        self._add_path_row(grid, 2, "Result file", self.result_edit, "result")
        grid.addWidget(QLabel("Run configuration"), 3, 0)
        grid.addWidget(self.config_edit, 3, 1)
        load_config = QPushButton("Load JSON")
        save_config = QPushButton("Save JSON")
        load_config.clicked.connect(self.load_run_config)
        save_config.clicked.connect(self.save_run_config)
        config_buttons = QHBoxLayout()
        config_buttons.addWidget(load_config)
        config_buttons.addWidget(save_config)
        grid.addLayout(config_buttons, 3, 2)
        grid.setColumnStretch(1, 1)
        layout.addWidget(inputs)

        action_row = QHBoxLayout()
        criteria_button = QPushButton("Performance Criteria")
        limits_button = QPushButton("Global Limits")
        self.run_button = QPushButton("Run Checks and Export")
        clear_button = QPushButton("Clear Log")
        criteria_button.clicked.connect(self.open_performance)
        limits_button.clicked.connect(self.limits_dialog.show)
        self.run_button.clicked.connect(self.start_run)
        clear_button.clicked.connect(self.log_edit_clear)
        action_row.addWidget(criteria_button)
        action_row.addWidget(limits_button)
        action_row.addStretch()
        action_row.addWidget(self.run_button)
        action_row.addWidget(clear_button)
        layout.addLayout(action_row)

        output_row = QHBoxLayout()
        self.open_output_button = QPushButton("Open Output Folder")
        self.open_tanks_button = QPushButton("Open Tank Dashboard")
        self.open_pumps_button = QPushButton("Open Pump Dashboard")
        self.open_valves_button = QPushButton("Open Valve Dashboard")
        self.open_output_button.clicked.connect(self.open_output_folder)
        self.open_tanks_button.clicked.connect(lambda: self.open_dashboard("tanks.html"))
        self.open_pumps_button.clicked.connect(lambda: self.open_dashboard("pumps.html"))
        self.open_valves_button.clicked.connect(lambda: self.open_dashboard("valves.html"))
        for button in (
            self.open_output_button, self.open_tanks_button,
            self.open_pumps_button, self.open_valves_button,
        ):
            output_row.addWidget(button)
        layout.addLayout(output_row)

        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setPlaceholderText("Run progress and messages will appear here.")
        log_layout.addWidget(self.log_edit)
        layout.addWidget(log_group, 1)

        self.setStyleSheet("""
            QGroupBox { font-weight: 600; margin-top: 8px; padding-top: 12px; }
            QLineEdit, QPlainTextEdit { border: 1px solid #aeb6c2; border-radius: 4px; padding: 5px; }
            QPushButton { padding: 7px 12px; }
            QPushButton:disabled { color: #8a8f98; }
        """)
        self.log("Ready. Select model files or load a run configuration.")

    def _add_path_row(self, grid: QGridLayout, row: int, label: str, edit: QLineEdit, kind: str) -> None:
        grid.addWidget(QLabel(label), row, 0)
        grid.addWidget(edit, row, 1)
        button = QPushButton("Pick Folder" if kind == "folder" else "Pick File")
        button.clicked.connect(lambda _checked=False, selected=kind: self.pick_path(selected))
        grid.addWidget(button, row, 2)

    def pick_path(self, kind: str) -> None:
        if kind == "folder":
            selected = QFileDialog.getExistingDirectory(self, "Select project folder", self.output_edit.text())
            if selected:
                self.output_edit.setText(selected)
            return
        if kind == "inp":
            selected, _ = QFileDialog.getOpenFileName(
                self, "Select EPANET input file", self.inp_edit.text(), "EPANET input (*.inp);;All files (*)"
            )
            if selected:
                self.inp_edit.setText(selected)
                self.update_asset_ids()
            return
        selected, _ = QFileDialog.getOpenFileName(
            self, "Select EPANET binary result", self.result_edit.text(),
            "EPANET results (*.tmp *.bin *.out);;All files (*)",
        )
        if selected:
            self.result_edit.setText(selected)

    def update_asset_ids(self) -> bool:
        path = Path(self.inp_edit.text().strip())
        if not path.is_file():
            return False
        try:
            junctions, tanks = read_asset_ids(path)
        except OSError as exc:
            self.log(f"Unable to read asset IDs: {exc}")
            return False
        self.performance_dialog.set_assets(junctions, tanks)
        self.log(f"Found {len(junctions):,} junctions and {len(tanks):,} tanks in the input file.")
        return True

    def open_performance(self) -> None:
        if not self.performance_dialog.asset_ids["junction"]:
            self.update_asset_ids()
        self.performance_dialog.show()
        self.performance_dialog.raise_()
        self.performance_dialog.activateWindow()

    def load_run_config(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Load run configuration", filter="JSON files (*.json)")
        if not filename:
            return
        try:
            config = RunConfig.load(filename)
            config.validate_paths(require_result=True)
            self.output_edit.setText(str(config.output_folder))
            self.inp_edit.setText(str(config.inp_file))
            self.result_edit.setText(str(config.result_file))
            self.update_asset_ids()
            self.performance_dialog.load_path(config.performance_criteria_file)
            self.limits_dialog.load_path(config.limits_file)
        except Exception as exc:
            QMessageBox.critical(self, "Unable to load configuration", str(exc))
            return
        self.run_config_path = Path(filename).resolve()
        self.config_edit.setText(str(self.run_config_path))
        self.log(f"Loaded run configuration: {self.run_config_path}")

    def save_run_config(self) -> None:
        if self.performance_dialog.current_path is None or self.limits_dialog.current_path is None:
            QMessageBox.information(
                self, "Save supporting files first",
                "Save the Performance Criteria and Global Limits JSON files before saving the run configuration.",
            )
            return
        initial = str(self.run_config_path or Path("run_config.json"))
        filename, _ = QFileDialog.getSaveFileName(self, "Save run configuration", initial, "JSON files (*.json)")
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        base = path.parent.resolve()

        def relative(value: Path) -> str:
            try:
                return os.path.relpath(value.resolve(), base)
            except ValueError:
                return str(value.resolve())

        value = {
            "output_folder": relative(Path(self.output_edit.text().strip())),
            "inp_file": relative(Path(self.inp_edit.text().strip())),
            "result_file": relative(Path(self.result_edit.text().strip())),
            "performance_criteria_file": relative(self.performance_dialog.current_path),
            "limits_file": relative(self.limits_dialog.current_path),
            "report_name": "epanet_check_report",
        }
        try:
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Unable to save configuration", str(exc))
            return
        self.run_config_path = path.resolve()
        self.config_edit.setText(str(self.run_config_path))
        self.log(f"Saved run configuration: {self.run_config_path}")

    def _current_config(self) -> RunConfig:
        output_text = self.output_edit.text().strip()
        inp_text = self.inp_edit.text().strip()
        result_text = self.result_edit.text().strip()
        if not output_text or not inp_text or not result_text:
            raise ValueError("Select a project folder, input file, and result file before running.")
        output = Path(output_text).expanduser().resolve()
        inp = Path(inp_text).expanduser().resolve()
        result = Path(result_text).expanduser().resolve()
        if not inp.is_file() or not result.is_file():
            raise ValueError("The selected input or result file does not exist.")
        placeholder_base = self.run_config_path.parent if self.run_config_path else output
        return RunConfig(
            config_path=self.run_config_path or placeholder_base / "run_config.json",
            output_folder=output,
            inp_file=inp,
            result_file=result,
            performance_criteria_file=(
                self.performance_dialog.current_path or placeholder_base / "<in-memory-performance>"
            ),
            limits_file=self.limits_dialog.current_path or placeholder_base / "<in-memory-limits>",
            report_name="epanet_check_report",
        )

    def start_run(self) -> None:
        if self.thread is not None:
            return
        try:
            config = self._current_config()
        except ValueError as exc:
            QMessageBox.warning(self, "Missing input", str(exc))
            return
        self.run_button.setEnabled(False)
        self.last_outcome = None
        self.log("Starting checks and exports...")
        self.thread = QThread(self)
        self.worker = AnalysisWorker(
            config, self.performance_dialog.data(), self.limits_dialog.data()
        )
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.log)
        self.worker.finished.connect(self.run_finished)
        self.worker.failed.connect(self.run_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

    @pyqtSlot(object)
    def run_finished(self, outcome: RunOutcome) -> None:
        self.last_outcome = outcome
        summary = outcome.report["summary"]
        self.log(
            f"Finished: {summary['PASS']:,} passed, {summary['FAIL']:,} failed, "
            f"{summary['MISSING']:,} missing, {summary['INVALID']:,} invalid."
        )
        self.log(f"Reports and {len(outcome.exports)} exports written to {outcome.json_report.parent}")
        QMessageBox.information(self, "EPANET Check complete", "Checks and exports are complete. See the log for the result summary.")

    @pyqtSlot(str)
    def run_failed(self, message: str) -> None:
        self.log(f"ERROR: {message}")
        QMessageBox.critical(self, "EPANET Check failed", message)

    @pyqtSlot()
    def _thread_finished(self) -> None:
        if self.thread is not None:
            self.thread.deleteLater()
        self.thread = None
        self.worker = None
        self.run_button.setEnabled(True)

    def log(self, message: str) -> None:
        self.log_edit.appendPlainText(f"[{datetime.now():%H:%M:%S}] {message}")

    def log_edit_clear(self) -> None:
        self.log_edit.clear()

    def open_output_folder(self) -> None:
        path = Path(self.output_edit.text().strip())
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QMessageBox.warning(self, "Folder not found", "The selected output folder does not exist.")

    def open_dashboard(self, filename: str) -> None:
        path = Path(self.output_edit.text().strip()) / filename
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QMessageBox.warning(self, "Dashboard not found", f"Run the export first to create {filename}.")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("EPANET Check")
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
