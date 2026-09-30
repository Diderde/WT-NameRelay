from __future__ import annotations

import os
import random
import re
from collections.abc import Iterable, Mapping

from app.contracts import TaskRandomSource
from app.models import (
    CopyPlan,
    CopyResult,
    CopyResultStatus,
    CopyTask,
    CrewGroupPlan,
    SourceFile,
    TargetAssignment,
)

from .crew_name_repository import CrewNameRepository

_VERSION_PATTERN = re.compile(r"_v(?P<major>[1-9]\d*)(?:_(?P<minor>[1-9]\d*))?$")


def natural_name_key(value: str) -> tuple[object, ...]:
    """Sort versioned names by numeric version components, then by text."""
    match = _VERSION_PATTERN.search(value)
    if match is None:
        return (value.casefold(), value)
    minor = match.group("minor")
    return (
        value[: match.start()].casefold(),
        int(match.group("major")),
        minor is not None,
        int(minor) if minor is not None else 0,
        value,
    )


class CopyTaskBuilder:
    """Build stable group views and frozen copy work without creating files."""

    def __init__(self, repository: CrewNameRepository, rng: TaskRandomSource | None = None) -> None:
        self._repository = repository
        self._rng = rng or random.SystemRandom()

    def build_group_plans(
        self,
        sources: Iterable[SourceFile],
        scope_key: str = "",
    ) -> tuple[CrewGroupPlan, ...]:
        unique_sources: dict[str, SourceFile] = {}
        for source in sources:
            unique_sources.setdefault(source.normalized_path, source)
        grouped_sources: dict[str, list[SourceFile]] = {}
        for source in unique_sources.values():
            if source.is_recognized and source.group_key is not None:
                grouped_sources.setdefault(source.group_key, []).append(source)

        plans: list[CrewGroupPlan] = []
        for group_key in sorted(grouped_sources, key=natural_name_key):
            group = self._repository.get_by_key(group_key)
            if group is None:
                continue
            group_sources = tuple(sorted(grouped_sources[group_key], key=lambda item: item.normalized_path))
            imported_names = {source.stem for source in group_sources}
            remaining_names = tuple(name for name in group.names if name not in imported_names)
            assignment_sources = [group_sources[index % len(group_sources)] for index in range(len(remaining_names))]
            self._rng.shuffle(assignment_sources)
            assignments = tuple(
                TargetAssignment(group.group_key, target_name, source, scope_key)
                for target_name, source in zip(remaining_names, assignment_sources, strict=True)
            )
            plans.append(CrewGroupPlan(group=group, sources=group_sources, assignments=assignments))
        return tuple(plans)

    @staticmethod
    def build_copy_plan(
        group_plans: Iterable[CrewGroupPlan],
        selected_targets: Mapping[str, bool],
    ) -> CopyPlan:
        tasks: list[CopyTask] = []
        pre_skipped: list[CopyResult] = []
        first_task_for_target: dict[str, CopyTask] = {}

        for group_plan in group_plans:
            for assignment in group_plan.assignments:
                if not selected_targets.get(assignment.selection_key, True):
                    continue
                task = CopyTask(
                    group_base=assignment.group_base,
                    source_path=assignment.source.path,
                    target_path=assignment.output_path,
                    target_name=assignment.target_name,
                )
                normalized_target = os.path.normcase(os.path.abspath(os.fspath(task.target_path)))
                if os.path.normcase(os.path.abspath(os.fspath(task.source_path))) == normalized_target:
                    pre_skipped.append(
                        CopyResult(task, CopyResultStatus.SKIPPED, "目标路径与来源文件相同，已跳过。")
                    )
                    continue
                earlier = first_task_for_target.get(normalized_target)
                if earlier is not None:
                    pre_skipped.append(
                        CopyResult(
                            task,
                            CopyResultStatus.SKIPPED,
                            f"目标路径与 {earlier.source_path.name} 的任务重复，已跳过。",
                        )
                    )
                    continue
                first_task_for_target[normalized_target] = task
                tasks.append(task)
        return CopyPlan(tasks=tuple(tasks), pre_skipped=tuple(pre_skipped))
