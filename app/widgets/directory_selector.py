from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.i18n import i18n_live, i18n_text
from app.i18n import mark as _i18n_mark
from app.i18n import refresh as _i18n_refresh


class DirectorySelector(QFrame):
    """Directory input, background-scan controls, and scan statistics."""
    choose_requested = Signal()
    scan_requested = Signal()
    rescan_requested = Signal()
    path_changed = Signal(str)

    def __init__(self, parent: QWidget | None=None) -> None:
        super().__init__(parent)
        self.setObjectName('directorySelector')
        root = QVBoxLayout(self)
        root.setContentsMargins(15, 14, 15, 14)
        root.setSpacing(10)
        title = _i18n_mark(QLabel(i18n_text('w.008')), 'text', 'w.008')
        title.setObjectName('crewPanelTitle')
        root.addWidget(title)
        self.path_edit = QLineEdit()
        self.path_edit.setObjectName('directoryPathEdit')
        self.path_edit.setPlaceholderText(i18n_live('w.009'))
        self.path_edit.textChanged.connect(self.path_changed.emit)
        root.addWidget(self.path_edit)
        buttons = QHBoxLayout()
        self.choose_button = _i18n_mark(QPushButton(i18n_text('w.010')), 'text', 'w.010')
        self.scan_button = _i18n_mark(QPushButton(i18n_text('w.011')), 'text', 'w.011')
        self.scan_button.setObjectName('autoScanButton')
        self.rescan_button = _i18n_mark(QPushButton(i18n_text('w.012')), 'text', 'w.012')
        buttons.addWidget(self.choose_button)
        buttons.addWidget(self.scan_button)
        buttons.addWidget(self.rescan_button)
        root.addLayout(buttons)
        self.include_children = _i18n_mark(QCheckBox(i18n_text('w.013')), 'text', 'w.013')
        self.include_children.setChecked(False)
        root.addWidget(self.include_children)
        self.status_label = _i18n_mark(QLabel(i18n_text('w.014')), 'text', 'w.014')
        self.status_label.setObjectName('autoScanStatus')
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        stats = QGridLayout()
        stats.setHorizontalSpacing(12)
        stats.setVerticalSpacing(8)
        self.audio_count_label = _i18n_mark(QLabel(i18n_text('w.015')), 'text', 'w.015')
        self.triggered_groups_label = _i18n_mark(QLabel(i18n_text('w.016')), 'text', 'w.016')
        self.missing_groups_label = _i18n_mark(QLabel(i18n_text('w.017')), 'text', 'w.017')
        stats.addWidget(self.audio_count_label, 0, 0)
        stats.addWidget(self.triggered_groups_label, 1, 0)
        stats.addWidget(self.missing_groups_label, 2, 0)
        root.addLayout(stats)
        root.addStretch(1)
        self.choose_button.clicked.connect(self.choose_requested.emit)
        self.scan_button.clicked.connect(self.scan_requested.emit)
        self.rescan_button.clicked.connect(self.rescan_requested.emit)
        self.set_controls_enabled(True, False)

    def retranslate(self) -> None:
        _i18n_refresh(self)

    def set_controls_enabled(self, enabled: bool, has_result: bool) -> None:
        self.path_edit.setEnabled(enabled)
        self.choose_button.setEnabled(enabled)
        self.include_children.setEnabled(enabled)
        has_path = bool(self.path_edit.text().strip())
        self.scan_button.setEnabled(enabled and has_path)
        self.rescan_button.setEnabled(enabled and has_path and has_result)

    def set_status(self, text: str) -> None:
        self.status_label.setText(i18n_live('w.004').format(text))

    def set_statistics(self, audio_count: int, triggered_groups: int, missing_groups: int) -> None:
        self.audio_count_label.setText(i18n_live('w.005').format(audio_count))
        self.triggered_groups_label.setText(i18n_live('w.006').format(triggered_groups))
        self.missing_groups_label.setText(i18n_live('w.007').format(missing_groups))