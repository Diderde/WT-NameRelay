from __future__ import annotations

import os
import shutil
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from app.contracts import TaskState, TaskStatusSnapshot
from app.models import (
    ConflictPolicy,
    CopyBatchResult,
    CopyPlan,
    CopyResult,
    CopyResultStatus,
    CopyTask,
)


class FileCopyWorker(QObject):
    """Background-only worker for one frozen manual-copy plan."""

    snapshot_changed = Signal(object)
    conflicts_detected = Signal(object)
    item_finished = Signal(object)
    finished = Signal(object)

    def __init__(
        self,
        plan: CopyPlan,
        cancel_event: threading.Event,
        default_conflict_policy: ConflictPolicy | None = None,
    ) -> None:
        super().__init__()
        self._plan = plan
        self._cancel_event = cancel_event
        self._default_conflict_policy = default_conflict_policy
        self._preexisting_targets: set[Path] = set()
        self._results: list[CopyResult] = list(plan.pre_skipped)
        self._waiting_for_policy = False
        self._finished = False

    @Slot()
    def prepare(self) -> None:
        if self._cancel_event.is_set():
            self._finish_cancelled(self._plan.tasks)
            return
        self._emit_snapshot(TaskState.PREPARING, "正在准备", "")
        for result in self._plan.pre_skipped:
            self.item_finished.emit(result)
        if not self._plan.tasks:
            self._finish_terminal()
            return

        existing_targets = tuple(task.target_path for task in self._plan.tasks if task.target_path.exists())
        if existing_targets:
            self._preexisting_targets = set(existing_targets)
            if self._default_conflict_policy is not None:
                self._copy_all(self._default_conflict_policy)
                return
            self._waiting_for_policy = True
            self.conflicts_detected.emit(existing_targets)
            return
        self._copy_all(ConflictPolicy.SKIP_EXISTING)

    @Slot(str)
    def apply_conflict_policy(self, policy_value: str) -> None:
        if self._finished or not self._waiting_for_policy:
            return
        self._waiting_for_policy = False
        try:
            policy = ConflictPolicy(policy_value)
        except ValueError:
            policy = ConflictPolicy.CANCEL_BATCH
        if self._cancel_event.is_set() or policy is ConflictPolicy.CANCEL_BATCH:
            self._finish_cancelled(self._plan.tasks)
            return
        self._copy_all(policy)

    @Slot()
    def cancel_if_waiting(self) -> None:
        if self._finished or not self._waiting_for_policy:
            return
        self._waiting_for_policy = False
        self._finish_cancelled(self._plan.tasks)

    def _copy_all(self, policy: ConflictPolicy) -> None:
        pending = list(self._plan.tasks)
        while pending:
            if self._cancel_event.is_set():
                self._finish_cancelled(tuple(pending))
                return
            task = pending.pop(0)
            self._emit_snapshot(TaskState.RUNNING, "正在复制", task.target_path.name)
            result = self._copy_one(task, policy)
            self._results.append(result)
            self.item_finished.emit(result)
            self._emit_snapshot(TaskState.RUNNING, "正在复制", task.target_path.name)
        self._finish_terminal()

    def _copy_one(self, task: CopyTask, policy: ConflictPolicy) -> CopyResult:
        source_path = task.source_path
        target_path = task.target_path
        temporary_path: Path | None = None
        try:
            if not source_path.is_file():
                return CopyResult(task, CopyResultStatus.FAILED, "来源文件不存在或已被移动。")
            if target_path in self._preexisting_targets and policy is ConflictPolicy.SKIP_EXISTING:
                return CopyResult(task, CopyResultStatus.SKIPPED, "执行前目标文件已存在，已跳过。")
            if target_path.exists() and policy is ConflictPolicy.SKIP_EXISTING:
                return CopyResult(task, CopyResultStatus.SKIPPED, "目标文件已存在，已跳过。")

            target_path.parent.mkdir(parents=False, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target_path.name}.",
                suffix=".part",
                dir=target_path.parent,
            )
            temporary_path = Path(temporary_name)
            with source_path.open("rb") as source_stream, os.fdopen(descriptor, "wb") as target_stream:
                shutil.copyfileobj(source_stream, target_stream, length=1024 * 1024)

            if policy is ConflictPolicy.OVERWRITE_EXISTING:
                os.replace(temporary_path, target_path)
            else:
                if target_path.exists():
                    return CopyResult(task, CopyResultStatus.SKIPPED, "目标文件已存在，已跳过。")
                try:
                    # On Windows this is a non-overwriting rename. A race is treated safely as skip.
                    os.rename(temporary_path, target_path)
                except FileExistsError:
                    return CopyResult(task, CopyResultStatus.SKIPPED, "目标文件已存在，已跳过。")
            temporary_path = None
            return CopyResult(task, CopyResultStatus.SUCCESS)
        except PermissionError:
            return CopyResult(task, CopyResultStatus.FAILED, "没有读取来源文件或写入输出目录的权限。")
        except OSError as error:
            return CopyResult(task, CopyResultStatus.FAILED, f"复制失败：{error}")
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _finish_cancelled(self, pending: tuple[CopyTask, ...] | list[CopyTask]) -> None:
        for task in pending:
            result = CopyResult(task, CopyResultStatus.CANCELLED, "任务已取消，未执行。")
            self._results.append(result)
            self.item_finished.emit(result)
        self._emit_snapshot(TaskState.CANCELLED, "任务已取消", "")
        self._emit_finished(TaskState.CANCELLED)

    def _finish_terminal(self) -> None:
        failures = sum(result.status is CopyResultStatus.FAILED for result in self._results)
        successes_or_skips = sum(
            result.status in (CopyResultStatus.SUCCESS, CopyResultStatus.SKIPPED) for result in self._results
        )
        if failures == 0:
            state = TaskState.COMPLETED
            message = "任务已完成"
        elif successes_or_skips == 0:
            state = TaskState.FAILED
            message = "任务失败"
        else:
            state = TaskState.PARTIAL_FAILED
            message = "任务部分失败"
        self._emit_snapshot(state, message, "")
        self._emit_finished(state)

    def _emit_snapshot(self, state: TaskState, message: str, current_file: str) -> None:
        succeeded = sum(result.status is CopyResultStatus.SUCCESS for result in self._results)
        skipped = sum(result.status is CopyResultStatus.SKIPPED for result in self._results)
        failed = sum(result.status is CopyResultStatus.FAILED for result in self._results)
        processed = succeeded + skipped + failed
        total = self._plan.total
        progress = round(processed * 100 / total) if total else 0
        self.snapshot_changed.emit(
            TaskStatusSnapshot(
                state=state,
                progress=progress,
                processed=processed,
                total=total,
                current_file=current_file,
                succeeded=succeeded,
                skipped=skipped,
                failed=failed,
                message=message,
            )
        )

    def _emit_finished(self, state: TaskState) -> None:
        if self._finished:
            return
        self._finished = True
        self.finished.emit(CopyBatchResult(state=state, results=tuple(self._results)))
