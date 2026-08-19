from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MatrixSubgroup:
    """One ordered three-member target unit from a name-library group."""

    index: int
    names: tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class MatrixGroupLayout:
    """Validated, immutable matrix layout shared by copy and audio workflows."""

    group_key: str
    names: tuple[str, ...]
    subgroups: tuple[MatrixSubgroup, ...]

    def subgroup_for(self, member_name: str) -> MatrixSubgroup | None:
        for subgroup in self.subgroups:
            if member_name in subgroup.names:
                return subgroup
        return None

    def cyclic_sources(
        self,
        source_indexes: Sequence[int],
        target_indexes: Iterable[int],
    ) -> tuple[tuple[int, int], ...]:
        """Map ordered targets to ordered sources without random state."""

        if not source_indexes:
            return ()
        return tuple(
            (target_index, source_indexes[offset % len(source_indexes)])
            for offset, target_index in enumerate(target_indexes)
        )


class MatrixGroupPlanner:
    """Validate and split JSON-ordered names into deterministic triples."""

    @staticmethod
    def analyze(
        group_key: str,
        names: Sequence[str],
        owner_key_for_name: Callable[[str], str | None] | None = None,
    ) -> MatrixGroupLayout | None:
        ordered = tuple(names)
        if len(ordered) < 9 or len(ordered) % 3:
            return None
        if len(set(ordered)) != len(ordered):
            return None
        if owner_key_for_name is not None and any(
            owner_key_for_name(name) != group_key for name in ordered
        ):
            return None
        subgroups = tuple(
            MatrixSubgroup(index // 3, (ordered[index], ordered[index + 1], ordered[index + 2]))
            for index in range(0, len(ordered), 3)
        )
        return MatrixGroupLayout(group_key, ordered, subgroups)
