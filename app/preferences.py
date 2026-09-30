# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""Shared access to the user preference file (config/settings.ini)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSettings

from app.paths import config_dir

_SETTINGS: QSettings | None = None


def _settings() -> QSettings:
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = QSettings(str(config_dir() / "settings.ini"), QSettings.IniFormat)
    return _SETTINGS


def get_preference(key: str, default: Any = None) -> Any:
    return _settings().value(key, default)


def set_preference(key: str, value: Any) -> None:
    _settings().setValue(key, value)
    _settings().sync()


def remove_preference(key: str) -> None:
    _settings().remove(key)
    _settings().sync()
