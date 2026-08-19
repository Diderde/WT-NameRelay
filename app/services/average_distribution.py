from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.models.average_distribution import (
    ConflictKind,
    DistributionPlan,
    SourceCandidate,
    TargetBucket,
    TargetOperation,
)

from .matrix_group_planner import MatrixGroupPlanner


AUDIO_SUFFIX_PRIORITY = (".wav", ".flac", ".ogg", ".mp3", ".m4a", ".aac", ".opus")
_SUFFIX_ORDER = {suffix: index for index, suffix in enumerate(AUDIO_SUFFIX_PRIORITY)}


@dataclass(frozen=True, slots=True)
class NormalizedSources:
    candidates: tuple[SourceCandidate, ...]
    all_source_paths: frozenset[str]
    warnings: tuple[str, ...]


class SourceCandidateNormalizer:
    """Normalize paths in JSON order and fold only equal complete triples."""

    def __init__(self) -> None:
        self._hash_cache: dict[tuple[str, int, int], str] = {}

    def normalize(
        self,
        group_members: Sequence[str],
        source_paths: Iterable[Path],
    ) -> NormalizedSources:
        members = tuple(group_members)
        member_indexes = {name: index for index, name in enumerate(members)}
        unique_paths: dict[str, Path] = {}
        for raw_path in source_paths:
            path = Path(raw_path)
            normalized = self._normalize_path(path)
            unique_paths.setdefault(normalized, path)

        by_member: dict[str, list[Path]] = {}
        for path in unique_paths.values():
            if path.stem in member_indexes:
                by_member.setdefault(path.stem, []).append(path)

        warnings: list[str] = []
        selected_paths: list[Path] = []
        for member in members:
            choices = sorted(
                by_member.get(member, ()),
                key=lambda path: (
                    _SUFFIX_ORDER.get(path.suffix.casefold(), len(_SUFFIX_ORDER)),
                    path.name.casefold(),
                    self._normalize_path(path),
                ),
            )
            if not choices:
                continue
            selected_paths.append(choices[0])
            if len(choices) > 1:
                warnings.append(
                    f"{member} 存在多个音频格式，已选择 {choices[0].name}，忽略："
                    + "、".join(path.name for path in choices[1:])
                )

        raw_candidates: list[SourceCandidate] = []
        for path in selected_paths:
            member_index = member_indexes[path.stem]
            content_hash = self.hash_file(path)
            raw_candidates.append(
                SourceCandidate(
                    original_path=path,
                    canonical_basename=path.stem,
                    extension=path.suffix,
                    json_member_index=member_index,
                    original_bucket_index=member_index // 3,
                    member_index_in_bucket=member_index % 3,
                    content_hash=content_hash,
                    source_id=f"{member_index}:{content_hash}:{self._normalize_path(path)}",
                )
            )

        by_bucket: dict[int, list[SourceCandidate]] = {}
        for candidate in raw_candidates:
            by_bucket.setdefault(candidate.original_bucket_index, []).append(candidate)

        folded: list[SourceCandidate] = []
        for bucket_index in range((len(members) + 2) // 3):
            bucket_candidates = by_bucket.get(bucket_index, [])
            bucket_candidates.sort(key=lambda candidate: candidate.json_member_index)
            complete = (
                len(bucket_candidates) == 3
                and {candidate.member_index_in_bucket for candidate in bucket_candidates} == {0, 1, 2}
            )
            same_content = complete and len({candidate.content_hash for candidate in bucket_candidates}) == 1
            if same_content:
                representative = bucket_candidates[0]
                folded.append(
                    SourceCandidate(
                        original_path=representative.original_path,
                        canonical_basename=representative.canonical_basename,
                        extension=representative.extension,
                        json_member_index=representative.json_member_index,
                        original_bucket_index=representative.original_bucket_index,
                        member_index_in_bucket=representative.member_index_in_bucket,
                        content_hash=representative.content_hash,
                        source_id=f"bucket:{bucket_index}:{representative.content_hash}",
                    )
                )
            else:
                folded.extend(bucket_candidates)

        return NormalizedSources(
            tuple(folded),
            frozenset(unique_paths),
            tuple(warnings),
        )

    def hash_file(self, path: Path) -> str:
        stat = path.stat()
        normalized = self._normalize_path(path)
        key = (normalized, stat.st_size, stat.st_mtime_ns)
        cached = self._hash_cache.get(key)
        if cached is not None:
            return cached
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        value = digest.hexdigest()
        self._hash_cache[key] = value
        return value

    @staticmethod
    def _normalize_path(path: Path) -> str:
        return os.path.normcase(os.path.abspath(os.fspath(path)))


class AverageDistributionPlanner:
    """Build the one authoritative deterministic average-distribution plan."""

    def __init__(self, normalizer: SourceCandidateNormalizer | None = None) -> None:
        self._normalizer = normalizer or SourceCandidateNormalizer()
        self._matrix_planner = MatrixGroupPlanner()

    def build(
        self,
        *,
        module: str,
        category: str | None,
        group_id: str,
        group_display_name: str,
        group_members: Sequence[str],
        source_paths: Iterable[Path],
        target_directory: Path,
        owner_key_for_name: Callable[[str], str | None] | None = None,
    ) -> DistributionPlan:
        layout = self._matrix_planner.analyze(group_id, group_members, owner_key_for_name)
        if layout is None:
            raise ValueError("项目组不符合平均分配的三成员矩阵条件。")
        normalized = self._normalizer.normalize(layout.names, source_paths)
        if not normalized.candidates:
            raise ValueError("当前项目组没有可用的来源文件。")
        if len(normalized.candidates) > len(layout.subgroups):
            raise ValueError(
                f"独立来源数 {len(normalized.candidates)} 超过目标小组数 {len(layout.subgroups)}，"
                "无法无歧义地平均分配。"
            )

        assigned: dict[int, SourceCandidate] = {}
        displaced: list[SourceCandidate] = []
        for source in normalized.candidates:
            if source.original_bucket_index not in assigned:
                assigned[source.original_bucket_index] = source
            else:
                displaced.append(source)
        empty_indexes = [index for index in range(len(layout.subgroups)) if index not in assigned]
        for source, target_index in zip(displaced, empty_indexes, strict=False):
            assigned[target_index] = source
        for target_index in range(len(layout.subgroups)):
            if target_index not in assigned:
                assigned[target_index] = normalized.candidates[target_index % len(normalized.candidates)]

        buckets = tuple(TargetBucket(subgroup.index, subgroup.names) for subgroup in layout.subgroups)
        bucket_sources = tuple(assigned[index] for index in range(len(buckets)))
        operations: list[TargetOperation] = []
        for bucket, source in zip(buckets, bucket_sources, strict=True):
            for target_name in bucket.names:
                target_path = target_directory / f"{target_name}{source.extension}"
                normalized_target = SourceCandidateNormalizer._normalize_path(target_path)
                if normalized_target in normalized.all_source_paths:
                    conflict = ConflictKind.SOURCE_TARGET
                elif target_path.exists():
                    conflict = ConflictKind.EXTERNAL_CONFLICT
                else:
                    conflict = ConflictKind.GENERATED_TARGET
                operations.append(
                    TargetOperation(
                        module,
                        category,
                        group_id,
                        group_display_name,
                        source,
                        bucket.index,
                        target_name,
                        target_path,
                        conflict,
                    )
                )
        return DistributionPlan(
            module,
            category,
            group_id,
            group_display_name,
            tuple(layout.names),
            target_directory,
            normalized.candidates,
            buckets,
            bucket_sources,
            tuple(operations),
            normalized.all_source_paths,
            normalized.warnings,
        )


class RadioManualSourceAdapter:
    def __init__(self, planner: AverageDistributionPlanner | None = None) -> None:
        self._planner = planner or AverageDistributionPlanner()

    def build(self, group: object, source_paths: Iterable[Path], target_directory: Path, owner_lookup: Callable[[str], str | None]) -> DistributionPlan:
        return self._planner.build(
            module="radio",
            category=getattr(group, "category", None),
            group_id=getattr(group, "group_key"),
            group_display_name=getattr(group, "base_name"),
            group_members=getattr(group, "names"),
            source_paths=source_paths,
            target_directory=target_directory,
            owner_key_for_name=owner_lookup,
        )


class AudioProcessingSourceAdapter:
    def __init__(self, planner: AverageDistributionPlanner | None = None) -> None:
        self._planner = planner or AverageDistributionPlanner()

    def build(self, group: object, source_paths: Iterable[Path], target_directory: Path, owner_lookup: Callable[[str], str | None]) -> DistributionPlan:
        return self._planner.build(
            module=getattr(group, "module"),
            category=getattr(group, "category", None),
            group_id=getattr(group, "group_key"),
            group_display_name=getattr(group, "base_name"),
            group_members=getattr(group, "names"),
            source_paths=source_paths,
            target_directory=target_directory,
            owner_key_for_name=owner_lookup,
        )
