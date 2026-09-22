from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal

from app.models import ConflictPolicy, CopyBatchResult, RadioStagedCopyPlan

from .base_service import BaseTaskService
from .radio_staged_worker import DistributionFileCopyWorker


class DistributionFileCopyService(BaseTaskService):
    conflicts_detected = Signal(object)
    item_finished = Signal(object)
    batch_finished = Signal(object)
    busy_changed = Signal(bool)
    _policy_selected = Signal(str)
    _cancel_waiting = Signal()

    service_name = "average_distribution"

    def __init__(self, *, temporary_parent: Path | None = None) -> None:
        super().__init__()
        self._temporary_parent = temporary_parent
        self._thread: QThread | None = None
        self._worker: DistributionFileCopyWorker | None = None
        self._cancel_event: threading.Event | None = None
        self._busy = False

    @property
    def is_busy(self) -> bool:
        return self._busy

    def start_copy(
        self,
        plan: RadioStagedCopyPlan,
        default_conflict_policy: ConflictPolicy | None = None,
    ) -> bool:
        if self._busy:
            logging.getLogger("wt_name_relay").warning(
                "Average distribution start rejected because the service is busy: %s files",
                plan.total,
            )
            return False
        source_count = len({operation.source_snapshot_key for operation in plan.operations})
        logger = logging.getLogger("wt_name_relay")
        logger.info(
            "Average distribution start requested: files=%s source_snapshots=%s",
            plan.total,
            source_count,
        )
        self._busy = True
        self.busy_changed.emit(True)
        self._cancel_event = threading.Event()
        self._thread = QThread(self)
        self._worker = DistributionFileCopyWorker(
            plan,
            self._cancel_event,
            default_conflict_policy,
            temporary_parent=self._temporary_parent,
        )
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
        logger.debug(
            "Average distribution worker and thread started: worker=%s thread=%s files=%s",
            type(self._worker).__name__,
            type(self._thread).__name__,
            plan.total,
        )
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
        logging.getLogger("wt_name_relay").info("Average distribution finished: %s", result.state.value)
        self.batch_finished.emit(result)

    def _on_thread_finished(self) -> None:
        logging.getLogger("wt_name_relay").debug("Average distribution thread finished")
        self._worker = None
        self._thread = None
        self._cancel_event = None
        if self._busy:
            self._busy = False
            self.busy_changed.emit(False)


# Compatibility name; all application pages use the generic service.
RadioStagedFileService = DistributionFileCopyService
