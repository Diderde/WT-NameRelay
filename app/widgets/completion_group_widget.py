from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.models import CompletionGroup


class CompletionGroupWidget(QFrame):
    """Collapsible automatic-completion group with existing and missing rows."""

    selection_changed = Signal(str, bool)

    def __init__(self, group: CompletionGroup, selections: Mapping[str, bool], failures: Mapping[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._group = group
        self._checkboxes: dict[str, QCheckBox] = {}
        self.setObjectName("autoCompletionGroup")
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        header = QHBoxLayout()
        self.toggle_button = QPushButton(group.plan.group.base_name)
        self.toggle_button.setObjectName("autoGroupToggle")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)
        self.toggle_button.setToolTip(str(group.directory))
        header.addWidget(self.toggle_button, 1)
        root.addLayout(header)

        summary = QLabel(
            f"类型：{group.plan.group.group_type.value}　当前：{group.current_logical_count} / {group.expected_count}　"
            f"缺失：{group.missing_count}　补全后：{group.expected_count}\n目录：{group.directory}"
        )
        summary.setObjectName("autoGroupSummary")
        summary.setWordWrap(True)
        summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary.setToolTip(summary.text())
        root.addWidget(summary)

        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)
        existing_caption = QLabel("已存在文件")
        existing_caption.setObjectName("existingFilesCaption")
        content_layout.addWidget(existing_caption)
        for source in group.existing_files:
            extra = "（同名多格式）" if source.stem in group.duplicate_stems else ""
            label = QLabel(f"{source.file_name}{extra}")
            label.setObjectName("existingAudioFile")
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setToolTip(str(source.path))
            content_layout.addWidget(label)

        missing_heading = QHBoxLayout()
        missing_caption = QLabel("待补全文件")
        missing_caption.setObjectName("missingFilesCaption")
        group_all = QPushButton("本组全选")
        group_none = QPushButton("本组取消")
        group_all.setObjectName("smallActionButton")
        group_none.setObjectName("smallActionButton")
        missing_heading.addWidget(missing_caption)
        missing_heading.addStretch(1)
        missing_heading.addWidget(group_all)
        missing_heading.addWidget(group_none)
        content_layout.addLayout(missing_heading)
        for assignment in group.plan.assignments:
            row = QFrame()
            row.setObjectName("autoMissingRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(9, 7, 9, 7)
            checkbox = QCheckBox()
            checkbox.setChecked(selections.get(assignment.selection_key, True))
            checkbox.toggled.connect(lambda checked, key=assignment.selection_key: self.selection_changed.emit(key, checked))
            info = QVBoxLayout()
            target = QLabel(assignment.output_path.name)
            target.setObjectName("autoMissingTarget")
            source = QLabel(f"来源：{assignment.source.file_name}")
            source.setObjectName("autoMissingMeta")
            output = QLabel(f"输出：{assignment.output_path}")
            output.setObjectName("autoMissingMeta")
            output.setWordWrap(True)
            output.setToolTip(str(assignment.output_path))
            info.addWidget(target)
            info.addWidget(source)
            info.addWidget(output)
            if reason := failures.get(assignment.selection_key):
                failed = QLabel(f"上次失败：{reason}")
                failed.setObjectName("autoFailureReason")
                failed.setWordWrap(True)
                info.addWidget(failed)
            row_layout.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignTop)
            row_layout.addLayout(info, 1)
            content_layout.addWidget(row)
            self._checkboxes[assignment.selection_key] = checkbox
        root.addWidget(self.content)
        self.toggle_button.toggled.connect(self.content.setVisible)
        group_all.clicked.connect(lambda: self.set_all_selected(True))
        group_none.clicked.connect(lambda: self.set_all_selected(False))

    @property
    def group(self) -> CompletionGroup:
        return self._group

    def set_all_selected(self, selected: bool) -> None:
        for checkbox in self._checkboxes.values():
            checkbox.setChecked(selected)
