from __future__ import annotations

import os
from collections import Counter

from app.contracts import TaskRandomSource
from app.models import AutoCompletionAnalysis, CompletionGroup, DirectoryScanResult

from .copy_task_builder import CopyTaskBuilder, natural_name_key
from .crew_name_repository import CrewNameRepository


class AutoCompletionAnalyzer:
    """Build directory-isolated completion views from one disk scan snapshot."""

    def __init__(self, repository: CrewNameRepository, rng: TaskRandomSource | None = None) -> None:
        self._task_builder = CopyTaskBuilder(repository, rng)

    def analyze(self, scan_result: DirectoryScanResult) -> AutoCompletionAnalysis:
        groups: list[CompletionGroup] = []
        triggered = 0
        complete = 0
        for scanned_directory in scan_result.directories:
            if not scanned_directory.recognized_sources:
                continue
            scope_key = os.path.normcase(os.fspath(scanned_directory.path))
            plans = self._task_builder.build_group_plans(scanned_directory.recognized_sources, scope_key)
            for plan in plans:
                triggered += 1
                if not plan.assignments:
                    complete += 1
                counts = Counter(source.stem for source in plan.sources)
                groups.append(
                    CompletionGroup(
                        directory=scanned_directory.path,
                        plan=plan,
                        existing_files=tuple(sorted(plan.sources, key=lambda source: natural_name_key(source.stem))),
                        duplicate_stems=frozenset(stem for stem, count in counts.items() if count > 1),
                    )
                )
        groups.sort(key=lambda group: (os.path.normcase(os.fspath(group.directory)), natural_name_key(group.plan.group.base_name)))
        return AutoCompletionAnalysis(scan_result, tuple(groups), triggered, complete)
