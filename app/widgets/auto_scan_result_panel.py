from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.i18n import i18n_live, i18n_text
from app.i18n import mark as _i18n_mark
from app.i18n import refresh as _i18n_refresh
from app.models import CompletionGroup

from .completion_group_widget import CompletionGroupWidget


class AutoScanResultPanel(QFrame):
    """Filterable, scrollable automatic-completion confirmation surface."""
    selection_changed = Signal(str, bool)

    def __init__(self, parent: QWidget | None=None) -> None:
        super().__init__(parent)
        self.setObjectName('autoScanResultPanel')
        self._group_widgets: list[CompletionGroupWidget] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(15, 14, 15, 14)
        root.setSpacing(9)
        title = _i18n_mark(QLabel(i18n_text('w.049')), 'text', 'w.049')
        title.setObjectName('crewPanelTitle')
        root.addWidget(title)
        controls = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName('autoSearchEdit')
        self.search_edit.setPlaceholderText(i18n_live('w.050'))
        self.only_missing = _i18n_mark(QCheckBox(i18n_text('w.051')), 'text', 'w.051')
        self.only_missing.setChecked(True)
        controls.addWidget(self.search_edit, 1)
        controls.addWidget(self.only_missing)
        root.addLayout(controls)
        legend = _i18n_mark(QLabel(i18n_text('w.052')), 'text', 'w.052')
        legend.setObjectName('autoLegend')
        root.addWidget(legend)
        self.plan_stats = _i18n_mark(QLabel(i18n_text('w.053')), 'text', 'w.053')
        self.plan_stats.setObjectName('autoPlanStats')
        root.addWidget(self.plan_stats)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName('autoResultsScroll')
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget()
        self.container.setObjectName('autoResultsContainer')
        self.group_layout = QVBoxLayout(self.container)
        self.group_layout.setContentsMargins(0, 0, 0, 0)
        self.group_layout.setSpacing(10)
        self.group_layout.addStretch(1)
        self.scroll_area.setWidget(self.container)
        root.addWidget(self.scroll_area, 1)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.only_missing.toggled.connect(self._apply_filter)

    def retranslate(self) -> None:
        _i18n_refresh(self)

    def set_groups(self, groups: tuple[CompletionGroup, ...], selections: Mapping[str, bool], failures: Mapping[str, str]) -> None:
        self._group_widgets.clear()
        while self.group_layout.count() > 1:
            item = self.group_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not groups:
            empty = _i18n_mark(QLabel(i18n_text('w.054')), 'text', 'w.054')
            empty.setObjectName('mutedLabel')
            self.group_layout.insertWidget(0, empty)
        else:
            for index, group in enumerate(groups):
                widget = CompletionGroupWidget(group, selections, failures)
                widget.selection_changed.connect(self.selection_changed)
                self._group_widgets.append(widget)
                self.group_layout.insertWidget(self.group_layout.count() - 1, widget)
                if index < len(groups) - 1:
                    separator = QFrame()
                    separator.setObjectName('autoGroupSeparator')
                    separator.setFrameShape(QFrame.Shape.HLine)
                    separator.setFixedHeight(1)
                    self.group_layout.insertWidget(self.group_layout.count() - 1, separator)
        self._apply_filter()

    def set_plan_statistics(self, before: int, planned: int) -> None:
        self.plan_stats.setText(i18n_live('w.048').format(before, planned, before + planned))

    def set_interaction_enabled(self, enabled: bool) -> None:
        self.search_edit.setEnabled(enabled)
        self.only_missing.setEnabled(enabled)
        self.scroll_area.setEnabled(enabled)

    def _apply_filter(self) -> None:
        query = self.search_edit.text().strip().casefold()
        for widget in self._group_widgets:
            group = widget.group
            matches_name = not query or query in group.plan.group.base_name.casefold()
            matches_missing = not self.only_missing.isChecked() or group.missing_count > 0
            widget.setVisible(matches_name and matches_missing)