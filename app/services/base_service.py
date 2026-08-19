from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot


class BaseTaskService(QObject):
    """Signal/slot boundary for a future worker-backed task service.

    File processing must be implemented by a worker moved to QThread. This
    placeholder deliberately performs no file-system work.
    """

    snapshot_changed = Signal(object)
    completed = Signal()
    failed = Signal(str)

    service_name = "base"

    @Slot()
    def start(self) -> None:
        self.failed.emit("功能尚未接入")

    @Slot()
    def pause(self) -> None:
        self.failed.emit("功能尚未接入")

    @Slot()
    def cancel(self) -> None:
        self.failed.emit("功能尚未接入")
