from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .copy_task import CrewGroupPlan
from .directory_scan_result import DirectoryScanResult
from .source_file import SourceFile


@dataclass(frozen=True, slots=True)
class CompletionGroup:
    """One directory-scoped automatic completion group."""

    directory: Path
    plan: CrewGroupPlan
    existing_files: tuple[SourceFile, ...]
    duplicate_stems: frozenset[str]

    @property
    def scope_key(self) -> str:
        return str(self.directory)

    @property
    def current_logical_count(self) -> int:
        return len({source.stem for source in self.existing_files})

    @property
    def expected_count(self) -> int:
        return len(self.plan.group.names)

    @property
    def missing_count(self) -> int:
        return len(self.plan.assignments)


@dataclass(frozen=True, slots=True)
class AutoCompletionAnalysis:
    scan_result: DirectoryScanResult
    groups: tuple[CompletionGroup, ...]
    triggered_group_count: int
    complete_group_count: int

    @property
    def missing_group_count(self) -> int:
        return sum(group.missing_count > 0 for group in self.groups)
