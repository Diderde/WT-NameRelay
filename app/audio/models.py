from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from uuid import uuid4


def seconds_to_ms(value: float) -> int:
    return max(0, round(value * 1000))


def format_ms(value: int) -> str:
    minutes, remainder = divmod(max(0, value), 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


@dataclass(frozen=True, slots=True)
class WaveformEnvelope:
    """Immutable multi-resolution min/max envelope."""

    levels: tuple[tuple[tuple[float, float], ...], ...]
    sample_rate: int
    sample_count: int

    def level_for_width(self, pixel_width: int) -> tuple[tuple[float, float], ...]:
        if not self.levels:
            return ()
        target = max(1, pixel_width * 2)
        for level in self.levels:
            if len(level) <= target:
                return level
        return self.levels[-1]


@dataclass(frozen=True, slots=True)
class AudioClip:
    clip_id: str
    source_path: Path
    source_duration_ms: int
    trim_start_ms: int = 0
    trim_end_ms: int | None = None
    waveform: WaveformEnvelope | None = None

    @property
    def effective_end_ms(self) -> int:
        return self.source_duration_ms if self.trim_end_ms is None else self.trim_end_ms

    @property
    def duration_ms(self) -> int:
        return max(1, self.effective_end_ms - self.trim_start_ms)

    @property
    def duration(self) -> float:
        return self.duration_ms / 1000

    @property
    def trim_start(self) -> float:
        return self.trim_start_ms / 1000

    @property
    def trim_end(self) -> float:
        return self.effective_end_ms / 1000

    @classmethod
    def create(cls, path: Path, duration: float) -> AudioClip:
        duration_ms = max(1, seconds_to_ms(duration))
        return cls(uuid4().hex, path, duration_ms, 0, duration_ms)


@dataclass(frozen=True, slots=True)
class BlankClip:
    clip_id: str
    duration_ms: int = 2000

    @property
    def duration(self) -> float:
        return self.duration_ms / 1000

    @classmethod
    def create(cls, duration: float = 2.0) -> BlankClip:
        return cls(uuid4().hex, max(1, seconds_to_ms(duration)))


TimelineItem = AudioClip | BlankClip


class TimelineClipKind(str, Enum):
    AUDIO = "audio"
    BLANK = "blank"


class TimelineEditKind(str, Enum):
    GENERIC = "generic"
    SPLIT = "split"


@dataclass(frozen=True, slots=True)
class TimelineClipSnapshot:
    clip_id: str
    kind: TimelineClipKind
    source_path: Path | None
    source_start_ms: int
    source_end_ms: int
    duration_ms: int


@dataclass(frozen=True, slots=True)
class TimelineSnapshot:
    clips: tuple[TimelineClipSnapshot, ...]
    total_duration_ms: int
    version: int
    sample_rate: int = 48000
    channels: int = 1


@dataclass(frozen=True, slots=True)
class TimelineLocation:
    clip_id: str
    index: int
    kind: TimelineClipKind
    timeline_start_ms: int
    offset_ms: int
    source_ms: int | None


@dataclass(frozen=True, slots=True)
class TimelineSplitResult:
    original_clip_id: str
    left_clip_id: str
    right_clip_id: str
    timeline_position_ms: int
    source_position_ms: int


@dataclass(frozen=True, slots=True)
class TimelineUndoResult:
    kind: TimelineEditKind
    split: TimelineSplitResult | None = None


@dataclass(frozen=True, slots=True)
class _TimelineHistoryEntry:
    items: tuple[TimelineItem, ...]
    kind: TimelineEditKind = TimelineEditKind.GENERIC
    split: TimelineSplitResult | None = None


@dataclass(frozen=True, slots=True)
class ExportSettings:
    sample_rate: int = 48000
    channels: int = 1
    bit_depth: str = "16-bit PCM"
    normalize_mode: str | None = None  # peak | loudness | speech | None
    normalize_target: float = -1.0
    keep_timeline: bool = False
    worker_threads: int = 1
    output_format: str = "wav"  # wav | mp3 | flac | opus | m4a
    quality: str = ""  # 有损码率（mp3/opus/m4a）或 flac 压缩级；WAV 忽略
    fade_ms: int = 0  # 每个音频片段首尾淡入淡出
    trim_silence: str = "off"  # off | edges（去除拼接后首尾静音）
    denoise: str = "off"  # off | afftdn | anlmdn
    denoise_strength: int = 12  # afftdn 的 nr 参数（dB）
    declick: bool = False
    deesser: bool = False
    voice_preset: str = "off"  # off | low_cut | voice | broadcast
    gain_db: float = 0.0  # 整体音量增益，在归一化之后追加


class TimelineModel:
    """Contiguous non-destructive timeline; all persisted edit values are milliseconds."""
    def __init__(self) -> None:
        self._items: list[TimelineItem] = []
        self._history: list[_TimelineHistoryEntry] = []
        self._future: list[_TimelineHistoryEntry] = []
        self._version = 0

    @property
    def items(self) -> tuple[TimelineItem, ...]: return tuple(self._items)
    @property
    def duration_ms(self) -> int: return sum(item.duration_ms for item in self._items)
    @property
    def duration(self) -> float: return self.duration_ms / 1000
    @property
    def dirty(self) -> bool: return bool(self._items)
    def _commit(
        self,
        kind: TimelineEditKind = TimelineEditKind.GENERIC,
        split: TimelineSplitResult | None = None,
    ) -> None:
        self._history.append(_TimelineHistoryEntry(tuple(self._items), kind, split))
        self._future.clear()
        self._version += 1
    def snapshot(self, sample_rate: int = 48000, channels: int = 1) -> TimelineSnapshot:
        clips = tuple(
            TimelineClipSnapshot(
                clip_id=item.clip_id,
                kind=TimelineClipKind.AUDIO if isinstance(item, AudioClip) else TimelineClipKind.BLANK,
                source_path=item.source_path if isinstance(item, AudioClip) else None,
                source_start_ms=item.trim_start_ms if isinstance(item, AudioClip) else 0,
                source_end_ms=item.effective_end_ms if isinstance(item, AudioClip) else item.duration_ms,
                duration_ms=item.duration_ms,
            )
            for item in self._items
        )
        return TimelineSnapshot(clips, sum(clip.duration_ms for clip in clips), self._version, sample_rate, channels)
    def add_audio(self, path: Path, duration: float, index: int | None = None) -> AudioClip:
        self._commit(); clip=AudioClip.create(path,duration); self._items.insert(len(self._items) if index is None else max(0,min(index,len(self._items))),clip); return clip
    def add_blank(self, index: int | None = None, duration: float = 2.0) -> BlankClip:
        self._commit(); clip=BlankClip.create(duration); self._items.insert(len(self._items) if index is None else max(0,min(index,len(self._items))),clip); return clip
    def remove(self, ids: set[str]) -> None: self._commit(); self._items=[item for item in self._items if item.clip_id not in ids]
    def move(self, ids: set[str], insert_index: int) -> None:
        self._commit(); selected=[item for item in self._items if item.clip_id in ids]; rest=[item for item in self._items if item.clip_id not in ids]; index=max(0,min(insert_index,len(rest))); self._items=rest[:index]+selected+rest[index:]
    def trim_ms(self, clip_id: str, start_ms: int, end_ms: int) -> None:
        for item in self._items:
            if item.clip_id != clip_id: continue
            self._commit()
            if isinstance(item, AudioClip):
                start=max(0,min(start_ms,item.source_duration_ms-1)); end=max(start+1,min(end_ms,item.source_duration_ms)); replacement=replace(item,trim_start_ms=start,trim_end_ms=end)
            else: replacement=replace(item,duration_ms=max(1,end_ms-start_ms))
            self._items=[replacement if candidate.clip_id==clip_id else candidate for candidate in self._items]
            return
    def set_waveform(self, clip_id: str, waveform: WaveformEnvelope) -> None:
        self._items=[replace(item,waveform=waveform) if isinstance(item,AudioClip) and item.clip_id==clip_id else item for item in self._items]
    def trim(self, clip_id: str, start: float, end: float) -> None: self.trim_ms(clip_id,seconds_to_ms(start),seconds_to_ms(end))
    def clear(self) -> None: self._commit(); self._items.clear()
    def locate(self, time_ms: int) -> TimelineLocation | None:
        position = max(0, time_ms)
        start = 0
        for index, item in enumerate(self._items):
            end = start + item.duration_ms
            if start <= position < end:
                offset = position - start
                return TimelineLocation(
                    clip_id=item.clip_id,
                    index=index,
                    kind=TimelineClipKind.AUDIO if isinstance(item, AudioClip) else TimelineClipKind.BLANK,
                    timeline_start_ms=start,
                    offset_ms=offset,
                    source_ms=item.trim_start_ms + offset if isinstance(item, AudioClip) else None,
                )
            start = end
        return None
    def split_audio_at(
        self,
        clip_id: str,
        playhead_time_ms: int,
        min_duration_ms: int = 1,
    ) -> TimelineSplitResult:
        minimum = max(1, min_duration_ms)
        timeline_start = 0
        for index, item in enumerate(self._items):
            if item.clip_id != clip_id:
                timeline_start += item.duration_ms
                continue
            if not isinstance(item, AudioClip):
                raise ValueError("空白片段不能执行音频裁剪")  # noqa: TRY004  # 片段类型不适用，非参数类型错误
            offset = playhead_time_ms - timeline_start
            if offset < minimum or item.duration_ms - offset < minimum:
                raise ValueError("裁剪位置距离片段边缘过近")
            source_position = item.trim_start_ms + offset
            left = replace(
                item,
                clip_id=uuid4().hex,
                trim_end_ms=source_position,
            )
            right = replace(
                item,
                clip_id=uuid4().hex,
                trim_start_ms=source_position,
            )
            result = TimelineSplitResult(
                original_clip_id=item.clip_id,
                left_clip_id=left.clip_id,
                right_clip_id=right.clip_id,
                timeline_position_ms=playhead_time_ms,
                source_position_ms=source_position,
            )
            self._commit(TimelineEditKind.SPLIT, result)
            self._items[index:index + 1] = [left, right]
            return result
        raise ValueError("实时指针未位于可裁剪的音频片段中")

    def split_at_silences(self, midpoints_ms: list[int]) -> int:
        """在静音中点批量切分；整个批次一次提交，一次撤销即可整体回滚。"""
        points = sorted({int(point) for point in midpoints_ms if int(point) >= 1})
        if not points:
            return 0
        self._commit(TimelineEditKind.SPLIT)
        completed = 0
        for point in points:
            location = self.locate(point)
            if location is None or location.kind is not TimelineClipKind.AUDIO:
                continue
            item = self._items[location.index]
            offset = location.offset_ms
            if offset < 1 or item.duration_ms - offset < 1:
                continue
            left = replace(item, clip_id=uuid4().hex, trim_end_ms=item.trim_start_ms + offset)
            right = replace(item, clip_id=uuid4().hex, trim_start_ms=item.trim_start_ms + offset)
            self._items[location.index:location.index + 1] = [left, right]
            completed += 1
        return completed
    def undo(self) -> TimelineUndoResult | None:
        if not self._history:
            return None
        entry = self._history.pop()
        self._future.append(_TimelineHistoryEntry(tuple(self._items), entry.kind, entry.split))
        self._items = list(entry.items)
        self._version += 1
        return TimelineUndoResult(entry.kind, entry.split)
    def redo(self) -> TimelineUndoResult | None:
        if not self._future:
            return None
        entry = self._future.pop()
        self._history.append(_TimelineHistoryEntry(tuple(self._items), entry.kind, entry.split))
        self._items = list(entry.items)
        self._version += 1
        return TimelineUndoResult(entry.kind, entry.split)
    def reset(self) -> None: self._items.clear(); self._history.clear(); self._future.clear(); self._version += 1
