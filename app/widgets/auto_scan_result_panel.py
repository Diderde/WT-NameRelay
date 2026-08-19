from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from app.models import CompletionGroup

from .completion_group_widget import CompletionGroupWidget


class AutoScanResultPanel(QFrame):
    """Filterable, scrollable automatic-completion confirmation surface."""

    selection_changed = Signal(str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("autoScanResultPanel")
        self._group_widgets: list[CompletionGroupWidget] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(15, 14, 15, 14)
        root.setSpacing(9)
        title = QLabel("扫描结果与待确认区")
        title.setObjectName("crewPanelTitle")
        root.addWidget(title)
        controls = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("autoSearchEdit")
        self.search_edit.setPlaceholderText("搜索基础名称")
        self.only_missing = QCheckBox("仅显示缺失组")
        self.only_missing.setChecked(True)
        controls.addWidget(self.search_edit, 1)
        controls.addWidget(self.only_missing)
        root.addLayout(controls)
        legend = QLabel("红色：目录中已存在　　白色：待复制补全")
        legend.setObjectName("autoLegend")
        root.addWidget(legend)
        self.plan_stats = QLabel("复制前文件数：0　计划新增：0　复制后文件数：0")
        self.plan_stats.setObjectName("autoPlanStats")
        root.addWidget(self.plan_stats)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("autoResultsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget()
        self.container.setObjectName("autoResultsContainer")
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(10)
        self.layout.addStretch(1)
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.only_missing.toggled.connect(self._apply_filter)

    def set_groups(
        self,
        groups: tuple[CompletionGroup, ...],
        selections: Mapping[str, bool],
        failures: Mapping[str, str],
    ) -> None:
        self._group_widgets.clear()
        while self.layout.count() > 1:
            item = self.layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not groups:
            empty = QLabel("暂无需要补全的触发组。")
            empty.setObjectName("mutedLabel")
            self.layout.insertWidget(0, empty)
        else:
            for index, group in enumerate(groups):
                widget = CompletionGroupWidget(group, selections, failures)
                widget.selection_changed.connect(self.selection_changed)
                self._group_widgets.append(widget)
                self.layout.insertWidget(self.layout.count() - 1, widget)
                if index < len(groups) - 1:
                    separator = QFrame()
                    separator.setObjectName("autoGroupSeparator")
                    separator.setFrameShape(QFrame.Shape.HLine)
                    separator.setFixedHeight(1)
                    self.layout.insertWidget(self.layout.count() - 1, separator)
        self._apply_filter()

    def set_plan_statistics(self, before: int, planned: int) -> None:
        self.plan_stats.setText(
            f"复制前文件数：{before}　计划新增：{planned}　复制后文件数：{before + planned}"
        )

    def set_interaction_enabled(self, enabled: bool) -> None:
        self.search_edit.setEnabled(enabled)
        self.only_missing.setEnabled(enabled)
        self.scroll.setEnabled(enabled)

    def _apply_filter(self) -> None:
        query = self.search_edit.text().strip().casefold()
        for widget in self._group_widgets:
            group = widget.group
            matches_name = not query or query in group.plan.group.base_name.casefold()
            matches_missing = not self.only_missing.isChecked() or group.missing_count > 0
            widget.setVisible(matches_name and matches_missing)
