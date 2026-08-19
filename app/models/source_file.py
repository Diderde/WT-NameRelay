from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class RecognitionState(str, Enum):
    """Recognition result shown for every imported source file."""

    RECOGNIZED = "recognized"
    NO_EXTENSION = "no_extension"
    UNKNOWN_NAME = "unknown_name"


@dataclass(frozen=True, slots=True)
class SourceFile:
    """An imported source file and its exact name-library recognition result."""

    path: Path
    normalized_path: str
    file_name: str
    stem: str
    suffix: str
    state: RecognitionState
    reason: str = ""
    group_base: str | None = None
    group_key: str | None = None

    @property
    def is_recognized(self) -> bool:
        return self.state is RecognitionState.RECOGNIZED
