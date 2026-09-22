from __future__ import annotations

import json
from typing import Final

from PySide6.QtCore import QFile, QIODevice

from app.models import CrewGroupType, CrewNameGroup

# 副作用导入：注册内嵌名称库等 Qt 资源（:/data/...），不直接引用其符号。
from app.resources import resources_rc as _resources_rc  # noqa: F401

RESOURCE_PATH: Final = ":/data/crew_name_groups.json"


class CrewNameRepository:
    """Read-only, exact-match access to an embedded module name library."""

    def __init__(self, resource_path: str = RESOURCE_PATH) -> None:
        self.resource_path = resource_path
        self._groups_by_key, self._groups_by_name = self._load(resource_path)

    def lookup(self, stem: str) -> CrewNameGroup | None:
        """Return the group containing *stem*, without case folding or guessing."""
        return self._groups_by_name.get(stem)

    def groups(self) -> tuple[CrewNameGroup, ...]:
        return tuple(self._groups_by_key.values())

    def get_by_key(self, group_key: str) -> CrewNameGroup | None:
        return self._groups_by_key.get(group_key)

    @staticmethod
    def _load(resource_path: str) -> tuple[dict[str, CrewNameGroup], dict[str, CrewNameGroup]]:
        resource = QFile(resource_path)
        if not resource.open(QIODevice.OpenModeFlag.ReadOnly):
            raise RuntimeError(f"无法读取内置名称库：{resource_path}")
        try:
            payload = json.loads(bytes(resource.readAll()).decode("utf-8"))
        finally:
            resource.close()

        raw_groups = payload.get("groups") if isinstance(payload, dict) and "groups" in payload else payload
        if not isinstance(raw_groups, dict):
            raise RuntimeError("内置名称库根对象无效")  # noqa: TRY004  # 资源数据格式无效，非参数类型错误
        groups_by_key: dict[str, CrewNameGroup] = {}
        groups_by_name: dict[str, CrewNameGroup] = {}
        for group_key, entry in raw_groups.items():
            try:
                group_type = CrewGroupType(entry["type"])
                names = tuple(entry["names"])
            except (KeyError, TypeError, ValueError) as error:
                raise RuntimeError(f"内置名称库格式无效：{group_key}") from error
            base_name = entry.get("base_name", group_key)
            if not isinstance(base_name, str) or not base_name:
                raise RuntimeError(f"内置名称库基础名称无效：{group_key}")
            group = CrewNameGroup(
                group_key=group_key,
                base_name=base_name,
                group_type=group_type,
                names=names,
            )
            groups_by_key[group_key] = group
            for name in names:
                if name in groups_by_name:
                    raise RuntimeError(f"内置名称库包含重复名称：{name}")
                groups_by_name[name] = group
        return groups_by_key, groups_by_name
