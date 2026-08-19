from __future__ import annotations

import array
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from .ffmpeg_service import FfmpegLocator, _FLAGS
from .models import WaveformEnvelope


class WaveformCache:
    """Process-local cache keyed by path metadata; zoom never invokes FFmpeg."""

    _lock = threading.Lock()
    _values: dict[tuple[str, int, int], tuple[int, WaveformEnvelope]] = {}
    hits = 0
    misses = 0

    @classmethod
    def key(cls, path: Path) -> tuple[str, int, int]:
        stat = path.stat()
        return (str(path.resolve()).casefold(), stat.st_size, stat.st_mtime_ns)

    @classmethod
    def get(cls, path: Path) -> tuple[int, WaveformEnvelope] | None:
        key = cls.key(path)
        with cls._lock:
            value = cls._values.get(key)
            if value is not None:
                cls.hits += 1
            else:
                cls.misses += 1
            return value

    @classmethod
    def put(cls, path: Path, duration_ms: int, envelope: WaveformEnvelope) -> None:
        key = cls.key(path)
        with cls._lock:
            # Remove stale metadata variants for the same normalized path.
            for stale in [candidate for candidate in cls._values if candidate[0] == key[0] and candidate != key]:
                cls._values.pop(stale, None)
            cls._values[key] = (duration_ms, envelope)


def _aggregate(
    source: tuple[tuple[float, float], ...],
    factor: int = 4,
) -> tuple[tuple[float, float], ...]:
    return tuple(
        (
            min(value[0] for value in source[index : index + factor]),
            max(value[1] for value in source[index : index + factor]),
        )
        for index in range(0, len(source), factor)
    )


class WaveformWorker(QObject):
    """Probe duration and decode a reusable multi-level waveform off the UI thread."""

    finished = Signal(str, int, object, str)

    def __init__(self, clip_id: str, path: Path) -> None:
        super().__init__()
        self.clip_id = clip_id
        self.path = path

    @Slot()
    def run(self) -> None:
        try:
            cached = WaveformCache.get(self.path)
            if cached is not None:
                duration_ms, envelope = cached
                self.finished.emit(self.clip_id, duration_ms, envelope, "")
                return
            duration_ms = FfmpegLocator.probe_duration_ms(self.path)
            sample_rate = 8_000
            result = subprocess.run(
                [
                    str(FfmpegLocator.executable("ffmpeg")),
                    "-v",
                    "error",
                    "-i",
                    str(self.path),
                    "-f",
                    "s16le",
                    "-ac",
                    "1",
                    "-ar",
                    str(sample_rate),
                    "-",
                ],
                capture_output=True,
                creationflags=_FLAGS,
                check=True,
            )
            values = array.array("h")
            values.frombytes(result.stdout)
            if not values:
                raise ValueError("音频未解码出 PCM 数据")
            # Level zero is bounded but preserves enough detail for 1 px/ms.
            buckets = min(16_384, max(256, len(values) // 4))
            step = max(1, len(values) // buckets)
            base = tuple(
                (
                    min(values[index : index + step]) / 32768,
                    max(values[index : index + step]) / 32768,
                )
                for index in range(0, len(values), step)
            )
            levels = [base]
            while len(levels[-1]) > 64:
                levels.append(_aggregate(levels[-1]))
            envelope = WaveformEnvelope(tuple(levels), sample_rate, len(values))
            WaveformCache.put(self.path, duration_ms, envelope)
            self.finished.emit(self.clip_id, duration_ms, envelope, "")
        except Exception as error:
            self.finished.emit(self.clip_id, 0, None, str(error))
