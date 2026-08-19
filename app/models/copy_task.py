from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.contracts import TaskState

from .crew_name_group import CrewNameGroup
from .source_file import SourceFile


class ConflictPolicy(str, Enum):
    SKIP_EXISTING = "skip_existing"
    OVERWRITE_EXISTING = "overwrite_existing"
    CANCEL_BATCH = "cancel_batch"


class CopyResultStatus(str, Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ManualBatchState(str, Enum):
    """UI lifecycle for an editable manual-copy batch."""

    EMPTY = "empty"
    EDITING = "editing"
    RUNNING = "running"
    RESULT_RETAINED = "result_retained"


@dataclass(frozen=True, slots=True)
class TargetAssignment:
    """A target name with a fixed source selected for this confirmation view."""

    group_base: str
    target_name: str
    source: SourceFile
    scope_key: str = ""

    @property
    def selection_key(self) -> str:
        return f"{self.scope_key}\x00{self.group_base}\x00{self.target_name}"

    @property
    def output_path(self) -> Path:
        return self.source.path.with_name(f"{self.target_name}{self.source.suffix}")


@dataclass(frozen=True, slots=True)
class CrewGroupPlan:
    """Presentation-ready confirmation data for one recognised name group."""

    group: CrewNameGroup
    sources: tuple[SourceFile, ...]
    assignments: tuple[TargetAssignment, ...]


@dataclass(frozen=True, slots=True)
class CopyTask:
    """A frozen file operation handed to the background worker."""

    group_base: str
    source_path: Path
    target_path: Path
    target_name: str


@dataclass(frozen=True, slots=True)
class CopyResult:
    """Terminal result for a selected target item."""

    task: CopyTask
    status: CopyResultStatus
    reason: str = ""
    overwritten: bool = False


@dataclass(frozen=True, slots=True)
class CopyPlan:
    """Frozen selected work plus deterministic pre-execution skips."""

    tasks: tuple[CopyTask, ...]
    pre_skipped: tuple[CopyResult, ...] = ()

    @property
    def total(self) -> int:
        return len(self.tasks) + len(self.pre_skipped)


@dataclass(frozen=True, slots=True)
class CopyBatchResult:
    """All results emitted after a manual-copy batch reaches a terminal state."""

    state: TaskState
    results: tuple[CopyResult, ...]

    @property
    def succeeded(self) -> int:
        return sum(result.status is CopyResultStatus.SUCCESS for result in self.results)

    @property
    def skipped(self) -> int:
        return sum(result.status is CopyResultStatus.SKIPPED for result in self.results)

    @property
    def failed(self) -> int:
        return sum(result.status is CopyResultStatus.FAILED for result in self.results)

    @property
    def overwritten(self) -> int:
        return sum(result.status is CopyResultStatus.SUCCESS and result.overwritten for result in self.results)

    @property
    def created(self) -> int:
        return sum(result.status is CopyResultStatus.SUCCESS and not result.overwritten for result in self.results)

    @property
    def cancelled(self) -> int:
        return sum(result.status is CopyResultStatus.CANCELLED for result in self.results)
