from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.i18n import i18n_text
from app.i18n import mark as _i18n_mark
from app.i18n import refresh as _i18n_refresh
from app.models import CompletionGroup


class CompletionGroupWidget(QFrame):
    """Collapsible automatic-completion group with existing and missing rows."""
    selection_changed = Signal(str, bool)

    def __init__(self, group: CompletionGroup, selections: Mapping[str, bool], failures: Mapping[str, str], parent: QWidget | None=None) -> None:
        super().__init__(parent)
        self._group = group
        self._checkboxes: dict[str, QCheckBox] = {}
        self.setObjectName('autoCompletionGroup')
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)
        header = QHBoxLayout()
        self.toggle_button = QPushButton(group.plan.group.base_name)
        self.toggle_button.setObjectName('autoGroupToggle')
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)
        self.toggle_button.setToolTip(str(group.directory))
        header.addWidget(self.toggle_button, 1)
        root.addLayout(header)
        summary = _i18n_mark(QLabel(i18n_text('w.058').format(group.plan.group.group_type.value, group.current_logical_count, group.expected_count, group.missing_count, group.expected_count, group.directory)), 'text', 'w.058')
        summary.setObjectName('autoGroupSummary')
        summary.setWordWrap(True)
        summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary.setToolTip(summary.text())
        root.addWidget(summary)
        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)
        existing_caption = _i18n_mark(QLabel(i18n_text('w.061')), 'text', 'w.061')
        existing_caption.setObjectName('existingFilesCaption')
        content_layout.addWidget(existing_caption)
        for source in group.existing_files:
            extra = i18n_text('w.070') if source.stem in group.duplicate_stems else ''
            label = QLabel(f'{source.file_name}{extra}')
            label.setObjectName('existingAudioFile')
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setToolTip(str(source.path))
            content_layout.addWidget(label)
        missing_heading = QHBoxLayout()
        missing_caption = _i18n_mark(QLabel(i18n_text('w.062')), 'text', 'w.062')
        missing_caption.setObjectName('missingFilesCaption')
        group_all = _i18n_mark(QPushButton(i18n_text('w.063')), 'text', 'w.063')
        group_none = _i18n_mark(QPushButton(i18n_text('w.064')), 'text', 'w.064')
        group_all.setObjectName('smallActionButton')
        group_none.setObjectName('smallActionButton')
        missing_heading.addWidget(missing_caption)
        missing_heading.addStretch(1)
        missing_heading.addWidget(group_all)
        missing_heading.addWidget(group_none)
        content_layout.addLayout(missing_heading)
        for assignment in group.plan.assignments:
            row = QFrame()
            row.setObjectName('autoMissingRow')
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(9, 7, 9, 7)
            checkbox = QCheckBox()
            checkbox.setChecked(selections.get(assignment.selection_key, True))
            checkbox.toggled.connect(lambda checked, key=assignment.selection_key: self.selection_changed.emit(key, checked))
            info = QVBoxLayout()
            target = QLabel(assignment.output_path.name)
            target.setObjectName('autoMissingTarget')
            source = _i18n_mark(QLabel(i18n_text('w.059').format(assignment.source.file_name)), 'text', 'w.059')
            source.setObjectName('autoMissingMeta')
            output = _i18n_mark(QLabel(i18n_text('ui.174').format(assignment.output_path)), 'text', 'ui.174')
            output.setObjectName('autoMissingMeta')
            output.setWordWrap(True)
            output.setToolTip(str(assignment.output_path))
            info.addWidget(target)
            info.addWidget(source)
            info.addWidget(output)
            if (reason := failures.get(assignment.selection_key)):
                failed = _i18n_mark(QLabel(i18n_text('w.060').format(reason)), 'text', 'w.060')
                failed.setObjectName('autoFailureReason')
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

    def retranslate(self) -> None:
        _i18n_refresh(self)

    @property
    def group(self) -> CompletionGroup:
        return self._group

    def set_all_selected(self, selected: bool) -> None:
        for checkbox in self._checkboxes.values():
            checkbox.setChecked(selected)