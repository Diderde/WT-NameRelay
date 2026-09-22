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
from app.models import ManualCopyMode, RadioManualGroupPlan, RadioTargetConflictKind


class RadioManualConfirmationGroup(QFrame):
    selection_changed = Signal(str, bool)

    def __init__(self, plan: RadioManualGroupPlan, selected_targets: Mapping[str, bool], parent: QWidget | None=None, *, locked: bool=False, result_messages: Mapping[str, str] | None=None) -> None:
        super().__init__(parent)
        self.setObjectName('confirmationGroup')
        self._checkboxes: dict[str, QCheckBox] = {}
        result_messages = result_messages or {}
        root = QVBoxLayout(self)
        root.setContentsMargins(15, 13, 15, 13)
        root.setSpacing(8)
        title = _i18n_mark(QLabel(i18n_text('w.074').format(plan.group.base_name)), 'text', 'w.074')
        title.setObjectName('confirmationGroupTitle')
        title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(title)
        mode_text = i18n_text('w.078') if plan.copy_mode is ManualCopyMode.AVERAGE else i18n_text('w.079')
        if plan.fallback_reason:
            mode_text += i18n_text('w.080')
        summary = _i18n_mark(QLabel(i18n_text('w.075').format(mode_text, plan.group.group_type.value, plan.directory)), 'text', 'w.075')
        summary.setObjectName('confirmationGroupSummary')
        summary.setWordWrap(True)
        summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(summary)
        if plan.fallback_reason:
            fallback = QLabel(plan.fallback_reason)
            fallback.setObjectName('assignmentHint')
            fallback.setWordWrap(True)
            root.addWidget(fallback)
        if not plan.assignments:
            empty = _i18n_mark(QLabel(i18n_text('w.086')), 'text', 'w.086')
            empty.setObjectName('mutedLabel')
            root.addWidget(empty)
            return
        selected_count = sum(selected_targets.get(item.selection_key, True) for item in plan.assignments)
        count = _i18n_mark(QLabel(i18n_text('w.076').format(len(plan.assignments), selected_count)), 'text', 'w.076')
        count.setObjectName('confirmationGroupCount')
        root.addWidget(count)
        if plan.copy_mode is ManualCopyMode.AVERAGE:
            assignments_by_group: dict[int, list[object]] = {}
            for assignment in plan.assignments:
                assignments_by_group.setdefault(assignment.target_group_index, []).append(assignment)
            for triple in plan.triples:
                block = QFrame()
                block.setObjectName('radioAverageTriple')
                block_layout = QVBoxLayout(block)
                block_layout.setContentsMargins(10, 8, 10, 8)
                source = _i18n_mark(QLabel(i18n_text('w.077').format(triple.index + 1, triple.source.file_name)), 'text', 'w.077')
                source.setObjectName('confirmationTargetMeta')
                source.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                block_layout.addWidget(source)
                for assignment in assignments_by_group.get(triple.index, []):
                    self._add_target_row(block_layout, assignment, selected_targets, locked, result_messages)
                root.addWidget(block)
        else:
            for assignment in plan.assignments:
                self._add_target_row(root, assignment, selected_targets, locked, result_messages)

    def retranslate(self) -> None:
        _i18n_refresh(self)

    def _add_target_row(self, parent_layout: QVBoxLayout, assignment: object, selected_targets: Mapping[str, bool], locked: bool, result_messages: Mapping[str, str]) -> None:
        row = QFrame()
        row.setObjectName('confirmationTargetRow')
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(9, 7, 9, 7)
        checkbox = QCheckBox()
        key = assignment.selection_key
        checkbox.setChecked(selected_targets.get(key, True))
        checkbox.setEnabled(not locked)
        checkbox.toggled.connect(lambda checked, item_key=key: self.selection_changed.emit(item_key, checked))
        metadata = QVBoxLayout()
        target_text = assignment.target_name
        if assignment.conflict_kind is RadioTargetConflictKind.SOURCE_TARGET:
            target_text += i18n_text('w.081')
        elif assignment.conflict_kind is RadioTargetConflictKind.EXTERNAL_CONFLICT:
            target_text += i18n_text('w.090')
        target = QLabel(target_text)
        target.setObjectName('confirmationTargetName')
        source = _i18n_mark(QLabel(i18n_text('w.059').format(assignment.source.file_name)), 'text', 'w.059')
        source.setObjectName('confirmationTargetMeta')
        output = _i18n_mark(QLabel(i18n_text('ui.174').format(assignment.output_path)), 'text', 'ui.174')
        output.setObjectName('confirmationTargetMeta')
        output.setToolTip(str(assignment.output_path))
        for label in (target, source, output):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            metadata.addWidget(label)
        if (message := result_messages.get(key)):
            result = QLabel(message)
            result.setObjectName('confirmationTargetResult')
            result.setWordWrap(True)
            metadata.addWidget(result)
        row_layout.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignTop)
        row_layout.addLayout(metadata, 1)
        parent_layout.addWidget(row)
        self._checkboxes[key] = checkbox