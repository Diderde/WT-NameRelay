from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TaskState(str, Enum):
    """UI-facing lifecycle states for future file-processing tasks."""

    WAITING = "waiting"
    PREPARING = "preparing"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class TaskStatusSnapshot:
    """Immutable snapshot delivered from a future worker to the UI."""

    state: TaskState = TaskState.WAITING
    progress: int = 0
    processed: int = 0
    total: int = 0
    current_file: str = ""
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    message: str = ""
