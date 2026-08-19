from __future__ import annotations

import json

from PySide6.QtCore import QFile, QIODevice

from app.resources import resources_rc as _resources_rc


class BankNameRepository:
    """Read-only access to the embedded Bank category/country library."""

    RESOURCE_PATH = ":/data/bank_name_groups.json"

    def __init__(self) -> None:
        resource = QFile(self.RESOURCE_PATH)
        if not resource.open(QIODevice.OpenModeFlag.ReadOnly):
            raise RuntimeError("无法读取内置 Bank 名称库。")
        try:
            payload = json.loads(bytes(resource.readAll()).decode("utf-8"))
        finally:
            resource.close()
        categories = payload.get("categories")
        if not isinstance(categories, dict):
            raise RuntimeError("内置 Bank 名称库格式无效。")
        self._categories: dict[str, dict[str, dict[str, object]]] = {
            category: entry.get("countries", {}) for category, entry in categories.items()
        }

    def countries(self, category: str) -> tuple[str, ...]:
        return tuple(sorted(self._categories.get(category, {})))

    def has_country(self, category: str, country: str) -> bool:
        return country in self._categories.get(category, {})

    def file_name(self, category: str, country: str, role: str) -> str:
        value = self._categories[category][country].get(role)
        if not isinstance(value, str) or not value:
            raise KeyError(f"未知 Bank 名称：{category}/{country}/{role}")
        return value

    def categories(self) -> tuple[str, ...]:
        return tuple(sorted(self._categories))
