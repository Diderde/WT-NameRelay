from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.models import ManualCopyMode, RadioManualGroupPlan, RadioTargetConflictKind


class RadioManualConfirmationGroup(QFrame):
    selection_changed = Signal(str, bool)

    def __init__(
        self,
        plan: RadioManualGroupPlan,
        selected_targets: Mapping[str, bool],
        parent: QWidget | None = None,
        *,
        locked: bool = False,
        result_messages: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("confirmationGroup")
        self._checkboxes: dict[str, QCheckBox] = {}
        result_messages = result_messages or {}
        root = QVBoxLayout(self)
        root.setContentsMargins(15, 13, 15, 13)
        root.setSpacing(8)

        title = QLabel(f"项目组：{plan.group.base_name}")
        title.setObjectName("confirmationGroupTitle")
        title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(title)
        mode_text = "平均分配" if plan.copy_mode is ManualCopyMode.AVERAGE else "顺序复制"
        if plan.fallback_reason:
            mode_text += "（平均分配不可用）"
        summary = QLabel(
            f"复制模式：{mode_text}\n命名类型：{plan.group.group_type.value}\n源目录：{plan.directory}"
        )
        summary.setObjectName("confirmationGroupSummary")
        summary.setWordWrap(True)
        summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(summary)
        if plan.fallback_reason:
            fallback = QLabel(plan.fallback_reason)
            fallback.setObjectName("assignmentHint")
            fallback.setWordWrap(True)
            root.addWidget(fallback)

        if not plan.assignments:
            empty = QLabel("该组没有需要补全的文件。")
            empty.setObjectName("mutedLabel")
            root.addWidget(empty)
            return
        selected_count = sum(selected_targets.get(item.selection_key, True) for item in plan.assignments)
        count = QLabel(f"待处理 {len(plan.assignments)} 个，已选 {selected_count} 个")
        count.setObjectName("confirmationGroupCount")
        root.addWidget(count)

        if plan.copy_mode is ManualCopyMode.AVERAGE:
            assignments_by_group: dict[int, list[object]] = {}
            for assignment in plan.assignments:
                assignments_by_group.setdefault(assignment.target_group_index, []).append(assignment)
            for triple in plan.triples:
                block = QFrame()
                block.setObjectName("radioAverageTriple")
                block_layout = QVBoxLayout(block)
                block_layout.setContentsMargins(10, 8, 10, 8)
                source = QLabel(f"第 {triple.index + 1} 小组来源：{triple.source.file_name}")
                source.setObjectName("confirmationTargetMeta")
                source.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                block_layout.addWidget(source)
                for assignment in assignments_by_group.get(triple.index, []):
                    self._add_target_row(block_layout, assignment, selected_targets, locked, result_messages)
                root.addWidget(block)
        else:
            for assignment in plan.assignments:
                self._add_target_row(root, assignment, selected_targets, locked, result_messages)

    def _add_target_row(
        self,
        parent_layout: QVBoxLayout,
        assignment: object,
        selected_targets: Mapping[str, bool],
        locked: bool,
        result_messages: Mapping[str, str],
    ) -> None:
        row = QFrame()
        row.setObjectName("confirmationTargetRow")
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
            target_text += "　来源重写（平均分配所需）"
        elif assignment.conflict_kind is RadioTargetConflictKind.EXTERNAL_CONFLICT:
            target_text += "　外部文件冲突"
        target = QLabel(target_text)
        target.setObjectName("confirmationTargetName")
        source = QLabel(f"来源：{assignment.source.file_name}")
        source.setObjectName("confirmationTargetMeta")
        output = QLabel(f"输出：{assignment.output_path}")
        output.setObjectName("confirmationTargetMeta")
        output.setToolTip(str(assignment.output_path))
        for label in (target, source, output):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            metadata.addWidget(label)
        if message := result_messages.get(key):
            result = QLabel(message)
            result.setObjectName("confirmationTargetResult")
            result.setWordWrap(True)
            metadata.addWidget(result)
        row_layout.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignTop)
        row_layout.addLayout(metadata, 1)
        parent_layout.addWidget(row)
        self._checkboxes[key] = checkbox
