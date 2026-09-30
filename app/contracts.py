from __future__ import annotations

from collections.abc import MutableSequence, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class TaskRandomSource(Protocol):
    """随机源注入点要求的最小接口。

    生产默认使用 ``random.SystemRandom()``；测试可注入确定性实现以获得
    可复现的分配结果，而不必依赖 ``random`` 模块。
    """

    def shuffle(self, sequence: MutableSequence[Any]) -> None: ...

    def choice(self, sequence: Sequence[Any]) -> Any: ...


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
