from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.models import CrewGroupPlan


class ConfirmationGroup(QFrame):
    """One independently selectable group of pending manual-copy targets."""

    selection_changed = Signal(str, bool)

    def __init__(
        self,
        plan: CrewGroupPlan,
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
        title = QLabel(plan.group.base_name)
        title.setObjectName("confirmationGroupTitle")
        title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(title)

        source_names = "、".join(source.file_name for source in plan.sources)
        source_dirs = "\n".join(sorted({str(source.path.parent) for source in plan.sources}))
        summary = QLabel(f"来源文件：{source_names}\n来源目录：{source_dirs}")
        summary.setObjectName("confirmationGroupSummary")
        summary.setWordWrap(True)
        summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary.setToolTip(summary.text())
        root.addWidget(summary)

        if not plan.assignments:
            empty = QLabel("该组没有需要补全的文件。")
            empty.setObjectName("mutedLabel")
            root.addWidget(empty)
            return

        selected_count = sum(selected_targets.get(item.selection_key, True) for item in plan.assignments)
        count_label = QLabel(f"待生成 {len(plan.assignments)} 个，已选 {selected_count} 个")
        count_label.setObjectName("confirmationGroupCount")
        root.addWidget(count_label)

        for assignment in plan.assignments:
            row = QFrame()
            row.setObjectName("confirmationTargetRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(9, 7, 9, 7)
            row_layout.setSpacing(9)
            checkbox = QCheckBox()
            checkbox.setChecked(selected_targets.get(assignment.selection_key, True))
            checkbox.setEnabled(not locked)
            checkbox.toggled.connect(
                lambda checked, key=assignment.selection_key: self.selection_changed.emit(key, checked)
            )
            target = QLabel(assignment.target_name)
            target.setObjectName("confirmationTargetName")
            target.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            source = QLabel(f"来源：{assignment.source.file_name}")
            source.setObjectName("confirmationTargetMeta")
            output = QLabel(f"输出：{assignment.output_path.parent}")
            output.setObjectName("confirmationTargetMeta")
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
                result.setObjectName("confirmationTargetResult")
                result.setWordWrap(True)
                metadata.addWidget(result)
            row_layout.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignTop)
            row_layout.addLayout(metadata, 1)
            root.addWidget(row)
            self._checkboxes[assignment.selection_key] = checkbox

    def set_all_selected(self, selected: bool) -> None:
        for checkbox in self._checkboxes.values():
            checkbox.setChecked(selected)
