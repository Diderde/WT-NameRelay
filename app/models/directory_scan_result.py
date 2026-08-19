from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .source_file import SourceFile


class AutoScanState(str, Enum):
    NO_DIRECTORY = "no_directory"
    WAITING = "waiting"
    SCANNING = "scanning"
    SCAN_COMPLETE = "scan_complete"
    NO_RECOGNIZED_FILES = "no_recognized_files"
    ALL_COMPLETE = "all_complete"
    MISSING_FOUND = "missing_found"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ScannedDirectory:
    path: Path
    audio_files: tuple[Path, ...]
    recognized_sources: tuple[SourceFile, ...]

    @property
    def audio_count(self) -> int:
        return len(self.audio_files)


@dataclass(frozen=True, slots=True)
class DirectoryScanResult:
    root_path: Path
    include_subdirectories: bool
    directories: tuple[ScannedDirectory, ...]

    @property
    def audio_count(self) -> int:
        return sum(directory.audio_count for directory in self.directories)

    @property
    def recognized_count(self) -> int:
        return sum(len(directory.recognized_sources) for directory in self.directories)
