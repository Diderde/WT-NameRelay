from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import threading
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, Signal, Slot

from app.contracts import TaskState, TaskStatusSnapshot
from app.models import (
    ConflictPolicy,
    CopyBatchResult,
    CopyResult,
    CopyResultStatus,
    RadioStagedCopyPlan,
    RadioTargetOperation,
)


class DistributionFileCopyWorker(QObject):
    """Snapshot every source before an average-distribution target is touched."""

    snapshot_changed = Signal(object)
    conflicts_detected = Signal(object)
    item_finished = Signal(object)
    finished = Signal(object)

    def __init__(
        self,
        plan: RadioStagedCopyPlan,
        cancel_event: threading.Event,
        default_conflict_policy: ConflictPolicy | None = None,
        *,
        temporary_parent: Path | None = None,
    ) -> None:
        super().__init__()
        self._plan = plan
        self._cancel_event = cancel_event
        self._default_conflict_policy = default_conflict_policy
        self._temporary_parent = temporary_parent
        self._results: list[CopyResult] = list(plan.pre_skipped)
        # 增量计数：避免每次发快照都对全部结果重新求和（O(n^2) -> O(1)）。
        self._counters = {"succeeded": 0, "skipped": 0, "failed": 0}
        for _seed in self._results:
            self._count(_seed)
        self._waiting_for_policy = False
        self._finished = False
        self._preexisting_targets: set[Path] = set()
        self.last_temporary_directory: Path | None = None

    @Slot()
    def prepare(self) -> None:
        if self._cancel_event.is_set():
            self._finish_cancelled(self._plan.operations)
            return
        self._emit_snapshot(TaskState.PREPARING, "正在准备", "")
        for result in self._plan.pre_skipped:
            self.item_finished.emit(result)
        if not self._plan.operations:
            self._finish_terminal()
            return
        existing = self._plan.current_external_conflicts()
        self._preexisting_targets = set(existing)
        if existing and self._default_conflict_policy is None:
            self._waiting_for_policy = True
            self.conflicts_detected.emit(existing)
            return
        self._stage_and_copy(self._default_conflict_policy or ConflictPolicy.SKIP_EXISTING)

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
            self._finish_cancelled(self._plan.operations)
            return
        self._stage_and_copy(policy)

    @Slot()
    def cancel_if_waiting(self) -> None:
        if self._finished or not self._waiting_for_policy:
            return
        self._waiting_for_policy = False
        self._finish_cancelled(self._plan.operations)

    def _stage_and_copy(self, policy: ConflictPolicy) -> None:
        temp_root = Path(
            tempfile.mkdtemp(
                prefix="WT-NameRelay-average-distribution-",
                dir=str(self._temporary_parent) if self._temporary_parent is not None else None,
            )
        )
        self.last_temporary_directory = temp_root
        snapshots: dict[str, Path] = {}
        failed_key: str | None = None
        failed_reason = ""
        try:
            unique_sources: dict[str, tuple[Path, str]] = {}
            for operation in self._plan.operations:
                unique_sources.setdefault(
                    operation.source_snapshot_key,
                    (operation.source_original_path, operation.source_content_hash),
                )
            for snapshot_key, (source, expected_hash) in unique_sources.items():
                if self._cancel_event.is_set():
                    self._finish_cancelled(self._plan.operations)
                    return
                self._emit_snapshot(TaskState.PREPARING, "正在暂存来源", source.name)
                snapshot_path = temp_root / f"{uuid4().hex}{source.suffix}"
                try:
                    self._copy_snapshot(source, snapshot_path)
                    if expected_hash and self._hash_file(snapshot_path) != expected_hash:
                        raise OSError("来源文件在计划建立后发生变化，快照校验失败。")
                except InterruptedError:
                    self._finish_cancelled(self._plan.operations)
                    return
                except (OSError, PermissionError) as error:
                    failed_key = snapshot_key
                    failed_reason = f"来源暂存失败：{error}"
                    break
                snapshots[snapshot_key] = snapshot_path
            if failed_key is not None:
                self._finish_staging_failed(failed_key, failed_reason)
                return

            pending = list(self._plan.operations)
            while pending:
                if self._cancel_event.is_set():
                    self._finish_cancelled(tuple(pending))
                    return
                operation = pending.pop(0)
                self._emit_snapshot(TaskState.RUNNING, "正在复制", operation.target_path.name)
                result = self._copy_one(operation, snapshots[operation.source_snapshot_key], policy)
                self._append(result)
                self.item_finished.emit(result)
            self._finish_terminal()
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    def _copy_snapshot(self, source: Path, target: Path) -> None:
        if not source.is_file():
            raise FileNotFoundError(f"来源文件不存在或已被移动：{source}")
        with source.open("rb") as source_stream, target.open("wb") as target_stream:
            while True:
                block = source_stream.read(1024 * 1024)
                if not block:
                    break
                if self._cancel_event.is_set():
                    raise InterruptedError("任务已取消")
                target_stream.write(block)

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _copy_one(
        self,
        operation: RadioTargetOperation,
        staged_source: Path,
        policy: ConflictPolicy,
    ) -> CopyResult:
        task = operation.task
        target = operation.target_path
        temporary_path: Path | None = None
        try:
            source_target = self._plan.is_source_target(target)
            effective_policy = (
                ConflictPolicy.OVERWRITE_EXISTING if source_target else policy
            )
            existed = target.exists()
            if existed and effective_policy is ConflictPolicy.SKIP_EXISTING:
                return CopyResult(task, CopyResultStatus.SKIPPED, "目标文件已存在，已跳过。")
            target.parent.mkdir(parents=False, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.", suffix=".part", dir=target.parent
            )
            temporary_path = Path(temporary_name)
            with staged_source.open("rb") as source_stream, os.fdopen(descriptor, "wb") as target_stream:
                shutil.copyfileobj(source_stream, target_stream, length=1024 * 1024)
            if effective_policy is ConflictPolicy.OVERWRITE_EXISTING:
                overwritten = target.exists()
                temporary_path.replace(target)
                temporary_path = None
                return CopyResult(
                    task,
                    CopyResultStatus.SUCCESS,
                    (
                        "来源目标已按平均分配计划重写。"
                        if source_target
                        else "已覆盖。" if overwritten else ""
                    ),
                    overwritten,
                )
            if target.exists():
                return CopyResult(task, CopyResultStatus.SKIPPED, "目标文件已存在，已跳过。")
            try:
                os.rename(temporary_path, target)
            except FileExistsError:
                return CopyResult(task, CopyResultStatus.SKIPPED, "目标文件已存在，已跳过。")
            temporary_path = None
            return CopyResult(task, CopyResultStatus.SUCCESS)
        except PermissionError:
            return CopyResult(task, CopyResultStatus.FAILED, "没有读取暂存文件或写入输出目录的权限。")
        except OSError as error:
            return CopyResult(task, CopyResultStatus.FAILED, f"复制失败：{error}")
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _finish_staging_failed(self, failed_key: str, reason: str) -> None:
        for operation in self._plan.operations:
            if operation.source_snapshot_key == failed_key:
                result = CopyResult(operation.task, CopyResultStatus.FAILED, reason)
            else:
                result = CopyResult(
                    operation.task,
                    CopyResultStatus.CANCELLED,
                    "来源暂存未全部完成，本项未执行。",
                )
            self._append(result)
            self.item_finished.emit(result)
        self._emit_snapshot(TaskState.FAILED, "来源暂存失败，未写入任何目标", "")
        self._emit_finished(TaskState.FAILED)

    def _finish_cancelled(
        self, pending: tuple[RadioTargetOperation, ...] | list[RadioTargetOperation]
    ) -> None:
        for operation in pending:
            result = CopyResult(operation.task, CopyResultStatus.CANCELLED, "任务已取消，未执行。")
            self._append(result)
            self.item_finished.emit(result)
        self._emit_snapshot(TaskState.CANCELLED, "任务已取消", "")
        self._emit_finished(TaskState.CANCELLED)

    def _finish_terminal(self) -> None:
        failures = sum(result.status is CopyResultStatus.FAILED for result in self._results)
        successes_or_skips = sum(
            result.status in (CopyResultStatus.SUCCESS, CopyResultStatus.SKIPPED)
            for result in self._results
        )
        if failures == 0:
            state, message = TaskState.COMPLETED, "任务已完成"
        elif successes_or_skips == 0:
            state, message = TaskState.FAILED, "任务失败"
        else:
            state, message = TaskState.PARTIAL_FAILED, "任务部分失败"
        self._emit_snapshot(state, message, "")
        self._emit_finished(state)

    def _count(self, result: CopyResult) -> None:
        if result.status is CopyResultStatus.SUCCESS:
            self._counters["succeeded"] += 1
        elif result.status is CopyResultStatus.SKIPPED:
            self._counters["skipped"] += 1
        elif result.status is CopyResultStatus.FAILED:
            self._counters["failed"] += 1

    def _append(self, result: CopyResult) -> None:
        self._results.append(result)
        self._count(result)

    def _emit_snapshot(self, state: TaskState, message: str, current_file: str) -> None:
        counters = self._counters
        succeeded, skipped, failed = counters["succeeded"], counters["skipped"], counters["failed"]
        processed = succeeded + skipped + failed
        progress = round(processed * 100 / self._plan.total) if self._plan.total else 0
        self.snapshot_changed.emit(
            TaskStatusSnapshot(
                state=state,
                progress=progress,
                processed=processed,
                total=self._plan.total,
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
        self.finished.emit(CopyBatchResult(state, tuple(self._results)))


# Compatibility name for existing integrations and third-party tests.
RadioStagedFileCopyWorker = DistributionFileCopyWorker
