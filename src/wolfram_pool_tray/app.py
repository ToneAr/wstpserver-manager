from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

from PyQt6.QtCore import Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QCloseEvent, QDesktopServices, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .config import default_config, first_pool, load_config, pools, save_config, update_first_pool
from .service import BaseServiceManager, DetectionResult, ServiceError, get_service_manager

APP_NAME = "WSTPServer Manager"
TRAY_ICON_PATH = Path(__file__).with_name("assets") / "spikey.svg"

ROOT_BOOLEAN_KEYS = (
    "AllowStealingKernels",
    "AllowSilentKernelReplacement",
    "EnableAutomaticKernelConnection",
    "SendInputNamePacketUponKernelConnection",
)
POOL_BOOLEAN_KEYS = (
    "Default",
    "ParallelKernelDefault",
    "ParallelKernels",
    "KeepAlive",
    "ReservePreviouslyConnectedKernels",
)
POOL_INTEGER_KEYS = (
    "MinimumKernelNumber",
    "MaximumKernelNumber",
)
POOL_TEXT_KEYS = (
    "KernelPath",
    "InitializationFile",
    "KernelOptions",
)


class OptionalBooleanCombo(QComboBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.addItem("Use WSTPServer default / automatic", None)
        self.addItem("True", True)
        self.addItem("False", False)

    def set_config_value(self, value: object, *, present: bool) -> None:
        if not present:
            self.setCurrentIndex(0)
        else:
            self.setCurrentIndex(1 if _bool_from_config(value) else 2)

    def config_value(self) -> bool | None:
        data = self.currentData()
        return data if isinstance(data, bool) else None


class OptionalSpinBox(QWidget):
    def __init__(self, *, minimum: int, maximum: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.enabled_check = QCheckBox("Set value")
        self.spin = QSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setEnabled(False)
        self.enabled_check.toggled.connect(self.spin.setEnabled)
        layout.addWidget(self.enabled_check)
        layout.addWidget(self.spin)
        layout.addStretch(1)

    def set_config_value(self, value: object, *, present: bool, default: int) -> None:
        self.enabled_check.setChecked(present)
        try:
            self.spin.setValue(int(str(value)) if present else default)
        except (TypeError, ValueError):
            self.spin.setValue(default)

    def config_value(self) -> int | None:
        return self.spin.value() if self.enabled_check.isChecked() else None


class ConfigEditorDialog(QDialog):
    """GUI editor for documented WSTPServer configuration keys.

    Unknown root and pool keys are preserved when saving so users can keep
    settings added by newer WSTPServer versions or manual edits.
    """

    def __init__(self, path: Path, *, default_kernel_path: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = path
        self.config = self._load_or_default(default_kernel_path)
        self.current_pool_name: str | None = None
        self.loading_pool = False
        self.setWindowTitle(f"Edit WSTPServer Config — {path.name}")
        self.setMinimumSize(720, 640)

        self.root_boolean_edits = {key: OptionalBooleanCombo() for key in ROOT_BOOLEAN_KEYS}
        self.pool_boolean_edits = {key: OptionalBooleanCombo() for key in POOL_BOOLEAN_KEYS}
        self.pool_integer_edits = {
            "MinimumKernelNumber": OptionalSpinBox(minimum=0, maximum=1024),
            "MaximumKernelNumber": OptionalSpinBox(minimum=1, maximum=1024),
        }
        self.pool_text_edits = {key: QLineEdit() for key in POOL_TEXT_KEYS}
        self.initialization_code_edit = QPlainTextEdit()
        self.initialization_code_edit.setPlaceholderText("Optional Wolfram Language code to evaluate when kernels start")
        self.initialization_code_edit.setMaximumBlockCount(5000)
        self.pool_selector = QComboBox()

        self._build_ui()
        self._load_root()
        self._reload_pool_selector()

    def _load_or_default(self, default_kernel_path: str) -> dict[str, Any]:
        if self.path.exists() and self.path.stat().st_size > 0:
            return load_config(self.path)
        return default_config(default_kernel_path)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        path_label = QLabel(str(self.path))
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(QLabel("Configuration file:"))
        layout.addWidget(path_label)

        tabs = QTabWidget()
        tabs.addTab(self._server_tab(), "Server")
        tabs.addTab(self._pools_tab(), "Pools")
        layout.addWidget(tabs, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _server_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.addRow(QLabel("Root-level settings from the WSTPServer configuration file documentation."))
        for key, editor in self.root_boolean_edits.items():
            layout.addRow(f"{key}:", editor)
        return widget

    def _pools_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        controls = QHBoxLayout()
        self.pool_selector.currentTextChanged.connect(self._pool_changed)
        add_button = QPushButton("Add Pool…")
        add_button.clicked.connect(self._add_pool)
        rename_button = QPushButton("Rename…")
        rename_button.clicked.connect(self._rename_pool)
        remove_button = QPushButton("Remove")
        remove_button.clicked.connect(self._remove_pool)
        controls.addWidget(QLabel("Pool:"))
        controls.addWidget(self.pool_selector, stretch=1)
        controls.addWidget(add_button)
        controls.addWidget(rename_button)
        controls.addWidget(remove_button)
        layout.addLayout(controls)

        form = QFormLayout()
        for key, editor in self.pool_boolean_edits.items():
            form.addRow(f"{key}:", editor)
        form.addRow("KernelPath:", self._path_row(self.pool_text_edits["KernelPath"], executable=True))
        form.addRow("InitializationFile:", self._path_row(self.pool_text_edits["InitializationFile"], executable=False))
        form.addRow("InitializationCode:", self.initialization_code_edit)
        form.addRow("KernelOptions:", self.pool_text_edits["KernelOptions"])
        for key, editor in self.pool_integer_edits.items():
            form.addRow(f"{key}:", editor)
        layout.addLayout(form)
        layout.addStretch(1)
        return widget

    def _path_row(self, line_edit: QLineEdit, *, executable: bool) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("Browse…")
        button.clicked.connect(lambda: self._browse_path(line_edit, executable=executable))
        layout.addWidget(line_edit, stretch=1)
        layout.addWidget(button)
        return widget

    def _browse_path(self, line_edit: QLineEdit, *, executable: bool) -> None:
        title = "Choose executable" if executable else "Choose initialization file"
        filename, _ = QFileDialog.getOpenFileName(self, title, str(Path.home()))
        if filename:
            line_edit.setText(filename)

    def _load_root(self) -> None:
        for key, editor in self.root_boolean_edits.items():
            editor.set_config_value(self.config.get(key), present=key in self.config)

    def _commit_root(self) -> None:
        for key, editor in self.root_boolean_edits.items():
            value = editor.config_value()
            if value is None:
                self.config.pop(key, None)
            else:
                self.config[key] = value

    def _reload_pool_selector(self, selected: str | None = None) -> None:
        pool_map = pools(self.config)
        if not pool_map:
            pool_map["StandardKernels"] = default_config("")["Pools"]["StandardKernels"]
        self.loading_pool = True
        self.pool_selector.clear()
        self.pool_selector.addItems(pool_map.keys())
        if selected and selected in pool_map:
            self.pool_selector.setCurrentText(selected)
        self.loading_pool = False
        self.current_pool_name = self.pool_selector.currentText() or None
        if self.current_pool_name:
            self._load_pool(self.current_pool_name)

    def _pool_changed(self, name: str) -> None:
        if self.loading_pool:
            return
        if self.current_pool_name:
            self._commit_pool(self.current_pool_name)
        self.current_pool_name = name or None
        if self.current_pool_name:
            self._load_pool(self.current_pool_name)

    def _load_pool(self, name: str) -> None:
        pool = pools(self.config).get(name, {})
        if not isinstance(pool, dict):
            QMessageBox.warning(self, "Invalid pool", f"Pool '{name}' is not an object and cannot be edited with the GUI.")
            pool = {}
        for key, editor in self.pool_boolean_edits.items():
            editor.set_config_value(pool.get(key), present=key in pool)
        for key, editor in self.pool_text_edits.items():
            editor.setText(str(pool.get(key, "")))
        self.initialization_code_edit.setPlainText(str(pool.get("InitializationCode", "")))
        self.pool_integer_edits["MinimumKernelNumber"].set_config_value(
            pool.get("MinimumKernelNumber"), present="MinimumKernelNumber" in pool, default=2
        )
        self.pool_integer_edits["MaximumKernelNumber"].set_config_value(
            pool.get("MaximumKernelNumber"), present="MaximumKernelNumber" in pool, default=4
        )

    def _commit_pool(self, name: str) -> None:
        pool_map = pools(self.config)
        pool = pool_map.setdefault(name, {})
        if not isinstance(pool, dict):
            pool = {}
            pool_map[name] = pool
        for key, editor in self.pool_boolean_edits.items():
            value = editor.config_value()
            if value is None:
                pool.pop(key, None)
            else:
                pool[key] = value
        for key, editor in self.pool_text_edits.items():
            value = editor.text().strip()
            if value:
                pool[key] = value
            else:
                pool.pop(key, None)
        initialization_code = self.initialization_code_edit.toPlainText()
        if initialization_code.strip():
            pool["InitializationCode"] = initialization_code
        else:
            pool.pop("InitializationCode", None)
        for key, editor in self.pool_integer_edits.items():
            value = editor.config_value()
            if value is None:
                pool.pop(key, None)
            else:
                pool[key] = value

    def _add_pool(self) -> None:
        if self.current_pool_name:
            self._commit_pool(self.current_pool_name)
        name, ok = QInputDialog.getText(self, "Add kernel pool", "Pool name:")
        name = name.strip()
        if not ok or not name:
            return
        pool_map = pools(self.config)
        if name in pool_map:
            QMessageBox.warning(self, "Pool exists", f"A pool named '{name}' already exists.")
            return
        pool_map[name] = {}
        self._reload_pool_selector(name)

    def _rename_pool(self) -> None:
        old_name = self.current_pool_name
        if not old_name:
            return
        self._commit_pool(old_name)
        new_name, ok = QInputDialog.getText(self, "Rename kernel pool", "Pool name:", text=old_name)
        new_name = new_name.strip()
        if not ok or not new_name or new_name == old_name:
            return
        pool_map = pools(self.config)
        if new_name in pool_map:
            QMessageBox.warning(self, "Pool exists", f"A pool named '{new_name}' already exists.")
            return
        pool_map[new_name] = pool_map.pop(old_name)
        self._reload_pool_selector(new_name)

    def _remove_pool(self) -> None:
        name = self.current_pool_name
        if not name:
            return
        pool_map = pools(self.config)
        if len(pool_map) <= 1:
            QMessageBox.warning(self, "Pool required", "WSTPServer requires at least one pool.")
            return
        choice = QMessageBox.question(
            self,
            "Remove kernel pool?",
            f"Remove pool '{name}' from the configuration?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        pool_map.pop(name, None)
        self._reload_pool_selector(next(iter(pool_map), None))

    def accept(self) -> None:
        try:
            self._commit_root()
            if self.current_pool_name:
                self._commit_pool(self.current_pool_name)
            if not pools(self.config):
                raise ValueError("WSTPServer requires at least one kernel pool")
            save_config(self.path, self.config)
        except Exception as exc:  # noqa: BLE001 - GUI boundary
            QMessageBox.critical(self, "Could not save config", str(exc))
            return
        super().accept()


class OperationThread(QThread):
    finished_with_result = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, operation: Callable[[], str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._operation = operation

    def run(self) -> None:
        try:
            self.finished_with_result.emit(self._operation())
        except Exception as exc:  # noqa: BLE001 - show actionable GUI error
            detail = str(exc) or exc.__class__.__name__
            if not isinstance(exc, ServiceError):
                detail = f"{detail}\n\n{traceback.format_exc()}"
            self.failed.emit(detail)


class MainWindow(QMainWindow):
    def __init__(self, manager: BaseServiceManager, tray: QSystemTrayIcon | None = None) -> None:
        super().__init__()
        self.manager = manager
        self.tray = tray
        self.worker: OperationThread | None = None
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(760, 620)

        self.status_label = QLabel("Checking…")
        self.installed_label = QLabel("—")
        self.running_label = QLabel("—")
        self.enabled_label = QLabel("—")
        self.kernel_processes_label = QLabel("—")
        self.config_path_label = QLabel(str(self.manager.paths().config_file))
        self.log_path_label = QLabel(str(self.manager.paths().log_file))
        self.platform_label = QLabel(self.manager.name)

        self.wstpserver_edit = QLineEdit()
        self.kernel_edit = QLineEdit()
        self.pool_name_label = QLabel("—")
        self.minimum_spin = QSpinBox()
        self.minimum_spin.setRange(0, 1024)
        self.maximum_spin = QSpinBox()
        self.maximum_spin.setRange(1, 1024)
        self.keep_alive_check = QCheckBox("Keep kernels warm")

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(1000)

        self.install_button = QPushButton("Install / Update Service")
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.restart_button = QPushButton("Restart")
        self.uninstall_button = QPushButton("Uninstall Service")
        self.detect_button = QPushButton("Auto-detect Binaries")
        self.save_config_button = QPushButton("Save Kernel Pool Config")
        self.edit_config_button = QPushButton("Edit Full Config…")
        self.edit_other_config_button = QPushButton("Edit Other Config…")
        self.refresh_button = QPushButton("Refresh")
        self.open_config_button = QPushButton("Open Config Folder")
        self.open_log_button = QPushButton("Open Log Folder")

        self._build_ui()
        self._connect_signals()
        self.escape_shortcut: QShortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.escape_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.escape_shortcut.activated.connect(self.close)
        self.load_config_into_form()
        self.refresh_status()
        QTimer.singleShot(0, self.detect_binaries_on_startup)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(5000)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)

        summary = QGroupBox("Service status")
        summary_layout = QGridLayout(summary)
        summary_layout.addWidget(QLabel("Platform:"), 0, 0)
        summary_layout.addWidget(self.platform_label, 0, 1)
        summary_layout.addWidget(QLabel("Status:"), 1, 0)
        summary_layout.addWidget(self.status_label, 1, 1)
        summary_layout.addWidget(QLabel("Installed:"), 2, 0)
        summary_layout.addWidget(self.installed_label, 2, 1)
        summary_layout.addWidget(QLabel("Running:"), 3, 0)
        summary_layout.addWidget(self.running_label, 3, 1)
        summary_layout.addWidget(QLabel("Enabled at login:"), 4, 0)
        summary_layout.addWidget(self.enabled_label, 4, 1)
        summary_layout.addWidget(QLabel("Detected kernel processes:"), 5, 0)
        summary_layout.addWidget(self.kernel_processes_label, 5, 1)
        summary_layout.addWidget(QLabel("Config:"), 6, 0)
        summary_layout.addWidget(self.config_path_label, 6, 1)
        summary_layout.addWidget(QLabel("Log:"), 7, 0)
        summary_layout.addWidget(self.log_path_label, 7, 1)
        root_layout.addWidget(summary)

        actions_layout = QHBoxLayout()
        for button in (
            self.install_button,
            self.start_button,
            self.stop_button,
            self.restart_button,
            self.uninstall_button,
            self.refresh_button,
        ):
            actions_layout.addWidget(button)
        root_layout.addLayout(actions_layout)

        binaries = QGroupBox("Wolfram binaries")
        binaries_layout = QGridLayout(binaries)
        binaries_layout.addWidget(QLabel("wstpserver:"), 0, 0)
        binaries_layout.addWidget(self.wstpserver_edit, 0, 1)
        browse_wstpserver = QPushButton("Browse…")
        browse_wstpserver.clicked.connect(lambda: self._browse_binary(self.wstpserver_edit))
        binaries_layout.addWidget(browse_wstpserver, 0, 2)
        binaries_layout.addWidget(QLabel("WolframKernel:"), 1, 0)
        binaries_layout.addWidget(self.kernel_edit, 1, 1)
        browse_kernel = QPushButton("Browse…")
        browse_kernel.clicked.connect(lambda: self._browse_binary(self.kernel_edit))
        binaries_layout.addWidget(browse_kernel, 1, 2)
        binaries_layout.addWidget(self.detect_button, 2, 1)
        root_layout.addWidget(binaries)

        pool = QGroupBox("Kernel pool")
        pool_layout = QFormLayout(pool)
        pool_layout.addRow("Pool:", self.pool_name_label)
        pool_layout.addRow("Minimum kernels:", self.minimum_spin)
        pool_layout.addRow("Maximum kernels:", self.maximum_spin)
        pool_layout.addRow("KeepAlive:", self.keep_alive_check)
        pool_buttons = QHBoxLayout()
        pool_buttons.addWidget(self.save_config_button)
        pool_buttons.addWidget(self.edit_config_button)
        pool_buttons.addWidget(self.edit_other_config_button)
        pool_buttons.addWidget(self.open_config_button)
        pool_buttons.addWidget(self.open_log_button)
        pool_layout.addRow(pool_buttons)
        root_layout.addWidget(pool)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        root_layout.addWidget(separator)
        root_layout.addWidget(QLabel("Operation output"))
        root_layout.addWidget(self.output, stretch=1)
        self.setCentralWidget(root)

    def _connect_signals(self) -> None:
        self.detect_button.clicked.connect(self.detect_binaries)
        self.install_button.clicked.connect(self.install_service)
        self.start_button.clicked.connect(lambda: self._run_operation("Start", self.manager.start))
        self.stop_button.clicked.connect(lambda: self._run_operation("Stop", self.manager.stop))
        self.restart_button.clicked.connect(lambda: self._run_operation("Restart", self.manager.restart))
        self.uninstall_button.clicked.connect(self.uninstall_service)
        self.save_config_button.clicked.connect(self.save_pool_config)
        self.edit_config_button.clicked.connect(lambda: self.edit_config_file(self.manager.paths().config_file))
        self.edit_other_config_button.clicked.connect(self.choose_and_edit_config_file)
        self.refresh_button.clicked.connect(self.refresh_status)
        self.open_config_button.clicked.connect(lambda: self._open_folder(self.manager.paths().config_file.parent))
        self.open_log_button.clicked.connect(lambda: self._open_folder(self.manager.paths().log_file.parent))

    def detect_binaries(self) -> None:
        detection = self.manager.detect_binaries()
        self._apply_detection(detection, only_empty=False)
        self._append_output("Detection", "\n".join(detection.notes))

    def detect_binaries_on_startup(self) -> None:
        detection = self.manager.detect_binaries()
        self._apply_detection(detection, only_empty=True)
        self._append_output("Detection", "\n".join(detection.notes))

    def _apply_detection(self, detection: DetectionResult, *, only_empty: bool) -> None:
        if detection.wstpserver_bin and (not only_empty or not self.wstpserver_edit.text().strip()):
            self.wstpserver_edit.setText(str(detection.wstpserver_bin))
        if detection.kernel_bin and (not only_empty or not self.kernel_edit.text().strip()):
            self.kernel_edit.setText(str(detection.kernel_bin))

    def install_service(self) -> None:
        wstpserver = _path_or_none(self.wstpserver_edit.text())
        kernel = _path_or_none(self.kernel_edit.text())
        self._run_operation("Install", lambda: self.manager.install(wstpserver, kernel))

    def uninstall_service(self) -> None:
        choice = QMessageBox.question(
            self,
            "Uninstall service?",
            "Remove the background service/task? Config and logs will be kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if choice == QMessageBox.StandardButton.Yes:
            self._run_operation("Uninstall", self.manager.uninstall)

    def save_pool_config(self) -> None:
        kernel = self.kernel_edit.text().strip()
        if not kernel:
            detection = self.manager.detect_binaries()
            self._apply_detection(detection, only_empty=True)
            self._append_output("Detection", "\n".join(detection.notes))
            kernel = self.kernel_edit.text().strip()
        if not kernel:
            QMessageBox.warning(self, "Kernel path required", "Choose or auto-detect a WolframKernel path first.")
            return
        try:
            update_first_pool(
                self.manager.paths().config_file,
                kernel_path=kernel,
                minimum_kernels=self.minimum_spin.value(),
                maximum_kernels=self.maximum_spin.value(),
                keep_alive=self.keep_alive_check.isChecked(),
            )
        except Exception as exc:  # noqa: BLE001 - GUI boundary
            QMessageBox.critical(self, "Could not save config", str(exc))
            return
        self._append_output("Config", f"Saved {self.manager.paths().config_file}")
        self.load_config_into_form()

    def edit_config_file(self, path: Path) -> None:
        try:
            dialog = ConfigEditorDialog(path, default_kernel_path=self.kernel_edit.text().strip(), parent=self)
        except Exception as exc:  # noqa: BLE001 - GUI boundary
            self._append_output("Config error", str(exc))
            QMessageBox.critical(self, "Could not open config", str(exc))
            return
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._append_output("Config", f"Saved {path}")
            if path == self.manager.paths().config_file:
                self.load_config_into_form()
            self.refresh_status()

    def choose_and_edit_config_file(self) -> None:
        dialog = QFileDialog(self, "Choose or create WSTPServer config", str(self.manager.paths().config_file.parent))
        dialog.setNameFilter("WSTPServer config (*.conf *.json);;All files (*)")
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setOption(QFileDialog.Option.DontConfirmOverwrite, True)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selectedFiles():
            self.edit_config_file(Path(dialog.selectedFiles()[0]))

    def load_config_into_form(self) -> None:
        path = self.manager.paths().config_file
        if not path.exists():
            self.pool_name_label.setText("No config yet")
            self.minimum_spin.setValue(2)
            self.maximum_spin.setValue(4)
            self.keep_alive_check.setChecked(True)
            return
        try:
            config = load_config(path)
            pool_name, pool = first_pool(config)
        except Exception as exc:  # noqa: BLE001 - GUI boundary
            self.pool_name_label.setText("Could not load config")
            self._append_output("Config error", str(exc))
            return
        self.pool_name_label.setText(pool_name)
        self.kernel_edit.setText(str(pool.get("KernelPath", "")))
        self.minimum_spin.setValue(int(pool.get("MinimumKernelNumber", 2)))
        self.maximum_spin.setValue(int(pool.get("MaximumKernelNumber", 4)))
        self.keep_alive_check.setChecked(_bool_from_config(pool.get("KeepAlive", True)))

    def refresh_status(self) -> None:
        try:
            status = self.manager.status()
        except Exception as exc:  # noqa: BLE001 - GUI boundary
            self.status_label.setText("Error")
            self.installed_label.setText("—")
            self.running_label.setText("—")
            self.enabled_label.setText("—")
            self.kernel_processes_label.setText("—")
            self._update_tray(False, f"Status error: {exc}")
            return
        self.status_label.setText(status.detail)
        self.installed_label.setText("Yes" if status.installed else "No")
        self.running_label.setText("Yes" if status.running else "No")
        if status.enabled is None:
            self.enabled_label.setText("Unknown")
        else:
            self.enabled_label.setText("Yes" if status.enabled else "No")
        if status.kernel_process_count is None:
            self.kernel_processes_label.setText("Unknown")
        else:
            self.kernel_processes_label.setText(str(status.kernel_process_count))
        self._update_tray(status.running, status.detail)
        self.start_button.setEnabled(status.installed and not status.running)
        self.stop_button.setEnabled(status.installed and status.running)
        self.restart_button.setEnabled(status.installed)
        self.uninstall_button.setEnabled(status.installed)

    def _run_operation(self, title: str, operation: Callable[[], str]) -> None:
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Operation in progress", "Wait for the current operation to finish.")
            return
        self._set_buttons_enabled(False)
        self._append_output(title, "Running…")
        self.worker = OperationThread(operation, self)
        self.worker.finished_with_result.connect(lambda message: self._operation_finished(title, message))
        self.worker.failed.connect(lambda message: self._operation_failed(title, message))
        self.worker.start()

    def _operation_finished(self, title: str, message: str) -> None:
        self._append_output(title, message)
        self._set_buttons_enabled(True)
        self.load_config_into_form()
        self.refresh_status()
        if self.tray:
            self.tray.showMessage(APP_NAME, message, QSystemTrayIcon.MessageIcon.Information, 5000)

    def _operation_failed(self, title: str, message: str) -> None:
        self._append_output(f"{title} failed", message)
        self._set_buttons_enabled(True)
        self.refresh_status()
        QMessageBox.critical(self, f"{title} failed", message)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for button in (
            self.install_button,
            self.start_button,
            self.stop_button,
            self.restart_button,
            self.uninstall_button,
            self.detect_button,
            self.save_config_button,
            self.edit_config_button,
            self.edit_other_config_button,
            self.refresh_button,
        ):
            button.setEnabled(enabled)

    def _append_output(self, title: str, message: str) -> None:
        self.output.appendPlainText(f"[{title}]\n{message.strip()}\n")

    def _browse_binary(self, target: QLineEdit) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Choose executable", str(Path.home()))
        if filename:
            target.setText(filename)

    def _open_folder(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _update_tray(self, running: bool, detail: str) -> None:
        if not self.tray:
            return
        self.tray.setIcon(make_icon(running))
        self.tray.setToolTip(f"{APP_NAME}: {detail}")

    def closeEvent(self, a0: QCloseEvent | None) -> None:
        if self.tray and self.tray.isVisible():
            self.hide()
            if a0 is not None:
                a0.ignore()
            self.tray.showMessage(APP_NAME, "Still running in the system tray.", QSystemTrayIcon.MessageIcon.Information, 3000)
        elif a0 is not None:
            super().closeEvent(a0)


def make_icon(running: bool = False) -> QIcon:
    icon = QIcon(str(TRAY_ICON_PATH))
    if not icon.isNull():
        return icon

    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor("transparent"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#2aa876") if running else QColor("#777777"))
    painter.setPen(QColor("#222222"))
    painter.drawEllipse(6, 6, 52, 52)
    painter.setPen(QColor("white"))
    font = painter.font()
    font.setBold(True)
    font.setPointSize(18)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "W")
    painter.end()
    return QIcon(pixmap)


def build_tray(app: QApplication, manager: BaseServiceManager) -> tuple[QSystemTrayIcon | None, MainWindow]:
    tray = QSystemTrayIcon(make_icon(False), app) if QSystemTrayIcon.isSystemTrayAvailable() else None
    window = MainWindow(manager, tray)
    if tray:
        menu = QMenu()
        show_action = QAction("Show Manager", menu)
        show_action.triggered.connect(lambda: _show_window(window))
        menu.addAction(show_action)
        menu.addSeparator()
        start_action = QAction("Start WSTPServer", menu)
        start_action.triggered.connect(lambda: window._run_operation("Start", manager.start))
        menu.addAction(start_action)
        stop_action = QAction("Stop WSTPServer", menu)
        stop_action.triggered.connect(lambda: window._run_operation("Stop", manager.stop))
        menu.addAction(stop_action)
        restart_action = QAction("Restart WSTPServer", menu)
        restart_action.triggered.connect(lambda: window._run_operation("Restart", manager.restart))
        menu.addAction(restart_action)
        menu.addSeparator()
        config_menu = QMenu("Configuration", menu)
        menu.addMenu(config_menu)
        edit_config_action = QAction("Edit Service Config…", config_menu)
        edit_config_action.triggered.connect(lambda: window.edit_config_file(manager.paths().config_file))
        config_menu.addAction(edit_config_action)
        edit_other_config_action = QAction("Edit Other Config File…", config_menu)
        edit_other_config_action.triggered.connect(window.choose_and_edit_config_file)
        config_menu.addAction(edit_other_config_action)
        open_config_action = QAction("Open Config Folder", config_menu)
        open_config_action.triggered.connect(lambda: window._open_folder(manager.paths().config_file.parent))
        config_menu.addAction(open_config_action)
        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(app.quit)
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda reason: _tray_activated(reason, window))
        tray.show()
    return tray, window


def _tray_activated(reason: QSystemTrayIcon.ActivationReason, window: MainWindow) -> None:
    if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
        _show_window(window)


def _show_window(window: MainWindow) -> None:
    window.show()
    window.raise_()
    window.activateWindow()


def _path_or_none(value: str) -> Path | None:
    value = value.strip()
    return Path(value) if value else None


def _bool_from_config(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv if argv is None or not argv else argv)
    app_args, start_hidden = _parse_app_args(raw_argv)
    app = QApplication(app_args)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(make_icon(False))
    app.setQuitOnLastWindowClosed(False)
    manager = get_service_manager()
    tray, window = build_tray(app, manager)
    if not start_hidden or tray is None:
        window.show()
    return app.exec()


def _parse_app_args(argv: list[str]) -> tuple[list[str], bool]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--start-hidden", "--background", action="store_true")
    args, qt_args = parser.parse_known_args(argv[1:])
    return [argv[0], *qt_args], bool(args.start_hidden)
