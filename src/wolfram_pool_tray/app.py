from __future__ import annotations

import argparse
import getpass
import re
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any, Callable

from PyQt6.QtCore import QPoint, QRect, QSize, QLockFile, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QCloseEvent, QDesktopServices, QIcon, QKeySequence, QPainter, QPalette, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
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
    QLayout,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QSystemTrayIcon,
    QHeaderView,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .config import default_config, first_pool, load_config, pools, save_config, update_first_pool
from .service import BaseServiceManager, DetectionResult, KernelProcess, ServiceError, get_service_manager

APP_NAME = "WSTPServer Manager"
TRAY_ICON_PATH = Path(__file__).with_name("assets") / "spikey.svg"
KERNEL_TABLE_ROW_HEIGHT = 40
KERNEL_SIGNAL_BUTTON_HEIGHT = 30

def build_dashboard_style(app: QApplication) -> str:
    palette = app.palette()
    accent = _system_accent_color(app)

    window = palette.color(QPalette.ColorRole.Window)
    window_text = palette.color(QPalette.ColorRole.WindowText)
    base = palette.color(QPalette.ColorRole.Base)
    text = palette.color(QPalette.ColorRole.Text)
    button = palette.color(QPalette.ColorRole.Button)
    button_text = palette.color(QPalette.ColorRole.ButtonText)
    alternate_base = palette.color(QPalette.ColorRole.AlternateBase)
    mid = palette.color(QPalette.ColorRole.Mid)
    placeholder = palette.color(QPalette.ColorRole.PlaceholderText)
    disabled_button = palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button)
    disabled_button_text = palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText)
    disabled_mid = palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Mid)

    is_dark = window.lightness() < 128

    accent_hex = accent.name()
    accent_soft = _mix_colors(base, accent, 0.16).name()
    accent_border = _mix_colors(mid, accent, 0.55).name()
    accent_hover = _mix_colors(button, accent, 0.22).name()
    accent_pressed = _mix_colors(button, accent, 0.38).name()
    accent_focus = (accent.lighter(130) if is_dark else accent.darker(115)).name()
    accent_separator = _mix_colors(mid, accent, 0.30).name()

    window_hex = window.name()
    window_text_hex = window_text.name()
    base_hex = base.name()
    text_hex = text.name()
    button_hex = button.name()
    button_text_hex = button_text.name()
    alternate_base_hex = alternate_base.name()
    mid_hex = mid.name()
    placeholder_hex = placeholder.name()
    disabled_button_hex = disabled_button.name()
    disabled_button_text_hex = disabled_button_text.name()
    disabled_mid_hex = disabled_mid.name()

    return f"""
QWidget#dashboardRoot {{
    background: {window_hex};
    color: {window_text_hex};
    font-size: 13px;
}}
QGroupBox {{
    background: {base_hex};
    border: 1px solid {accent_border};
    border-radius: 16px;
    margin-top: 18px;
    padding: 18px 16px 14px 16px;
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 18px;
    padding: 0 8px;
    color: {window_text_hex};
}}
QLabel {{
    color: {window_text_hex};
}}
QLabel#captionLabel {{
    color: {placeholder_hex};
    font-weight: 600;
}}
QLabel#pathLabel {{
    color: {text_hex};
    background: {accent_soft};
    border: 1px solid {accent_border};
    border-radius: 8px;
    padding: 6px 8px;
}}
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTableWidget {{
    background: {base_hex};
    color: {text_hex};
    border: 1px solid {mid_hex};
    border-radius: 10px;
    padding: 7px 9px;
    selection-background-color: {accent_hex};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {accent_focus};
}}
QPushButton {{
    background: {button_hex};
    color: {button_text_hex};
    border: 1px solid {mid_hex};
    border-radius: 10px;
    padding: 8px 12px;
    font-weight: 650;
}}
QPushButton:hover {{
    background: {accent_hover};
    border-color: {accent_border};
}}
QPushButton:pressed {{
    background: {accent_pressed};
    border-color: {accent_hex};
}}
QPushButton:disabled {{
    background: {disabled_button_hex};
    color: {disabled_button_text_hex};
    border-color: {disabled_mid_hex};
}}
QTableWidget {{
    gridline-color: {mid_hex};
    alternate-background-color: {alternate_base_hex};
}}
QHeaderView::section {{
    background: {accent_soft};
    color: {text_hex};
    border: 0;
    border-right: 1px solid {accent_border};
    padding: 7px;
    font-weight: 700;
}}
QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator:checked {{
    background: {accent_hex};
    border: 1px solid {accent_focus};
}}
QFrame#separatorLine {{
    color: {accent_separator};
    background: {accent_separator};
    max-height: 1px;
}}
"""

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


