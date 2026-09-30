# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""Silence detection for the audio timeline (background worker over ffmpeg)."""
from __future__ import annotations

import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from .ffmpeg_service import _FLAGS, FfmpegLocator


@dataclass(frozen=True, slots=True)
class SilenceInterval:
    """一段静音，时间为所属片段裁切范围内的相对毫秒。"""

    start_ms: int
    end_ms: int


def parse_silence_log(stderr: str) -> list[SilenceInterval]:
    """解析 silencedetect 的 stderr 行；时间为秒，转换为整数毫秒。"""
    starts = re.findall(r"silence_start:\s*([0-9.]+)", stderr)
    ends = re.findall(r"silence_end:\s*([0-9.]+)", stderr)
    intervals: list[SilenceInterval] = []
    for index, start in enumerate(starts):
        end = ends[index] if index < len(ends) else None
        if end is None:
            break
        intervals.append(SilenceInterval(int(float(start) * 1000), int(float(end) * 1000)))
    return intervals


class SilenceDetectWorker(QObject):
    """对若干片段裁切范围逐一执行 silencedetect，全部在后台线程完成。"""

    finished = Signal(object, str)  # list[dict]（含 clip_id 与区间），error

    def __init__(
        self,
        items: tuple[tuple[str, int, Path, int, int], ...],
        threshold_db: int,
        min_duration_ms: int,
        cancel_event: threading.Event,
    ) -> None:
        super().__init__()
        # (clip_id, 时间轴起点 ms, source_path, trim_start_ms, trim_end_ms)
        self._items = items
        self._threshold = 10 ** (threshold_db / 20)
        self._min_duration = max(0.05, min_duration_ms / 1000)
        self._cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        results: list[dict] = []
        try:
            for clip_id, timeline_start_ms, source, trim_start_ms, trim_end_ms in self._items:
                if self._cancel_event.is_set():
                    raise RuntimeError("任务已取消")
                command = [
                    str(FfmpegLocator.executable("ffmpeg")),
                    "-nostdin",
                    "-hide_banner",
                    "-i",
                    str(source),
                    "-af",
                    (
                        f"atrim=start={trim_start_ms / 1000:.3f}:end={trim_end_ms / 1000:.3f},"
                        f"asetpts=PTS-STARTPTS,"
                        f"silencedetect=noise={self._threshold:.6f}:d={self._min_duration:.3f}"
                    ),
                    "-f",
                    "null",
                    "NUL",
                ]
                process = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=_FLAGS,
                    timeout=120,
                )
                if self._cancel_event.is_set():
                    raise RuntimeError("任务已取消")
                if process.returncode != 0:
                    raise RuntimeError(f"静音检测失败：{source.name}")
                # silencedetect 报告的是 trim 段内相对时间；换算回时间轴绝对
                # 坐标（timeline_start + rel），供切分定位与界面显示直接使用。
                for interval in parse_silence_log(process.stderr):
                    results.append(
                        {
                            "clip_id": clip_id,
                            "start_ms": timeline_start_ms + interval.start_ms,
                            "end_ms": timeline_start_ms + interval.end_ms,
                        }
                    )
        except (subprocess.TimeoutExpired, RuntimeError, OSError) as error:
            self.finished.emit(None, str(error))
            return
        self.finished.emit(results, "")
