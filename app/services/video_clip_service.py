# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""视频裁剪后端：剪辑模型纯逻辑 + ffmpeg 流复制落盘 + 说话人文件夹。

许可边界：落盘仅使用 LGPL 基线能力（解封装 / `-c copy` 流复制 / 封装），
不触碰任何 GPL 编解码器；裁切按关键帧对齐（流复制不做重编码），GUI 时间轴
上的裁剪点仍为精确值，落盘时刻对齐到不晚于起点的最近关键帧。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.audio.ffmpeg_service import FfmpegLocator

CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config"
CLIPS_ROOT = CONFIG_ROOT / "video_clips"
SPEAKER_FOLDER_NAMES = ("说话人A", "说话人B", "说话人C")
#: 说话人下的两种用途：训练素材（微调训练后再 TTS 生成成员组语音）与
#: 使用素材（直接导入作为成员组语音）。
PURPOSE_FOLDERS = ("训练素材", "使用素材")


@dataclass(frozen=True, slots=True)
class VideoAsset:
    """已导入的视频素材（探测结果）。"""

    path: Path
    duration_ms: int
    size_bytes: int


@dataclass(slots=True)
class ClipSegment:
    """时间轴上的一个保留片段（毫秒，闭开区间）。"""

    start_ms: int
    end_ms: int


class ClipTimelineModel:
    """纯逻辑剪辑模型：排序不重叠的保留片段 + 播放头 + 选中态。

    语义（与剪映对齐的阉割版）：
    - 向左裁剪 = 选中段起点推进到播放头（砍掉段内播放头左侧部分）；
    - 向右裁剪 = 选中段终点回缩到播放头；
    - 从中裁剪 = 选中段在播放头处一分为二；
    - 删除 = 移除选中段（该区间不再保留）。
    """

    def __init__(self, duration_ms: int) -> None:
        if duration_ms <= 0:
            raise ValueError("duration must be positive")
        self.duration_ms = duration_ms
        self.segments: list[ClipSegment] = [ClipSegment(0, duration_ms)]
        self.selected: int | None = None
        self.playhead_ms = 0

    # ---------------------------------------------------------------- selection

    def select_at(self, position_ms: int) -> bool:
        """选中包含该时刻的片段；无命中则维持现选中。返回是否命中。"""
        for index, segment in enumerate(self.segments):
            if segment.start_ms <= position_ms < segment.end_ms:
                self.selected = index
                return True
        return False

    def seek(self, position_ms: int) -> None:
        self.playhead_ms = max(0, min(self.duration_ms, position_ms))

    @property
    def selected_segment(self) -> ClipSegment | None:
        if self.selected is None or not (0 <= self.selected < len(self.segments)):
            return None
        return self.segments[self.selected]

    # ---------------------------------------------------------------- operations

    def trim_left(self) -> bool:
        segment = self.selected_segment
        if segment is None or not (
            segment.start_ms < self.playhead_ms < segment.end_ms
        ):
            return False
        segment.start_ms = self.playhead_ms
        return True

    def trim_right(self) -> bool:
        segment = self.selected_segment
        if segment is None or not (
            segment.start_ms < self.playhead_ms < segment.end_ms
        ):
            return False
        segment.end_ms = self.playhead_ms
        return True

    def split_at(self) -> bool:
        segment = self.selected_segment
        if segment is None or not (
            segment.start_ms < self.playhead_ms < segment.end_ms
        ):
            return False
        index = self.selected
        right = ClipSegment(self.playhead_ms, segment.end_ms)
        segment.end_ms = self.playhead_ms
        self.segments.insert(index + 1, right)
        return True

    def delete_selected(self) -> bool:
        if self.selected is None or not self.segments:
            return False
        index = min(self.selected, len(self.segments) - 1)
        self.segments.pop(index)
        if not self.segments:
            self.selected = None
        else:
            self.selected = min(index, len(self.segments) - 1)
        return True

    def segment_at(self, position_ms: int) -> int | None:
        for index, segment in enumerate(self.segments):
            if segment.start_ms <= position_ms < segment.end_ms:
                return index
        return None


