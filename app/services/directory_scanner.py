from __future__ import annotations

import os
import threading
from collections.abc import Iterable
from pathlib import Path

from app.models import DirectoryScanResult, ScannedDirectory

from .crew_name_parser import CrewNameParser

SUPPORTED_AUDIO_SUFFIXES = frozenset({".wav", ".flac", ".ogg", ".mp3", ".m4a", ".aac", ".opus"})


class ScanCancelled(RuntimeError):
    """Raised internally when a directory scan receives a cancellation request."""


class DirectoryScanner:
    """Enumerate supported audio files without crossing directory boundaries."""

    def __init__(self, parser: CrewNameParser) -> None:
        self._parser = parser

    def scan(
        self,
        root_path: Path,
        include_subdirectories: bool,
        cancel_event: threading.Event | None = None,
    ) -> DirectoryScanResult:
        root = Path(os.path.abspath(os.fspath(root_path)))
        if not root.is_dir():
            raise FileNotFoundError("目标目录不存在或不可访问。")
        directory_paths = self._directory_paths(root, include_subdirectories, cancel_event)
        scanned_directories: list[ScannedDirectory] = []
        for directory in directory_paths:
            self._check_cancelled(cancel_event)
            files = tuple(self._audio_files(directory, cancel_event))
            recognized = tuple(
                source for source in (self._parser.parse(path) for path in files) if source.is_recognized
            )
            scanned_directories.append(ScannedDirectory(directory, files, recognized))
        return DirectoryScanResult(root, include_subdirectories, tuple(scanned_directories))

    @staticmethod
    def _directory_paths(
        root: Path,
        include_subdirectories: bool,
        cancel_event: threading.Event | None,
    ) -> tuple[Path, ...]:
        if not include_subdirectories:
            return (root,)
        directories: list[Path] = []
        for current, child_directories, _files in os.walk(root, followlinks=False):
            if cancel_event is not None and cancel_event.is_set():
                raise ScanCancelled()
            child_directories[:] = sorted(
                directory
                for directory in child_directories
                if not Path(current, directory).is_symlink()
            )
            directories.append(Path(current))
        return tuple(sorted(directories, key=lambda path: os.path.normcase(os.fspath(path))))

    @staticmethod
    def _audio_files(directory: Path, cancel_event: threading.Event | None) -> Iterable[Path]:
        try:
            entries = sorted(directory.iterdir(), key=lambda path: path.name.casefold())
        except OSError:
            return ()
        files: list[Path] = []
        for path in entries:
            if cancel_event is not None and cancel_event.is_set():
                raise ScanCancelled()
            if path.is_file() and path.suffix.casefold() in SUPPORTED_AUDIO_SUFFIXES:
                files.append(path)
        return tuple(files)

    @staticmethod
    def _check_cancelled(cancel_event: threading.Event | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise ScanCancelled()
