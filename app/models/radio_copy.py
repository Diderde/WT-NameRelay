from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .copy_task import CopyPlan, CopyResult, CopyTask
from .crew_name_group import CrewNameGroup
from .source_file import SourceFile
from .average_distribution import ConflictKind, DistributionPlan


class ManualCopyMode(str, Enum):
    """Radio manual-copy assignment mode."""

    SEQUENTIAL = "sequential"
    AVERAGE = "average"


RadioTargetConflictKind = ConflictKind


@dataclass(frozen=True, slots=True)
class RadioSourceUnit:
    """Recognised sources isolated by name group and physical directory."""

    group: CrewNameGroup
    directory: Path
    scope_key: str
    sources: tuple[SourceFile, ...]


@dataclass(frozen=True, slots=True)
class RadioTargetAssignment:
    group_id: str
    group_display_name: str
    source: SourceFile
    target_name: str
    directory: Path
    scope_key: str
    copy_mode: ManualCopyMode
    target_group_index: int
    will_overwrite: bool
    conflict_kind: RadioTargetConflictKind

    @property
    def selection_key(self) -> str:
        return f"{self.scope_key}\x00{self.group_id}\x00{self.target_name}"

    @property
    def output_path(self) -> Path:
        return self.directory / f"{self.target_name}{self.source.suffix}"


@dataclass(frozen=True, slots=True)
class RadioTargetTriple:
    index: int
    names: tuple[str, str, str]
    source: SourceFile


@dataclass(frozen=True, slots=True)
class RadioManualGroupPlan:
    group: CrewNameGroup
    directory: Path
    sources: tuple[SourceFile, ...]
    assignments: tuple[RadioTargetAssignment, ...]
    copy_mode: ManualCopyMode
    triples: tuple[RadioTargetTriple, ...] = ()
    fallback_reason: str = ""
    distribution_plan: DistributionPlan | None = None


@dataclass(frozen=True, slots=True)
class RadioTargetOperation:
    module: str
    group_id: str
    group_display_name: str
    source_original_path: Path
    source_snapshot_key: str
    source_member_name: str
    target_member_name: str
    target_path: Path
    copy_mode: ManualCopyMode
    will_overwrite: bool
    conflict_kind: RadioTargetConflictKind
    source_content_hash: str = ""

    @property
    def task(self) -> CopyTask:
        return CopyTask(
            group_base=self.group_display_name,
            source_path=self.source_original_path,
            target_path=self.target_path,
            target_name=self.target_member_name,
        )


@dataclass(frozen=True, slots=True)
class RadioStagedCopyPlan:
    """Frozen target mapping whose sources are snapshotted before any write."""

    operations: tuple[RadioTargetOperation, ...]
    pre_skipped: tuple[CopyResult, ...] = ()
    imported_source_paths: frozenset[str] = frozenset()

    @property
    def tasks(self) -> tuple[CopyTask, ...]:
        return tuple(operation.task for operation in self.operations)

    @property
    def total(self) -> int:
        return len(self.operations) + len(self.pre_skipped)

    def is_source_target(self, target_path: Path) -> bool:
        normalized = os.path.normcase(os.path.abspath(os.fspath(target_path)))
        return normalized in self.imported_source_paths

    def current_external_conflicts(self) -> tuple[Path, ...]:
        return tuple(
            operation.target_path
            for operation in self.operations
            if not self.is_source_target(operation.target_path) and operation.target_path.exists()
        )

    def as_copy_plan(self) -> CopyPlan:
        return CopyPlan(self.tasks, self.pre_skipped)
