from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QMessageBox, QWidget

from app.i18n import i18n_live, i18n_text
from app.i18n import mark as _i18n_mark
from app.i18n import refresh as _i18n_refresh
from app.models import (
    ConflictPolicy,
    CopyBatchResult,
    CopyResultStatus,
    ManualBatchState,
    ManualCopyMode,
    RadioManualGroupPlan,
    RadioStagedCopyPlan,
)
from app.module_config import RADIO_MODULE
from app.services import DistributionFileCopyService, RadioAveragePlanBuilder
from app.widgets import CopyModeSwitch, RadioManualConfirmationGroup

from .crew_page import CrewPage


class RadioPage(CrewPage):
    """Radio workflow with an isolated deterministic average manual-copy mode."""

    def __init__(self, parent: QWidget | None=None) -> None:
        self._manual_copy_mode = ManualCopyMode.SEQUENTIAL
        self._submitted_copy_mode = ManualCopyMode.SEQUENTIAL
        self._radio_import_order: list[str] = []
        self._fallback_warning_signature: tuple[str, ...] = ()
        self._average_service = DistributionFileCopyService()
        self._radio_average_builder: RadioAveragePlanBuilder | None = None
        super().__init__(parent, config=RADIO_MODULE)
        self._average_service.setParent(self)
        self._radio_average_builder = RadioAveragePlanBuilder(self._repository, self._task_builder)
        self.copy_mode_switch = CopyModeSwitch(self.action_bar)
        action_layout = self.action_bar.layout()
        assert action_layout is not None
        action_layout.insertWidget(action_layout.indexOf(self.start_copy_button), self.copy_mode_switch)
        self.copy_mode_switch.mode_changed.connect(self._change_copy_mode)
        self._average_service.snapshot_changed.connect(self.manual_status_panel.set_snapshot)
        self._average_service.batch_finished.connect(self._show_average_results)
        self._average_service.busy_changed.connect(self._sync_interaction_state)
        self._average_service.conflicts_detected.connect(self._resolve_average_conflicts)
        self._refresh_sources_and_groups()
        self._sync_interaction_state()
        _i18n_mark(self.directory_selector, 'scope', None)
        _i18n_mark(self.results_summary, 'scope', None)

    def retranslate(self) -> None:
        self._module_label = i18n_live('ui.135')
        super().retranslate()
        _i18n_refresh(self)
        self._refresh_sources_and_groups()

    @property
    def is_busy(self) -> bool:
        return super().is_busy or self._average_service.is_busy

    def request_safe_close(self) -> bool:
        if not self._average_service.is_busy:
            return super().request_safe_close()
        if self._close_pending:
            return False
        answer = QMessageBox.question(self, i18n_text('ui.005'), i18n_text('ui.067'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer is QMessageBox.StandardButton.Yes:
            self._close_pending = True
            self._average_service.cancel()
            self._service.cancel()
            self._auto_copy_service.cancel()
            self._scan_service.cancel()
        return False

    def _change_copy_mode(self, average: bool) -> None:
        if self.is_busy or self._manual_batch_state in (ManualBatchState.RUNNING, ManualBatchState.RESULT_RETAINED):
            self.copy_mode_switch.set_average_checked(self._manual_copy_mode is ManualCopyMode.AVERAGE, emit=False)
            return
        requested = ManualCopyMode.AVERAGE if average else ManualCopyMode.SEQUENTIAL
        if requested is ManualCopyMode.AVERAGE:
            builder = self._require_average_builder()
            violations = builder.limit_violations(self._imported_files)
            if violations:
                self.copy_mode_switch.set_average_checked(False, emit=False)
                self._show_limit_violations(violations, switching=True)
                return
        previous = self._logical_selections()
        self._manual_scroll_guard.preserve()
        self._manual_copy_mode = requested
        if requested is ManualCopyMode.SEQUENTIAL:
            self._fallback_warning_signature = ()
        self._refresh_sources_and_groups()
        for plan in self._group_plans:
            group_id = plan.group.group_key
            for assignment in plan.assignments:
                logical = (group_id, assignment.target_name)
                if logical in previous:
                    self._selected_targets[assignment.selection_key] = previous[logical]
        self._render_confirmation_groups()
        self._sync_interaction_state()

    def _logical_selections(self) -> dict[tuple[str, str], bool]:
        logical: dict[tuple[str, str], bool] = {}
        for plan in self._group_plans:
            group_id = plan.group.group_key
            for assignment in plan.assignments:
                logical[group_id, assignment.target_name] = self._selected_targets.get(assignment.selection_key, True)
        return logical

    def _add_paths(self, paths: Iterable[str]) -> None:
        if self.is_busy:
            return
        self._manual_scroll_guard.preserve()
        known_paths = {source.normalized_path for source in self._imported_files}
        accepted = []
        ignored_directories = ignored_duplicates = ignored_invalid = 0
        rejected: dict[tuple[str, str], list[tuple[object, Path]]] = {}
        builder = self._require_average_builder()
        counts: dict[tuple[str, str], int] = {}
        for source in self._imported_files:
            if source.is_recognized and source.group_key is not None:
                scope = self._scope_key(source.path.parent)
                counts[source.group_key, scope] = counts.get((source.group_key, scope), 0) + 1
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
            if self._manual_copy_mode is ManualCopyMode.AVERAGE and source.is_recognized and (source.group_key is not None):
                maximum = builder.maximum_sources(source.group_key)
                if maximum is not None:
                    scope = self._scope_key(source.path.parent)
                    unit_key = (source.group_key, scope)
                    actual = counts.get(unit_key, 0) + 1
                    if actual > maximum:
                        rejected.setdefault(unit_key, []).append((source, candidate))
                        counts[unit_key] = actual
                        continue
                    counts[unit_key] = actual
            known_paths.add(source.normalized_path)
            accepted.append(source)
        if accepted and self._manual_batch_state is ManualBatchState.RESULT_RETAINED:
            self._clear_previous_result_for_new_batch()
        for source in accepted:
            self._imported_files.append(source)
            self._radio_import_order.append(source.normalized_path)
        self._imported_files.sort(key=lambda item: item.normalized_path)
        messages: list[str] = []
        if accepted:
            messages.append(i18n_text('ui.068').format(len(accepted)))
        if ignored_directories:
            messages.append(i18n_text('ui.069').format(ignored_directories))
        if ignored_duplicates:
            messages.append(i18n_text('ui.070').format(ignored_duplicates))
        if ignored_invalid:
            messages.append(i18n_text('ui.071').format(ignored_invalid))
        if rejected:
            messages.append(i18n_text('ui.072').format(sum(len(items) for items in rejected.values())))
        if messages:
            self.import_message.setText('；'.join(messages) + '。')
        if self._imported_files:
            self._manual_batch_state = ManualBatchState.EDITING
        self._refresh_sources_and_groups()
        if rejected:
            self._show_rejected_imports(rejected)

    def _remove_source(self, normalized_path: str) -> None:
        self._radio_import_order = [item for item in self._radio_import_order if item != normalized_path]
        super()._remove_source(normalized_path)

    def clear_manual_copy_completely(self) -> None:
        self._radio_import_order.clear()
        self._fallback_warning_signature = ()
        self._submitted_copy_mode = ManualCopyMode.SEQUENTIAL
        super().clear_manual_copy_completely()

    def _clear_previous_result_for_new_batch(self) -> None:
        self._fallback_warning_signature = ()
        self._submitted_copy_mode = ManualCopyMode.SEQUENTIAL
        super()._clear_previous_result_for_new_batch()

    def clear_sources_after_submission(self) -> None:
        self._radio_import_order.clear()
        super().clear_sources_after_submission()

    def _refresh_sources_and_groups(self) -> None:
        if self._manual_copy_mode is ManualCopyMode.SEQUENTIAL or self._radio_average_builder is None:
            super()._refresh_sources_and_groups()
            return
        self.source_list.set_files(self._imported_files)
        self._group_plans = self._radio_average_builder.build_group_plans(self._imported_files, self._radio_import_order)
        valid_keys = {assignment.selection_key for group_plan in self._group_plans for assignment in group_plan.assignments}
        self._selected_targets = {key: self._selected_targets.get(key, True) for key in valid_keys}
        self._render_confirmation_groups()
        self._update_action_state()
        self._show_fallback_warning_once()

    def _render_confirmation_groups(self) -> None:
        submitted = self._manual_batch_state in (ManualBatchState.RUNNING, ManualBatchState.RESULT_RETAINED)
        render_mode = self._submitted_copy_mode if submitted else self._manual_copy_mode
        if render_mode is ManualCopyMode.SEQUENTIAL:
            super()._render_confirmation_groups()
            return
        self._confirmation_groups.clear()
        while self.confirmation_layout.count() > 1:
            item = self.confirmation_layout.takeAt(0)
            if item.widget() is not None:
                # hide() 立即移出视图，deleteLater 的延迟销毁期间不再叠印旧文案
                item.widget().hide()
                item.widget().deleteLater()
        plans = self._submitted_group_plans if submitted else self._group_plans
        selections = self._submitted_targets if submitted else self._selected_targets
        if not plans:
            empty = _i18n_mark(QLabel(i18n_text('ui.073')), 'text', 'ui.073')
            empty.setObjectName('mutedLabel')
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.confirmation_layout.insertWidget(0, empty)
            return
        for index, plan in enumerate(plans):
            widget = RadioManualConfirmationGroup(plan, selections, locked=submitted, result_messages=self._manual_result_messages)
            widget.selection_changed.connect(self._on_selection_changed)
            self._confirmation_groups.append(widget)
            self.confirmation_layout.insertWidget(self.confirmation_layout.count() - 1, widget)
            if index < len(plans) - 1:
                separator = QFrame()
                separator.setObjectName('confirmationSeparator')
                separator.setFrameShape(QFrame.Shape.HLine)
                separator.setFixedHeight(1)
                self.confirmation_layout.insertWidget(self.confirmation_layout.count() - 1, separator)

    def _start_copy(self) -> None:
        if self._manual_copy_mode is ManualCopyMode.SEQUENTIAL:
            self._submitted_copy_mode = ManualCopyMode.SEQUENTIAL
            super()._start_copy()
            return
        if self.is_busy or self._manual_batch_state is not ManualBatchState.EDITING:
            return
        plan = self._require_average_builder().build_staged_copy_plan(self._group_plans, self._selected_targets)
        if plan.total == 0:
            self._manual_scroll_guard.preserve()
            QMessageBox.information(self, i18n_text('ui.074'), i18n_text('ui.075'))
            return
        policy = self._choose_average_conflict_policy(plan)
        if policy is None:
            return
        self._manual_scroll_guard.begin_hold()
        self._manual_scroll_guard.preserve()
        self.results_panel.setVisible(False)
        self.results_tree.clear()
        self.manual_status_panel.reset()
        self._submitted_group_plans = self._group_plans
        self._submitted_targets = dict(self._selected_targets)
        self._submitted_copy_mode = ManualCopyMode.AVERAGE
        self._submitted_task_keys = {str(assignment.output_path).casefold(): assignment.selection_key for group in self._submitted_group_plans for assignment in group.assignments}
        self._manual_result_messages.clear()
        self._manual_batch_state = ManualBatchState.RUNNING
        self.cancel_task_button.setEnabled(True)
        self.cancel_task_button.setFocus(Qt.FocusReason.OtherFocusReason)
        if self._average_service.start_copy(plan, policy):
            self.clear_sources_after_submission()
            self._render_confirmation_groups()
            self._sync_interaction_state()
        else:
            self._manual_batch_state = ManualBatchState.EDITING
            self._submitted_copy_mode = ManualCopyMode.SEQUENTIAL
            self._manual_scroll_guard.end_hold()

    def _choose_average_conflict_policy(self, plan: RadioStagedCopyPlan) -> ConflictPolicy | None:
        """Ask only about existing files that are not sources in this frozen batch."""
        existing_paths = plan.current_external_conflicts()
        if not existing_paths:
            return ConflictPolicy.SKIP_EXISTING
        self._manual_scroll_guard.preserve()
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle(i18n_text('ui.076'))
        dialog.setText(i18n_text('ui.077').format(len(existing_paths)))
        dialog.setInformativeText(i18n_text('ui.078'))
        dialog.setDetailedText('\n'.join(str(path) for path in existing_paths))
        skip_button = dialog.addButton(i18n_text('ui.079'), QMessageBox.ButtonRole.AcceptRole)
        overwrite_button = dialog.addButton(i18n_text('ui.080'), QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = dialog.addButton(i18n_text('ui.081'), QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(skip_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec()
        if dialog.clickedButton() is overwrite_button:
            return ConflictPolicy.OVERWRITE_EXISTING
        if dialog.clickedButton() is skip_button:
            return ConflictPolicy.SKIP_EXISTING
        return None

    def _show_average_results(self, result: CopyBatchResult) -> None:
        super()._show_results(result)
        self.results_summary.setText(i18n_text('ui.082').format(result.created, result.overwritten, result.skipped, result.failed, result.cancelled))
        failures = [item for item in result.results if item.status is CopyResultStatus.FAILED]
        if failures:
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Warning)
            dialog.setWindowTitle(i18n_text('ui.083'))
            dialog.setText(i18n_text('ui.084').format(len(failures)))
            dialog.setDetailedText('\n'.join(f'{item.task.target_path}\n  {item.reason}' for item in failures))
            dialog.exec()

    def _cancel_manual_copy(self) -> None:
        self._manual_scroll_guard.preserve()
        self._service.cancel()
        self._average_service.cancel()

    def _resolve_average_conflicts(self, paths: tuple[Path, ...]) -> None:
        if not self._average_service.is_busy:
            return
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle(i18n_text('ui.076'))
        dialog.setText(i18n_text('ui.077').format(len(paths)))
        dialog.setInformativeText(i18n_text('ui.085'))
        dialog.setDetailedText('\n'.join(str(path) for path in paths))
        skip_button = dialog.addButton(i18n_text('ui.079'), QMessageBox.ButtonRole.AcceptRole)
        overwrite_button = dialog.addButton(i18n_text('ui.080'), QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = dialog.addButton(i18n_text('ui.081'), QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(skip_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec()
        if dialog.clickedButton() is overwrite_button:
            policy = ConflictPolicy.OVERWRITE_EXISTING
        elif dialog.clickedButton() is skip_button:
            policy = ConflictPolicy.SKIP_EXISTING
        else:
            policy = ConflictPolicy.CANCEL_BATCH
        self._average_service.resolve_conflict(policy)

    def _sync_interaction_state(self, *_args: object) -> None:
        super()._sync_interaction_state(*_args)
        if not hasattr(self, 'copy_mode_switch'):
            return
        locked = self._manual_batch_state in (ManualBatchState.RUNNING, ManualBatchState.RESULT_RETAINED)
        self.copy_mode_switch.setEnabled(not self.is_busy and (not locked))
        self.cancel_task_button.setEnabled(self._service.is_busy or self._average_service.is_busy)

    def _show_fallback_warning_once(self) -> None:
        if self._manual_copy_mode is not ManualCopyMode.AVERAGE:
            return
        fallback = tuple(f'{plan.group.base_name}\n  {plan.directory}' for plan in self._group_plans if isinstance(plan, RadioManualGroupPlan) and plan.fallback_reason)
        signature = tuple(sorted(fallback))
        if not signature or signature == self._fallback_warning_signature:
            return
        self._fallback_warning_signature = signature
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setWindowTitle(i18n_text('ui.086'))
        dialog.setText(i18n_text('ui.087'))
        dialog.setDetailedText('\n\n'.join(fallback))
        dialog.exec()

    def _show_limit_violations(self, violations: tuple[object, ...], *, switching: bool) -> None:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle(i18n_text('ui.088') if switching else i18n_text('ui.089'))
        dialog.setText(i18n_text('ui.090') if switching else i18n_text('ui.091'))
        dialog.setDetailedText('\n\n'.join(i18n_text('ui.092').format(item.group_name, item.directory, item.member_count, item.maximum, item.actual) for item in violations))
        dialog.exec()

    def _show_rejected_imports(self, rejected: dict[tuple[str, str], list[tuple[object, Path]]]) -> None:
        builder = self._require_average_builder()
        details: list[str] = []
        for (group_key, _scope), items in rejected.items():
            group = self._repository.get_by_key(group_key)
            maximum = builder.maximum_sources(group_key)
            if group is None or maximum is None:
                continue
            accepted_count = sum(source.group_key == group_key and self._scope_key(source.path.parent) == _scope for source in self._imported_files)
            details.append(i18n_text('ui.093').format(group.base_name, len(group.names), maximum, accepted_count + len(items)) + '\n'.join((f'  {path}' for _source, path in items)))
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle(i18n_text('ui.089'))
        dialog.setText(i18n_text('ui.094'))
        dialog.setDetailedText('\n\n'.join(details))
        dialog.exec()

    def _require_average_builder(self) -> RadioAveragePlanBuilder:
        if self._radio_average_builder is None:
            raise RuntimeError(i18n_text('ui.095'))
        return self._radio_average_builder

    @staticmethod
    def _scope_key(directory: Path) -> str:
        return os.path.normcase(os.path.abspath(os.fspath(directory)))