from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.i18n import i18n_text
from app.i18n import mark as _i18n_mark
from app.i18n import refresh as _i18n_refresh
from app.models import CrewGroupPlan


class ConfirmationGroup(QFrame):
    """One independently selectable group of pending manual-copy targets."""
    selection_changed = Signal(str, bool)

    def __init__(self, plan: CrewGroupPlan, selected_targets: Mapping[str, bool], parent: QWidget | None=None, *, locked: bool=False, result_messages: Mapping[str, str] | None=None) -> None:
        super().__init__(parent)
        self.setObjectName('confirmationGroup')
        self._checkboxes: dict[str, QCheckBox] = {}
        result_messages = result_messages or {}
        root = QVBoxLayout(self)
        root.setContentsMargins(15, 13, 15, 13)
        root.setSpacing(8)
        title = QLabel(plan.group.base_name)
        title.setObjectName('confirmationGroupTitle')
        title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(title)
        source_names = '、'.join(source.file_name for source in plan.sources)
        source_dirs = '\n'.join(sorted({str(source.path.parent) for source in plan.sources}))
        summary = _i18n_mark(QLabel(i18n_text('w.093').format(source_names, source_dirs)), 'text', 'w.093')
        summary.setObjectName('confirmationGroupSummary')
        summary.setWordWrap(True)
        summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary.setToolTip(summary.text())
        root.addWidget(summary)
        if not plan.assignments:
            empty = _i18n_mark(QLabel(i18n_text('w.086')), 'text', 'w.086')
            empty.setObjectName('mutedLabel')
            root.addWidget(empty)
            return
        selected_count = sum(selected_targets.get(item.selection_key, True) for item in plan.assignments)
        count_label = _i18n_mark(QLabel(i18n_text('w.094').format(len(plan.assignments), selected_count)), 'text', 'w.094')
        count_label.setObjectName('confirmationGroupCount')
        root.addWidget(count_label)
        for assignment in plan.assignments:
            row = QFrame()
            row.setObjectName('confirmationTargetRow')
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(9, 7, 9, 7)
            row_layout.setSpacing(9)
            checkbox = QCheckBox()
            checkbox.setChecked(selected_targets.get(assignment.selection_key, True))
            checkbox.setEnabled(not locked)
            checkbox.toggled.connect(lambda checked, key=assignment.selection_key: self.selection_changed.emit(key, checked))
            target = QLabel(assignment.target_name)
            target.setObjectName('confirmationTargetName')
            target.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            source = _i18n_mark(QLabel(i18n_text('w.059').format(assignment.source.file_name)), 'text', 'w.059')
            source.setObjectName('confirmationTargetMeta')
            output = _i18n_mark(QLabel(i18n_text('ui.174').format(assignment.output_path.parent)), 'text', 'ui.174')
            output.setObjectName('confirmationTargetMeta')
            output.setToolTip(str(assignment.output_path))
            output.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            metadata = QVBoxLayout()
            metadata.setSpacing(2)
            metadata.addWidget(target)
            metadata.addWidget(source)
            metadata.addWidget(output)
            result_message = result_messages.get(assignment.selection_key)
            if result_message:
                result = QLabel(result_message)
                result.setObjectName('confirmationTargetResult')
                result.setWordWrap(True)
                metadata.addWidget(result)
            row_layout.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignTop)
            row_layout.addLayout(metadata, 1)
            root.addWidget(row)
            self._checkboxes[assignment.selection_key] = checkbox

    def retranslate(self) -> None:
        _i18n_refresh(self)

    def set_all_selected(self, selected: bool) -> None:
        for checkbox in self._checkboxes.values():
            checkbox.setChecked(selected)