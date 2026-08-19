from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class BankFileRole(str, Enum):
    ASSETS = "assets"
    MAIN = "main"


@dataclass(frozen=True, slots=True)
class BankFile:
    path: Path
    category: str | None = None
    country: str | None = None
    role: BankFileRole | None = None
    reason: str = ""

    @property
    def normalized_path(self) -> str:
        return os.path.normcase(os.path.abspath(os.fspath(self.path)))

    @property
    def valid(self) -> bool:
        return self.category is not None and self.country is not None and self.role is not None


@dataclass(frozen=True, slots=True)
class BankCountryGroup:
    directory: Path
    category: str
    country: str
    assets: BankFile | None
    main: BankFile | None
    ambiguous: bool = False

    @property
    def complete(self) -> bool:
        return not self.ambiguous and self.assets is not None and self.main is not None

    @property
    def missing_roles(self) -> tuple[BankFileRole, ...]:
        return tuple(role for role, item in ((BankFileRole.ASSETS, self.assets), (BankFileRole.MAIN, self.main)) if item is None)


@dataclass(frozen=True, slots=True)
class BankCountryAssignment:
    scope_key: str
    category: str
    country: str
    source: BankCountryGroup
    target_roles: tuple[BankFileRole, ...]
    target_directory: Path

    @property
    def selection_key(self) -> str:
        return f"{self.scope_key}\x00{self.category}\x00{self.country}"
