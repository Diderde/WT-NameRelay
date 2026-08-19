from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Iterable, Mapping

from app.models import BankCountryAssignment, BankCountryGroup, BankFileRole, CopyPlan, CopyTask

from .bank_name_repository import BankNameRepository


class BankCopyTaskBuilder:
    """Create country-level assignments, then flatten them for the shared worker."""

    def __init__(self, repository: BankNameRepository, rng: random.Random | None = None) -> None:
        self._repository = repository
        self._rng = rng or random.SystemRandom()

    def build_assignments(self, groups: Iterable[BankCountryGroup]) -> tuple[BankCountryAssignment, ...]:
        all_groups = tuple(groups)
        by_category: dict[str, list[BankCountryGroup]] = defaultdict(list)
        for group in all_groups:
            by_category[group.category].append(group)
        assignments: list[BankCountryAssignment] = []
        for category, category_groups in by_category.items():
            sources = [group for group in category_groups if group.complete and self._repository.has_country(category, group.country)]
            if not sources:
                continue
            occupied_countries = {group.country for group in category_groups}
            targets = [country for country in self._repository.countries(category) if country not in occupied_countries]
            allocated = [sources[index % len(sources)] for index in range(len(targets))]
            self._rng.shuffle(allocated)
            for country, source in zip(targets, allocated, strict=True):
                assignments.append(BankCountryAssignment(
                    scope_key=str(source.directory).casefold(), category=category, country=country,
                    source=source, target_roles=(BankFileRole.ASSETS, BankFileRole.MAIN), target_directory=source.directory,
                ))
            # A partial imported/scanned target may safely receive its missing role
            # only when a complete source is available in that same directory.
            for group in category_groups:
                local_sources = [source for source in sources if source.directory == group.directory]
                if group.complete or group.ambiguous or not local_sources or not self._repository.has_country(category, group.country):
                    continue
                assignments.append(BankCountryAssignment(
                    scope_key=str(group.directory).casefold(), category=category, country=group.country,
                    source=self._rng.choice(local_sources), target_roles=group.missing_roles, target_directory=group.directory,
                ))
        return tuple(sorted(assignments, key=lambda item: (item.category, item.country, str(item.target_directory).casefold())))

    def build_copy_plan(self, assignments: Iterable[BankCountryAssignment], selected: Mapping[str, bool]) -> CopyPlan:
        tasks: list[CopyTask] = []
        for assignment in assignments:
            if not selected.get(assignment.selection_key, True):
                continue
            for role in assignment.target_roles:
                source = assignment.source.assets if role is BankFileRole.ASSETS else assignment.source.main
                assert source is not None
                name = self._repository.file_name(assignment.category, assignment.country, role.value)
                tasks.append(CopyTask(f"{assignment.category}/{assignment.country}", source.path, assignment.target_directory / name, name))
        return CopyPlan(tuple(tasks))
