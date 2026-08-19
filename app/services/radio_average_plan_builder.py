from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.models import (
    CopyResult,
    CopyResultStatus,
    ManualCopyMode,
    RadioManualGroupPlan,
    RadioSourceUnit,
    RadioStagedCopyPlan,
    RadioTargetAssignment,
    RadioTargetConflictKind,
    RadioTargetOperation,
    RadioTargetTriple,
    SourceFile,
)

from .average_distribution import (
    AverageDistributionPlanner,
    RadioManualSourceAdapter,
    SourceCandidateNormalizer,
)
from .copy_task_builder import CopyTaskBuilder
from .crew_name_repository import CrewNameRepository
from .matrix_group_planner import MatrixGroupPlanner


@dataclass(frozen=True, slots=True)
class RadioImportLimitViolation:
    group_key: str
    group_name: str
    directory: Path
    member_count: int
    maximum: int
    actual: int


class RadioAveragePlanBuilder:
    """Radio-page adapter over the shared average-distribution planner."""

    def __init__(self, repository: CrewNameRepository, sequential_builder: CopyTaskBuilder) -> None:
        self._repository = repository
        self._sequential_builder = sequential_builder
        self._matrix_planner = MatrixGroupPlanner()
        self._source_normalizer = SourceCandidateNormalizer()
        self._distribution_planner = AverageDistributionPlanner(self._source_normalizer)
        self._source_adapter = RadioManualSourceAdapter(self._distribution_planner)

    def matrix_layout(self, group_key: str):
        group = self._repository.get_by_key(group_key)
        if group is None:
            return None
        return self._matrix_planner.analyze(
            group.group_key,
            group.names,
            lambda name: (
                owner.group_key if (owner := self._repository.lookup(name)) is not None else None
            ),
        )

    def is_average_eligible(self, group_key: str) -> bool:
        return self.matrix_layout(group_key) is not None

    def maximum_sources(self, group_key: str) -> int | None:
        layout = self.matrix_layout(group_key)
        return len(layout.subgroups) if layout is not None else None

    def limit_violations(self, sources: Iterable[SourceFile]) -> tuple[RadioImportLimitViolation, ...]:
        units: dict[tuple[str, str], list[SourceFile]] = {}
        for source in sources:
            if not source.is_recognized or source.group_key is None:
                continue
            maximum = self.maximum_sources(source.group_key)
            if maximum is None:
                continue
            units.setdefault(
                (source.group_key, self._scope_key(source.path.parent)), []
            ).append(source)

        violations: list[RadioImportLimitViolation] = []
        for (group_key, _scope), unit_sources in units.items():
            group = self._repository.get_by_key(group_key)
            maximum = self.maximum_sources(group_key)
            if group is None or maximum is None:
                continue
            actual = len(
                self._source_normalizer.normalize(
                    group.names, (source.path for source in unit_sources)
                ).candidates
            )
            if actual > maximum:
                violations.append(
                    RadioImportLimitViolation(
                        group_key,
                        group.base_name,
                        unit_sources[0].path.parent,
                        len(group.names),
                        maximum,
                        actual,
                    )
                )
        return tuple(violations)

    def build_group_plans(
        self,
        sources: Iterable[SourceFile],
        import_order: Sequence[str],
    ) -> tuple[RadioManualGroupPlan, ...]:
        del import_order  # Average mapping is intentionally independent of picker order.
        unique = {source.normalized_path: source for source in sources}
        units: dict[tuple[str, str], list[SourceFile]] = {}
        for source in unique.values():
            if not source.is_recognized or source.group_key is None:
                continue
            key = (source.group_key, self._scope_key(source.path.parent))
            units.setdefault(key, []).append(source)

        plans: list[RadioManualGroupPlan] = []
        for (group_key, scope_key), unit_sources in units.items():
            group = self._repository.get_by_key(group_key)
            if group is None:
                continue
            indexes = {name: index for index, name in enumerate(group.names)}
            unit_sources.sort(
                key=lambda source: (indexes.get(source.stem, len(group.names)), source.normalized_path)
            )
            unit = RadioSourceUnit(group, unit_sources[0].path.parent, scope_key, tuple(unit_sources))
            if self.is_average_eligible(group_key):
                plans.append(self._build_average_unit(unit))
            else:
                plans.append(self._build_fallback_unit(unit))
        return tuple(plans)

    def build_staged_copy_plan(
        self,
        group_plans: Iterable[RadioManualGroupPlan],
        selected_targets: Mapping[str, bool],
    ) -> RadioStagedCopyPlan:
        frozen_group_plans = tuple(group_plans)
        imported_source_paths = frozenset(
            source.normalized_path
            for group_plan in frozen_group_plans
            for source in group_plan.sources
        )
        operations: list[RadioTargetOperation] = []
        pre_skipped: list[CopyResult] = []
        targets: dict[str, RadioTargetOperation] = {}
        for plan in frozen_group_plans:
            common_by_target = (
                {operation.target_member_name: operation for operation in plan.distribution_plan.operations}
                if plan.distribution_plan is not None
                else {}
            )
            for assignment in plan.assignments:
                if not selected_targets.get(assignment.selection_key, True):
                    continue
                common = common_by_target.get(assignment.target_name)
                operation = RadioTargetOperation(
                    module="radio",
                    group_id=assignment.group_id,
                    group_display_name=assignment.group_display_name,
                    source_original_path=assignment.source.path,
                    source_snapshot_key=(
                        common.source.source_id if common is not None else assignment.source.normalized_path
                    ),
                    source_member_name=assignment.source.stem,
                    target_member_name=assignment.target_name,
                    target_path=assignment.output_path,
                    copy_mode=assignment.copy_mode,
                    will_overwrite=assignment.output_path.exists(),
                    # Revalidate filesystem conflicts without changing the frozen mapping.
                    conflict_kind=self._classify_target(
                        assignment.output_path, imported_source_paths
                    ),
                    source_content_hash=common.source.content_hash if common is not None else "",
                )
                normalized_target = self._normalize_path(operation.target_path)
                earlier = targets.get(normalized_target)
                if earlier is not None:
                    pre_skipped.append(
                        CopyResult(
                            operation.task,
                            CopyResultStatus.SKIPPED,
                            f"目标路径与 {earlier.source_original_path.name} 的任务重复，已跳过。",
                        )
                    )
                    continue
                targets[normalized_target] = operation
                operations.append(operation)
        return RadioStagedCopyPlan(tuple(operations), tuple(pre_skipped), imported_source_paths)

    def _build_average_unit(self, unit: RadioSourceUnit) -> RadioManualGroupPlan:
        distribution = self._source_adapter.build(
            unit.group,
            (source.path for source in unit.sources),
            unit.directory,
            lambda name: (
                owner.group_key if (owner := self._repository.lookup(name)) is not None else None
            ),
        )
        source_by_path = {source.normalized_path: source for source in unit.sources}
        target_triples: list[RadioTargetTriple] = []
        assignments: list[RadioTargetAssignment] = []
        for bucket, common_source in zip(distribution.buckets, distribution.bucket_sources, strict=True):
            source = source_by_path[common_source.normalized_path]
            target_triples.append(RadioTargetTriple(bucket.index, bucket.names, source))
            for operation in distribution.operations:
                if operation.target_bucket_index != bucket.index:
                    continue
                assignments.append(
                    RadioTargetAssignment(
                        unit.group.group_key,
                        unit.group.base_name,
                        source,
                        operation.target_member_name,
                        unit.directory,
                        unit.scope_key,
                        ManualCopyMode.AVERAGE,
                        bucket.index,
                        operation.will_overwrite,
                        operation.conflict_kind,
                    )
                )
        return RadioManualGroupPlan(
            unit.group,
            unit.directory,
            unit.sources,
            tuple(assignments),
            ManualCopyMode.AVERAGE,
            tuple(target_triples),
            distribution_plan=distribution,
        )

    def _build_fallback_unit(self, unit: RadioSourceUnit) -> RadioManualGroupPlan:
        sequential = self._sequential_builder.build_group_plans(unit.sources, unit.scope_key)
        assignments: list[RadioTargetAssignment] = []
        imported_source_paths = frozenset(source.normalized_path for source in unit.sources)
        if sequential:
            for assignment in sequential[0].assignments:
                target_path = assignment.output_path
                assignments.append(
                    RadioTargetAssignment(
                        unit.group.group_key,
                        unit.group.base_name,
                        assignment.source,
                        assignment.target_name,
                        assignment.source.path.parent,
                        unit.scope_key,
                        ManualCopyMode.SEQUENTIAL,
                        -1,
                        target_path.exists(),
                        self._classify_target(target_path, imported_source_paths),
                    )
                )
        return RadioManualGroupPlan(
            unit.group,
            unit.directory,
            unit.sources,
            tuple(assignments),
            ManualCopyMode.SEQUENTIAL,
            fallback_reason="成员数量或分组结构不符合每组三项的平均分配条件。",
        )

    @staticmethod
    def _scope_key(directory: Path) -> str:
        return RadioAveragePlanBuilder._normalize_path(directory)

    @staticmethod
    def _normalize_path(path: Path) -> str:
        return os.path.normcase(os.path.abspath(os.fspath(path)))

    @staticmethod
    def _classify_target(
        target_path: Path,
        imported_source_paths: frozenset[str],
    ) -> RadioTargetConflictKind:
        normalized = RadioAveragePlanBuilder._normalize_path(target_path)
        if normalized in imported_source_paths:
            return RadioTargetConflictKind.SOURCE_TARGET
        if target_path.exists():
            return RadioTargetConflictKind.EXTERNAL_CONFLICT
        return RadioTargetConflictKind.GENERATED_TARGET
