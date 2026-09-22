from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.i18n import i18n_text
from app.i18n import mark as _i18n_mark
from app.i18n import refresh as _i18n_refresh
from app.models import (
    BankCountryAssignment,
    BankCountryGroup,
    BankFile,
    ConflictPolicy,
    CopyBatchResult,
    CopyResultStatus,
    ManualBatchState,
)
from app.services import (
    AutoScanService,
    BankCopyTaskBuilder,
    BankFilenameParser,
    BankFileService,
    BankNameRepository,
    BankPairMatcher,
)
from app.services.directory_scanner import ScanCancelled
from app.widgets import (
    DirectorySelector,
    FileDropArea,
    ScrollPositionGuard,
    TaskStatusPanel,
)

from .base_tool_page import BaseToolPage


@dataclass(frozen=True, slots=True)
class BankScanResult:
    root: Path
    files: tuple[BankFile, ...]
    groups: tuple[BankCountryGroup, ...]

    @property
    def file_count(self) -> int:
        return len(self.files)

class _BankDirectoryScanner:

    def __init__(self, parser: BankFilenameParser, matcher: BankPairMatcher) -> None:
        self._parser, self._matcher = (parser, matcher)

    def scan(self, root_path: Path, include_subdirectories: bool, cancel_event: threading.Event | None=None) -> BankScanResult:
        root = Path(os.path.abspath(os.fspath(root_path)))
        if not root.is_dir():
            raise FileNotFoundError(i18n_text('ui.001'))
        directories = [root]
        if include_subdirectories:
            directories = []
            for current, child_dirs, _files in os.walk(root, followlinks=False):
                if cancel_event is not None and cancel_event.is_set():
                    raise ScanCancelled()
                child_dirs[:] = [child for child in child_dirs if not Path(current, child).is_symlink()]
                directories.append(Path(current))
        files: list[BankFile] = []
        for directory in directories:
            if cancel_event is not None and cancel_event.is_set():
                raise ScanCancelled()
            for entry in directory.iterdir():
                if entry.is_file():
                    parsed = self._parser.parse(entry)
                    if parsed.valid:
                        files.append(parsed)
        return BankScanResult(root, tuple(files), self._matcher.group(files))

