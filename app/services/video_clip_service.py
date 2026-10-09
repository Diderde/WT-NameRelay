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
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.audio.ffmpeg_service import BACKGROUND_FLAGS, FfmpegLocator
from app.paths import config_dir

CONFIG_ROOT = Path(__file__).resolve().parents[2] / "config"
CLIPS_ROOT = CONFIG_ROOT / "video_clips"
SPEAKER_FOLDER_NAMES = ("说话人A", "说话人B", "说话人C")
#: 说话人下的两种用途：训练素材（微调训练后再 TTS 生成成员组语音）与
#: 使用素材（直接导入作为成员组语音）。
PURPOSE_FOLDERS = ("训练素材", "使用素材")

#: 最短保留段（毫秒）：低于该长度的框选/修边一律拒绝，避免零宽片段
MIN_SEGMENT_MS = 50


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

    撤销/重做：每次"会真正改动"的操作前压一份 (segments, selected) 快照。
    拖拽修边 / 整段平移每帧 mousemove 都会改动模型，由界面在按下时
    `begin_gesture(kind)` 压一步、抬起时 `end_gesture()`，手势内的改动不再
    重复入栈——否则一次拖拽要按几十下 Ctrl+Z 才回到拖拽前。
    """

    #: 撤销栈上限：段列表很小，64 步足够覆盖一次剪辑会话的手误
    HISTORY_LIMIT = 64

    def __init__(self, duration_ms: int) -> None:
        if duration_ms <= 0:
            raise ValueError("duration must be positive")
        self.duration_ms = duration_ms
        self.segments: list[ClipSegment] = [ClipSegment(0, duration_ms)]
        self.selected: int | None = None
        self.playhead_ms = 0
        self._undo: list[tuple[list[ClipSegment], int | None]] = []
        self._redo: list[tuple[list[ClipSegment], int | None]] = []
        self._gesture = ""

    # ---------------------------------------------------------------- history

    def _snapshot(self) -> tuple[list[ClipSegment], int | None]:
        return ([ClipSegment(s.start_ms, s.end_ms) for s in self.segments],
                self.selected)

    def begin_gesture(self, kind: str) -> None:
        """按下拖拽前调用：整次手势只占一个撤销步。"""
        self._push(kind)
        self._gesture = kind

    def end_gesture(self) -> None:
        self._gesture = ""

    def _push(self, kind: str) -> None:
        if self._gesture == kind:
            return  # 手势内只记一步
        self._undo.append(self._snapshot())
        if len(self._undo) > self.HISTORY_LIMIT:
            self._undo.pop(0)
        self._redo.clear()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self.segments, self.selected = self._undo.pop()
        self._gesture = ""
        self.playhead_ms = max(0, min(self.playhead_ms, self.duration_ms))
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self.segments, self.selected = self._redo.pop()
        self._gesture = ""
        self.playhead_ms = max(0, min(self.playhead_ms, self.duration_ms))
        return True

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
        self._push("trim")
        segment.start_ms = self.playhead_ms
        return True

    def trim_right(self) -> bool:
        segment = self.selected_segment
        if segment is None or not (
            segment.start_ms < self.playhead_ms < segment.end_ms
        ):
            return False
        self._push("trim")
        segment.end_ms = self.playhead_ms
        return True

    def split_at(self) -> bool:
        segment = self.selected_segment
        if segment is None or not (
            segment.start_ms < self.playhead_ms < segment.end_ms
        ):
            return False
        self._push("split")
        index = self.selected
        right = ClipSegment(self.playhead_ms, segment.end_ms)
        segment.end_ms = self.playhead_ms
        self.segments.insert(index + 1, right)
        return True

    def delete_selected(self) -> bool:
        if self.selected is None or not self.segments:
            return False
        self._push("delete")
        index = min(self.selected, len(self.segments) - 1)
        self.segments.pop(index)
        if not self.segments:
            self.selected = None
        else:
            self.selected = min(index, len(self.segments) - 1)
        return True

    def add_segment(self, start_ms: int, end_ms: int) -> int | None:
        """在空洞区框选新增保留段：与既有段重叠的部分并入，返回新段下标。"""
        start = max(0, min(self.duration_ms, int(start_ms)))
        end = max(0, min(self.duration_ms, int(end_ms)))
        if end - start < MIN_SEGMENT_MS:
            return None
        self._push("add")
        merged = ClipSegment(start, end)
        kept: list[ClipSegment] = []
        for segment in self.segments:
            if (segment.end_ms <= merged.start_ms
                    or segment.start_ms >= merged.end_ms):
                kept.append(segment)
                continue
            merged.start_ms = min(merged.start_ms, segment.start_ms)
            merged.end_ms = max(merged.end_ms, segment.end_ms)
        kept.append(merged)
        kept.sort(key=lambda item: item.start_ms)
        self.segments = kept
        self.selected = kept.index(merged)
        return self.selected

    def move_selected(self, start_ms: int, *, record: bool = True) -> bool:
        """把选中段整体平移到 `start_ms`（越界与压到邻段时自动夹紧）。

        `record=False` 供拖拽使用：手势开始时已由 `begin_gesture` 压过一步。
        """
        segment = self.selected_segment
        if segment is None or self.selected is None:
            return False
        index = self.selected
        width = segment.end_ms - segment.start_ms
        lowest = self.segments[index - 1].end_ms if index > 0 else 0
        next_index = index + 1
        highest = (self.segments[next_index].start_ms - width
                   if next_index < len(self.segments)
                   else self.duration_ms - width)
        start = max(lowest, min(max(lowest, highest), int(start_ms)))
        if start == segment.start_ms:
            return False
        if record:
            self._push("move")
        segment.start_ms = start
        segment.end_ms = start + width
        return True

    def segment_at(self, position_ms: int) -> int | None:
        for index, segment in enumerate(self.segments):
            if segment.start_ms <= position_ms < segment.end_ms:
                return index
        return None

    def replace_segments(self, ranges: list[tuple[int, int]]) -> bool:
        """整表替换保留段（静音切句"应用"走这里）：排序合并、掐掉过短段，
        一次调用只占一个撤销步。"""
        cleaned: list[list[int]] = []
        for start, end in sorted(ranges):
            start = max(0, min(self.duration_ms, int(start)))
            end = max(0, min(self.duration_ms, int(end)))
            if end - start < MIN_SEGMENT_MS:
                continue
            if cleaned and start <= cleaned[-1][1]:
                cleaned[-1][1] = max(cleaned[-1][1], end)
            else:
                cleaned.append([start, end])
        current = [[s.start_ms, s.end_ms] for s in self.segments]
        if not cleaned or cleaned == current:
            return False
        self._push("replace")
        self.segments = [ClipSegment(start, end) for start, end in cleaned]
        self.selected = 0
        return True


def _background_flags() -> dict:
    """后台 ffmpeg/ffprobe 的进程创建参数：无控制台 + 低于正常优先级
    （`BACKGROUND_FLAGS` 单一出处），免得导入抽帧跟界面渲染抢 CPU。
    非 Windows 上两个常量都取不到有效位，等价于不传。"""
    return {"creationflags": BACKGROUND_FLAGS}


#: 时长清单文件名与容量上限：超容量按写入时间淘汰最旧条目
DURATION_MANIFEST_NAME = "video_duration_manifest.json"
_DURATION_MANIFEST_LIMIT = 512


def _manifest_key(source: Path) -> str:
    """清单键的路径形状：解析真实路径后按平台大小写规则归一。"""
    return os.path.normcase(str(Path(source).resolve()))


class AyaMaruyama:
    """素材时长清单：以 `路径 + mtime_ns + 大小` 为键缓存 ffprobe 的时长。

    命中即不再派 ffprobe，同批素材二次导入只剩列表与抽帧。探测在并发工作
    线程里回写，读写都在实例锁内；落盘沿用"tmp + os.replace"原子写。清单
    只是加速手段：读不到/坏掉一律当空表，写失败保留内存态继续跑，不拦导入。
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = (Path(path) if path is not None
                     else config_dir() / DURATION_MANIFEST_NAME)
        self._lock = threading.Lock()
        self._entries: dict[str, dict] | None = None

    def _read(self) -> dict[str, dict]:
        """首次访问时读盘，之后走内存态（调用方须持锁）。"""
        if self._entries is not None:
            return self._entries
        entries: dict[str, dict] = {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        if isinstance(raw, dict):
            entries = {str(key): value for key, value in raw.items()
                       if isinstance(value, dict)}
        self._entries = entries
        return entries

    def _write(self, entries: dict[str, dict]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(entries, ensure_ascii=False),
                           encoding="utf-8")
            # Windows 上旧目标句柄延迟释放会让 os.replace 瞬时
            # 拒绝访问（高频循环实测）；短退避重试，最终失败只丢这次落盘
            for attempt in range(6):
                try:
                    os.replace(tmp, self.path)
                    return
                except OSError:
                    if attempt == 5:
                        tmp.unlink(missing_ok=True)
                time.sleep(0.02 * (attempt + 1))
        except OSError:
            return  # 清单只是加速手段：落盘失败留着内存态，不拦导入

    def duration_ms(self, source: Path) -> int | None:
        """命中返回时长；键不存在、素材已改动或值不可用都返回 None。"""
        target = Path(source)
        with self._lock:
            entry = self._read().get(_manifest_key(target))
        if not isinstance(entry, dict):
            return None
        stamp = _stat_of(target)
        if stamp is None:
            return None
        try:
            if (int(entry.get("mtime_ns", -1)) != stamp.st_mtime_ns
                    or int(entry.get("size", -1)) != stamp.st_size):
                return None
            duration_ms = int(entry.get("duration_ms", 0))
        except (TypeError, ValueError):
            return None
        return duration_ms if duration_ms > 0 else None

    def store(self, source: Path, duration_ms: int) -> None:
        target = Path(source)
        stamp = _stat_of(target)
        if stamp is None or duration_ms <= 0:
            return
        with self._lock:
            entries = self._read()
            entries[_manifest_key(target)] = {
                "mtime_ns": stamp.st_mtime_ns,
                "size": stamp.st_size,
                "duration_ms": int(duration_ms),
                "stored_at": time.time_ns(),
            }
            if len(entries) > _DURATION_MANIFEST_LIMIT:
                ordered = sorted(entries.items(),
                                 key=lambda item: _entry_rank(item[1]))
                entries = dict(ordered[-_DURATION_MANIFEST_LIMIT:])
                self._entries = entries
            self._write(entries)


def _entry_rank(entry: dict) -> int:
    """淘汰排序用的写入时刻：外来条目字段不可用时当最旧处理。"""
    try:
        return int(entry.get("stored_at", 0))
    except (TypeError, ValueError):
        return 0


def _stat_of(target: Path) -> os.stat_result | None:
    try:
        return target.stat()
    except OSError:
        return None


_duration_manifest: AyaMaruyama | None = None
_duration_manifest_lock = threading.Lock()


def duration_manifest() -> AyaMaruyama:
    """进程内共享的时长清单（懒建）。"""
    global _duration_manifest
    with _duration_manifest_lock:
        if _duration_manifest is None:
            _duration_manifest = AyaMaruyama()
    return _duration_manifest


def probe_video(path: Path,
                *, manifest: AyaMaruyama | None = None) -> VideoAsset:
    """ffprobe 探测时长与大小（失败抛异常，不静默降级）。

    先查时长清单：路径 + mtime_ns + 大小三项全等才认，命中则一个进程都不派。
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"video not found: {source}")
    cache = manifest if manifest is not None else duration_manifest()
    cached_ms = cache.duration_ms(source)
    if cached_ms is not None:
        size_bytes = source.stat().st_size
        return VideoAsset(path=source, duration_ms=cached_ms,
                          size_bytes=size_bytes)
    result = subprocess.run(
        [
            str(FfmpegLocator.executable("ffprobe")),
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(source),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, check=False, **_background_flags())
    if result.returncode != 0:
        raise ValueError(f"ffprobe failed for {source}: {result.stderr.strip()[-300:]}")
    info = json.loads(result.stdout or "{}")
    duration_s = float(info.get("format", {}).get("duration") or 0.0)
    if duration_s <= 0.0:
        raise ValueError(f"no duration probed for {source}")
    asset = VideoAsset(
        path=source,
        duration_ms=round(duration_s * 1000),
        size_bytes=source.stat().st_size,
    )
    cache.store(source, asset.duration_ms)
    return asset


def default_clips_root() -> Path:
    return CLIPS_ROOT


#: 路径展示用的根标签：绝对路径一长就被省略号吃掉中段，用户看不出素材落在
#: 谁名下——界面统一按「素材库 › 说话人 › 用途」的面包屑显示，完整路径留给
#: 悬浮提示与「打开位置」按钮兜底。
CLIPS_ROOT_LABEL = "素材库"
#: 面包屑分隔符：`/` 会被当成路径分隔符读，`›` 只表示层级，不带文件系统语义
_PATH_SEP = " › "


def describe_clip_path(target: Path, root: Path | None = None) -> str:
    """把素材库内的路径压成可读面包屑「素材库 › 说话人A › 训练素材」。

    素材库之外的路径（外部输出目录等）原样退回绝对路径，由调用方自行省略。
    """
    base = Path(root) if root is not None else CLIPS_ROOT
    candidate = Path(target)
    try:
        relative = candidate.resolve().relative_to(base.resolve())
    except (OSError, ValueError):
        return str(candidate)
    names = [part for part in relative.parts if part not in ("", ".")]
    return _PATH_SEP.join([CLIPS_ROOT_LABEL, *names])


# ---------------------------------------------------------------- 自动命名

#: 剪出来的素材统一叫 `<前缀>-<序号>`（raw-footage-1 / raw-footage-2 …）：
#: 源文件名是用户的原始长名，夹在说话人目录下既长又带不出顺序信息
DEFAULT_CLIP_PREFIX = "raw-footage"
#: 前缀长度上限：与说话人名同量级，够写但不至于撞文件系统限制
CLIP_PREFIX_MAX = 64
#: 文件名禁用的字符（Windows 的严集合；POSIX 只禁 `/`，一并从严）
_FORBIDDEN_IN_NAME = '<>:"/\\|?*'


def sanitize_clip_prefix(value: str) -> str:
    """把前缀修成文件系统吃得下的形态；空或全非法回退默认前缀。

    值来自界面文本框，随手打出斜杠/冒号很常见：静默净化比弹错顺手，净化结果
    由界面回写进输入框，用户看得见发生了什么。非法字符转成连字符而不是直接
    删掉——`raw/footage` 变成 `raw-footage`，比 `rawfootage` 更像人写的名字。
    """
    cleaned = "".join("-" if ch in _FORBIDDEN_IN_NAME or ord(ch) < 32 else ch
                      for ch in (value or ""))
    while "--" in cleaned:  # `a//b` 不必变成 `a--b`
        cleaned = cleaned.replace("--", "-")
    cleaned = cleaned.strip(" -").rstrip(".")
    # 截断可能重新切出尾部点/空格：再收一次（Windows 会静默吞掉它们）
    cleaned = cleaned[:CLIP_PREFIX_MAX].rstrip(" .")
    return cleaned or DEFAULT_CLIP_PREFIX


def next_clip_index(folder: Path, prefix: str) -> int:
    """目标目录里下一份素材的序号：已有 raw-footage-1..7 → 8。

    目录读不出来（不存在/没权限）就当空目录从 1 起——命名不该把导出卡住。
    """
    token = f"{prefix}-"
    highest = 0
    try:
        stems = [p.stem for p in Path(folder).iterdir() if p.is_file()]
    except OSError:
        return 1
    for stem in stems:
        if not stem.startswith(token):
            continue
        tail = stem[len(token):]
        # 只认 ASCII 数字：全角数字 isdigit 也为真、int() 也能解析，编号会跳
        if tail.isascii() and tail.isdigit():
            highest = max(highest, int(tail))
    return highest + 1


def next_clip_paths(folder: Path, prefix: str, suffix: str,
                    count: int = 1) -> list[Path]:
    """连续 `count` 个不与既有文件撞名的目标路径（`<前缀>-<序号><后缀>`）。

    序号只增不回头：目录里被别的工具塞进同号文件时，往前找空号而不是覆盖它。
    """
    base = Path(folder)
    index = next_clip_index(base, prefix)
    limit = index + max(count, 1) * 100 + 1000  # 安全阀：目录异常时不至于空转
    paths: list[Path] = []
    while len(paths) < count and index <= limit:
        candidate = base / f"{prefix}-{index}{suffix}"
        if not candidate.exists():
            paths.append(candidate)
        index += 1
    return paths


def list_speaker_folders(root: Path | None = None) -> list[Path]:
    """扫描既有说话人目录并补齐用途子文件夹（不创建默认三件套）。

    返回按名称排序的说话人根目录列表；根下为空时返回空列表。"""
    base = Path(root) if root is not None else CLIPS_ROOT
    base.mkdir(parents=True, exist_ok=True)
    speakers = [p for p in base.iterdir() if p.is_dir()]
    for speaker in speakers:
        for purpose in PURPOSE_FOLDERS:
            (speaker / purpose).mkdir(parents=True, exist_ok=True)
    return sorted(speakers, key=lambda p: p.name.casefold())


def ensure_speaker_folders(root: Path | None = None) -> list[Path]:
    """首次使用落默认三件套，之后只扫描补齐（幂等）。

    2026-10-03 语义修正：说话人支持自定义命名与增删后，固定重建
    说话人A/B/C 会与用户的改名/删除对着干——仅当根下无任何说话人
    目录时才创建默认三件套；随后交 `list_speaker_folders` 扫描。
    """
    base = Path(root) if root is not None else CLIPS_ROOT
    base.mkdir(parents=True, exist_ok=True)
    if not any(p.is_dir() for p in base.iterdir()):
        for name in SPEAKER_FOLDER_NAMES:
            (base / name).mkdir(parents=True, exist_ok=True)
    return list_speaker_folders(base)


#: Windows 文件名的保留设备名（大小写不敏感；含带扩展名的形态）
_RESERVED_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
#: 说话人名的长度上限（文件系统安全的保守值）
SPEAKER_NAME_MAX = 64


def validate_speaker_name(name: str) -> str:
    """校验并归一说话人名（即文件夹名）；非法抛 ValueError。

    允许中文/空格/常见符号，拦 Windows 非法字符、保留设备名、
    结尾点/空格（Windows 会静默吞掉，造成改名前后对不上）。"""
    normalized = (name or "").strip()
    if not normalized:
        raise ValueError("名称不能为空")
    if len(normalized) > SPEAKER_NAME_MAX:
        raise ValueError(f"名称过长（上限 {SPEAKER_NAME_MAX} 字符）")
    forbidden = set('<>:"/\\|?*')
    bad = sorted({ch for ch in normalized if ch in forbidden or ord(ch) < 32})
    if bad:
        raise ValueError(f"含有无法用于文件夹名的字符：{''.join(bad)!r}")
    if normalized != normalized.rstrip(" ."):
        raise ValueError("名称不能以点或空格结尾")
    if normalized.upper() in _RESERVED_DEVICE_NAMES:
        raise ValueError(f"{normalized} 是 Windows 保留设备名")
    return normalized


def _speaker_collision(root: Path, name: str, *, exclude: Path | None = None) -> bool:
    lowered = name.casefold()
    return any(
        p.name.casefold() == lowered and p != exclude
        for p in root.iterdir() if p.is_dir()
    )


def add_speaker_folder(name: str, root: Path | None = None) -> Path:
    """新增说话人（校验命名 + 同名冲突），建全用途子文件夹后返回路径。"""
    base = Path(root) if root is not None else CLIPS_ROOT
    normalized = validate_speaker_name(name)
    base.mkdir(parents=True, exist_ok=True)
    if _speaker_collision(base, normalized):
        raise ValueError(f"已存在同名说话人：{normalized}")
    speaker = base / normalized
    for purpose in PURPOSE_FOLDERS:
        (speaker / purpose).mkdir(parents=True, exist_ok=True)
    return speaker


def rename_speaker_folder(old: Path, new_name: str,
                          root: Path | None = None) -> Path:
    """重命名说话人（素材随目录整体迁移），返回新路径。"""
    base = Path(root) if root is not None else old.parent
    normalized = validate_speaker_name(new_name)
    if not old.is_dir():
        raise ValueError(f"说话人目录不存在：{old}")
    if _speaker_collision(base, normalized, exclude=old):
        raise ValueError(f"已存在同名说话人：{normalized}")
    target = base / normalized
    old.rename(target)
    return target


def remove_speaker_folder(path: Path) -> None:
    """删除说话人及其全部素材（不可恢复；UI 侧负责确认与忙时守卫）。"""
    shutil.rmtree(path)


def next_speaker_name(root: Path | None = None) -> str:
    """「新增」对话框的建议名：顺位取第一个未占用的 说话人A..Z，超出用数字。"""
    base = Path(root) if root is not None else CLIPS_ROOT
    existing = {p.name.casefold() for p in base.iterdir()} if base.is_dir() else set()
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        candidate = f"说话人{letter}"
        if candidate.casefold() not in existing:
            return candidate
    index = 1
    while True:
        candidate = f"说话人{index}"
        if candidate.casefold() not in existing:
            return candidate
        index += 1


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
            # 只出一帧就别让 ffmpeg 再去解音频/字幕轨
            "-ss", "0.5", "-i", str(src),
            "-frames:v", "1", "-an", "-sn", "-dn",
            "-vf", f"scale={width}:-1",
            "-y", str(target),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120, check=False, **_background_flags(),
    )
    if result.returncode != 0 or not target.is_file():
        raise RuntimeError(f"thumbnail failed: {result.stderr.strip()[-300:]}")
    return target


#: 胶片带单帧宽（像素）与帧数上下限：一帧约覆盖 0.5s，长片自动放宽
_FILMSTRIP_FRAME_W = 96
_FILMSTRIP_MIN_FRAMES = 16
_FILMSTRIP_MAX_FRAMES = 128


def filmstrip_frames(duration_ms: int) -> int:
    """按素材时长取胶片带帧数（时长越短帧越密，长片放宽避免超大图）。"""
    rough = int(max(1, duration_ms) / 500)
    return max(_FILMSTRIP_MIN_FRAMES, min(_FILMSTRIP_MAX_FRAMES, rough))


def _filmstrip_filter(count: int, duration_ms: int, width: int) -> str:
    """`fps → scale → tile` 的公共段：逐个与批量共用，出图才逐字节一致。"""
    seconds = max(0.04, duration_ms / 1000.0)
    return f"fps={count / seconds:.9f},scale={width}:-2,tile={count}x1"


def _filmstrip_target(src: Path, out_dir: Path, duration_ms: int, count: int,
                      width: int) -> Path:
    """胶片带缓存名：批量与逐个同键，谁先出图另一边都能复用。"""
    key = hashlib.sha256(
        f"{src}|{duration_ms}|{count}|{width}".encode()).hexdigest()[:16]
    return out_dir / f"strip_{key}.png"


def make_filmstrip(source: Path, out_dir: Path, *, duration_ms: int,
                   frames: int | None = None,
                   width: int = _FILMSTRIP_FRAME_W) -> Path:
    """生成横向拼接胶片带（解码 + scale + tile + png，LGPL 基线能力），带缓存。

    输出为单张 `frames × width` 宽的横条：时间轴视频轨按 `时间→帧序号`
    线性切片绘制，缩放时无需重跑 ffmpeg。帧数按时长自适应，长片下
    深度放大会有拉伸模糊，这是"一次抽帧"换零交互延迟的取舍。
    """
    src = Path(source)
    if not src.is_file():
        raise FileNotFoundError(f"source not found: {src}")
    count = frames or filmstrip_frames(duration_ms)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = _filmstrip_target(src, out_dir, duration_ms, count, width)
    if target.is_file() and target.stat().st_size > 0:
        return target
    result = subprocess.run(
        [
            str(FfmpegLocator.executable("ffmpeg")),
            "-hide_banner", "-loglevel", "error",
            "-i", str(src),
            "-vf", _filmstrip_filter(count, duration_ms, width),
            # 胶片带也只用视频轨：字幕/数据轨会参与滤镜图判定，
            # 见到软字幕容器可能白解一遍甚至报错
            "-frames:v", "1", "-an", "-sn", "-dn",
            "-y", str(target),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180, check=False, **_background_flags(),
    )
    if result.returncode != 0 or not target.is_file():
        raise RuntimeError(f"filmstrip failed: {result.stderr.strip()[-300:]}")
    return target


#: 批量胶片带的单条命令超时预算：按"每个输入都跑满单素材超时"折算
_STRIP_BATCH_TIMEOUT = 180


def make_filmstrips_batch(assets: list[tuple[Path, int]],
                          out_dir: Path,
                          *, width: int = _FILMSTRIP_FRAME_W
                          ) -> tuple[dict[Path, Path], dict[Path, str]]:
    """一条 ffmpeg 给 N 个素材各出一张胶片带，返回 (成功映射, 逐素材错误)。

    多输入各挂一条 `fps→scale→tile` 滤镜链，用 `-map` 分路出图：N 次进程启动
    与容器解析压成 1 次。缓存命中的素材不占命令行位置，暖导入直接零派生。
    只用 png 编码与 fps/scale/tile 滤镜，全部在 LGPL 基线内（本仓库自带构建
    无 libx264，任何 `-c:v libx264`/`-preset` 都会以 2880417800 失败）。

    一条命令坏一个输入会连坐整批，因此批量失败（返回码非零或个别图缺失）后
    逐素材回退到 `make_filmstrip`，失败原因按素材回报，调用方决定怎么记。
    """
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)
    done: dict[Path, Path] = {}
    failed: dict[Path, str] = {}
    todo: list[tuple[Path, int, int, Path]] = []
    for source, duration_ms in assets:
        src = Path(source)
        count = filmstrip_frames(duration_ms)
        target = _filmstrip_target(src, base, duration_ms, count, width)
        if target.is_file() and target.stat().st_size > 0:
            done[src] = target
            continue
        if not src.is_file():
            failed[src] = f"source not found: {src}"
            continue
        todo.append((src, duration_ms, count, target))
    if len(todo) == 1:
        # 只有一个待出图时合并无收益，直接走单素材路径
        src, duration_ms, count, _target = todo[0]
        try:
            done[src] = make_filmstrip(src, base, duration_ms=duration_ms,
                                       frames=count, width=width)
        except (OSError, RuntimeError, ValueError) as exc:
            failed[src] = str(exc)
        return done, failed
    if not todo:
        return done, failed
    args = [str(FfmpegLocator.executable("ffmpeg")),
            "-hide_banner", "-loglevel", "error"]
    inputs, chains, outputs = [], [], []
    for index, (src, duration_ms, count, target) in enumerate(todo):
        inputs += ["-i", str(src)]
        chains.append(f"[{index}:v]{_filmstrip_filter(count, duration_ms, width)}"
                      f"[s{index}]")
        outputs += ["-map", f"[s{index}]", "-frames:v", "1",
                    "-an", "-sn", "-dn", "-y", str(target)]
    result = subprocess.run(
        args + inputs + ["-filter_complex", ";".join(chains)] + outputs,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=_STRIP_BATCH_TIMEOUT * len(todo), check=False,
        **_background_flags())
    if result.returncode != 0:
        # 连坐的批里可能有半张写坏的图：清掉再逐个补，免得回退把它当缓存
        for _src, _duration, _count, target in todo:
            target.unlink(missing_ok=True)
    for src, duration_ms, count, target in todo:
        if result.returncode == 0 and target.is_file() \
                and target.stat().st_size > 0:
            done[src] = target
            continue
        try:
            done[src] = make_filmstrip(src, base, duration_ms=duration_ms,
                                       frames=count, width=width)
        except (OSError, RuntimeError, ValueError) as exc:
            failed[src] = str(exc)
    return done, failed


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


def cut_audio_segment(
    source: Path,
    start_ms: int,
    end_ms: int,
    destination: Path,
) -> Path:
    """把片段的音轨抽成 WAV（16-bit PCM）。

    台词最终要喂 TTS/语音处理链路，容器流复制给不了音频文件。解码 +
    `pcm_s16le` 封装与 `audioprep_worker` 的 DECODE 节点同款，仍在 LGPL
    基线内；`atrim` 按采样精确切，不受视频关键帧对齐影响。
    """
    src = Path(source)
    dst = Path(destination)
    if not src.is_file():
        raise FileNotFoundError(f"source not found: {src}")
    if not 0 <= start_ms < end_ms:
        raise ValueError(f"invalid segment: {start_ms}..{end_ms}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    result = subprocess.run(
        [
            str(FfmpegLocator.executable("ffmpeg")),
            "-hide_banner", "-loglevel", "error", "-nostdin",
            "-i", str(src),
            "-vn",
            "-af", (f"atrim=start={start_ms / 1000.0:.3f}:"
                    f"end={end_ms / 1000.0:.3f},asetpts=PTS-STARTPTS"),
            "-c:a", "pcm_s16le", "-f", "wav",
            "-y", str(dst),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300, check=False,
    )
    if result.returncode != 0 or not dst.is_file() or dst.stat().st_size == 0:
        raise RuntimeError(
            f"audio cut failed (exit {result.returncode}): "
            f"{result.stderr.strip()[-300:]}")
    return dst
