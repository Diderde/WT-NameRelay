from __future__ import annotations

import logging
import threading

from PySide6.QtCore import Qt, QThread, Signal

from app.models import ConflictPolicy, CopyBatchResult, CopyPlan

from .base_service import BaseTaskService
from .file_copy_worker import FileCopyWorker


class CrewFileService(BaseTaskService):
    """Own the worker thread used by one crew manual-copy batch at a time."""

    conflicts_detected = Signal(object)
    item_finished = Signal(object)
    batch_finished = Signal(object)
    busy_changed = Signal(bool)
    _policy_selected = Signal(str)
    _cancel_waiting = Signal()

    service_name = "crew"

    def __init__(self) -> None:
        super().__init__()
        self._thread: QThread | None = None
        self._worker: FileCopyWorker | None = None
        self._cancel_event: threading.Event | None = None
        self._busy = False

    @property
    def is_busy(self) -> bool:
        return self._busy

    def start_copy(
        self,
        plan: CopyPlan,
        default_conflict_policy: ConflictPolicy | None = None,
    ) -> bool:
        if self._busy:
            return False
        logging.getLogger("wt_name_relay").info("Copy task started: %s files", plan.total)
        self._busy = True
        self.busy_changed.emit(True)
        self._cancel_event = threading.Event()
        self._thread = QThread(self)
        self._worker = FileCopyWorker(plan, self._cancel_event, default_conflict_policy)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.prepare)
        self._worker.snapshot_changed.connect(self.snapshot_changed)
        self._worker.conflicts_detected.connect(self.conflicts_detected)
        self._worker.item_finished.connect(self.item_finished)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._policy_selected.connect(self._worker.apply_conflict_policy, Qt.ConnectionType.QueuedConnection)
        self._cancel_waiting.connect(self._worker.cancel_if_waiting, Qt.ConnectionType.QueuedConnection)
        self._thread.start()
        return True

    def resolve_conflict(self, policy: ConflictPolicy) -> None:
        if self._busy:
            self._policy_selected.emit(policy.value)

    def cancel(self) -> None:
        if not self._busy:
            return
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._cancel_waiting.emit()

    def _on_worker_finished(self, result: CopyBatchResult) -> None:
        logging.getLogger("wt_name_relay").info("Copy task finished: %s", result.state.value)
        self.batch_finished.emit(result)

    def _on_thread_finished(self) -> None:
        self._worker = None
        self._thread = None
        self._cancel_event = None
        if self._busy:
            self._busy = False
            self.busy_changed.emit(False)