class BankPage(BaseToolPage):
    """Country-paired Bank completion using the shared copy worker."""
    close_ready = Signal()

    def __init__(self, parent: QWidget | None=None) -> None:
        super().__init__('bank', i18n_text('ui.002'), parent)
        self._repository = BankNameRepository()
        self._parser = BankFilenameParser()
        self._matcher = BankPairMatcher()
        self._builder = BankCopyTaskBuilder(self._repository)
        self._manual_service = BankFileService()
        self._auto_service = BankFileService()
        self._scan_service = AutoScanService(_BankDirectoryScanner(self._parser, self._matcher))
        self._imported: list[BankFile] = []
        self._manual_assignments: tuple[BankCountryAssignment, ...] = ()
        self._auto_assignments: tuple[BankCountryAssignment, ...] = ()
        self._manual_selected: dict[str, bool] = {}
        self._auto_selected: dict[str, bool] = {}
        self._auto_result: BankScanResult | None = None
        self._manual_batch_state = ManualBatchState.EMPTY
        self._submitted_manual_groups: tuple[BankCountryGroup, ...] = ()
        self._submitted_manual_assignments: tuple[BankCountryAssignment, ...] = ()
        self._submitted_manual_selected: dict[str, bool] = {}
        self._submitted_task_keys: dict[str, str] = {}
        self._manual_result_messages: dict[str, str] = {}
        self._navigation_enabled = True
        self._close_pending = False
        self.status_panel.setVisible(False)
        self.set_body_widget(self._build_body())
        for service, panel in ((self._manual_service, self.manual_status), (self._auto_service, self.auto_status)):
            service.snapshot_changed.connect(panel.set_snapshot)
            service.conflicts_detected.connect(self._resolve_conflicts)
            service.batch_finished.connect(self._show_results)
            service.busy_changed.connect(self._sync_state)
        self._auto_service.batch_finished.connect(self._auto_finished)
        self._scan_service.scan_finished.connect(self._scan_finished)
        self._scan_service.scan_cancelled.connect(lambda: self.directory_selector.set_status(i18n_text('ui.003')))
        self._scan_service.scan_failed.connect(lambda reason: self.directory_selector.set_status(i18n_text('ui.004').format(reason)))
        self._scan_service.busy_changed.connect(self._sync_state)
        self._refresh_manual()
        _i18n_tree_helper = self.source_tree
        _i18n_mark(_i18n_tree_helper, 'tree', ('ui.238', 'ui.020', 'ui.021'))
        _i18n_tree_helper = self.results
        _i18n_mark(_i18n_tree_helper, 'tree', ('ui.239', 'ui.032', 'ui.240', 'ui.033'))
        _i18n_mark(self.manual_bar, 'list', ('ui.028', 'ui.029', 'ui.030', 'ui.010', 'ui.031'))
        _i18n_mark(self.auto_bar, 'list', ('ui.028', 'ui.029', 'ui.030', 'ui.017', 'ui.031'))
        _i18n_mark(self.directory_selector, 'scope', None)
        _i18n_mark(self.manual_stats, 'scope', None)
        _i18n_mark(self.auto_plan_stats, 'scope', None)

    def retranslate(self) -> None:
        super().retranslate()
        _i18n_refresh(self)
        self._refresh_manual()
        self._render_auto() if self._auto_result is not None else None

    @property
    def is_busy(self) -> bool:
        return self._manual_service.is_busy or self._auto_service.is_busy or self._scan_service.is_busy

    def can_navigate_away(self) -> bool:
        return not self.is_busy

    def request_safe_close(self) -> bool:
        if not self.is_busy:
            return True
        if not self._close_pending and QMessageBox.question(self, i18n_text('ui.005'), i18n_text('ui.006')) == QMessageBox.StandardButton.Yes:
            self._close_pending = True
            self._manual_service.cancel()
            self._auto_service.cancel()
            self._scan_service.cancel()
        return False

    def set_navigation_enabled(self, enabled: bool) -> None:
        self._navigation_enabled = enabled
        self.back_button.setEnabled(enabled and (not self.is_busy))

    def _build_body(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        root.addWidget(_i18n_mark(self._heading(i18n_text('ui.007'), i18n_text('ui.008')), 'pair', ('ui.007', 'ui.008')))
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self._manual_sources())
        split.addWidget(self._manual_confirmation())
        split.setSizes([400, 600])
        split.setMinimumHeight(390)
        root.addWidget(split)
        self.manual_stats = QLabel()
        self.manual_stats.setObjectName('mutedLabel')
        self.manual_stats.setWordWrap(True)
        root.addWidget(self.manual_stats)
        self.manual_status = TaskStatusPanel()
        self.manual_status.set_title(i18n_text('ui.009'))
        self.manual_status.set_controls_visible(False)
        root.addWidget(self.manual_status)
        self.manual_bar = self._action_bar(i18n_text('ui.010'), self._set_manual_all, self._start_manual, self._manual_service.cancel, include_reassign=True)
        root.addWidget(self.manual_bar)
        root.addWidget(_i18n_mark(self._heading(i18n_text('ui.011'), i18n_text('ui.012')), 'pair', ('ui.011', 'ui.012')))
        auto_split = QSplitter(Qt.Orientation.Horizontal)
        auto_split.setChildrenCollapsible(False)
        self.directory_selector = DirectorySelector()
        self.directory_selector.audio_count_label.setText(i18n_text('ui.013'))
        self.directory_selector.triggered_groups_label.setText(i18n_text('ui.014'))
        self.directory_selector.missing_groups_label.setText(i18n_text('ui.015'))
        auto_split.addWidget(self.directory_selector)
        auto_split.addWidget(self._auto_confirmation())
        auto_split.setSizes([360, 640])
        auto_split.setMinimumHeight(400)
        root.addWidget(auto_split)
        self.auto_plan_stats = QLabel()
        self.auto_plan_stats.setObjectName('mutedLabel')
        self.auto_plan_stats.setWordWrap(True)
        root.addWidget(self.auto_plan_stats)
        self.auto_status = TaskStatusPanel()
        self.auto_status.set_title(i18n_text('ui.016'))
        self.auto_status.set_controls_visible(False)
        root.addWidget(self.auto_status)
        self.auto_bar = self._action_bar(i18n_text('ui.017'), self._set_auto_all, self._start_auto, self._cancel_auto, include_reassign=True)
        root.addWidget(self.auto_bar)
        self._create_results(root)
        self.drop_area.choose_requested.connect(self._choose_files)
        self.drop_area.files_dropped.connect(self._add_paths)
        self.remove_source.clicked.connect(self._remove_selected)
        self.clear_sources.clicked.connect(self._clear_sources)
        self.directory_selector.choose_requested.connect(self._choose_directory)
        self.directory_selector.scan_requested.connect(self._start_scan)
        self.directory_selector.rescan_requested.connect(self._start_scan)
        self.directory_selector.path_changed.connect(self._clear_auto)
        scroll.setWidget(body)
        self._manual_scroll_guard = ScrollPositionGuard(scroll)
        return scroll

    @staticmethod
    def _heading(title: str, text: str) -> QWidget:
        frame = QFrame()
        frame.setObjectName('autoRecognitionPanel')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 11, 15, 11)
        label = QLabel(title)
        label.setObjectName('autoRecognitionTitle')
        note = QLabel(text)
        note.setObjectName('mutedLabel')
        note.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(note)
        return frame

    def _manual_sources(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName('crewManualPanel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 14, 15, 14)
        title = _i18n_mark(QLabel(i18n_text('ui.018')), 'text', 'ui.018')
        title.setObjectName('crewPanelTitle')
        layout.addWidget(title)
        self.drop_area = FileDropArea()
        layout.addWidget(self.drop_area)
        self.source_hint = _i18n_mark(QLabel(i18n_text('ui.019')), 'text', 'ui.019')
        self.source_hint.setObjectName('mutedLabel')
        self.source_hint.setWordWrap(True)
        layout.addWidget(self.source_hint)
        self.source_tree = QTreeWidget()
        self.source_tree.setHeaderLabels([i18n_text('ui.238'), i18n_text('ui.020'), i18n_text('ui.021')])
        self.source_tree.setColumnCount(3)
        self.source_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.source_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.source_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.source_tree, 1)
        buttons = QHBoxLayout()
        self.remove_source = _i18n_mark(QPushButton(i18n_text('ui.022')), 'text', 'ui.022')
        self.clear_sources = _i18n_mark(QPushButton(i18n_text('ui.023')), 'text', 'ui.023')
        buttons.addWidget(self.remove_source)
        buttons.addWidget(self.clear_sources)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return panel

    def _manual_confirmation(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName('crewManualPanel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 14, 15, 14)
        title = _i18n_mark(QLabel(i18n_text('ui.024')), 'text', 'ui.024')
        title.setObjectName('crewPanelTitle')
        layout.addWidget(title)
        self.manual_scroll, self.manual_layout = self._scroll_layout(i18n_text('ui.025'), 'manual')
        layout.addWidget(self.manual_scroll, 1)
        return panel

    def _auto_confirmation(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName('crewManualPanel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 14, 15, 14)
        title = _i18n_mark(QLabel(i18n_text('ui.026')), 'text', 'ui.026')
        title.setObjectName('crewPanelTitle')
        layout.addWidget(title)
        self.auto_scroll, self.auto_layout = self._scroll_layout(i18n_text('ui.027'), 'auto')
        layout.addWidget(self.auto_scroll, 1)
        return panel

    @staticmethod
    def _scroll_layout(empty: str, name: str) -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        container.setObjectName(f'bank{name.title()}Container')
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        scroll.setWidget(container)
        return (scroll, layout)

    def _action_bar(self, start_text: str, set_all, start, cancel, *, include_reassign: bool) -> QFrame:
        frame = QFrame()
        frame.setObjectName('crewActionBar')
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(13, 10, 13, 10)
        all_button = _i18n_mark(QPushButton(i18n_text('ui.028')), 'text', 'ui.028')
        none_button = _i18n_mark(QPushButton(i18n_text('ui.029')), 'text', 'ui.029')
        reassign = _i18n_mark(QPushButton(i18n_text('ui.030')), 'text', 'ui.030')
        start_button = QPushButton(start_text)
        cancel_button = _i18n_mark(QPushButton(i18n_text('ui.031')), 'text', 'ui.031')
        all_button.clicked.connect(lambda: set_all(True))
        none_button.clicked.connect(lambda: set_all(False))
        reassign.clicked.connect(self._reassign)
        start_button.clicked.connect(start)
        cancel_button.clicked.connect(cancel)
        layout.addWidget(all_button)
        layout.addWidget(none_button)
        layout.addWidget(reassign)
        layout.addStretch(1)
        layout.addWidget(start_button)
        layout.addWidget(cancel_button)
        frame.setProperty('bank_buttons', (all_button, none_button, reassign, start_button, cancel_button))
        return frame

    def _create_results(self, root: QVBoxLayout) -> None:
        self.results = QTreeWidget()
        self.results.setHeaderLabels([i18n_text('ui.239'), i18n_text('ui.032'), i18n_text('ui.240'), i18n_text('ui.033')])
        self.results.setColumnCount(4)
        self.results.setVisible(False)
        root.addWidget(self.results)

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, i18n_text('ui.034'), '', i18n_text('ui.035'))
        self._add_paths(paths)

    def _add_paths(self, paths: list[str]) -> None:
        if self.is_busy:
            return
        self._manual_scroll_guard.preserve()
        if self._manual_batch_state is ManualBatchState.RESULT_RETAINED:
            self._clear_previous_result_for_new_batch()
        known = {item.normalized_path for item in self._imported}
        for path in paths:
            candidate = Path(path)
            if candidate.is_file():
                item = self._parser.parse(candidate)
                if item.normalized_path not in known:
                    self._imported.append(item)
                    known.add(item.normalized_path)
        self._imported.sort(key=lambda item: item.normalized_path)
        if self._imported:
            self._manual_batch_state = ManualBatchState.EDITING
        self._refresh_manual()

    def _remove_selected(self) -> None:
        if self.is_busy:
            return
        self._manual_scroll_guard.preserve()
        item = self.source_tree.currentItem()
        if item is not None:
            self._imported = [source for source in self._imported if source.normalized_path != item.data(0, Qt.ItemDataRole.UserRole)]
            if not self._imported:
                self._manual_batch_state = ManualBatchState.EMPTY
            self._refresh_manual()

    def _clear_sources(self) -> None:
        if self.is_busy:
            return
        self._manual_scroll_guard.preserve()
        self.clear_manual_copy_completely()

    def clear_manual_copy_completely(self) -> None:
        self._imported.clear()
        self._manual_selected.clear()
        self._manual_assignments = ()
        self._submitted_manual_groups = ()
        self._submitted_manual_assignments = ()
        self._submitted_manual_selected.clear()
        self._submitted_task_keys.clear()
        self._manual_result_messages.clear()
        self._manual_batch_state = ManualBatchState.EMPTY
        self.results.clear()
        self.results.setVisible(False)
        self._refresh_manual()

    def _clear_previous_result_for_new_batch(self) -> None:
        self._manual_assignments = ()
        self._manual_selected.clear()
        self._submitted_manual_groups = ()
        self._submitted_manual_assignments = ()
        self._submitted_manual_selected.clear()
        self._submitted_task_keys.clear()
        self._manual_result_messages.clear()
        self.results.clear()
        self.results.setVisible(False)

    def clear_sources_after_submission(self) -> None:
        self._imported.clear()
        self.source_tree.clear()

    def _refresh_manual(self) -> None:
        self.source_tree.clear()
        for file in self._imported:
            state = f'{file.category} / {file.country} / {file.role.value}' if file.valid else file.reason
            item = QTreeWidgetItem([file.path.name, state, str(file.path)])
            item.setData(0, Qt.ItemDataRole.UserRole, file.normalized_path)
            item.setToolTip(2, str(file.path))
            self.source_tree.addTopLevelItem(item)
        groups = self._matcher.group(self._imported)
        self._manual_assignments = self._builder.build_assignments(groups)
        self._manual_selected = {assignment.selection_key: self._manual_selected.get(assignment.selection_key, True) for assignment in self._manual_assignments}
        self._render_groups(self.manual_layout, groups, self._manual_assignments, self._manual_selected, 'manual')
        self._update_statistics()
        self._sync_state()

    def _render_groups(self, layout: QVBoxLayout, groups: tuple[BankCountryGroup, ...], assignments: tuple[BankCountryAssignment, ...], selections: dict[str, bool], prefix: str) -> None:
        while layout.count() > 1:
            child = layout.takeAt(0)
            if child.widget():
                # hide() 立即移出视图，deleteLater 的延迟销毁期间不再叠印旧文案
                child.widget().hide()
                child.widget().deleteLater()
        by_category: dict[str, list[BankCountryGroup]] = {category: [] for category in self._repository.categories()}
        for group in groups:
            by_category.setdefault(group.category, []).append(group)
        for category in self._repository.categories():
            category_groups = by_category.get(category, [])
            category_assignments = [item for item in assignments if item.category == category]
            if not category_groups and (not category_assignments):
                continue
            caption = QLabel(category)
            caption.setObjectName('sectionEyebrow')
            layout.insertWidget(layout.count() - 1, caption)
            for group in category_groups:
                status = i18n_text('ui.037') if group.complete else i18n_text('ui.038') if group.ambiguous else i18n_text('ui.036').format(', '.join(role.value for role in group.missing_roles))
                label = QLabel(f'{group.country}\u3000{status}\n{group.directory}')
                label.setWordWrap(True)
                label.setObjectName('existingAudioFile' if group.complete else 'assignmentHint')
                layout.insertWidget(layout.count() - 1, label)
            for assignment in category_assignments:
                row = QFrame()
                row.setObjectName('autoMissingRow')
                row_layout = QVBoxLayout(row)
                check = _i18n_mark(QCheckBox(i18n_text('ui.039').format(assignment.country, assignment.source.country)), 'text', 'ui.039')
                check.setChecked(selections.get(assignment.selection_key, True))
                check.setEnabled(not (prefix == 'manual' and self._manual_batch_state in (ManualBatchState.RUNNING, ManualBatchState.RESULT_RETAINED)))
                check.toggled.connect(lambda value, key=assignment.selection_key, mode=prefix: self._selection_changed(mode, key, value))
                row_layout.addWidget(check)
                names = [self._repository.file_name(assignment.category, assignment.country, role.value) for role in assignment.target_roles]
                details = _i18n_mark(QLabel('\n'.join(names) + i18n_text('ui.040').format(assignment.target_directory)), 'text', 'ui.040')
                details.setObjectName('autoMissingMeta')
                details.setWordWrap(True)
                details.setToolTip(details.text())
                row_layout.addWidget(details)
                if prefix == 'manual' and assignment.selection_key in self._manual_result_messages:
                    result = QLabel(self._manual_result_messages[assignment.selection_key])
                    result.setObjectName('confirmationTargetResult')
                    result.setWordWrap(True)
                    row_layout.addWidget(result)
                layout.insertWidget(layout.count() - 1, row)
        if not groups and (not assignments):
            empty = _i18n_mark(QLabel(i18n_text('ui.041') if prefix == 'manual' else i18n_text('ui.042')), 'text', 'ui.041')
            empty.setObjectName('mutedLabel')
            layout.insertWidget(0, empty)

    def _selection_changed(self, mode: str, key: str, value: bool) -> None:
        (self._manual_selected if mode == 'manual' else self._auto_selected)[key] = value
        self._update_statistics()
        self._sync_state()

    def _set_manual_all(self, value: bool) -> None:
        if self.is_busy or self._manual_batch_state is not ManualBatchState.EDITING:
            return
        for key in self._manual_selected:
            self._manual_selected[key] = value
        self._render_groups(self.manual_layout, self._matcher.group(self._imported), self._manual_assignments, self._manual_selected, 'manual')
        self._update_statistics()
        self._sync_state()

    def _set_auto_all(self, value: bool) -> None:
        for key in self._auto_selected:
            self._auto_selected[key] = value
        self._render_auto()
        self._update_statistics()
        self._sync_state()

    def _reassign(self) -> None:
        if self.is_busy:
            return
        if self._manual_batch_state is ManualBatchState.EDITING:
            self._manual_assignments = self._builder.build_assignments(self._matcher.group(self._imported))
            self._manual_selected = {item.selection_key: self._manual_selected.get(item.selection_key, True) for item in self._manual_assignments}
        if self._auto_result is not None:
            self._auto_assignments = self._builder.build_assignments(self._auto_result.groups)
            self._auto_selected = {item.selection_key: self._auto_selected.get(item.selection_key, True) for item in self._auto_assignments}
            self._render_auto()
        if self._manual_batch_state is ManualBatchState.EDITING:
            self._refresh_manual()
        self._update_statistics()

    def _start_manual(self) -> None:
        if self.is_busy or self._manual_batch_state is not ManualBatchState.EDITING:
            return
        plan = self._builder.build_copy_plan(self._manual_assignments, self._manual_selected)
        if not plan.total:
            return
        policy = self._choose_manual_conflict_policy(plan)
        if policy is None:
            return
        self._manual_scroll_guard.begin_hold()
        self._manual_scroll_guard.preserve()
        self.manual_status.reset()
        self._submitted_manual_groups = self._matcher.group(self._imported)
        self._submitted_manual_assignments = self._manual_assignments
        self._submitted_manual_selected = dict(self._manual_selected)
        self._submitted_task_keys = {str(task.target_path).casefold(): assignment.selection_key for assignment in self._manual_assignments for task in self._builder.build_copy_plan((assignment,), {assignment.selection_key: True}).tasks}
        self._manual_result_messages.clear()
        self._manual_batch_state = ManualBatchState.RUNNING
        cancel = self.manual_bar.property('bank_buttons')[4]
        cancel.setEnabled(True)
        cancel.setFocus(Qt.FocusReason.OtherFocusReason)
        if self._manual_service.start_copy(plan, policy):
            self.clear_sources_after_submission()
            self._render_groups(self.manual_layout, self._submitted_manual_groups, self._submitted_manual_assignments, self._submitted_manual_selected, 'manual')
            self._sync_state()
        else:
            self._manual_batch_state = ManualBatchState.EDITING
            self._manual_scroll_guard.end_hold()

    def _choose_manual_conflict_policy(self, plan: object) -> ConflictPolicy | None:
        existing = tuple(task.target_path for task in getattr(plan, 'tasks', ()) if task.target_path.exists())
        if not existing:
            return ConflictPolicy.SKIP_EXISTING
        self._manual_scroll_guard.preserve()
        dialog = QMessageBox(self)
        dialog.setWindowTitle(i18n_text('ui.043'))
        dialog.setText(i18n_text('ui.044'))
        skip = dialog.addButton(i18n_text('ui.045'), QMessageBox.ButtonRole.AcceptRole)
        overwrite = dialog.addButton(i18n_text('ui.046'), QMessageBox.ButtonRole.DestructiveRole)
        cancel = dialog.addButton(i18n_text('ui.047'), QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(skip)
        dialog.setEscapeButton(cancel)
        dialog.exec()
        return ConflictPolicy.OVERWRITE_EXISTING if dialog.clickedButton() is overwrite else ConflictPolicy.SKIP_EXISTING if dialog.clickedButton() is skip else None

    def _resolve_conflicts(self, paths: object) -> None:
        service = self.sender()
        dialog = QMessageBox(self)
        dialog.setWindowTitle(i18n_text('ui.043'))
        dialog.setText(i18n_text('ui.044'))
        skip = dialog.addButton(i18n_text('ui.045'), QMessageBox.ButtonRole.AcceptRole)
        overwrite = dialog.addButton(i18n_text('ui.046'), QMessageBox.ButtonRole.DestructiveRole)
        cancel = dialog.addButton(i18n_text('ui.047'), QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(skip)
        dialog.setEscapeButton(cancel)
        dialog.exec()
        policy = ConflictPolicy.OVERWRITE_EXISTING if dialog.clickedButton() is overwrite else ConflictPolicy.SKIP_EXISTING if dialog.clickedButton() is skip else ConflictPolicy.CANCEL_BATCH
        if isinstance(service, BankFileService):
            service.resolve_conflict(policy)

    def _choose_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, i18n_text('ui.048'), self.directory_selector.path_edit.text())
        if directory:
            self.directory_selector.path_edit.setText(directory)

    def _clear_auto(self, _value: str='') -> None:
        if self.is_busy:
            return
        self._auto_result = None
        self._auto_assignments = ()
        self._auto_selected.clear()
        self._render_auto()
        self.directory_selector.set_statistics(0, 0, 0)
        self.directory_selector.set_status(i18n_text('ui.049') if _value else i18n_text('ui.050'))
        self._update_statistics()
        self._sync_state()

    def _start_scan(self) -> None:
        if self.is_busy:
            return
        path = Path(self.directory_selector.path_edit.text().strip())
        if not path.is_dir():
            self.directory_selector.set_status(i18n_text('ui.051'))
            return
        self._auto_result = None
        self._auto_assignments = ()
        self._auto_selected.clear()
        self.directory_selector.set_status(i18n_text('ui.052'))
        self._scan_service.start_scan(path, self.directory_selector.include_children.isChecked())
        self._sync_state()

    def _scan_finished(self, result: object) -> None:
        if not isinstance(result, BankScanResult):
            return
        self._auto_result = result
        self._auto_assignments = self._builder.build_assignments(result.groups)
        self._auto_selected = {item.selection_key: True for item in self._auto_assignments}
        self._render_auto()
        complete = sum(group.complete for group in result.groups)
        partial = sum(not group.complete for group in result.groups)
        planned_files = sum(len(item.target_roles) for item in self._auto_assignments)
        self.directory_selector.audio_count_label.setText(i18n_text('ui.053').format(result.file_count))
        self.directory_selector.triggered_groups_label.setText(i18n_text('ui.054').format(complete))
        self.directory_selector.missing_groups_label.setText(i18n_text('ui.055').format(partial, planned_files))
        self.directory_selector.set_status(i18n_text('ui.056') if self._auto_assignments else i18n_text('ui.057'))
        self._update_statistics()
        self._sync_state()

    def _render_auto(self) -> None:
        groups = self._auto_result.groups if self._auto_result else ()
        self._render_groups(self.auto_layout, groups, self._auto_assignments, self._auto_selected, 'auto')

    def _update_statistics(self) -> None:
        manual_files = sum(len(item.target_roles) for item in self._manual_assignments if self._manual_selected.get(item.selection_key, True))
        manual_countries = sum(self._manual_selected.get(item.selection_key, True) for item in self._manual_assignments)
        manual_sources = sum(group.complete for group in self._matcher.group(self._imported))
        self.manual_stats.setText(i18n_text('ui.058').format(manual_sources, manual_countries, manual_files, len(self._imported) + manual_files))
        before = self._auto_result.file_count if self._auto_result else 0
        auto_files = sum(len(item.target_roles) for item in self._auto_assignments if self._auto_selected.get(item.selection_key, True))
        auto_countries = sum(self._auto_selected.get(item.selection_key, True) for item in self._auto_assignments)
        self.auto_plan_stats.setText(i18n_text('ui.059').format(before, auto_countries, auto_files, before + auto_files))

    def _start_auto(self) -> None:
        plan = self._builder.build_copy_plan(self._auto_assignments, self._auto_selected)
        if plan.total:
            self.auto_status.reset()
            self._auto_service.start_copy(plan, ConflictPolicy.SKIP_EXISTING)
            self._sync_state()

    def _cancel_auto(self) -> None:
        self._scan_service.cancel()
        self._auto_service.cancel()

    def _auto_finished(self, _result: CopyBatchResult) -> None:
        self.directory_selector.set_status(i18n_text('ui.060'))
        QTimer.singleShot(0, self._start_scan)

    def _show_results(self, result: CopyBatchResult) -> None:
        manual_batch = self._manual_service.is_busy
        if manual_batch:
            self._manual_scroll_guard.preserve()
        self.results.clear()
        labels = {CopyResultStatus.SUCCESS: i18n_text('ui.061'), CopyResultStatus.SKIPPED: i18n_text('ui.045'), CopyResultStatus.FAILED: i18n_text('ui.241'), CopyResultStatus.CANCELLED: i18n_text('ui.062')}
        by_country: dict[str, list[object]] = {}
        for item in result.results:
            by_country.setdefault(item.task.group_base, []).append(item)
        for country_key, items in by_country.items():
            statuses = {item.status for item in items}
            summary = i18n_text('ui.063') if CopyResultStatus.FAILED in statuses and len(statuses) > 1 else i18n_text('ui.064') if statuses == {CopyResultStatus.FAILED} else i18n_text('ui.065')
            parent = QTreeWidgetItem([country_key, '', summary, ''])
            parent.setExpanded(True)
            self.results.addTopLevelItem(parent)
            for item in items:
                parent.addChild(QTreeWidgetItem([str(item.task.source_path), str(item.task.target_path), labels[item.status], item.reason]))
                if manual_batch:
                    key = self._submitted_task_keys.get(str(item.task.target_path).casefold())
                    if key is not None:
                        detail = i18n_text('ui.066').format(labels[item.status])
                        self._manual_result_messages[key] = f'{detail}，{item.reason}' if item.reason else detail
        self.results.setVisible(True)
        if manual_batch:
            self._manual_batch_state = ManualBatchState.RESULT_RETAINED
            self._render_groups(self.manual_layout, self._submitted_manual_groups, self._submitted_manual_assignments, self._submitted_manual_selected, 'manual')

    def _sync_state(self, *_args: object) -> None:
        busy = self.is_busy
        can_clear_manual = bool(self._imported) or self._manual_batch_state is ManualBatchState.RESULT_RETAINED
        self.drop_area.setEnabled(not busy)
        self.source_tree.setEnabled(not busy)
        self.remove_source.setEnabled(not busy)
        self.clear_sources.setEnabled(not busy and can_clear_manual)
        self.manual_scroll.setEnabled(True)
        self.directory_selector.set_controls_enabled(not busy, self._auto_result is not None)
        self.auto_scroll.setEnabled(not busy)
        self.back_button.setEnabled(self._navigation_enabled and (not busy))
        for bar, selected, service in ((self.manual_bar, self._manual_selected, self._manual_service), (self.auto_bar, self._auto_selected, self._auto_service)):
            all_button, none_button, reassign, start, cancel = bar.property('bank_buttons')
            editing = bar is not self.manual_bar or self._manual_batch_state is ManualBatchState.EDITING
            all_button.setEnabled(not busy and editing and bool(selected))
            none_button.setEnabled(not busy and editing and bool(selected))
            reassign.setEnabled(not busy and editing and bool(selected))
            start.setEnabled(not busy and editing and any(selected.values()))
            cancel.setEnabled(service.is_busy or (bar is self.auto_bar and self._scan_service.is_busy))
        if not self._manual_service.is_busy and self._manual_batch_state is ManualBatchState.RESULT_RETAINED:
            self._manual_scroll_guard.end_hold()
        if not busy and self._close_pending:
            self._close_pending = False
            self.close_ready.emit()