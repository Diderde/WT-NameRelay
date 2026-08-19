from __future__ import annotations

from collections import defaultdict

from app.models import BankCountryGroup, BankFile, BankFileRole


class BankPairMatcher:
    """Pair only files sharing the exact directory, category and country."""

    def group(self, files: list[BankFile] | tuple[BankFile, ...]) -> tuple[BankCountryGroup, ...]:
        buckets: dict[tuple[str, str, str], list[BankFile]] = defaultdict(list)
        for file in files:
            if file.valid:
                assert file.category is not None and file.country is not None
                buckets[(str(file.path.parent).casefold(), file.category, file.country)].append(file)
        groups: list[BankCountryGroup] = []
        for (_path, category, country), members in buckets.items():
            role_items: dict[BankFileRole, list[BankFile]] = defaultdict(list)
            for item in members:
                assert item.role is not None
                role_items[item.role].append(item)
            assets = role_items.get(BankFileRole.ASSETS, [])
            main = role_items.get(BankFileRole.MAIN, [])
            groups.append(BankCountryGroup(
                directory=members[0].path.parent, category=category, country=country,
                assets=assets[0] if len(assets) == 1 else None,
                main=main[0] if len(main) == 1 else None,
                ambiguous=len(assets) > 1 or len(main) > 1,
            ))
        return tuple(sorted(groups, key=lambda group: (str(group.directory).casefold(), group.category, group.country)))
