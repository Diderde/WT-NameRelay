from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ConflictKind(str, Enum):
    """Relationship between an average-distribution target and its sources."""

    SOURCE_TARGET = "source_target"
    GENERATED_TARGET = "generated_target"
    EXTERNAL_CONFLICT = "external_conflict"


@dataclass(frozen=True, slots=True)
class SourceCandidate:
    """One stable, content-identified audio source."""

    original_path: Path
    canonical_basename: str
    extension: str
    json_member_index: int
    original_bucket_index: int
    member_index_in_bucket: int
    content_hash: str
    source_id: str

    @property
    def normalized_path(self) -> str:
        return os.path.normcase(os.path.abspath(os.fspath(self.original_path)))


@dataclass(frozen=True, slots=True)
class TargetBucket:
    index: int
    names: tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class TargetOperation:
    module: str
    category: str | None
    group_id: str
    group_display_name: str
    source: SourceCandidate
    target_bucket_index: int
    target_member_name: str
    target_path: Path
    conflict_kind: ConflictKind

    @property
    def will_overwrite(self) -> bool:
        return self.target_path.exists()


@dataclass(frozen=True, slots=True)
class DistributionPlan:
    """Immutable mapping shared by radio manual-copy and audio processing."""

    module: str
    category: str | None
    group_id: str
    group_display_name: str
    group_members: tuple[str, ...]
    target_directory: Path
    sources: tuple[SourceCandidate, ...]
    buckets: tuple[TargetBucket, ...]
    bucket_sources: tuple[SourceCandidate, ...]
    operations: tuple[TargetOperation, ...]
    all_source_paths: frozenset[str]
    warnings: tuple[str, ...] = ()

    @property
    def final_pattern(self) -> str:
        source_numbers = {source.source_id: index + 1 for index, source in enumerate(self.sources)}
        return "".join(
            str(source_numbers[source.source_id]) * len(self.buckets[index].names)
            for index, source in enumerate(self.bucket_sources)
        )

    @property
    def source_target_count(self) -> int:
        return sum(op.conflict_kind is ConflictKind.SOURCE_TARGET for op in self.operations)

    @property
    def generated_count(self) -> int:
        return sum(op.conflict_kind is ConflictKind.GENERATED_TARGET for op in self.operations)

    @property
    def external_conflict_count(self) -> int:
        return sum(op.conflict_kind is ConflictKind.EXTERNAL_CONFLICT for op in self.operations)