class FlowLayout(QLayout):
    """A lightweight layout that wraps widgets onto new rows as width shrinks."""

    def __init__(self, parent: QWidget | None = None, *, margin: int = 0, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items: list[Any] = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, a0: Any) -> None:
        self._items.append(a0)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> Any | None:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> Any | None:
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, a0: int) -> int:
        return self._do_layout(QRect(0, 0, a0, 0), test_only=True)

    def setGeometry(self, a0: QRect) -> None:
        super().setGeometry(a0)
        self._do_layout(a0, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        size += QSize(left + right, top + bottom)
        return size

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(left, top, -right, -bottom)
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0
        spacing = self.spacing()

        for item in self._items:
            item_size = item.sizeHint()
            next_x = x + item_size.width() + spacing
            if next_x - spacing > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y += line_height + spacing
                next_x = x + item_size.width() + spacing
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item_size))

            x = next_x
            line_height = max(line_height, item_size.height())

        return y + line_height - rect.y() + bottom


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
        self.resize(920, 720)
        self.setMinimumSize(360, 360)

        self.status_label = QLabel("Checking…")
        self.status_label.setObjectName("statusPill")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setMinimumWidth(120)
        self.installed_label = QLabel("—")
        self.running_label = QLabel("—")
        self.enabled_label = QLabel("—")
        self.kernel_processes_label = QLabel("—")
        self.kernel_processes_table = QTableWidget(0, 7)
        self._kernel_processes: tuple[KernelProcess, ...] | None = None
        self._kernel_sort_column: int | None = None
        self._kernel_sort_order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
        self.config_path_label = QLabel(str(self.manager.paths().config_file))
        self.config_path_label.setObjectName("pathLabel")
        self.config_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.config_path_label.setWordWrap(True)
        self.config_path_label.setMinimumWidth(0)
        self.config_path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.log_path_label = QLabel(str(self.manager.paths().log_file))
        self.log_path_label.setObjectName("pathLabel")
        self.log_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.log_path_label.setWordWrap(True)
        self.log_path_label.setMinimumWidth(0)
        self.log_path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.platform_label = QLabel(self.manager.name)
        self.platform_label.setWordWrap(True)

        self.wstpserver_edit = QLineEdit()
        self.kernel_edit = QLineEdit()
        for path_edit in (self.wstpserver_edit, self.kernel_edit):
            path_edit.setMinimumWidth(0)
            path_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.pool_name_label = QLabel("—")
        self.minimum_spin = QSpinBox()
        self.minimum_spin.setRange(0, 1024)
        self.maximum_spin = QSpinBox()
        self.maximum_spin.setRange(1, 1024)
        self.keep_alive_check = QCheckBox("Keep kernels warm")

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(1000)
        self.output.setMinimumHeight(100)

        self.install_button = QPushButton("Install / Update")
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.restart_button = QPushButton("Restart")
        self.uninstall_button = QPushButton("Uninstall")
        self.detect_button = QPushButton("Auto-detect Binaries")
        self.save_config_button = QPushButton("Save Pool Config")
        self.edit_config_button = QPushButton("Edit Full Config…")
        self.edit_other_config_button = QPushButton("Edit Other Config…")
        self.refresh_button = QPushButton("Refresh")
        self.open_config_button = QPushButton("Config")
        self.open_log_button = QPushButton("Logs")
        self._apply_button_icons()

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
        root.setObjectName("dashboardRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(14)

        summary = QGroupBox("Service status")
        summary_layout = QGridLayout(summary)
        summary_layout.setHorizontalSpacing(14)
        summary_layout.setVerticalSpacing(10)
        summary_layout.addWidget(_caption_label("Activity"), 0, 0)
        summary_layout.addWidget(self.status_label, 0, 1)
        summary_layout.addWidget(_caption_label("Platform"), 1, 0)
        summary_layout.addWidget(self.platform_label, 1, 1)
        summary_layout.addWidget(_caption_label("Installed"), 2, 0)
        summary_layout.addWidget(self.installed_label, 2, 1)
        summary_layout.addWidget(_caption_label("Running"), 3, 0)
        summary_layout.addWidget(self.running_label, 3, 1)
        summary_layout.addWidget(_caption_label("Enabled at login"), 4, 0)
        summary_layout.addWidget(self.enabled_label, 4, 1)
        summary_layout.addWidget(_caption_label("Running kernels"), 5, 0)
        summary_layout.addWidget(self.kernel_processes_label, 5, 1)
        summary_layout.addWidget(_caption_label("Config"), 6, 0)
        summary_layout.addWidget(self.config_path_label, 6, 1)
        summary_layout.addWidget(_caption_label("Log"), 7, 0)
        summary_layout.addWidget(self.log_path_label, 7, 1)
        summary_layout.setColumnStretch(1, 1)
        root_layout.addWidget(summary)

        kernels = QGroupBox("Running kernels under WSTPServer")
        kernels_layout = QVBoxLayout(kernels)
        self.kernel_processes_table.setHorizontalHeaderLabels(("PID", "Parent PID", "CPU", "Memory", "Executable", "Command", "Signal"))
        vertical_header = self.kernel_processes_table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
            vertical_header.setMinimumSectionSize(KERNEL_TABLE_ROW_HEIGHT)
            vertical_header.setDefaultSectionSize(KERNEL_TABLE_ROW_HEIGHT)
        self.kernel_processes_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.kernel_processes_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.kernel_processes_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.kernel_processes_table.setAlternatingRowColors(True)
        self.kernel_processes_table.setMinimumSize(0, 96)
        self.kernel_processes_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        horizontal_header = self.kernel_processes_table.horizontalHeader()
        if horizontal_header is not None:
            horizontal_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            horizontal_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            horizontal_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            horizontal_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            horizontal_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            horizontal_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
            horizontal_header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
            horizontal_header.setSectionsClickable(True)
            horizontal_header.setSortIndicatorShown(True)
            horizontal_header.sectionClicked.connect(self._on_kernel_header_clicked)
        kernels_layout.addWidget(self.kernel_processes_table)
        root_layout.addWidget(kernels)

        actions_layout = FlowLayout(spacing=8)
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
        binaries_layout.addWidget(_caption_label("wstpserver"), 0, 0)
        binaries_layout.addWidget(self.wstpserver_edit, 0, 1)
        browse_wstpserver = QPushButton("Browse…")
        browse_wstpserver.setIcon(_standard_icon(QStyle.StandardPixmap.SP_DialogOpenButton))
        browse_wstpserver.clicked.connect(lambda: self._browse_binary(self.wstpserver_edit))
        binaries_layout.addWidget(browse_wstpserver, 0, 2)
        binaries_layout.addWidget(_caption_label("WolframKernel"), 1, 0)
        binaries_layout.addWidget(self.kernel_edit, 1, 1)
        browse_kernel = QPushButton("Browse…")
        browse_kernel.setIcon(_standard_icon(QStyle.StandardPixmap.SP_DialogOpenButton))
        browse_kernel.clicked.connect(lambda: self._browse_binary(self.kernel_edit))
        binaries_layout.addWidget(browse_kernel, 1, 2)
        binaries_layout.addWidget(self.detect_button, 2, 1)
        root_layout.addWidget(binaries)

        pool = QGroupBox("Kernel pool")
        pool_layout = QFormLayout(pool)
        pool_layout.addRow(_caption_label("Pool"), self.pool_name_label)
        pool_layout.addRow(_caption_label("Minimum kernels"), self.minimum_spin)
        pool_layout.addRow(_caption_label("Maximum kernels"), self.maximum_spin)
        pool_layout.addRow(_caption_label("KeepAlive"), self.keep_alive_check)
        pool_buttons = FlowLayout(spacing=8)
        pool_buttons.addWidget(self.save_config_button)
        pool_buttons.addWidget(self.edit_config_button)
        pool_buttons.addWidget(self.edit_other_config_button)
        pool_buttons.addWidget(self.open_config_button)
        pool_buttons.addWidget(self.open_log_button)
        pool_layout.addRow(pool_buttons)
        root_layout.addWidget(pool)

        separator = QFrame()
        separator.setObjectName("separatorLine")
        separator.setFrameShape(QFrame.Shape.HLine)
        root_layout.addWidget(separator)
        root_layout.addWidget(_caption_label("Operation output"))
        root_layout.addWidget(self.output, stretch=1)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(root)
        self.setCentralWidget(scroll_area)

    def _apply_button_icons(self) -> None:
        icon_map = (
            (self.install_button, QStyle.StandardPixmap.SP_ArrowDown),
            (self.start_button, QStyle.StandardPixmap.SP_MediaPlay),
            (self.stop_button, QStyle.StandardPixmap.SP_MediaStop),
            (self.restart_button, QStyle.StandardPixmap.SP_BrowserReload),
            (self.uninstall_button, QStyle.StandardPixmap.SP_TrashIcon),
            (self.detect_button, QStyle.StandardPixmap.SP_FileDialogInfoView),
            (self.save_config_button, QStyle.StandardPixmap.SP_DialogSaveButton),
            (self.edit_config_button, QStyle.StandardPixmap.SP_FileDialogDetailedView),
            (self.edit_other_config_button, QStyle.StandardPixmap.SP_FileIcon),
            (self.refresh_button, QStyle.StandardPixmap.SP_BrowserReload),
            (self.open_config_button, QStyle.StandardPixmap.SP_DirOpenIcon),
            (self.open_log_button, QStyle.StandardPixmap.SP_FileIcon),
        )
        for button, pixmap in icon_map:
            button.setIcon(_standard_icon(pixmap))

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
            self._set_activity_state("red", "Error")
            self.installed_label.setText("—")
            self.running_label.setText("—")
            self.enabled_label.setText("—")
            self.kernel_processes_label.setText("—")
            self._set_kernel_processes(None)
            self._update_tray(False, f"Status error: {exc}")
            return
        if status.running:
            self._set_activity_state("green", status.detail or "Running")
        elif status.installed:
            self._set_activity_state("yellow", status.detail or "Installed / idle")
        else:
            self._set_activity_state("red", status.detail or "Not installed")
        self.installed_label.setText("Yes" if status.installed else "No")
        self.running_label.setText("Active" if status.running else "Stopped")
        if status.enabled is None:
            self.enabled_label.setText("Unknown")
        else:
            self.enabled_label.setText("Yes" if status.enabled else "No")
        if status.kernel_process_count is None:
            self.kernel_processes_label.setText("Unknown")
        else:
            self.kernel_processes_label.setText(str(status.kernel_process_count))
        self._set_kernel_processes(status.kernel_processes)
        self._update_tray(status.running, status.detail)
        self.start_button.setEnabled(status.installed and not status.running)
        self.stop_button.setEnabled(status.installed and status.running)
        self.restart_button.setEnabled(status.installed)
        self.uninstall_button.setEnabled(status.installed)

    def _set_activity_state(self, light: str, detail: str) -> None:
        detail = detail.strip() or "Unknown"
        self.status_label.setText(detail)
        colors = {
            "green": ("#052e1a", "#86efac", "#22c55e"),
            "yellow": ("#2f2508", "#fde68a", "#f59e0b"),
            "red": ("#3f1218", "#fecaca", "#ef4444"),
        }
        background, foreground, border = colors.get(light, colors["yellow"])
        self.status_label.setStyleSheet(
            "QLabel#statusPill {"
            f"background: {background};"
            f"color: {foreground};"
            f"border: 1px solid {border};"
            "border-radius: 12px;"
            "padding: 8px 12px;"
            "font-weight: 800;"
            "}"
        )

    def _set_kernel_processes(self, processes: tuple[KernelProcess, ...] | None) -> None:
        self._kernel_processes = processes
        self._render_kernel_table()

    def _render_kernel_table(self) -> None:
        processes = self._kernel_processes
        self.kernel_processes_table.clearSpans()
        self.kernel_processes_table.setRowCount(0)
        if processes is None:
            self.kernel_processes_table.setRowCount(1)
            item = QTableWidgetItem("Kernel process details are unavailable on this platform")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.kernel_processes_table.setItem(0, 0, item)
            self.kernel_processes_table.setSpan(0, 0, 1, 7)
            return
        if not processes:
            self.kernel_processes_table.setRowCount(1)
            item = QTableWidgetItem("No running kernels detected under WSTPServer")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.kernel_processes_table.setItem(0, 0, item)
            self.kernel_processes_table.setSpan(0, 0, 1, 7)
            return

        main, parallel = _split_kernel_processes(processes)
        if self._kernel_sort_column is not None:
            main = _sort_kernel_processes(main, self._kernel_sort_column, self._kernel_sort_order)
            parallel = _sort_kernel_processes(parallel, self._kernel_sort_column, self._kernel_sort_order)

        self._append_kernel_group_rows("Main kernels", main)
        self._append_kernel_group_rows("Parallel kernels", parallel)

    def _append_kernel_group_rows(self, title: str, processes: tuple[KernelProcess, ...]) -> None:
        table = self.kernel_processes_table
        divider_row = table.rowCount()
        table.insertRow(divider_row)
        divider_item = QTableWidgetItem(title)
        divider_item.setFlags(divider_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        font = divider_item.font()
        font.setBold(True)
        divider_item.setFont(font)
        palette = table.palette()
        background = _mix_colors(
            palette.color(QPalette.ColorRole.Base),
            palette.color(QPalette.ColorRole.Mid),
            0.35,
        )
        divider_item.setBackground(background)
        table.setItem(divider_row, 0, divider_item)
        table.setSpan(divider_row, 0, 1, 7)

        if not processes:
            placeholder_row = table.rowCount()
            table.insertRow(placeholder_row)
            placeholder_item = QTableWidgetItem("None")
            placeholder_item.setFlags(placeholder_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            table.setItem(placeholder_row, 0, placeholder_item)
            table.setSpan(placeholder_row, 0, 1, 7)
            return

        for process in processes:
            row = table.rowCount()
            table.insertRow(row)
            parent_pid = "" if process.parent_pid is None else str(process.parent_pid)
            values = (
                str(process.pid),
                parent_pid,
                _format_cpu(process.cpu_percent),
                _format_bytes(process.memory_bytes),
                process.executable,
                process.command,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column < 4:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row, column, item)
            table.setCellWidget(row, 6, self._kernel_signal_buttons(process.pid))

    def _on_kernel_header_clicked(self, column: int) -> None:
        if column == 6:
            return
        if self._kernel_sort_column == column:
            self._kernel_sort_order = (
                Qt.SortOrder.DescendingOrder
                if self._kernel_sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self._kernel_sort_column = column
            self._kernel_sort_order = Qt.SortOrder.AscendingOrder
        horizontal_header = self.kernel_processes_table.horizontalHeader()
        if horizontal_header is not None:
            horizontal_header.setSortIndicator(column, self._kernel_sort_order)
        self._render_kernel_table()

    def _kernel_signal_buttons(self, pid: int) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        term_button = QPushButton("Term")
        term_button.setIcon(_standard_icon(QStyle.StandardPixmap.SP_MediaStop))
        term_button.setToolTip(f"Send SIGTERM to kernel process {pid}")
        term_button.setFixedWidth(72)
        term_button.setMinimumHeight(KERNEL_SIGNAL_BUTTON_HEIGHT)
        term_button.clicked.connect(lambda _checked=False, target_pid=pid: self._signal_kernel_process(target_pid, force=False))
        layout.addWidget(term_button)

        kill_button = QPushButton("Kill")
        kill_button.setIcon(_standard_icon(QStyle.StandardPixmap.SP_MessageBoxCritical))
        kill_button.setToolTip(f"Send SIGKILL to kernel process {pid}")
        kill_button.setFixedWidth(72)
        kill_button.setMinimumHeight(KERNEL_SIGNAL_BUTTON_HEIGHT)
        kill_button.clicked.connect(lambda _checked=False, target_pid=pid: self._signal_kernel_process(target_pid, force=True))
        layout.addWidget(kill_button)
        return widget

    def _signal_kernel_process(self, pid: int, *, force: bool) -> None:
        signal_name = "SIGKILL" if force else "SIGTERM"
        choice = QMessageBox.question(
            self,
            f"Send {signal_name}?",
            f"Send {signal_name} to kernel process {pid}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if choice == QMessageBox.StandardButton.Yes:
            self._run_operation(signal_name, lambda: self.manager.signal_kernel_process(pid, force=force))

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


def _caption_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("captionLabel")
    return label


def _system_accent_color(app: QApplication) -> QColor:
    # QPalette.Accent (Qt >= 6.6) is not reliably populated by every platform
    # theme integration (observed stuck at Qt's generic default on KDE via
    # xdg-desktop-portal), while Highlight is consistently wired to the live
    # system accent color across platforms. Use Highlight as the source of truth.
    return app.palette().color(QPalette.ColorRole.Highlight)


def _mix_colors(base: QColor, overlay: QColor, overlay_ratio: float) -> QColor:
    ratio = max(0.0, min(1.0, overlay_ratio))
    inverse = 1.0 - ratio
    return QColor(
        round(base.red() * inverse + overlay.red() * ratio),
        round(base.green() * inverse + overlay.green() * ratio),
        round(base.blue() * inverse + overlay.blue() * ratio),
    )


def _standard_icon(pixmap: QStyle.StandardPixmap) -> QIcon:
    style = QApplication.style()
    return style.standardIcon(pixmap) if style is not None else QIcon()


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


def _split_kernel_processes(
    processes: tuple[KernelProcess, ...],
) -> tuple[tuple[KernelProcess, ...], tuple[KernelProcess, ...]]:
    main = tuple(process for process in processes if not process.is_subkernel)
    parallel = tuple(process for process in processes if process.is_subkernel)
    return main, parallel


_KERNEL_SORT_KEYS: dict[int, Callable[[KernelProcess], Any]] = {
    0: lambda process: process.pid,
    1: lambda process: process.parent_pid,
    2: lambda process: process.cpu_percent,
    3: lambda process: process.memory_bytes,
    4: lambda process: process.executable.lower(),
    5: lambda process: process.command.lower(),
}


def _sort_kernel_processes(
    processes: tuple[KernelProcess, ...], column: int, order: Qt.SortOrder
) -> tuple[KernelProcess, ...]:
    key = _KERNEL_SORT_KEYS.get(column)
    if key is None:
        return processes
    # None always sorts last, in either direction, so reversing for
    # descending order can't be done with a single reverse=True sort.
    with_value = [process for process in processes if key(process) is not None]
    without_value = [process for process in processes if key(process) is None]
    with_value.sort(key=key, reverse=order == Qt.SortOrder.DescendingOrder)
    return tuple(with_value + without_value)


def _format_cpu(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}%"


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "—"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(amount)} {unit}"
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"


def _instance_lock_path() -> Path:
    user = re.sub(r"[^A-Za-z0-9_.-]", "_", getpass.getuser())
    return Path(tempfile.gettempdir()) / f"wolfram-wstpserver-tray-{user}.lock"


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv if argv is None or not argv else argv)
    app_args, start_hidden = _parse_app_args(raw_argv)
    app = QApplication(app_args)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(make_icon(False))

    def refresh_style(*_args: object) -> None:
        app.setStyleSheet(build_dashboard_style(app))

    refresh_style()
    app.paletteChanged.connect(refresh_style)
    style_hints = app.styleHints()
    if hasattr(style_hints, "colorSchemeChanged"):
        style_hints.colorSchemeChanged.connect(refresh_style)

    instance_lock = QLockFile(str(_instance_lock_path()))
    if not instance_lock.tryLock(0):
        if not start_hidden:
            QMessageBox.information(None, APP_NAME, "WSTPServer Manager is already running in the system tray.")
        return 0

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
