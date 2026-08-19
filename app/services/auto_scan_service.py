from __future__ import annotations

import threading
import logging
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.models import DirectoryScanResult

from .directory_scanner import DirectoryScanner, ScanCancelled


class _DirectoryScanWorker(QObject):
    finished = Signal(object)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(
        self,
        scanner: DirectoryScanner,
        root_path: Path,
        include_subdirectories: bool,
        cancel_event: threading.Event,
    ) -> None:
        super().__init__()
        self._scanner = scanner
        self._root_path = root_path
        self._include_subdirectories = include_subdirectories
        self._cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        try:
            result = self._scanner.scan(self._root_path, self._include_subdirectories, self._cancel_event)
        except ScanCancelled:
            self.cancelled.emit()
        except OSError as error:
            self.failed.emit(str(error))
        else:
            self.finished.emit(result)


class AutoScanService(QObject):
    """Own a cancellable background scan without blocking the Qt UI thread."""

    scan_finished = Signal(object)
    scan_cancelled = Signal()
    scan_failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, scanner: DirectoryScanner) -> None:
        super().__init__()
        self._scanner = scanner
        self._thread: QThread | None = None
        self._worker: _DirectoryScanWorker | None = None
        self._cancel_event: threading.Event | None = None
        self._busy = False

    @property
    def is_busy(self) -> bool:
        return self._busy

    def start_scan(self, root_path: Path, include_subdirectories: bool) -> bool:
        if self._busy:
            return False
        logging.getLogger("wt_name_relay").info("Directory scan started: %s", root_path)
        self._busy = True
        self.busy_changed.emit(True)
        self._cancel_event = threading.Event()
        self._thread = QThread(self)
        self._worker = _DirectoryScanWorker(
            self._scanner,
            root_path,
            include_subdirectories,
            self._cancel_event,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self.scan_finished)
        self._worker.cancelled.connect(self.scan_cancelled)
        self._worker.failed.connect(self.scan_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.cancelled.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._cleanup)
        self._thread.start()
        return True

    def cancel(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()

    def _cleanup(self) -> None:
        logging.getLogger("wt_name_relay").info("Directory scan finished")
        self._worker = None
        self._thread = None
        self._cancel_event = None
        if self._busy:
            self._busy = False
            self.busy_changed.emit(False)