def probe_video(path: Path) -> VideoAsset:
    """ffprobe 探测时长与大小（失败抛异常，不静默降级）。"""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"video not found: {source}")
    result = subprocess.run(
        [
            str(FfmpegLocator.executable("ffprobe")),
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(source),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, check=False)
    if result.returncode != 0:
        raise ValueError(f"ffprobe failed for {source}: {result.stderr.strip()[-300:]}")
    info = json.loads(result.stdout or "{}")
    duration_s = float(info.get("format", {}).get("duration") or 0.0)
    if duration_s <= 0.0:
        raise ValueError(f"no duration probed for {source}")
    return VideoAsset(
        path=source,
        duration_ms=round(duration_s * 1000),
        size_bytes=source.stat().st_size,
    )


def default_clips_root() -> Path:
    return CLIPS_ROOT


def ensure_speaker_folders(root: Path | None = None) -> list[Path]:
    """自动创建说话人文件夹及其用途子文件夹（幂等）。

    结构 = `<root>/说话人X/{训练素材, 使用素材}`；返回说话人根目录列表。
    """
    base = Path(root) if root is not None else CLIPS_ROOT
    base.mkdir(parents=True, exist_ok=True)
    speakers = []
    for name in SPEAKER_FOLDER_NAMES:
        speaker = base / name
        for purpose in PURPOSE_FOLDERS:
            (speaker / purpose).mkdir(parents=True, exist_ok=True)
        speakers.append(speaker)
    return speakers


def make_thumbnail(source: Path, out_dir: Path, *, width: int = 160) -> Path:
    """抽取一帧缩略图（解码 + scale + png，均为 LGPL 基线能力），带缓存。"""
    src = Path(source)
    if not src.is_file():
        raise FileNotFoundError(f"source not found: {src}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(str(src).encode("utf-8")).hexdigest()[:16]
    target = out_dir / f"{key}.png"
    if target.is_file() and target.stat().st_size > 0:
        return target
    result = subprocess.run(
        [
            str(FfmpegLocator.executable("ffmpeg")),
            "-hide_banner", "-loglevel", "error",
            "-ss", "0.5", "-i", str(src),
            "-frames:v", "1", "-vf", f"scale={width}:-1",
            "-y", str(target),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120, check=False,
    )
    if result.returncode != 0 or not target.is_file():
        raise RuntimeError(f"thumbnail failed: {result.stderr.strip()[-300:]}")
    return target


def cut_segment(
    source: Path,
    start_ms: int,
    end_ms: int,
    destination: Path,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """`-c copy` 流复制落盘一个片段（关键帧对齐），进度经 on_progress(0..1)。"""
    src = Path(source)
    dst = Path(destination)
    if not src.is_file():
        raise FileNotFoundError(f"source not found: {src}")
    if not 0 <= start_ms < end_ms:
        raise ValueError(f"invalid segment: {start_ms}..{end_ms}")
    duration_s = (end_ms - start_ms) / 1000.0
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    process = subprocess.Popen(
        [
            str(FfmpegLocator.executable("ffmpeg")),
            "-hide_banner", "-loglevel", "error", "-nostats",
            "-ss", f"{start_ms / 1000.0:.3f}",
            "-i", str(src),
            "-t", f"{duration_s:.3f}",
            "-c", "copy", "-map", "0",
            "-progress", "pipe:1",
            "-y", str(dst),
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    try:
        assert process.stdout is not None
        for line in process.stdout:
            if on_progress is not None and line.startswith("out_time_us="):
                try:
                    done_us = int(line.split("=", 1)[1].strip())
                except ValueError:
                    continue
                on_progress(max(0.0, min(1.0, done_us / 1_000_000.0 / duration_s)))
        _, stderr = process.communicate(timeout=600)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        raise RuntimeError(f"cut timed out: {src}") from exc
    if process.returncode != 0:
        raise RuntimeError(
            f"cut failed (exit {process.returncode}): {stderr.strip()[-400:]}")
    if not dst.is_file() or dst.stat().st_size == 0:
        raise RuntimeError(f"cut produced no output: {dst}")
    if on_progress is not None:
        on_progress(1.0)
    return dst
