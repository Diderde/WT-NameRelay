from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QFile, QIODevice

from app.services.directory_scanner import SUPPORTED_AUDIO_SUFFIXES
from app.models import CrewGroupType


CREW_CATEGORIES = ("artillery", "aviation", "chief_m", "commander", "driver", "gunner", "loader")
RADIO_CATEGORIES = ("additional_01", "\u6001\u52bf\u64ad\u62a5", "\u4fe1\u606f")
PROJECT_AUDIO_SUFFIX_ORDER = (".wav", ".flac", ".ogg", ".mp3", ".m4a", ".aac", ".opus")


@dataclass(frozen=True, slots=True)
class ProjectGroup:
    group_key: str
    base_name: str
    group_type: CrewGroupType
    module: str
    category: str | None
    names: tuple[str, ...]


class ProjectGroupRepository:
    """Read-only exact lookup over the two existing embedded name libraries."""

    def __init__(self) -> None:
        self._by_name: dict[str, ProjectGroup] = {}
        for resource, default_module in (
            (":/data/crew_name_groups.json", "crew"),
            (":/data/radio_name_groups.json", "radio"),
        ):
            file = QFile(resource)
            if not file.open(QIODevice.OpenModeFlag.ReadOnly):
                raise RuntimeError(f"Unable to load {resource}")
            try:
                payload = json.loads(bytes(file.readAll()).decode("utf-8"))
            finally:
                file.close()
            groups = payload.get("groups", payload)
            for key, entry in groups.items():
                group = ProjectGroup(
                    group_key=key,
                    base_name=entry.get("base_name", key),
                    group_type=CrewGroupType(entry["type"]),
                    module=entry.get("module", default_module),
                    category=entry.get("category"),
                    names=tuple(entry["names"]),
                )
                for name in group.names:
                    self._by_name[name] = group

    def lookup(self, name: str) -> ProjectGroup | None:
        return self._by_name.get(name)


class AudioProjectService:
    def ensure_layout(self, root: Path) -> None:
        for module, categories in (("\u8f66\u7ec4", CREW_CATEGORIES), ("\u65e0\u7ebf\u7535", RADIO_CATEGORIES)):
            for category in categories:
                (root / module / category).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def directory(root: Path, module: str, category: str) -> Path:
        return root / ("\u8f66\u7ec4" if module == "crew" else "\u65e0\u7ebf\u7535") / category

    def group_progress(self, directory: Path, group: ProjectGroup) -> tuple[set[str], dict[str, list[Path]]]:
        found: dict[str, list[Path]] = {}
        if directory.is_dir():
            for path in directory.iterdir():
                if path.is_file() and path.suffix.casefold() in SUPPORTED_AUDIO_SUFFIXES:
                    found.setdefault(path.stem, []).append(path)
        suffix_order = {suffix: index for index, suffix in enumerate(PROJECT_AUDIO_SUFFIX_ORDER)}
        for paths in found.values():
            paths.sort(key=lambda path: (suffix_order.get(path.suffix.casefold(), 999), path.name.casefold()))
        return set(group.names) & set(found), found

    @staticmethod
    def parse_target(raw: str) -> str:
        candidate = Path(raw.strip()).name
        suffix = Path(candidate).suffix.casefold()
        return Path(candidate).stem if suffix in SUPPORTED_AUDIO_SUFFIXES else candidate

    @staticmethod
    def valid_filename(name: str) -> bool:
        return bool(name) and not any(char in name for char in '<>:"/\\|?*') and name not in {".", ".."}
