# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""Project-local storage locations anchored at the repository root.

Every writable artefact (logs, settings, temporary renders) stays inside the
project folder so the application leaves nothing in system directories.
"""

from __future__ import annotations

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _ensure(subdir: str) -> Path:
    path = PROJECT_ROOT / subdir
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    return _ensure("logs")


def config_dir() -> Path:
    return _ensure("config")


def temp_dir() -> Path:
    return _ensure("temp")
