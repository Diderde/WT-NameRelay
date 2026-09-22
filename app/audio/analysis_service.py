# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""Per-clip loudness analysis (EBU R128) and spectrum image rendering."""
from __future__ import annotations

import re
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from .ffmpeg_service import _FLAGS, FfmpegLocator


def parse_ebur128_summary(stderr: str) -> dict | None:
    """从 ebur128 print_format=summary 的输出提取 integrated LUFS 与真峰值。"""
    index = stderr.find("Summary:")
    if index < 0:
        return None
    summary = stderr[index:]
    lufs = re.search(r"I:\s*(-?[\d.]+)\s*LUFS", summary)
    peak = re.search(r"Peak:\s*(-?[\d.]+)", summary)
    if lufs is None:
        return None
    return {
        "lufs": float(lufs.group(1)),
        "peak_dbfs": float(peak.group(1)) if peak is not None else None,
    }


class LoudnessScanWorker(QObject):
    """对若干片段裁切范围逐一测量 integrated LUFS 与真峰值。"""

    finished = Signal(object, str)  # list[dict] | None, error

    def __init__(
        self,
        items: tuple[tuple[str, str, Path, int, int], ...],
        cancel_event: threading.Event,
    ) -> None:
        super().__init__()
        # (clip_id, 显示名, source_path, trim_start_ms, trim_end_ms)
        self._items = items
        self._cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        results: list[dict] = []
        try:
            for clip_id, label, source, trim_start_ms, trim_end_ms in self._items:
                if self._cancel_event.is_set():
                    raise RuntimeError("任务已取消")
                process = subprocess.run(
                    [
                        str(FfmpegLocator.executable("ffmpeg")),
                        "-nostdin",
                        "-hide_banner",
                        "-i",
                        str(source),
                        "-af",
                        (
                            f"atrim=start={trim_start_ms / 1000:.3f}:end={trim_end_ms / 1000:.3f},"
                            f"asetpts=PTS-STARTPTS,ebur128=peak=true"
                        ),
                        "-f",
                        "null",
                        "NUL",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=_FLAGS,
                    timeout=180,
                )
                if self._cancel_event.is_set():
                    raise RuntimeError("任务已取消")
                summary = parse_ebur128_summary(process.stderr)
                if summary is None:
                    raise RuntimeError(f"响度分析失败：{label}")
                results.append(
                    {
                        "clip_id": clip_id,
                        "label": label,
                        "duration_ms": trim_end_ms - trim_start_ms,
                        "lufs": summary["lufs"],
                        "peak_dbfs": summary["peak_dbfs"],
                    }
                )
        except (subprocess.TimeoutExpired, RuntimeError, OSError) as error:
            self.finished.emit(None, str(error))
            return
        self.finished.emit(results, "")


class SpectrumWorker(QObject):
    """渲染一个片段裁切范围的频谱图 PNG。"""

    finished = Signal(object, str)  # Path | None, error

    def __init__(
        self,
        source: Path,
        trim_start_ms: int,
        trim_end_ms: int,
        target: Path,
        cancel_event: threading.Event,
    ) -> None:
        super().__init__()
        self._source = source
        self._trim_start_ms = trim_start_ms
        self._trim_end_ms = trim_end_ms
        self._target = target
        self._cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        try:
            process = subprocess.run(
                [
                    str(FfmpegLocator.executable("ffmpeg")),
                    "-nostdin",
                    "-hide_banner",
                    "-y",
                    "-i",
                    str(self._source),
                    "-lavfi",
                    (
                        f"atrim=start={self._trim_start_ms / 1000:.3f}:end={self._trim_end_ms / 1000:.3f},"
                        f"asetpts=PTS-STARTPTS,showspectrumpic=s=800x240:legend=disabled"
                    ),
                    "-frames:v",
                    "1",
                    str(self._target),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_FLAGS,
                timeout=180,
            )
        except (subprocess.TimeoutExpired, OSError) as error:
            self.finished.emit(None, str(error))
            return
        if self._cancel_event.is_set():
            self.finished.emit(None, "任务已取消")
            return
        if process.returncode != 0 or not self._target.is_file():
            self._target.unlink(missing_ok=True)
            self.finished.emit(None, "频谱图生成失败")
            return
        self.finished.emit(self._target, "")
