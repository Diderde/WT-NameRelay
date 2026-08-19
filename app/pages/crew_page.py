from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
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

from app.models import (
    AutoCompletionAnalysis,
    AutoScanState,
    ConflictPolicy,
    CopyBatchResult,
    CopyResultStatus,
    CrewGroupPlan,
    DirectoryScanResult,
    ManualBatchState,
    SourceFile,
)
from app.contracts import TaskState
from app.module_config import CREW_MODULE, ModuleConfig
from app.services import (
    AutoCompletionAnalyzer,
    AutoScanService,
    CopyTaskBuilder,
    CrewFileService,
    CrewNameParser,
    CrewNameRepository,
    DirectoryScanner,
)
from app.widgets import (
    AutoScanResultPanel,
    ConfirmationGroup,
    DirectorySelector,
    FileDropArea,
    SourceFileList,
    ScrollPositionGuard,
    TaskStatusPanel,
)

from .base_tool_page import BaseToolPage


class CrewPage(BaseToolPage):
    """Configurable manual and automatic completion workflow for a name module."""

    close_ready = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        config: ModuleConfig = CREW_MODULE,
    ) -> None:
        self._config = config
        self._module_label = config.module_label
        super().__init__(config.module_id, config.title, parent)
        self._repository = CrewNameRepository(config.data_path)
        self._parser = CrewNameParser(self._repository)
        self._task_builder = CopyTaskBuilder(self._repository)
        self._service = CrewFileService()
        self._auto_copy_service = CrewFileService()
        self._scan_service = AutoScanService(DirectoryScanner(self._parser))
        self._auto_analyzer = AutoCompletionAnalyzer(self._repository)
        self._imported_files: list[SourceFile] = []
        self._group_plans: tuple[CrewGroupPlan, ...] = ()
        self._selected_targets: dict[str, bool] = {}
        self._confirmation_groups: list[ConfirmationGroup] = []
        self._manual_batch_state = ManualBatchState.EMPTY
        self._submitted_group_plans: tuple[CrewGroupPlan, ...] = ()
        self._submitted_targets: dict[str, bool] = {}
        self._submitted_task_keys: dict[str, str] = {}
        self._manual_result_messages: dict[str, str] = {}
        self._navigation_enabled = True
        self._close_pending = False
        self._auto_analysis: AutoCompletionAnalysis | None = None
        self._auto_selected_targets: dict[str, bool] = {}
        self._auto_failures: dict[str, str] = {}
        self._auto_target_keys: dict[str, str] = {}
        self._auto_rescan_after_copy = False

        self.status_panel.setVisible(False)
        self.set_body_widget(self._create_manual_body())

        self._service.snapshot_changed.connect(self.manual_status_panel.set_snapshot)
        self._service.conflicts_detected.connect(self._resolve_conflicts)
        self._service.batch_finished.connect(self._show_results)
        self._service.busy_changed.connect(self._sync_interaction_state)
        self._auto_copy_service.snapshot_changed.connect(self.auto_status_panel.set_snapshot)
        self._auto_copy_service.batch_finished.connect(self._on_auto_copy_finished)
        self._auto_copy_service.busy_changed.connect(self._sync_interaction_state)
        self._scan_service.scan_finished.connect(self._on_scan_finished)
        self._scan_service.scan_cancelled.connect(self._on_scan_cancelled)
        self._scan_service.scan_failed.connect(self._on_scan_failed)
        self._scan_service.busy_changed.connect(self._sync_interaction_state)
        self._refresh_sources_and_groups()

    @property
    def is_busy(self) -> bool:
        return self._service.is_busy or self._auto_copy_service.is_busy or self._scan_service.is_busy

    def can_navigate_away(self) -> bool:
        return not self.is_busy

    def request_safe_close(self) -> bool:
        """Request cancellation asynchronously when the application is closing."""
        if not self.is_busy:
            return True
        if self._close_pending:
            return False
        answer = QMessageBox.question(
            self,
            "任务正在运行",
            f"{self._module_label}文件复制任务仍在运行。是否安全取消并在当前文件完成后关闭？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is QMessageBox.StandardButton.Yes:
            self._close_pending = True
            self._service.cancel()
            self._auto_copy_service.cancel()
            self._scan_service.cancel()
        return False

    def set_navigation_enabled(self, enabled: bool) -> None:
        self._navigation_enabled = enabled
        self.back_button.setEnabled(enabled and not self.is_busy)

    def _create_manual_body(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("crewContentScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        body = QWidget()
        body.setObjectName("crewManualBody")
        root = QVBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        section_heading = QLabel("手动复制")
        section_heading.setObjectName("crewSectionTitle")
        root.addWidget(section_heading)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("crewManualSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        splitter.addWidget(self._create_source_panel())
        splitter.addWidget(self._create_confirmation_panel())
        splitter.setStretchFactor(0, 42)
        splitter.setStretchFactor(1, 58)
        splitter.setSizes([420, 580])
        splitter.setMinimumHeight(470)
        root.addWidget(splitter, 1)

        self.manual_status_panel = TaskStatusPanel()
        self.manual_status_panel.set_title("手动复制进度")
        self.manual_status_panel.set_controls_visible(False)
        root.addWidget(self.manual_status_panel)

        self.action_bar = QFrame()
        self.action_bar.setObjectName("crewActionBar")
        actions = QHBoxLayout(self.action_bar)
        actions.setContentsMargins(13, 10, 13, 10)
        actions.setSpacing(9)
        self.select_all_button = QPushButton("全选")
        self.select_none_button = QPushButton("全部取消")
        self.start_copy_button = QPushButton("开始复制")
        self.start_copy_button.setObjectName("crewStartCopyButton")
        self.cancel_task_button = QPushButton("取消任务")
        self.cancel_task_button.setObjectName("crewCancelTaskButton")
        actions.addWidget(self.select_all_button)
        actions.addWidget(self.select_none_button)
        actions.addStretch(1)
        actions.addWidget(self.start_copy_button)
        actions.addWidget(self.cancel_task_button)
        root.addWidget(self.action_bar)

        self.select_all_button.clicked.connect(lambda: self._set_all_targets(True))
        self.select_none_button.clicked.connect(lambda: self._set_all_targets(False))
        self.start_copy_button.clicked.connect(self._start_copy)
        self.cancel_task_button.clicked.connect(self._cancel_manual_copy)

        auto_panel = QFrame()
        auto_panel.setObjectName("autoRecognitionPanel")
        self.auto_copy_panel = auto_panel
        auto_layout = QVBoxLayout(auto_panel)
        auto_layout.setContentsMargins(15, 12, 15, 12)
        auto_title = QLabel("自动检索与补全")
        auto_title.setObjectName("autoRecognitionTitle")
        auto_text = QLabel(f"扫描目标目录后，仅补全已出现但尚不完整的{self._module_label}名称组。")
        auto_text.setObjectName("mutedLabel")
        auto_text.setWordWrap(True)
        auto_layout.addWidget(auto_title)
        auto_layout.addWidget(auto_text)
        auto_splitter = QSplitter(Qt.Orientation.Horizontal)
        auto_splitter.setObjectName("autoScanSplitter")
        auto_splitter.setChildrenCollapsible(False)
        auto_splitter.setHandleWidth(8)
        self.directory_selector = DirectorySelector()
        self.auto_result_panel = AutoScanResultPanel()
        auto_splitter.addWidget(self.directory_selector)
        auto_splitter.addWidget(self.auto_result_panel)
        auto_splitter.setStretchFactor(0, 35)
        auto_splitter.setStretchFactor(1, 65)
        auto_splitter.setSizes([360, 640])
        auto_splitter.setMinimumHeight(430)
        auto_layout.addWidget(auto_splitter)
        root.addWidget(auto_panel)

        self.auto_status_panel = TaskStatusPanel()
        self.auto_status_panel.set_title("自动补全进度")
        self.auto_status_panel.set_controls_visible(False)
        root.addWidget(self.auto_status_panel)

        self.auto_action_bar = QFrame()
        self.auto_action_bar.setObjectName("autoActionBar")
        auto_actions = QHBoxLayout(self.auto_action_bar)
        auto_actions.setContentsMargins(13, 10, 13, 10)
        auto_actions.setSpacing(9)
        self.auto_select_all_button = QPushButton("全选")
        self.auto_select_none_button = QPushButton("全部取消")
        self.auto_reassign_button = QPushButton("重新分配来源")
        self.auto_start_copy_button = QPushButton("开始自动复制")
        self.auto_start_copy_button.setObjectName("autoStartCopyButton")
        self.auto_cancel_task_button = QPushButton("取消任务")
        self.auto_cancel_task_button.setObjectName("autoCancelTaskButton")
        for button in (
            self.auto_select_all_button,
            self.auto_select_none_button,
            self.auto_reassign_button,
            self.auto_start_copy_button,
            self.auto_cancel_task_button,
        ):
            auto_actions.addWidget(button)
        auto_actions.insertStretch(3, 1)
        root.addWidget(self.auto_action_bar)

        self.directory_selector.choose_requested.connect(self._choose_auto_directory)
        self.directory_selector.scan_requested.connect(self._start_auto_scan)
        self.directory_selector.rescan_requested.connect(self._start_auto_scan)
        self.directory_selector.path_changed.connect(self._on_auto_path_changed)
        self.auto_result_panel.selection_changed.connect(self._on_auto_selection_changed)
        self.auto_select_all_button.clicked.connect(lambda: self._set_all_auto_targets(True))
        self.auto_select_none_button.clicked.connect(lambda: self._set_all_auto_targets(False))
        self.auto_reassign_button.clicked.connect(self._reassign_auto_sources)
        self.auto_start_copy_button.clicked.connect(self._start_auto_completion)
        self.auto_cancel_task_button.clicked.connect(self._cancel_auto_work)

        self._create_results_panel(root)
        scroll.setWidget(body)
        self._manual_scroll_guard = ScrollPositionGuard(scroll)
        return scroll

    def _create_source_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("crewManualPanel")
        panel.setMinimumWidth(300)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 14, 15, 14)
        layout.setSpacing(11)
        title = QLabel("选择复制文件")
        title.setObjectName("crewPanelTitle")
        layout.addWidget(title)

        self.drop_area = FileDropArea()
        self.drop_area.choose_requested.connect(self._choose_files)
        self.drop_area.files_dropped.connect(self._add_paths)
        layout.addWidget(self.drop_area)

        self.import_message = QLabel("可导入多个实际文件；未识别文件会保留在列表中。")
        self.import_message.setObjectName("mutedLabel")
        self.import_message.setWordWrap(True)
        layout.addWidget(self.import_message)

        self.source_list = SourceFileList()
        self.source_list.remove_requested.connect(self._remove_source)
        self.source_list.clear_requested.connect(self._clear_sources)
        layout.addWidget(self.source_list, 1)
        return panel

    def _create_confirmation_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("crewManualPanel")
        panel.setMinimumWidth(350)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 14, 15, 14)
        layout.setSpacing(10)
        title = QLabel("识别待确认区")
        title.setObjectName("crewPanelTitle")
        hint = QLabel("仅显示从内置名称库精确识别出的分组；每个目标可单独取消。")
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        assignment_hint = QLabel(
            "同组多个来源会在导入或移除时自动随机且均衡地分配，无需手动选择。"
        )
        assignment_hint.setObjectName("assignmentHint")
        assignment_hint.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(assignment_hint)

        self.confirmation_scroll = QScrollArea()
        self.confirmation_scroll.setObjectName("confirmationScroll")
        self.confirmation_scroll.setWidgetResizable(True)
        self.confirmation_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.confirmation_container = QWidget()
        self.confirmation_container.setObjectName("confirmationContainer")
        self.confirmation_layout = QVBoxLayout(self.confirmation_container)
        self.confirmation_layout.setContentsMargins(0, 0, 0, 0)
        self.confirmation_layout.setSpacing(10)
        self.confirmation_layout.addStretch(1)
        self.confirmation_scroll.setWidget(self.confirmation_container)
        layout.addWidget(self.confirmation_scroll, 1)
        return panel

    def _create_results_panel(self, root: QVBoxLayout) -> None:
        self.results_panel = QFrame()
        self.results_panel.setObjectName("resultPanel")
        results_layout = QVBoxLayout(self.results_panel)
        results_layout.setContentsMargins(14, 12, 14, 12)
        results_layout.setSpacing(8)
        heading = QHBoxLayout()
        self.results_toggle = QPushButton("显示本次结果")
        self.results_toggle.setObjectName("resultsToggle")
        self.results_toggle.setCheckable(True)
        self.results_summary = QLabel("")
        self.results_summary.setObjectName("mutedLabel")
        heading.addWidget(self.results_toggle)
        heading.addWidget(self.results_summary, 1)
        results_layout.addLayout(heading)

        self.results_tree = QTreeWidget()
        self.results_tree.setObjectName("resultsTree")
        self.results_tree.setColumnCount(4)
        self.results_tree.setHeaderLabels(["来源路径", "目标路径", "结果", "说明"])
        self.results_tree.setRootIsDecorated(False)
        self.results_tree.setAlternatingRowColors(False)
        header = self.results_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.results_tree.setVisible(False)
        self.results_toggle.toggled.connect(self.results_tree.setVisible)
        results_layout.addWidget(self.results_tree)
        self.results_panel.setVisible(False)
        root.addWidget(self.results_panel)

    def _choose_files(self) -> None:
        if self.is_busy:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "选择复制文件", "", "所有文件 (*)")
        if paths:
            self._add_paths(paths)

    def _add_paths(self, paths: Iterable[str]) -> None:
        if self.is_busy:
            return
        self._manual_scroll_guard.preserve()
        if self._manual_batch_state is ManualBatchState.RESULT_RETAINED:
            self._clear_previous_result_for_new_batch()
        known_paths = {source.normalized_path for source in self._imported_files}
        added = 0
        ignored_directories = 0
        ignored_duplicates = 0
        ignored_invalid = 0
        for raw_path in paths:
            candidate = Path(raw_path)
            if candidate.is_dir():
                ignored_directories += 1
                continue
            if not candidate.is_file():
                ignored_invalid += 1
                continue
            source = self._parser.parse(candidate)
            if source.normalized_path in known_paths:
                ignored_duplicates += 1
                continue
            known_paths.add(source.normalized_path)
            self._imported_files.append(source)
            added += 1
        self._imported_files.sort(key=lambda item: item.normalized_path)
        messages = []
        if added:
            messages.append(f"已导入 {added} 个文件")
        if ignored_directories:
            messages.append(f"已忽略 {ignored_directories} 个文件夹")
        if ignored_duplicates:
            messages.append(f"已忽略 {ignored_duplicates} 个重复路径")
        if ignored_invalid:
            messages.append(f"已忽略 {ignored_invalid} 个无效路径")
        if messages:
            self.import_message.setText("；".join(messages) + "。")
        if self._imported_files:
            self._manual_batch_state = ManualBatchState.EDITING
        self._refresh_sources_and_groups()

    def _remove_source(self, normalized_path: str) -> None:
        if self.is_busy:
            return
        self._manual_scroll_guard.preserve()
        self._imported_files = [
            source for source in self._imported_files if source.normalized_path != normalized_path
        ]
        if not self._imported_files:
            self._manual_batch_state = ManualBatchState.EMPTY
        self.import_message.setText("已移除文件，并自动更新受影响名称组的来源分配。")
        self._refresh_sources_and_groups()

    def _clear_sources(self) -> None:
        if self.is_busy:
            return
        self._manual_scroll_guard.preserve()
        self.clear_manual_copy_completely()

    def clear_manual_copy_completely(self) -> None:
        """Reset only this module's editable manual-copy batch."""
        self._imported_files.clear()
        self._selected_targets.clear()
        self._group_plans = ()
        self._submitted_group_plans = ()
        self._submitted_targets.clear()
        self._submitted_task_keys.clear()
        self._manual_result_messages.clear()
        self._manual_batch_state = ManualBatchState.EMPTY
        self.results_tree.clear()
        self.results_panel.setVisible(False)
        self.import_message.setText("列表已清空。")
        self._refresh_sources_and_groups()

    def _clear_previous_result_for_new_batch(self) -> None:
        self._group_plans = ()
        self._selected_targets.clear()
        self._submitted_group_plans = ()
        self._submitted_targets.clear()
        self._submitted_task_keys.clear()
        self._manual_result_messages.clear()
        self.results_tree.clear()
        self.results_panel.setVisible(False)

    def clear_sources_after_submission(self) -> None:
        """Clear the editable left-side model without rebuilding the submitted right side."""
        self._imported_files.clear()
        self.source_list.set_files(())
        # Keep the explicit reset action available for the retained right-side result.
        self.source_list.clear_button.setEnabled(True)

    def rebuild_confirmation_for_current_sources(self) -> None:
        self._refresh_sources_and_groups()

    def _refresh_sources_and_groups(self) -> None:
        self.source_list.set_files(self._imported_files)
        self._group_plans = self._task_builder.build_group_plans(self._imported_files)
        valid_keys = {
            assignment.selection_key
            for group_plan in self._group_plans
            for assignment in group_plan.assignments
        }
        self._selected_targets = {
            key: self._selected_targets.get(key, True) for key in valid_keys
        }
        self._render_confirmation_groups()
        self._update_action_state()

    def _render_confirmation_groups(self) -> None:
        self._confirmation_groups.clear()
        while self.confirmation_layout.count() > 1:
            item = self.confirmation_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        submitted = self._manual_batch_state in (ManualBatchState.RUNNING, ManualBatchState.RESULT_RETAINED)
        plans = self._submitted_group_plans if submitted else self._group_plans
        selections = self._submitted_targets if submitted else self._selected_targets
        if not plans:
            empty = QLabel(f"尚未识别到可补全的{self._module_label}文件。")
            empty.setObjectName("mutedLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.confirmation_layout.insertWidget(0, empty)
            return
        for index, group_plan in enumerate(plans):
            group_widget = ConfirmationGroup(
                group_plan,
                selections,
                locked=submitted,
                result_messages=self._manual_result_messages,
            )
            group_widget.selection_changed.connect(self._on_selection_changed)
            self._confirmation_groups.append(group_widget)
            self.confirmation_layout.insertWidget(self.confirmation_layout.count() - 1, group_widget)
            if index < len(plans) - 1:
                separator = QFrame()
                separator.setObjectName("confirmationSeparator")
                separator.setFrameShape(QFrame.Shape.HLine)
                separator.setFixedHeight(1)
                self.confirmation_layout.insertWidget(self.confirmation_layout.count() - 1, separator)

    def _on_selection_changed(self, key: str, selected: bool) -> None:
        if not self.is_busy:
            self._selected_targets[key] = selected
            self._update_action_state()

    def _set_all_targets(self, selected: bool) -> None:
        if self.is_busy or self._manual_batch_state is not ManualBatchState.EDITING:
            return
        for group_plan in self._group_plans:
            for assignment in group_plan.assignments:
                self._selected_targets[assignment.selection_key] = selected
        self._render_confirmation_groups()
        self._update_action_state()

    def _start_copy(self) -> None:
        if self.is_busy or self._manual_batch_state is not ManualBatchState.EDITING:
            return
        plan = self._task_builder.build_copy_plan(self._group_plans, self._selected_targets)
        if plan.total == 0:
            self._manual_scroll_guard.preserve()
            QMessageBox.information(self, "没有可复制的文件", "请先导入已识别的文件，并至少选择一个待生成名称。")
            return
        policy = self._choose_manual_conflict_policy(plan)
        if policy is None:
            return
        self._manual_scroll_guard.begin_hold()
        self._manual_scroll_guard.preserve()
        self.results_panel.setVisible(False)
        self.results_tree.clear()
        self.manual_status_panel.reset()
        self._submitted_group_plans = self._group_plans
        self._submitted_targets = dict(self._selected_targets)
        self._submitted_task_keys = {
            str(assignment.output_path).casefold(): assignment.selection_key
            for group in self._submitted_group_plans
            for assignment in group.assignments
        }
        self._manual_result_messages.clear()
        self._manual_batch_state = ManualBatchState.RUNNING
        self.cancel_task_button.setEnabled(True)
        self.cancel_task_button.setFocus(Qt.FocusReason.OtherFocusReason)
        if self._service.start_copy(plan, policy):
            self.clear_sources_after_submission()
            self._render_confirmation_groups()
            self._sync_interaction_state()
        else:
            self._manual_batch_state = ManualBatchState.EDITING
            self._manual_scroll_guard.end_hold()

    def _choose_manual_conflict_policy(self, plan: object) -> ConflictPolicy | None:
        existing_paths = tuple(task.target_path for task in getattr(plan, "tasks", ()) if task.target_path.exists())
        if not existing_paths:
            return ConflictPolicy.SKIP_EXISTING
        self._manual_scroll_guard.preserve()
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("发现已存在的目标文件")
        dialog.setText(f"本批任务中有 {len(existing_paths)} 个目标文件已存在。")
        dialog.setInformativeText("请选择对本批冲突文件统一应用的处理方式。")
        dialog.setDetailedText("\n".join(str(path) for path in existing_paths))
        skip_button = dialog.addButton("跳过已存在文件", QMessageBox.ButtonRole.AcceptRole)
        overwrite_button = dialog.addButton("覆盖已存在文件", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = dialog.addButton("取消本次任务", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(skip_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec()
        if dialog.clickedButton() is overwrite_button:
            return ConflictPolicy.OVERWRITE_EXISTING
        if dialog.clickedButton() is skip_button:
            return ConflictPolicy.SKIP_EXISTING
        return None

    def _resolve_conflicts(self, paths: tuple[Path, ...]) -> None:
        if not self.is_busy:
            return
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("发现已存在的目标文件")
        dialog.setText(f"本批任务中有 {len(paths)} 个目标文件已存在。")
        dialog.setInformativeText("请选择对本批所有冲突文件统一应用的处理方式。")
        dialog.setDetailedText("\n".join(str(path) for path in paths))
        skip_button = dialog.addButton("跳过已存在文件", QMessageBox.ButtonRole.AcceptRole)
        overwrite_button = dialog.addButton("覆盖已存在文件", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = dialog.addButton("取消本次任务", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(skip_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked is overwrite_button:
            policy = ConflictPolicy.OVERWRITE_EXISTING
        elif clicked is skip_button:
            policy = ConflictPolicy.SKIP_EXISTING
        else:
            policy = ConflictPolicy.CANCEL_BATCH
        self._service.resolve_conflict(policy)

    def _show_results(self, result: CopyBatchResult) -> None:
        self._manual_scroll_guard.preserve()
        self.results_tree.clear()
        labels = {
            CopyResultStatus.SUCCESS: "成功",
            CopyResultStatus.SKIPPED: "跳过",
            CopyResultStatus.FAILED: "失败",
            CopyResultStatus.CANCELLED: "已取消",
        }
        for item_result in result.results:
            task = item_result.task
            row = QTreeWidgetItem(
                [
                    str(task.source_path),
                    str(task.target_path),
                    labels[item_result.status],
                    item_result.reason,
                ]
            )
            row.setToolTip(0, str(task.source_path))
            row.setToolTip(1, str(task.target_path))
            row.setToolTip(3, item_result.reason)
            self.results_tree.addTopLevelItem(row)
            key = self._submitted_task_keys.get(str(task.target_path).casefold())
            if key is not None:
                text = f"结果：{labels[item_result.status]}"
                if item_result.reason:
                    text = f"{text}，{item_result.reason}"
                self._manual_result_messages[key] = text
        self.results_summary.setText(
            f"成功 {result.succeeded}，跳过 {result.skipped}，失败 {result.failed}。"
        )
        self.results_toggle.setChecked(False)
        self.results_panel.setVisible(True)
        self._manual_batch_state = ManualBatchState.RESULT_RETAINED
        self._render_confirmation_groups()

    def _cancel_manual_copy(self) -> None:
        self._manual_scroll_guard.preserve()
        self._service.cancel()

    def _choose_auto_directory(self) -> None:
        if self.is_busy:
            return
        directory = QFileDialog.getExistingDirectory(self, "选择目标目录", self.directory_selector.path_edit.text())
        if directory:
            self.directory_selector.path_edit.setText(directory)

    def _on_auto_path_changed(self, _path: str) -> None:
        if self.is_busy:
            return
        self._auto_analysis = None
        self._auto_selected_targets.clear()
        self._auto_failures.clear()
        self._auto_target_keys.clear()
        self.auto_result_panel.set_groups((), {}, {})
        self.auto_result_panel.set_plan_statistics(0, 0)
        self.directory_selector.set_statistics(0, 0, 0)
        self.directory_selector.set_status("等待识别" if _path.strip() else "未选择目录")
        self._sync_interaction_state()

    def _start_auto_scan(self, retain_failures: bool = False) -> None:
        if self.is_busy:
            return
        raw_path = self.directory_selector.path_edit.text().strip()
        directory = Path(raw_path)
        if not raw_path or not directory.is_dir():
            self.directory_selector.set_status("目标目录不存在或不可访问")
            return
        self._auto_analysis = None
        self._auto_selected_targets.clear()
        self._auto_target_keys.clear()
        if not retain_failures:
            self._auto_failures.clear()
        self.auto_result_panel.set_groups((), {}, {})
        self.directory_selector.set_status("正在扫描")
        self._scan_service.start_scan(directory, self.directory_selector.include_children.isChecked())
        self._sync_interaction_state()

    def _on_scan_finished(self, scan_result: DirectoryScanResult) -> None:
        analysis = self._auto_analyzer.analyze(scan_result)
        self._auto_analysis = analysis
        valid_keys = {
            assignment.selection_key
            for group in analysis.groups
            for assignment in group.plan.assignments
        }
        self._auto_selected_targets = {key: True for key in valid_keys}
        self._auto_failures = {
            key: reason for key, reason in self._auto_failures.items() if key in valid_keys
        }
        self._render_auto_analysis()
        self.directory_selector.set_statistics(
            scan_result.audio_count,
            analysis.triggered_group_count,
            analysis.missing_group_count,
        )
        if scan_result.recognized_count == 0:
            status = f"未发现可识别的{self._module_label}文件"
        elif analysis.missing_group_count == 0:
            status = "所有已出现的触发组均已完整"
        else:
            status = "发现缺失文件"
        self.directory_selector.set_status(status)
        self._auto_rescan_after_copy = False
        self._sync_interaction_state()

    def _on_scan_cancelled(self) -> None:
        self.directory_selector.set_status("扫描已取消")
        self._sync_interaction_state()

    def _on_scan_failed(self, reason: str) -> None:
        self.directory_selector.set_status(f"扫描失败：{reason}")
        self._sync_interaction_state()

    def _render_auto_analysis(self) -> None:
        analysis = self._auto_analysis
        if analysis is None:
            self.auto_result_panel.set_groups((), {}, {})
            self.auto_result_panel.set_plan_statistics(0, 0)
            return
        self.auto_result_panel.set_groups(analysis.groups, self._auto_selected_targets, self._auto_failures)
        self._auto_target_keys = {
            str(assignment.output_path).casefold(): assignment.selection_key
            for group in analysis.groups
            for assignment in group.plan.assignments
        }
        self._update_auto_statistics()

    def _on_auto_selection_changed(self, key: str, selected: bool) -> None:
        if not self.is_busy:
            self._auto_selected_targets[key] = selected
            self._update_auto_statistics()
            self._sync_interaction_state()

    def _set_all_auto_targets(self, selected: bool) -> None:
        if self.is_busy or self._auto_analysis is None:
            return
        for group in self._auto_analysis.groups:
            for assignment in group.plan.assignments:
                self._auto_selected_targets[assignment.selection_key] = selected
        self._render_auto_analysis()
        self._sync_interaction_state()

    def _reassign_auto_sources(self) -> None:
        if self.is_busy or self._auto_analysis is None:
            return
        previous_selections = dict(self._auto_selected_targets)
        self._auto_analysis = self._auto_analyzer.analyze(self._auto_analysis.scan_result)
        self._auto_selected_targets = {
            assignment.selection_key: previous_selections.get(assignment.selection_key, True)
            for group in self._auto_analysis.groups
            for assignment in group.plan.assignments
        }
        self._render_auto_analysis()
        self._sync_interaction_state()

    def _start_auto_completion(self) -> None:
        if self.is_busy or self._auto_analysis is None:
            return
        if any(not group.directory.is_dir() for group in self._auto_analysis.groups):
            self.directory_selector.set_status("目标目录已不存在，请重新识别")
            return
        plan = self._task_builder.build_copy_plan(
            (group.plan for group in self._auto_analysis.groups),
            self._auto_selected_targets,
        )
        if plan.total == 0:
            QMessageBox.information(self, "没有可补全的文件", "请先完成识别，并至少选择一个待补全文件。")
            return
        self.auto_status_panel.reset()
        self.directory_selector.set_status("正在补全")
        self._auto_copy_service.start_copy(plan, ConflictPolicy.SKIP_EXISTING)
        self._sync_interaction_state()

    def _cancel_auto_work(self) -> None:
        self._scan_service.cancel()
        self._auto_copy_service.cancel()

    def _on_auto_copy_finished(self, result: CopyBatchResult) -> None:
        failures: dict[str, str] = {}
        for item_result in result.results:
            if item_result.status in (CopyResultStatus.FAILED, CopyResultStatus.CANCELLED):
                key = self._auto_target_keys.get(str(item_result.task.target_path).casefold())
                if key is not None:
                    failures[key] = item_result.reason or "补全未完成。"
        self._auto_failures = failures
        if result.state is TaskState.COMPLETED:
            self.directory_selector.set_status("补全完成，正在刷新结果")
        elif result.state is TaskState.PARTIAL_FAILED:
            self.directory_selector.set_status("部分文件补全失败，正在刷新结果")
        elif result.state is TaskState.CANCELLED:
            self.directory_selector.set_status("任务已取消，正在刷新结果")
        else:
            self.directory_selector.set_status("补全结束，正在刷新结果")
        self._auto_rescan_after_copy = True

    def _update_auto_statistics(self) -> None:
        before = self._auto_analysis.scan_result.audio_count if self._auto_analysis is not None else 0
        planned = sum(self._auto_selected_targets.values())
        self.auto_result_panel.set_plan_statistics(before, planned)

    def _sync_interaction_state(self, *_args: object) -> None:
        busy = self.is_busy
        self.drop_area.setEnabled(not busy)
        self.source_list.setEnabled(not busy)
        # Keep the nested scroll usable for reviewing the frozen submitted batch.
        self.confirmation_scroll.setEnabled(True)
        editing = self._manual_batch_state is ManualBatchState.EDITING
        self.select_all_button.setEnabled(not busy and editing and bool(self._group_plans))
        self.select_none_button.setEnabled(not busy and editing and bool(self._group_plans))
        has_selection = any(self._selected_targets.values())
        self.start_copy_button.setEnabled(not busy and editing and has_selection)
        self.cancel_task_button.setEnabled(self._service.is_busy)

        has_auto_analysis = self._auto_analysis is not None
        auto_has_selection = any(self._auto_selected_targets.values())
        self.directory_selector.set_controls_enabled(not busy, has_auto_analysis)
        self.auto_result_panel.set_interaction_enabled(not busy)
        self.auto_select_all_button.setEnabled(not busy and has_auto_analysis)
        self.auto_select_none_button.setEnabled(not busy and has_auto_analysis)
        self.auto_reassign_button.setEnabled(not busy and has_auto_analysis)
        self.auto_start_copy_button.setEnabled(not busy and has_auto_analysis and auto_has_selection)
        self.auto_cancel_task_button.setEnabled(self._auto_copy_service.is_busy or self._scan_service.is_busy)
        self.back_button.setEnabled(self._navigation_enabled and not busy)
        if not self._service.is_busy and self._manual_batch_state is ManualBatchState.RESULT_RETAINED:
            self._manual_scroll_guard.end_hold()
        if not busy and self._close_pending:
            self._close_pending = False
            self.close_ready.emit()
        if not busy and self._auto_rescan_after_copy:
            self._auto_rescan_after_copy = False
            QTimer.singleShot(0, lambda: self._start_auto_scan(retain_failures=True))

    def _update_action_state(self) -> None:
        self._sync_interaction_state()
