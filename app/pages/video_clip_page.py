# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""视频裁剪工作台：剪映式编辑器布局。

上排三面板（素材库 / 播放器 / 导出），下排全宽双轨时间轴
（`app.widgets.clip_timeline.ClipTimeline`）。面板一律 `QFrame` 挂
`placeholderPanel`：全局样式表的选择器是 `QFrame#placeholderPanel`，
此前用 `QWidget` 挂同名 objectName 选不中，三块面板才一直没有卡片底。
页内细节样式由 `theme.color()` 现取现拼，昼夜切换时整表重建；图标全部
QPainter 自绘，不引外部资源。落盘走 `cut_segment`（`-c copy`，LGPL 基线）。
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import threading
from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from PySide6.QtCore import (
    QElapsedTimer,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.audio.models import WaveformEnvelope
from app.audio.silence_service import SilenceDetectWorker
from app.audio.waveform_service import WaveformWorker
from app.i18n import tr
from app.pages.base_tool_page import BaseToolPage
from app.preferences import get_preference, set_preference
from app.services.video_clip_errorlog import RokkaAsahi, enable_crash_log
from app.services.video_clip_service import (
    DEFAULT_CLIP_PREFIX,
    MIN_SEGMENT_MS,
    PURPOSE_FOLDERS,
    ClipTimelineModel,
    VideoAsset,
    add_speaker_folder,
    cut_audio_segment,
    cut_segment,
    describe_clip_path,
    ensure_speaker_folders,
    filmstrip_frames,
    list_speaker_folders,
    make_filmstrip,
    make_filmstrips_batch,
    make_thumbnail,
    next_clip_paths,
    next_speaker_name,
    probe_video,
    remove_speaker_folder,
    rename_speaker_folder,
    sanitize_clip_prefix,
)
from app.styles import theme
from app.styles.theme import off_mode_changed, on_mode_changed
from app.widgets.clip_timeline import (
    MS_PER_PX_MAX,
    MS_PER_PX_MIN,
    ClipTimeline,
    format_clock,
    format_tc,
)

_SPEEDS = (0.5, 1.0, 2.0, 4.0, 8.0)
_THUMB_DIR = Path(tempfile.gettempdir()) / "wt_video_thumbs"
_MIN_FRAME_MS = 33  # 预览取帧节流：30fps 上限，不为解码帧率全量重缩放
_FRAME_MS = 33  # 逐帧步进的近似帧长（未探帧率，按 30fps 取）
_THUMB_W = 92
_THUMB_H = 52
_ICON_PX = 18
_DASH = "—"
_LOGGER = logging.getLogger("wt_name_relay")
_SILENCE_DB = -35  # 静音门限：台词间隙通常远低于 -35dB，环境噪底之上
_SILENCE_MIN_MS = 250  # 短于该值的静音不算切点（呼吸/顿挫不切）
_MIN_SPEECH_MS = 300  # 短于该值的语音段丢弃（咔哒声不成句）
_MERGE_GAP_MS = 150  # 间隔小于该值的相邻语音段合并成一句
_PROBE_WORKERS = 3  # 导入探测并发上限：池化，批量导入不会瞬间拉起几十个 ffprobe
_PREVIEW_WORKERS = 2  # 胶片带/封面抽帧并发上限：解码吃 CPU，两个就够
_STRIP_BATCH_MAX = 8  # 单条 ffmpeg 合并出图的素材数上限：再多输入句柄不划算
#: 导出命名：自动编号（raw-footage-1）或沿用源文件名（原名 + 时间戳）
_NAMING_MODES = ("auto", "source")
#: 命名前缀的持久化键（config/settings.ini）
CLIP_PREFIX_SETTING = "video_clip/name_prefix"
#: 后缀预览的兜底值：还没导入素材时按最常见的容器后缀显示
_FALLBACK_SUFFIX = ".mp4"


# ---------------------------------------------------------------- 自绘图标

def _poly(*points: tuple[float, float], close: bool = True) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(*points[0])
    for point in points[1:]:
        path.lineTo(*point)
    if close:
        path.closeSubpath()
    return path


def _glyph(painter: QPainter, name: str) -> None:
    """在 18×18 逻辑坐标里画图标：实心件用 brush，线件用 pen（同一颜色）。"""

    def stroke(*points: tuple[float, float]) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(_poly(*points, close=False))

    if name == "play":
        painter.drawPath(_poly((5.6, 3.4), (14.6, 9.0), (5.6, 14.6)))
    elif name == "pause":
        painter.drawRect(QRectF(5.2, 3.6, 2.8, 10.8))
        painter.drawRect(QRectF(10.0, 3.6, 2.8, 10.8))
    elif name == "start":
        painter.drawRect(QRectF(3.4, 3.8, 1.8, 10.4))
        painter.drawPath(_poly((14.4, 3.8), (14.4, 14.2), (6.4, 9.0)))
    elif name == "end":
        painter.drawPath(_poly((3.6, 3.8), (3.6, 14.2), (11.6, 9.0)))
        painter.drawRect(QRectF(12.8, 3.8, 1.8, 10.4))
    elif name == "prev":
        painter.drawPath(_poly((12.6, 4.4), (12.6, 13.6), (5.6, 9.0)))
    elif name == "next":
        painter.drawPath(_poly((5.4, 4.4), (5.4, 13.6), (12.4, 9.0)))
    elif name in ("volume", "mute"):
        painter.drawPath(_poly((3.4, 7.0), (6.4, 7.0), (9.8, 4.0), (9.8, 14.0),
                               (6.4, 11.0), (3.4, 11.0)))
        if name == "volume":
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QRectF(11.0, 5.4, 5.4, 7.2), -62 * 16, 124 * 16)
        else:
            stroke((12.0, 7.0), (15.8, 10.8))
            stroke((15.8, 7.0), (12.0, 10.8))
    elif name == "split":
        # 中间虚线 = 播放头，两侧箭头 = 一分为二
        stroke((6.6, 4.8), (3.0, 9.0), (6.6, 13.2))
        stroke((11.4, 4.8), (15.0, 9.0), (11.4, 13.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(painter.pen().color(), 1.5, Qt.PenStyle.DashLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(9.0, 2.8), QPointF(9.0, 15.2))
    elif name in ("trim_left", "trim_right"):
        # 实心竖线 = 播放头；箭头指向被丢弃的一侧
        edge = 4.4 if name == "trim_left" else 13.6
        bar = 12.6 if name == "trim_left" else 5.4
        head = -2.8 if name == "trim_left" else 2.8
        painter.drawRect(QRectF(bar - 0.9, 3.4, 1.8, 11.2))
        stroke((edge, 4.0), (edge, 7.2))
        stroke((edge, 10.8), (edge, 14.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(edge, 9.0), QPointF(bar, 9.0))
        stroke((bar + head, 6.4), (bar, 9.0), (bar + head, 11.6))
    elif name == "trash":
        stroke((4.6, 5.8), (13.4, 5.8), (12.5, 15.0), (5.5, 15.0), (4.6, 5.8))
        stroke((2.8, 5.8), (15.2, 5.8))
        stroke((6.8, 5.8), (6.8, 3.4), (11.2, 3.4), (11.2, 5.8))
        painter.drawLine(QPointF(7.6, 8.4), QPointF(7.9, 12.6))
        painter.drawLine(QPointF(10.4, 8.4), QPointF(10.1, 12.6))
    elif name in ("zoom_in", "zoom_out"):
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(3.4, 3.4, 9.0, 9.0))
        stroke((11.8, 11.8), (15.6, 15.6))
        painter.drawLine(QPointF(5.6, 7.9), QPointF(10.2, 7.9))
        if name == "zoom_in":
            painter.drawLine(QPointF(7.9, 5.6), QPointF(7.9, 10.2))
    elif name == "fit":
        for corner in (((3.0, 6.6), (3.0, 3.0), (6.6, 3.0)),
                       ((11.4, 3.0), (15.0, 3.0), (15.0, 6.6)),
                       ((15.0, 11.4), (15.0, 15.0), (11.4, 15.0)),
                       ((6.6, 15.0), (3.0, 15.0), (3.0, 11.4))):
            stroke(*corner)
    elif name in ("import", "export"):
        stroke((3.0, 8.0), (6.6, 8.0), (8.0, 6.0), (15.0, 6.0), (15.0, 14.4),
               (3.0, 14.4), (3.0, 8.0))
        painter.drawLine(QPointF(9.4, 8.2), QPointF(9.4, 12.6))
        if name == "export":
            stroke((7.4, 10.2), (9.4, 8.2), (11.4, 10.2))
        else:
            stroke((7.4, 10.6), (9.4, 12.6), (11.4, 10.6))
    elif name in ("undo", "redo"):
        # 回退/前进箭头：拐弯 shaft + 箭头
        if name == "undo":
            stroke((14.6, 12.6), (14.6, 9.4), (11.4, 6.2), (5.4, 6.2))
            stroke((8.0, 3.2), (5.0, 6.2), (8.0, 9.2))
        else:
            stroke((3.4, 12.6), (3.4, 9.4), (6.6, 6.2), (12.6, 6.2))
            stroke((10.0, 3.2), (13.0, 6.2), (10.0, 9.2))
    elif name == "autocut":
        # 小波形 + 两道切线：按静音切句
        stroke((2.6, 9.0), (4.6, 5.4), (6.6, 12.0), (8.6, 6.6), (10.6, 11.0),
               (12.6, 9.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(painter.pen().color(), 1.4, Qt.PenStyle.DashLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(5.6, 2.8), QPointF(5.6, 15.2))
        painter.drawLine(QPointF(11.6, 2.8), QPointF(11.6, 15.2))
    elif name == "export_all":
        stroke((3.0, 10.0), (3.0, 14.4), (15.0, 14.4), (15.0, 10.0))
        painter.drawLine(QPointF(6.6, 8.6), QPointF(6.6, 3.4))
        stroke((4.8, 5.2), (6.6, 3.4), (8.4, 5.2))
        painter.drawLine(QPointF(11.4, 8.6), QPointF(11.4, 3.4))
        stroke((9.6, 5.2), (11.4, 3.4), (13.2, 5.2))


def _clip_icon(name: str, color: str) -> QIcon:
    """2× 超采样绘制后按 DPR 交给 Qt：任何缩放都不糊，换肤只是换个色。"""
    ratio = 2
    canvas = QPixmap(_ICON_PX * ratio, _ICON_PX * ratio)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(ratio, ratio)
    tint = QColor(color)
    painter.setPen(QPen(tint, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                        Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(tint)
    _glyph(painter, name)
    painter.end()
    canvas.setDevicePixelRatio(ratio)
    return QIcon(canvas)


def _human_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


# ---------------------------------------------------------------- 后台任务池

class HimariUehara:
    """固定宽度的后台任务池：任务进队列，守护线程按 FIFO 消费。

    此前每个素材各起一条线程（探测一条、缩略图一条、胶片带
    一条），批量导入会瞬间拉起几十个 ffmpeg：进程启动互相抢、内存峰值失控，
    且线程对象本身是运行期 GC 的垃圾来源。池化后并发被钉死在上限内，任务
    排队等着，线程数恒为上限。
    """

    #: 空闲线程等待时限（秒）：到点仍无任务才退，避免反复建/毁线程
    IDLE_WAIT_S = 30.0

    def __init__(self, workers: int, name: str) -> None:
        self._width = max(1, int(workers))
        self._name = name
        self._queue: deque[Callable[[], None]] = deque()
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._threads: list[threading.Thread] = []
        self._running = 0

    def submit(self, task: Callable[[], None]) -> None:
        """入队一个任务；池内线程不足且未达上限时补齐。"""
        pending: list[threading.Thread] = []
        with self._cond:
            self._queue.append(task)
            self._threads = [thread for thread in self._threads
                             if thread.is_alive()]
            while len(self._threads) < self._width:
                thread = threading.Thread(target=self._drain, name=self._name,
                                          daemon=True)
                self._threads.append(thread)
                pending.append(thread)
            self._cond.notify()
        for thread in pending:
            thread.start()

    def _drain(self) -> None:
        while True:
            with self._cond:
                # "看到空队列就退出"会把刚入队的任务永久留在
                # 队里（提交方判定线程还活着、不再补人）；改成空队列先等一
                # 段，被唤醒后重新看队列，到点仍空才退
                if not self._queue:
                    self._cond.wait(self.IDLE_WAIT_S)
                    if not self._queue:
                        # 决定退出时须在同一条件锁内把自己摘出
                        # 名册：否则提交方会把这条"将死未死"的线程当活人、不再
                        # 补人、notify 落空，刚入队的任务被永久晾在队里
                        current = threading.current_thread()
                        if current in self._threads:
                            self._threads.remove(current)
                        return
                task = self._queue.popleft()
                self._running += 1
            try:
                task()
            except Exception as error:  # noqa: BLE001  工作线程边界：一个任务炸了不能带走整条队
                _LOGGER.error("video clip worker failed: %s", error)
            finally:
                with self._cond:
                    self._running -= 1

    def busy(self) -> bool:
        """队列非空或仍有任务在跑 → True（GC 安全点与忙碌判定共用）。

        只看"有没有活儿"，不看线程是否还存活：空闲等待的线程不算忙，否则
        GC 安全点会因为常驻线程永远判定为不安全。
        """
        with self._lock:
            return bool(self._queue) or self._running > 0


# ---------------------------------------------------------------- 素材卡片

class MediaCard(QFrame):
    """素材库卡片：圆角缩略图 + 文件名 + 时长/体积，选中态走 QSS 属性选择器。"""

    def __init__(self, asset: VideoAsset, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName('clipCard')
        self._asset = asset
        self._thumb = QLabel()
        self._thumb.setObjectName('clipThumb')
        self._thumb.setFixedSize(_THUMB_W, _THUMB_H)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name = QLabel(asset.path.name)
        self._name.setObjectName('clipCardName')
        self._name.setToolTip(str(asset.path))
        self._meta = QLabel(f"{format_clock(asset.duration_ms)}  ·  "
                            f"{_human_size(asset.size_bytes)}")
        self._meta.setObjectName('clipCardMeta')
        column = QVBoxLayout()
        column.setSpacing(2)
        column.addWidget(self._name)
        column.addWidget(self._meta)
        column.addStretch(1)
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 6, 10, 6)
        row.setSpacing(10)
        row.addWidget(self._thumb, 0)
        row.addLayout(column, 1)

    def sizeHint(self) -> QSize:
        return QSize(_THUMB_W + 190, _THUMB_H + 14)

    def set_active(self, active: bool) -> None:
        wanted = 'true' if active else 'false'
        if self.property('active') == wanted:
            return
        self.setProperty('active', wanted)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_thumbnail(self, source: str | QPixmap) -> None:
        """封面裁成圆角：QSS 的 border-radius 不会裁 QLabel 里的位图。

        接受路径或已解码位图——胶片带的第 0 帧就是封面，直接传位图可省掉
        一次专门的 ffmpeg 抽帧。
        """
        source = QPixmap(source) if isinstance(source, str) else source
        if source.isNull():
            return
        scaled = source.scaled(_THUMB_W, _THUMB_H,
                               Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                               Qt.TransformationMode.SmoothTransformation)
        canvas = QPixmap(_THUMB_W, _THUMB_H)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(0, 0, _THUMB_W, _THUMB_H), 6, 6)
        painter.setClipPath(shape)
        painter.drawPixmap(0, 0, scaled)
        painter.end()
        self._thumb.setPixmap(canvas)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # 名字按可用宽度中段省略，完整路径留在 tooltip
        room = max(40, self.width() - _THUMB_W - 36)
        self._name.setText(QFontMetrics(self._name.font()).elidedText(
            self._asset.path.name, Qt.TextElideMode.ElideMiddle, room))


# ---------------------------------------------------------------- 页面样式

#: 页内样式取用的主题令牌：两套色板都必须齐全，缺键在拼表时就炸出来
QSS_KEYS = (
    "accent", "accent_dark", "accent_hover", "accent_hover_border",
    "background_alt", "border", "border_hover", "button_hover", "disabled_bg",
    "disabled_border", "drag_active_bg", "drop_border", "item_border",
    "on_accent", "progress_bg", "surface", "surface_hover", "surface_pressed",
    "text", "text_disabled", "text_muted",
)


def page_qss() -> str:
    """页内样式表：颜色现取当前色板，昼夜切换时整张重建。

    绝不能出现 QVideoWidget 选择器——与 app 级样式表重打磨并发会原生崩溃。
    """
    missing = [key for key in QSS_KEYS
               for mode in theme.PALETTES if key not in theme.PALETTES[mode]]
    if missing:
        raise KeyError(f"色板缺令牌：{sorted(set(missing))}")
    c = theme.color
    return f"""
    VideoClipPage QLabel {{ font-size: 12px; color: {c('text')}; }}
    /* 页级样式表离 widget 更近，上面的泛规则在实测中会盖掉应用级的
       #sectionEyebrow/#pageTitle（eyebrow 变黑、标题缩到 12px——
       2026-10-05 用户截图对比其它工具页发现）。这里按全局规格显式
       补回，保证与 BaseToolPage 其它页同一版式。 */
    VideoClipPage QLabel#sectionEyebrow {{
        color: {c('accent')}; font-size: 12px; font-weight: 600; }}
    VideoClipPage QLabel#pageTitle {{
        color: {c('text')}; font-size: 24px; font-weight: 700; }}
    VideoClipPage QLabel#mutedLabel {{ color: {c('text_muted')}; font-size: 11px; }}
    VideoClipPage QLabel#crewPanelTitle {{
        font-size: 13px; font-weight: 650; color: {c('text')}; }}
    VideoClipPage QFrame#clipCard {{
        background-color: {c('background_alt')};
        border: 1px solid {c('item_border')}; border-radius: 10px; }}
    VideoClipPage QFrame#clipCard:hover {{ border-color: {c('border_hover')}; }}
    VideoClipPage QFrame#clipCard[active="true"] {{
        background-color: {c('drag_active_bg')};
        border: 1px solid {c('accent')}; }}
    VideoClipPage QLabel#clipCardName {{
        color: {c('text')}; font-size: 12px; font-weight: 600; }}
    VideoClipPage QLabel#clipCardMeta {{
        color: {c('text_muted')}; font-size: 11px;
        font-family: Consolas, 'Segoe UI Mono', monospace; }}
    VideoClipPage QLabel#clipThumb {{ background-color: {c('disabled_bg')}; }}
    VideoClipPage QListWidget#clipList {{
        background: transparent; border: none; outline: none; font-size: 12px; }}
    VideoClipPage QListWidget#clipList::item {{
        background: transparent; border: none; padding: 0; }}
    VideoClipPage QListWidget#clipList::item:selected {{ background: transparent; }}
    VideoClipPage QListWidget#clipFolder {{
        background-color: {c('background_alt')}; border: 1px solid {c('item_border')};
        border-radius: 9px; font-size: 12px; padding: 3px; outline: none; }}
    VideoClipPage QListWidget#clipFolder::item {{
        border: none; border-radius: 6px; padding: 5px 8px; color: {c('text')}; }}
    VideoClipPage QListWidget#clipFolder::item:hover {{
        background-color: {c('surface_hover')}; }}
    VideoClipPage QListWidget#clipFolder::item:selected {{
        background-color: {c('accent')}; color: {c('on_accent')}; font-weight: 600; }}
    VideoClipPage QLabel#clipChip {{
        color: {c('text_muted')}; background-color: {c('background_alt')};
        border: 1px solid {c('border')}; border-radius: 10px;
        padding: 2px 9px; font-size: 11px; font-weight: 600; }}
    VideoClipPage QLabel#clipClock {{
        color: {c('text_muted')}; font-size: 11px; font-weight: 600;
        font-family: Consolas, 'Segoe UI Mono', monospace; }}
    VideoClipPage QFrame#clipField {{
        background-color: {c('background_alt')}; border: 1px solid {c('border')};
        border-radius: 9px; }}
    VideoClipPage QLabel#clipFieldLabel {{
        color: {c('text_muted')}; font-size: 10px; font-weight: 600; }}
    VideoClipPage QLabel#clipFieldValue {{
        color: {c('text')}; font-size: 12px; font-weight: 650;
        font-family: Consolas, 'Segoe UI Mono', monospace; }}
    VideoClipPage QToolButton#clipTool {{
        background-color: {c('surface')}; border: 1px solid {c('border')};
        border-radius: 8px; padding: 0; margin: 0; }}
    VideoClipPage QToolButton#clipTool:hover:enabled {{
        background-color: {c('button_hover')}; border-color: {c('border_hover')}; }}
    VideoClipPage QToolButton#clipTool:pressed:enabled {{
        background-color: {c('surface_pressed')}; }}
    VideoClipPage QToolButton#clipTool:disabled {{
        background-color: {c('disabled_bg')}; border-color: {c('disabled_border')}; }}
    VideoClipPage QToolButton#clipPlayBtn {{
        background-color: {c('accent')}; border: 1px solid {c('accent')};
        border-radius: 18px; padding: 0; margin: 0; }}
    VideoClipPage QToolButton#clipPlayBtn:hover {{
        background-color: {c('accent_hover')};
        border-color: {c('accent_hover_border')}; }}
    VideoClipPage QFrame#clipSegment {{
        background-color: {c('background_alt')}; border: 1px solid {c('border')};
        border-radius: 10px; }}
    VideoClipPage QPushButton#clipSegmentBtn {{
        background: transparent; border: none; border-radius: 8px;
        padding: 5px 10px; min-height: 0; font-size: 12px;
        color: {c('text_muted')}; font-weight: 600; }}
    VideoClipPage QPushButton#clipSegmentBtn:hover {{ color: {c('text')}; }}
    VideoClipPage QPushButton#clipSegmentBtn:checked {{
        background-color: {c('accent')}; color: {c('on_accent')}; }}
    VideoClipPage QPushButton#clipGhost {{
        background-color: {c('surface')}; border: 1px dashed {c('drop_border')};
        border-radius: 9px; padding: 5px 12px; min-height: 26px; font-size: 12px;
        color: {c('text')}; font-weight: 600; }}
    VideoClipPage QPushButton#clipGhost:hover {{
        background-color: {c('drag_active_bg')}; border-color: {c('accent')};
        color: {c('accent')}; }}
    VideoClipPage QPushButton#clipSoft {{
        background-color: {c('surface_hover')}; border: 1px solid {c('border')};
        border-radius: 9px; padding: 5px 12px; min-height: 30px; font-size: 12px;
        color: {c('text')}; font-weight: 600; }}
    VideoClipPage QPushButton#clipSoft:hover {{
        background-color: {c('button_hover')}; border-color: {c('border_hover')}; }}
    VideoClipPage QPushButton#clipSoft:disabled {{
        color: {c('text_disabled')}; background-color: {c('disabled_bg')};
        border-color: {c('disabled_border')}; }}
    VideoClipPage QPushButton#clipPrimary {{
        color: {c('on_accent')}; background-color: {c('accent')};
        border: 1px solid {c('accent')}; border-radius: 9px;
        min-height: 34px; font-size: 13px; font-weight: 700; }}
    VideoClipPage QPushButton#clipPrimary:hover {{
        background-color: {c('accent_hover')};
        border-color: {c('accent_hover_border')}; }}
    VideoClipPage QPushButton#clipPrimary:pressed {{
        background-color: {c('accent_dark')}; }}
    VideoClipPage QPushButton#clipPrimary:disabled {{
        color: {c('text_disabled')}; background-color: {c('disabled_bg')};
        border-color: {c('disabled_border')}; }}
    VideoClipPage QComboBox#clipSpeed {{
        background-color: {c('surface')}; border: 1px solid {c('border')};
        border-radius: 8px; padding: 2px 6px; min-height: 22px; font-size: 11px;
        font-weight: 600; color: {c('text')}; }}
    VideoClipPage QComboBox#clipSpeed:hover {{ border-color: {c('border_hover')}; }}
    VideoClipPage QComboBox#clipSpeed QAbstractItemView {{
        background-color: {c('surface')}; color: {c('text')};
        border: 1px solid {c('border')}; outline: none;
        selection-background-color: {c('accent')}; selection-color: {c('on_accent')}; }}
    VideoClipPage QSlider#clipScrub::groove:horizontal {{
        height: 4px; border-radius: 2px; background: {c('border')}; }}
    VideoClipPage QSlider#clipScrub::sub-page:horizontal {{
        background: {c('accent')}; border-radius: 2px; }}
    VideoClipPage QSlider#clipScrub::handle:horizontal {{
        width: 12px; height: 12px; margin: -4px -6px; border: none;
        border-radius: 6px; background: {c('text')}; }}
    VideoClipPage QSlider#clipScrub::handle:horizontal:hover {{
        background: {c('accent')}; }}
    VideoClipPage QSlider#clipZoom::groove:horizontal {{
        height: 3px; border-radius: 1px; background: {c('progress_bg')}; }}
    VideoClipPage QSlider#clipZoom::sub-page:horizontal {{
        background: {c('accent_dark')}; border-radius: 1px; }}
    VideoClipPage QSlider#clipZoom::handle:horizontal {{
        width: 10px; height: 10px; margin: -4px -5px; border: none;
        border-radius: 5px; background: {c('text_muted')}; }}
    VideoClipPage QSlider#clipZoom::handle:horizontal:hover {{
        background: {c('accent')}; }}
    """


class VideoClipPage(BaseToolPage):
    """视频裁剪工作台页面。"""

    #: 导出进度/完成回传（工作线程 → GUI 线程）
    _export_report = Signal(int)
    _export_finish = Signal(str)
    #: 探测完成回传（工作线程 → GUI 线程）：(序号, 路径, VideoAsset|None, 错误)
    _probe_ready = Signal(int, str, object, str)
    #: 胶片带/封面就绪（工作线程 → GUI 线程）：(素材行号, png 路径, 帧数)
    #: 帧数为 0 表示这条路只出了封面（胶片带失败退回单帧抽图）
    _preview_ready = Signal(int, str, int)
    #: 胶片带就绪（工作线程 → GUI 线程）：(令牌, png 路径, 帧数)
    _strip_ready = Signal(int, str, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__('video', tr('page.video.title'), parent)
        self._labeled: list[tuple[QWidget, str]] = []
        self._tips: list[tuple[QWidget, str]] = []
        self._tools: list[tuple[QWidget, str, str]] = []
        self._assets: list[VideoAsset] = []
        self._cards: dict[int, MediaCard] = {}
        self._current: VideoAsset | None = None
        self._current_row = -1
        self._model: ClipTimelineModel | None = None
        # 剪辑态曾只有一份模型：切走再切回，上一段的裁剪/撤销
        # 栈全丢。按素材行号各自留档，来回切换零丢失
        self._models: dict[int, ClipTimelineModel] = {}
        # 波形与胶片带按行号留档：切回看过的素材立即上屏，不再等后台任务
        self._wave_cache: dict[int, tuple[tuple[float, float], ...]] = {}
        self._preview_cache: dict[int, tuple[str, int]] = {}
        # 预览任务在飞行中的行号：导入即选中，选中与预览并发时会把同一条
        # 素材的全片解码跑两遍——有在飞任务就不再补一次
        self._preview_inflight: set[int] = set()
        # 攒着等合并出图的素材（行号 → 素材）：探测边落地边攒，探测收尾
        # （或攒满一批）后一条 ffmpeg 把这批胶片带全出，进程数 N→1
        self._strip_queue: dict[int, VideoAsset] = {}
        self._export_thread: threading.Thread | None = None
        # 胶片带 latest-wins：令牌只认最后一次请求，旧结果回传即丢
        self._strip_token = 0
        self._strip_thread: threading.Thread | None = None
        self._silence_worker: SilenceDetectWorker | None = None
        self._silence_thread: threading.Thread | None = None
        self._silence_cancel: threading.Event | None = None
        self._export_format = "video"
        # 导出命名：默认自动编号（raw-footage-1），前缀记进偏好，下次还在
        self._export_naming = _NAMING_MODES[0]
        self._clip_prefix = sanitize_clip_prefix(
            str(get_preference(CLIP_PREFIX_SETTING, DEFAULT_CLIP_PREFIX)))
        # I/O 选区（对齐剪映入点/出点）：按素材行号留档，切换素材不丢
        self._region_in: int | None = None
        self._region_out: int | None = None
        self._regions: dict[int, tuple[int | None, int | None]] = {}
        # ffprobe 曾同步跑在 GUI 线程（单文件最长 60s 超时），
        # 拖拽即"未响应"——探测改后台异步化；此前是单线程串行队列，多素材
        # 导入要一个一个等，现改为有界并发 + 序号重排，既并行又保序
        self._probe_pool = HimariUehara(_PROBE_WORKERS, 'video-probe')
        self._preview_pool = HimariUehara(_PREVIEW_WORKERS, 'video-preview')
        self._probe_seq = 0
        self._probe_next = 1
        self._probe_buffer: dict[int, tuple[str, object, str]] = {}
        self._probe_seen: set[str] = set()
        self._probe_pending = 0
        self._status_text = ""
        # 导出目标目录（当前说话人 + 用途）与最近一次导出结果：给「打开位置」
        # 按钮用，避免用户拿着一条长路径自己去找
        self._target_dir: Path | None = None
        self._last_exported: Path | None = None
        #: 「打开位置」拉起的 explorer 进程句柄：保活引用避免 GC 期 ResourceWarning
        self._explorer_proc: subprocess.Popen[bytes] | None = None
        self._wave_worker: WaveformWorker | None = None
        # 波形解码串行 + latest-wins：宽度 1 的池保证同一时刻只解一条
        self._wave_pool = HimariUehara(1, 'clip-waveform')
        self._wave_target = ""
        self._wave_rows: dict[str, int] = {}  # clip_id → 行号：解码结果不浪费
        self._frame_clock = QElapsedTimer()
        self._frame_clock.start()
        self._speakers: list[Path] = []
        self._purpose = PURPOSE_FOLDERS[0]
        self._scrubbing = False
        self.status_panel.setVisible(False)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # 时间轴先建：传输条与工具条的回调都指向它，构建顺序不能倒
        self._timeline = ClipTimeline()
        self._timeline.seek_requested.connect(self._on_timeline_seek)
        self._timeline.selection_changed.connect(self._refresh_clip_state)
        self._timeline.zoom_changed.connect(self._on_zoom_changed)
        self._timeline.edit_action.connect(self._on_edit_action)
        self._apply_page_style()
        self._build_body()
        self._export_report.connect(self._progress.setValue)
        self._export_finish.connect(self._on_export_finished)
        self._probe_ready.connect(self._on_probe_ready)
        self._preview_ready.connect(self._on_preview_ready)
        self._strip_ready.connect(self._on_strip_ready)
        # 说话人目录建不出来（配置盘只读/被占用）曾让整页构造
        # 抛异常，应用起不来——降级成空列表 + 提示，导出入口再拦一道
        try:
            self._speakers = ensure_speaker_folders()
        except OSError as error:
            self._speakers = []
            self._status_text = tr('video.clip.speaker_init_fail',
                                   detail=str(error)[-200:])
        self._refresh_speakers()
        on_mode_changed(self._on_mode_changed)
        self.destroyed.connect(lambda: off_mode_changed(self._on_mode_changed))
        # 错误日志：Python 层错误进 JSON；原生崩溃栈由 faulthandler 转储兜底
        self._errorlog = RokkaAsahi()
        enable_crash_log()
        self._player.errorOccurred.connect(self._on_player_error)
        self._refresh_icons()
        self._refresh_clip_state()
        self._on_zoom_changed()

    # ---------------------------------------------------------------- 主题

    def _apply_page_style(self) -> None:
        self.setStyleSheet(page_qss())

    def _on_mode_changed(self, mode: str) -> None:
        _ = mode
        # 主题通知在全局重打磨中途派发，同步触碰自绘控件会原生崩溃；
        # 延后到下一轮事件循环再重绘与重画图标
        QTimer.singleShot(0, self._retheme)

    @Slot()
    def _retheme(self) -> None:
        self._apply_page_style()
        self._refresh_icons()
        self._timeline.update()

    def _refresh_icons(self) -> None:
        """图标颜色烘焙在 QPixmap 里：换肤与播放/静音态切换都要重画。"""
        for button, name, role in self._tools:
            if role == 'play':
                playing = (self._player.playbackState()
                           == QMediaPlayer.PlaybackState.PlayingState)
                name = 'pause' if playing else 'play'
                color = theme.color('on_accent')
            elif role == 'mute':
                name = 'mute' if self._audio_output.isMuted() else 'volume'
                color = theme.color('text')
            elif role == 'accent':
                color = theme.color('accent')
            elif role == 'on_accent':
                color = theme.color('on_accent')
            else:
                color = theme.color('text')
            button.setIcon(_clip_icon(name, color))

    # ---------------------------------------------------------------- 拖放

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local:
                self.import_video(Path(local))
        event.acceptProposedAction()

    # ---------------------------------------------------------------- 布局

    def _build_body(self) -> None:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self._build_media_panel(), 0)
        top.addWidget(self._build_player_panel(), 1)
        top.addWidget(self._build_export_panel(), 0)
        layout.addLayout(top, 3)

        layout.addWidget(self._build_timeline_panel(), 2)
        self.set_body_widget(body)

    def _panel(self, title_key: str) -> tuple[QFrame, QVBoxLayout, QHBoxLayout, QLabel]:
        """卡片面板：必须是 QFrame，全局选择器是 `QFrame#placeholderPanel`。"""
        panel = QFrame()
        panel.setObjectName('placeholderPanel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(tr(title_key))
        title.setObjectName('crewPanelTitle')
        self._labeled.append((title, title_key))
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)
        return panel, layout, header, title

    def _chip(self, text: str = "") -> QLabel:
        chip = QLabel(text)
        chip.setObjectName('clipChip')
        return chip

    def _tool_button(self, name: str, tip_key: str, handler, *,
                     role: str = 'plain', side: int = 30) -> QToolButton:
        button = QToolButton()
        button.setObjectName('clipPlayBtn' if role == 'play' else 'clipTool')
        button.setFixedSize(side, side)
        button.setIconSize(QSize(_ICON_PX, _ICON_PX))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        # 按钮绝不能拿焦点：否则空格会被"再点一次"截走，播放快捷键失效
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(handler)
        self._tools.append((button, name, role))
        self._tips.append((button, tip_key))
        return button

    def _build_media_panel(self) -> QWidget:
        panel, layout, header, _title = self._panel('video.clip.upload')
        panel.setMinimumWidth(272)
        self._media_chip = self._chip(tr('video.clip.media.count', n=0))
        header.addWidget(self._media_chip)

        self._add_button = QPushButton(tr('video.clip.add'))
        self._add_button.setObjectName('clipGhost')
        self._add_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._add_button.clicked.connect(self._add_videos)
        self._labeled.append((self._add_button, 'video.clip.add'))
        self._tips.append((self._add_button, 'video.clip.tip.add'))
        self._tools.append((self._add_button, 'import', 'accent'))
        layout.addWidget(self._add_button)

        self._asset_list = QListWidget()
        self._asset_list.setObjectName('clipList')
        self._asset_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._asset_list.setSpacing(6)
        self._asset_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._asset_list.currentRowChanged.connect(self._on_asset_selected)
        layout.addWidget(self._asset_list, 1)
        return panel

    def _build_player_panel(self) -> QWidget:
        panel, layout, header, title = self._panel('video.clip.player')
        self._player_title = title
        header.addWidget(self._chip(tr('video.clip.preview')))

        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.playbackStateChanged.connect(lambda _state: self._refresh_icons())

        # 预览不用原生合成窗口：它与昼夜切换的全局重打磨并发会把 backing
        # store 打成 painter 活跃态，随后重绘随机 SIGSEGV（对照实验：
        # 原生形态崩、QVideoSink 软件取帧形态稳定）。改走手动取帧。
        self._preview_label = QLabel(tr('video.clip.preview_empty'))
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumHeight(168)
        self._preview_label.setAutoFillBackground(True)
        palette = self._preview_label.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor('#000000'))
        palette.setColor(QPalette.ColorRole.WindowText, QColor('#6b7280'))
        self._preview_label.setPalette(palette)
        self._preview_label.setScaledContents(False)
        self._video_widget = self._preview_label
        self._preview_sink = QVideoSink(self)
        self._preview_sink.videoFrameChanged.connect(self._on_video_frame)
        self._player.setVideoSink(self._preview_sink)
        layout.addWidget(self._preview_label, 1)

        self._scrub = QSlider(Qt.Orientation.Horizontal)
        self._scrub.setObjectName('clipScrub')
        self._scrub.setRange(0, 0)
        self._scrub.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._scrub.sliderPressed.connect(lambda: setattr(self, '_scrubbing', True))
        self._scrub.sliderReleased.connect(self._on_scrub_released)
        self._scrub.sliderMoved.connect(self._on_scrub_moved)
        layout.addWidget(self._scrub)

        transport = QHBoxLayout()
        transport.setSpacing(5)
        self._clock_left = QLabel(format_tc(0))
        self._clock_left.setObjectName('clipClock')
        self._clock_right = QLabel(format_tc(0))
        self._clock_right.setObjectName('clipClock')
        transport.addWidget(self._clock_left)
        transport.addStretch(1)
        transport.addWidget(self._tool_button(
            'start', 'video.clip.tip.start', lambda: self._timeline.seek(0)))
        transport.addWidget(self._tool_button(
            'prev', 'video.clip.tip.prev',
            lambda: self._timeline.nudge(-_FRAME_MS)))
        self._play_button = self._tool_button('play', 'video.clip.tip.play',
                                              self._toggle_play, role='play',
                                              side=36)
        transport.addWidget(self._play_button)
        transport.addWidget(self._tool_button(
            'next', 'video.clip.tip.next',
            lambda: self._timeline.nudge(_FRAME_MS)))
        transport.addWidget(self._tool_button('end', 'video.clip.tip.end',
                                              self._jump_end))
        transport.addSpacing(8)
        self._mute_button = self._tool_button('volume', 'video.clip.tip.mute',
                                              self._toggle_mute, role='mute')
        transport.addWidget(self._mute_button)
        self._speed_combo = QComboBox()
        self._speed_combo.setObjectName('clipSpeed')
        self._speed_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for speed in _SPEEDS:
            self._speed_combo.addItem(f"{speed:g}×", speed)
        self._speed_combo.setCurrentIndex(1)
        self._speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        transport.addWidget(self._speed_combo)
        transport.addStretch(1)
        transport.addWidget(self._clock_right)
        layout.addLayout(transport)

        info = QHBoxLayout()
        info.setSpacing(6)
        self._in_value = self._info_field('video.clip.info.in', info)
        self._out_value = self._info_field('video.clip.info.out', info)
        self._len_value = self._info_field('video.clip.info.len', info)
        layout.addLayout(info)
        return panel

    def _info_field(self, key: str, parent_layout: QHBoxLayout) -> QLabel:
        field = QFrame()
        field.setObjectName('clipField')
        column = QVBoxLayout(field)
        column.setContentsMargins(10, 4, 10, 4)
        column.setSpacing(0)
        label = QLabel(tr(key))
        label.setObjectName('clipFieldLabel')
        value = QLabel(_DASH)
        value.setObjectName('clipFieldValue')
        self._labeled.append((label, key))
        column.addWidget(label)
        column.addWidget(value)
        parent_layout.addWidget(field, 1)
        return value

    @Slot(object)
    def _on_video_frame(self, frame) -> None:
        if not frame.isValid() or not self.isVisible():
            return
        # 曾按解码帧率逐帧 toImage+Smooth 缩放，GUI 线程被
        # 打满且短命包装海量进出 GC（段错误诱因放大器）——节流到 30fps 上限
        if self._frame_clock.elapsed() < _MIN_FRAME_MS:
            return
        self._frame_clock.restart()
        image = frame.toImage()
        if image.isNull():
            return
        self._preview_label.setPixmap(QPixmap.fromImage(image).scaled(
            self._preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation))

    def _build_export_panel(self) -> QWidget:
        panel, layout, _header, _title = self._panel('video.clip.speakers')
        panel.setMinimumWidth(268)

        self._folder_list = QListWidget()
        self._folder_list.setObjectName('clipFolder')
        self._folder_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._folder_list.setMaximumHeight(94)
        self._folder_list.currentRowChanged.connect(
            lambda _row: self._on_target_scope_changed())
        layout.addWidget(self._folder_list)

        # 说话人管理（2026-10-03：自定义命名 + 增删，目录即身份，素材随目录走）
        manage = QFrame()
        manage.setObjectName('clipSegment')
        manage_row = QHBoxLayout(manage)
        manage_row.setContentsMargins(3, 3, 3, 3)
        manage_row.setSpacing(3)
        self._speaker_rename_btn = QPushButton(tr('video.clip.speaker.rename'))
        self._speaker_add_btn = QPushButton(tr('video.clip.speaker.add'))
        self._speaker_remove_btn = QPushButton(tr('video.clip.speaker.remove'))
        for button, key in (
                (self._speaker_rename_btn, 'video.clip.speaker.rename'),
                (self._speaker_add_btn, 'video.clip.speaker.add'),
                (self._speaker_remove_btn, 'video.clip.speaker.remove')):
            button.setObjectName('clipSegmentBtn')
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._labeled.append((button, key))
            manage_row.addWidget(button, 1)
        self._speaker_rename_btn.clicked.connect(self._rename_speaker)
        self._speaker_add_btn.clicked.connect(self._add_speaker)
        self._speaker_remove_btn.clicked.connect(self._remove_speaker)
        layout.addWidget(manage)

        segment = QFrame()
        segment.setObjectName('clipSegment')
        row = QHBoxLayout(segment)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(3)
        self._purpose_buttons: list[QPushButton] = []
        for purpose in PURPOSE_FOLDERS:
            button = QPushButton(purpose)
            button.setObjectName('clipSegmentBtn')
            button.setCheckable(True)
            button.setChecked(purpose == self._purpose)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(
                lambda _checked, name=purpose: self._select_purpose(name))
            self._purpose_buttons.append(button)
            row.addWidget(button, 1)
        layout.addWidget(segment)

        self._purpose_hint = QLabel(self._purpose_hint_text())
        self._purpose_hint.setObjectName('mutedLabel')
        self._purpose_hint.setWordWrap(True)
        layout.addWidget(self._purpose_hint)

        hint_row = QHBoxLayout()
        hint_row.setSpacing(4)
        self._speaker_hint = QLabel("")
        self._speaker_hint.setObjectName('mutedLabel')
        self._speaker_hint.setWordWrap(False)
        # 水平策略取 Ignored：省略宽度由布局给的剩余空间说了算，长路径不会
        # 反向把导出面板撑宽（撑宽会把三面板布局挤变形）
        self._speaker_hint.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        hint_row.addWidget(self._speaker_hint, 1)
        self._open_target_btn = QPushButton(tr('video.clip.target.open'))
        self._open_target_btn.setObjectName('clipGhost')
        self._open_target_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._open_target_btn.clicked.connect(self._open_target_folder)
        self._labeled.append((self._open_target_btn, 'video.clip.target.open'))
        self._tips.append((self._open_target_btn, 'video.clip.target.open.tip'))
        self._open_target_btn.setEnabled(False)
        hint_row.addWidget(self._open_target_btn, 0)
        layout.addLayout(hint_row)

        fmt = QFrame()
        fmt.setObjectName('clipSegment')
        fmt_row = QHBoxLayout(fmt)
        fmt_row.setContentsMargins(3, 3, 3, 3)
        fmt_row.setSpacing(3)
        self._format_buttons: list[tuple[QPushButton, str]] = []
        for key, value in (('video.clip.format.video', 'video'),
                           ('video.clip.format.wav', 'wav')):
            button = QPushButton(tr(key))
            button.setObjectName('clipSegmentBtn')
            button.setCheckable(True)
            button.setChecked(value == self._export_format)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(
                lambda _checked, name=value: self._select_format(name))
            self._format_buttons.append((button, value))
            self._labeled.append((button, key))
            fmt_row.addWidget(button, 1)
        layout.addWidget(fmt)

        # 命名：剪出来的素材按 `<前缀>-<序号>` 落名，预览给出下一个会被叫的名字
        naming = QFrame()
        naming.setObjectName('clipSegment')
        naming_row = QHBoxLayout(naming)
        naming_row.setContentsMargins(3, 3, 3, 3)
        naming_row.setSpacing(3)
        self._naming_buttons: list[tuple[QPushButton, str]] = []
        for key, value in (('video.clip.name.auto', 'auto'),
                           ('video.clip.name.source', 'source')):
            button = QPushButton(tr(key))
            button.setObjectName('clipSegmentBtn')
            button.setCheckable(True)
            button.setChecked(value == self._export_naming)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(
                lambda _checked, name=value: self._select_naming(name))
            self._naming_buttons.append((button, value))
            self._labeled.append((button, key))
            naming_row.addWidget(button, 1)
        layout.addWidget(naming)

        prefix_row = QHBoxLayout()
        prefix_row.setSpacing(4)
        self._prefix_label = QLabel(tr('video.clip.name.prefix'))
        self._prefix_label.setObjectName('mutedLabel')
        self._labeled.append((self._prefix_label, 'video.clip.name.prefix'))
        prefix_row.addWidget(self._prefix_label)
        self._prefix_edit = QLineEdit(self._clip_prefix)
        self._prefix_edit.setObjectName('clipPrefix')
        self._prefix_edit.setFixedWidth(118)
        # 边打字边预览，提交（失焦/回车）时才净化回写并落盘：打字过程中改写
        # 输入框内容会把光标顶走
        self._prefix_edit.textChanged.connect(self._refresh_name_preview)
        self._prefix_edit.editingFinished.connect(self._on_prefix_committed)
        self._tips.append((self._prefix_edit, 'video.clip.name.prefix.tip'))
        # 沿用源文件名时前缀没意义：禁用但不清空，切回自动编号还是原来那个
        self._prefix_edit.setEnabled(self._export_naming == 'auto')
        prefix_row.addWidget(self._prefix_edit, 1)
        # 前缀是持久化的：写脏了（手滑一大串字符、旧版残留）得有路子退回默认，
        # 不然用户只能去 settings.ini 里手改
        self._prefix_reset_btn = QPushButton(tr('video.clip.name.reset'))
        self._prefix_reset_btn.setObjectName('clipGhost')
        self._prefix_reset_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._prefix_reset_btn.clicked.connect(self._reset_prefix)
        self._labeled.append((self._prefix_reset_btn, 'video.clip.name.reset'))
        self._tips.append((self._prefix_reset_btn, 'video.clip.name.reset.tip'))
        self._prefix_reset_btn.setEnabled(self._export_naming == 'auto')
        prefix_row.addWidget(self._prefix_reset_btn, 0)
        layout.addLayout(prefix_row)

        self._name_preview = QLabel("")
        self._name_preview.setObjectName('mutedLabel')
        self._name_preview.setWordWrap(False)
        self._name_preview.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._name_preview)

        layout.addStretch(1)
        self._export_btn = QPushButton(tr('video.clip.export'))
        self._export_btn.setObjectName('clipPrimary')
        self._export_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._export_btn.clicked.connect(self._export_selected)
        self._labeled.append((self._export_btn, 'video.clip.export'))
        self._tools.append((self._export_btn, 'export', 'on_accent'))
        layout.addWidget(self._export_btn)
        self._export_all_btn = QPushButton(tr('video.clip.export_all'))
        self._export_all_btn.setObjectName('clipSoft')
        self._export_all_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._export_all_btn.clicked.connect(self._export_all_segments)
        self._labeled.append((self._export_all_btn, 'video.clip.export_all'))
        self._tools.append((self._export_all_btn, 'export_all', 'accent'))
        layout.addWidget(self._export_all_btn)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)
        return panel

    def _build_timeline_panel(self) -> QWidget:
        panel, layout, header, _title = self._panel('video.clip.timeline')
        self._summary_chip = self._chip(
            tr('video.clip.summary', n=0, tc=format_clock(0)))
        header.addWidget(self._summary_chip)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        self._split_btn = self._tool_button('split', 'video.clip.tip.split',
                                            self._split_center)
        self._trim_left_btn = self._tool_button('trim_left',
                                                'video.clip.tip.trim_left',
                                                self._trim_left)
        self._trim_right_btn = self._tool_button('trim_right',
                                                 'video.clip.tip.trim_right',
                                                 self._trim_right)
        self._delete_btn = self._tool_button('trash', 'video.clip.tip.delete',
                                             self._delete_selected)
        for button in (self._split_btn, self._trim_left_btn,
                       self._trim_right_btn, self._delete_btn):
            toolbar.addWidget(button)
        toolbar.addSpacing(10)
        self._undo_btn = self._tool_button('undo', 'video.clip.tip.undo', self._undo)
        self._redo_btn = self._tool_button('redo', 'video.clip.tip.redo', self._redo)
        toolbar.addWidget(self._undo_btn)
        toolbar.addWidget(self._redo_btn)
        toolbar.addSpacing(10)
        self._autocut_btn = self._tool_button('autocut', 'video.clip.tip.autocut',
                                              self._detect_silence)
        toolbar.addWidget(self._autocut_btn)
        toolbar.addSpacing(10)
        self._zoom_out_btn = self._tool_button('zoom_out', 'video.clip.tip.zoom_out',
                                               self._timeline.zoom_out)
        self._zoom_in_btn = self._tool_button('zoom_in', 'video.clip.tip.zoom_in',
                                              self._timeline.zoom_in)
        self._fit_btn = self._tool_button('fit', 'video.clip.tip.fit',
                                          self._fit_timeline)
        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setObjectName('clipZoom')
        self._zoom_slider.setRange(0, 100)
        self._zoom_slider.setValue(50)
        self._zoom_slider.setFixedWidth(150)
        self._zoom_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._zoom_slider.valueChanged.connect(self._on_zoom_slider)
        toolbar.addWidget(self._zoom_out_btn)
        toolbar.addWidget(self._zoom_slider)
        toolbar.addWidget(self._zoom_in_btn)
        toolbar.addSpacing(6)
        toolbar.addWidget(self._fit_btn)
        toolbar.addStretch(1)
        self._zoom_label = self._chip()
        toolbar.addWidget(self._zoom_label)
        layout.addLayout(toolbar)

        # 静音切句确认条：候选段必须人工勾选后"应用"才写进模型
        self._autocut_bar = QFrame()
        self._autocut_bar.setObjectName('clipSegment')
        bar = QHBoxLayout(self._autocut_bar)
        bar.setContentsMargins(10, 5, 8, 5)
        bar.setSpacing(8)
        self._autocut_label = QLabel(tr('video.clip.autocut.bar', n=0, m=0))
        self._autocut_label.setObjectName('mutedLabel')
        bar.addWidget(self._autocut_label, 1)
        self._autocut_apply = QPushButton(tr('video.clip.autocut.apply'))
        self._autocut_apply.setObjectName('clipGhost')
        self._autocut_apply.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._autocut_apply.clicked.connect(self._apply_proposals)
        self._autocut_cancel = QPushButton(tr('video.clip.autocut.cancel'))
        self._autocut_cancel.setObjectName('clipGhost')
        self._autocut_cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._autocut_cancel.clicked.connect(self._cancel_proposals)
        self._labeled.append((self._autocut_apply, 'video.clip.autocut.apply'))
        self._labeled.append((self._autocut_cancel, 'video.clip.autocut.cancel'))
        bar.addWidget(self._autocut_apply)
        bar.addWidget(self._autocut_cancel)
        self._autocut_bar.setVisible(False)
        layout.addWidget(self._autocut_bar)

        layout.addWidget(self._timeline, 1)

        hint = QLabel(tr('video.clip.shortcuts.hint'))
        hint.setObjectName('mutedLabel')
        hint.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._tips.append((hint, 'video.clip.shortcuts.hint'))
        layout.addWidget(hint)
        return panel

    # ---------------------------------------------------------------- i18n

    def retranslate(self) -> None:
        super().retranslate()
        for widget, key in self._labeled:
            widget.setText(tr(key))
        for widget, key in self._tips:
            widget.setToolTip(tr(key))
        self._purpose_hint.setText(self._purpose_hint_text())
        self._refresh_clip_state()
        self._refresh_target_label()
        self._refresh_name_preview()

    # ---------------------------------------------------------------- 素材库

    def _add_videos(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, tr('video.clip.add'), '',
            'Video (*.mp4 *.mov *.mkv *.avi *.webm *.wav)')
        for name in files:
            self.import_video(Path(name))

    def import_video(self, path: Path) -> None:
        """编程入口（测试/拖拽扩展用）。探测后台化：入队即返回，并发但保序。"""
        target = Path(path)
        key = str(target).casefold()
        # 同一个文件反复拖入/点开会重复建卡片、重复抽帧；
        # 已在列表里就直接聚焦到那一行，重复探测不做第二次
        if key in self._probe_seen:
            self._focus_asset(key)
            return
        self._probe_seen.add(key)
        self._probe_seq += 1
        self._probe_pending += 1
        self._refresh_import_hint()
        self._probe_pool.submit(
            lambda seq=self._probe_seq, item=target: self._probe_work(seq, item))

    def _focus_asset(self, key: str) -> None:
        for row, asset in enumerate(self._assets):
            if str(asset.path).casefold() == key:
                self._asset_list.setCurrentRow(row)
                return

    def _probe_work(self, seq: int, path: Path) -> None:
        """单个素材的探测：结果带序号回传，由 GUI 线程按序号重排。"""
        try:
            asset, error = probe_video(path), ""
        # 这里曾只接 (OSError, ValueError)：ffprobe 超时抛的是
        # TimeoutExpired，接不住就把探测线程整条带走，队列里剩下的素材永远
        # 没人处理（导入静默半途而废）。工作线程边界一律宽容接住
        except Exception as exc:  # noqa: BLE001
            asset, error = None, str(exc)
        self._probe_ready.emit(seq, str(path), asset, error)

    @Slot(int, str, object, str)
    def _on_probe_ready(self, seq: int, path: str, asset: object,
                        error: str) -> None:
        self._probe_pending = max(0, self._probe_pending - 1)
        self._probe_buffer[seq] = (path, asset, error)
        # 并发探测完成顺序不定：按序号连续段依次落列表，拖入顺序就是列表顺序
        while self._probe_next in self._probe_buffer:
            item_path, item_asset, item_error = self._probe_buffer.pop(
                self._probe_next)
            self._probe_next += 1
            self._on_probe_result(item_path, item_asset, item_error)
        self._refresh_import_hint()

    def _on_probe_result(self, path: str, asset: object, error: str) -> None:
        if error or not isinstance(asset, VideoAsset):
            self._probe_seen.discard(str(path).casefold())
            self._errorlog.record("import", error or "unknown", source=path)
            self._set_status(
                tr('video.clip.import_fail', detail=(error or "unknown")[-200:]))
            return
        self._assets.append(asset)
        row = len(self._assets) - 1
        card = MediaCard(asset)
        item = QListWidgetItem()
        item.setSizeHint(card.sizeHint())
        item.setData(Qt.ItemDataRole.UserRole, row)
        self._asset_list.addItem(item)
        self._asset_list.setItemWidget(item, card)
        self._cards[row] = card
        # 必须先标记"在飞"再切选中：setCurrentRow 会同步触发选中回调，晚一步
        # 标记就又补一次全片解码
        self._preview_inflight.add(row)
        self._asset_list.setCurrentRow(self._asset_list.count() - 1)
        self._strip_queue[row] = asset
        self._flush_strip_queue()

    def _flush_strip_queue(self) -> None:
        """把攒下的素材压成一条 ffmpeg 出胶片带。

        攒批时机：这批探测已全部落地（末尾那条一到就 flush，冷导入只等
        一次出图），或攒到上限先走一波，免得超大导入把最后几张封面拖太久。
        单条素材立刻出图，交互路径不因攒批而变慢。
        """
        if not self._strip_queue:
            return
        if self._probe_pending > 0 and len(self._strip_queue) < _STRIP_BATCH_MAX:
            return
        batch = self._strip_queue
        self._strip_queue = {}
        self._preview_pool.submit(
            lambda items=batch: self._preview_work(items))

    def _preview_work(self, batch: dict[int, VideoAsset]) -> None:
        """一条抽帧同时出这批素材的胶片带与封面：胶片带第 0 帧即封面。

        坏素材不连坐：批量命令失败或个别图缺失时由服务层逐素材回退，回退也
        失败的（无视频轨/纯音频）再退单帧封面，封面拿不到就留空。
        """
        paths = [(asset.path, asset.duration_ms) for asset in batch.values()]
        try:
            done, failed = make_filmstrips_batch(paths, _THUMB_DIR)
        except Exception as exc:  # noqa: BLE001  后台边界：整批都没出图
            done, failed = {}, {asset.path: str(exc) for asset in batch.values()}
        for row, asset in batch.items():
            strip = done.get(asset.path)
            if strip is not None:
                self._preview_ready.emit(row, str(strip),
                                         filmstrip_frames(asset.duration_ms))
                continue
            if asset.path in failed:
                self._errorlog.record("filmstrip", failed[asset.path],
                                      source=str(asset.path))
            try:
                thumb = make_thumbnail(asset.path, _THUMB_DIR)
            except Exception:  # noqa: BLE001  纯音频素材本来就没有封面
                thumb = None
            # 失败也要回一次：否则这一行永远留在"在飞"集合里
            self._preview_ready.emit(row, str(thumb) if thumb else "", 0)

    @Slot(int, str, int)
    def _on_preview_ready(self, row: int, path: str, frames: int) -> None:
        self._preview_inflight.discard(row)
        if path:
            self._preview_cache[row] = (path, frames)
        card = self._cards.get(row)
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        if frames > 0:
            if row == self._current_row:
                self._timeline.set_filmstrip(pixmap, frames)
            if card is not None:
                width = max(1, pixmap.width() // max(1, frames))
                card.set_thumbnail(pixmap.copy(0, 0, width, pixmap.height()))
        elif card is not None:
            card.set_thumbnail(pixmap)

    def _on_asset_selected(self, row: int) -> None:
        if not 0 <= row < len(self._assets):
            return
        # 选区与模型一样按行号留档：切走前收进字典，切回来后恢复
        if 0 <= self._current_row < len(self._assets) and self._current_row != row:
            self._regions[self._current_row] = (self._region_in, self._region_out)
        for index, card in self._cards.items():
            card.set_active(index == row)
        self._current = self._assets[row]
        self._current_row = row
        # 换素材可能换容器后缀（.mp4 ↔ .mkv），命名预览跟着更新
        self._refresh_name_preview()
        model = self._models.get(row)
        if model is None:
            model = ClipTimelineModel(self._current.duration_ms)
            model.selected = 0
            self._models[row] = model
        self._model = model
        self._timeline.set_model(self._model)
        # 看过的素材直接回放缓存：不等后台任务，切换是瞬时的
        self._timeline.set_peaks(self._wave_cache.get(row, ()))
        cached = self._preview_cache.get(row)
        if cached is None:
            self._timeline.set_filmstrip(None, 0)
        else:
            pixmap = QPixmap(cached[0])
            if not pixmap.isNull():
                self._timeline.set_filmstrip(pixmap, cached[1])
        self._timeline.clear_proposals()
        self._autocut_bar.setVisible(False)
        self._region_in, self._region_out = self._regions.get(row, (None, None))
        self._sync_region()
        self._player_title.setText(
            tr('video.clip.player_file', name=self._current.path.name))
        self._clock_right.setText(format_tc(self._current.duration_ms))
        self._clock_left.setText(format_tc(0))
        self._scrub.setRange(0, self._current.duration_ms)
        self._scrub.setValue(0)
        self._preview_label.setText("")
        self._player.setSource(QUrl.fromLocalFile(str(self._current.path)))
        self._player.pause()
        if row not in self._wave_cache:
            # 曾用普通闭包桥接 worker 信号——闭包无 QObject 上下文，
            # 回调在发射线程（工作线程）直连执行，等于从后台线程摸 QWidget；
            # 直连页面方法（GUI 线程 QObject）后 AutoConnection 自动 queued。
            # 时长由探测结果带进来，省掉 worker 内部再跑一次 ffprobe
            worker = WaveformWorker(str(self._current.path),
                                    self._current.path,
                                    self._current.duration_ms)
            worker.finished.connect(self._on_waveform)
            self._wave_worker = worker
            self._request_waveform(worker)
        if cached is None:
            self._request_filmstrip(self._current)
        self._refresh_clip_state()

    def _request_waveform(self, worker: WaveformWorker) -> None:
        """波形解码 latest-wins：只为"最终停留"的那条素材解音频。

        批量导入会依次自动选中每一行，逐行解一遍音频等于给所有素材都跑一次
        全片解码，而屏幕上只需要最后一条。目标被更新时排队中的旧任务直接放弃。
        """
        self._wave_target = worker.clip_id
        self._wave_rows[worker.clip_id] = self._current_row
        self._wave_pool.submit(
            lambda item=worker: self._wave_work(item))

    def _wave_work(self, worker: WaveformWorker) -> None:
        if self._wave_target != worker.clip_id:
            return  # 已被更新的目标取代：不白跑一次全片解码
        try:
            worker.run()
        except Exception as error:  # noqa: BLE001  后台边界：转日志，不拖死池
            _LOGGER.error("waveform failed: %s", error)

    def _on_waveform(self, clip_id: str, duration_ms: int, waveform: object,
                     error: str) -> None:
        _ = duration_ms
        if error or waveform is None or self._current is None:
            return
        envelope = cast(WaveformEnvelope, waveform)
        # worker 回传的是 WaveformEnvelope（无 __iter__），
        # tuple() 必抛 TypeError、波形永不显示——0 层即全时长峰值层，直接上屏
        peaks = envelope.levels[0]
        row = self._wave_rows.get(clip_id, -1)
        if row >= 0:
            # 先留档再判时效：哪怕结果回来时用户已经切走，这份解码也不白做
            self._wave_cache[row] = peaks
        # 时效校验：过期结果不上屏，防快速连点时波形串台
        if str(self._current.path) != clip_id or row != self._current_row:
            return
        self._timeline.set_peaks(peaks)

    # ---------------------------------------------------------------- 胶片带

    def _request_filmstrip(self, asset: VideoAsset) -> None:
        """后台抽整条接触表：一次 ffmpeg 出图，时间轴缩放时零重抽。"""
        # 导入即选中时预览任务往往还在解码全片，这里再请求一次
        # 会让同一条素材被完整解码两遍——有在飞任务就交给它，结果回到当前行
        # 会自动上屏
        if self._current_row in self._preview_inflight:
            return
        self._strip_token += 1
        self._timeline.set_filmstrip(None, 0)
        self._strip_thread = threading.Thread(
            target=self._strip_work, args=(self._strip_token, asset),
            name='video-filmstrip', daemon=True)
        self._strip_thread.start()

    def _strip_work(self, token: int, asset: VideoAsset) -> None:
        try:
            strip = make_filmstrip(asset.path, _THUMB_DIR,
                                   duration_ms=asset.duration_ms)
        except (OSError, RuntimeError, ValueError) as exc:
            # 胶片带是观感增强项：失败退回纯色轨，不打断剪辑
            self._errorlog.record("filmstrip", str(exc), source=str(asset.path))
            return
        self._strip_ready.emit(token, str(strip),
                               filmstrip_frames(asset.duration_ms))

    @Slot(int, str, int)
    def _on_strip_ready(self, token: int, strip_path: str, frames: int) -> None:
        if token != self._strip_token:
            return  # latest-wins：切素材期间回传的旧胶片带一律丢弃
        pixmap = QPixmap(strip_path)
        if not pixmap.isNull():
            if self._current_row >= 0:
                self._preview_cache[self._current_row] = (strip_path, frames)
            self._timeline.set_filmstrip(pixmap, frames)

    # ---------------------------------------------------------------- 播放

    def _toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _jump_end(self) -> None:
        if self._model is not None:
            self._timeline.seek(self._model.duration_ms)

    def _toggle_mute(self) -> None:
        self._audio_output.setMuted(not self._audio_output.isMuted())
        self._refresh_icons()

    def _on_speed_changed(self, index: int) -> None:
        speed = self._speed_combo.itemData(index)
        if speed is not None:
            self._player.setPlaybackRate(float(speed))

    def _on_position_changed(self, position_ms: int) -> None:
        if self._model is None:
            return
        self._model.seek(position_ms)
        self._timeline.reveal_playhead()
        self._timeline.update()
        self._clock_left.setText(format_tc(position_ms))
        if not self._scrubbing:
            self._scrub.setValue(position_ms)

    def _on_scrub_moved(self, position_ms: int) -> None:
        self._clock_left.setText(format_tc(position_ms))
        self._timeline.seek(position_ms, emit=False)

    def _on_scrub_released(self) -> None:
        self._scrubbing = False
        self._on_timeline_seek(int(self._scrub.value()))

    def _on_timeline_seek(self, position_ms: int) -> None:
        self._player.setPosition(position_ms)
        self._clock_left.setText(format_tc(position_ms))
        if not self._scrubbing:
            self._scrub.setValue(position_ms)

    # ---------------------------------------------------------------- 剪辑态

    def _refresh_clip_state(self) -> None:
        """模型 → UI：入出点、时长、摘要芯片、按钮可用性。"""
        has_model = self._model is not None
        for button in (self._split_btn, self._trim_left_btn, self._trim_right_btn,
                       self._delete_btn, self._zoom_in_btn, self._zoom_out_btn,
                       self._fit_btn):
            button.setEnabled(has_model)
        self._zoom_slider.setEnabled(has_model)
        self._scrub.setEnabled(has_model)
        self._undo_btn.setEnabled(has_model and self._model.can_undo)
        self._redo_btn.setEnabled(has_model and self._model.can_redo)
        self._autocut_btn.setEnabled(has_model and not self._silence_busy())
        segment = self._model.selected_segment if has_model else None
        self._export_btn.setEnabled(segment is not None)
        segments = self._model.segments if has_model else []
        self._export_all_btn.setEnabled(bool(segments))
        for value in (self._in_value, self._out_value, self._len_value):
            value.setText(_DASH)
        if segment is not None:
            self._in_value.setText(format_tc(segment.start_ms))
            self._out_value.setText(format_tc(segment.end_ms))
            self._len_value.setText(format_tc(segment.end_ms - segment.start_ms))
        segments = self._model.segments if has_model else []
        kept = sum(item.end_ms - item.start_ms for item in segments)
        self._summary_chip.setText(tr('video.clip.summary', n=len(segments),
                                      tc=format_clock(kept)))
        self._refresh_import_hint()
        if self._autocut_bar.isVisible():
            self._refresh_autocut_bar()
        self._timeline.update()

    def _fit_timeline(self) -> None:
        self._timeline.fit()

    def _on_zoom_changed(self) -> None:
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(round(self._timeline.zoom_ratio() * 100))
        self._zoom_slider.blockSignals(False)
        self._zoom_label.setText(
            tr('video.clip.zoom.value', v=round(self._timeline.ms_per_px())))

    def _on_zoom_slider(self, value: int) -> None:
        ratio = max(0.0, min(1.0, value / 100.0))
        span = MS_PER_PX_MAX / MS_PER_PX_MIN
        self._timeline.set_ms_per_px(MS_PER_PX_MAX / (1.0 + ratio * (span - 1.0)))

    # ---------------------------------------------------------------- 剪辑操作

    def _trim_left(self) -> None:
        if self._model and self._model.trim_left():
            self._timeline.update()
            self._refresh_clip_state()

    def _trim_right(self) -> None:
        if self._model and self._model.trim_right():
            self._timeline.update()
            self._refresh_clip_state()

    def _split_center(self) -> None:
        if self._model and self._model.split_at():
            self._timeline.update()
            self._refresh_clip_state()

    def _delete_selected(self) -> None:
        if self._model and self._model.delete_selected():
            self._timeline.update()
            self._refresh_clip_state()

    def _undo(self) -> None:
        if self._model and self._model.undo():
            self._timeline.update()
            self._refresh_clip_state()

    def _redo(self) -> None:
        if self._model and self._model.redo():
            self._timeline.update()
            self._refresh_clip_state()

    # ---------------------------------------------------------------- 静音切句

    def _silence_busy(self) -> bool:
        return self._silence_thread is not None and self._silence_thread.is_alive()

    def _detect_silence(self) -> None:
        """后台跑 silencedetect；结果只进"候选"，写模型必须人工应用。"""
        if self._current is None or self._silence_busy():
            return
        self._autocut_label.setText(tr('video.clip.autocut.busy'))
        self._autocut_apply.setEnabled(False)
        self._autocut_bar.setVisible(True)
        cancel = threading.Event()
        self._silence_cancel = cancel
        items = ((str(self._current.path), 0, self._current.path, 0,
                  self._current.duration_ms),)
        worker = SilenceDetectWorker(items, _SILENCE_DB, _SILENCE_MIN_MS, cancel)
        worker.finished.connect(self._on_silence_finished)
        self._silence_worker = worker
        self._silence_thread = threading.Thread(
            target=worker.run, name='clip-silence', daemon=True)
        self._silence_thread.start()

    @Slot(object, str)
    def _on_silence_finished(self, results: object, error: str) -> None:
        self._autocut_apply.setEnabled(True)
        if error or not results:
            self._timeline.clear_proposals()
            self._autocut_bar.setVisible(False)
            self._set_status(
                tr('video.clip.autocut.fail', detail=error[-200:]) if error
                else tr('video.clip.autocut.none'))
            self._refresh_clip_state()
            return
        silences = sorted((int(item['start_ms']), int(item['end_ms']))
                          for item in results)
        speech = self._speech_ranges(silences)
        if not speech:
            self._timeline.clear_proposals()
            self._autocut_bar.setVisible(False)
            self._set_status(tr('video.clip.autocut.none'))
            self._refresh_clip_state()
            return
        self._timeline.set_proposals(speech)
        self._refresh_clip_state()

    def apply_external_proposals(self, source_stem: str,
                                 ranges: list[tuple[int, int]]) -> bool:
        """人声分离页送来的对白轨切点候选：同名素材在位才挂载。

        与页内 autocut 同一纪律——只挂 proposals，写模型仍须用户在界面
        确认应用（R2 契约的候选→决策两段式）。返回 False 表示当前素材
        不是同名源，调用方（MainWindow）负责向分离页回报。
        """
        if self._current is None or not ranges:
            return False
        if Path(self._current.path).stem != source_stem:
            return False
        cleaned = sorted((int(start), int(end)) for start, end in ranges)
        self._timeline.set_proposals(cleaned)
        self._refresh_clip_state()
        return True

    def _speech_ranges(self, silences: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """静音区间的补集即语音段：掐掉过短的，再把挨得近的合并成一句。"""
        duration = self._current.duration_ms
        ranges: list[list[int]] = []
        cursor = 0
        for start, end in silences:
            if start - cursor >= _MIN_SPEECH_MS:
                ranges.append([cursor, start])
            cursor = max(cursor, end)
        if duration - cursor >= _MIN_SPEECH_MS:
            ranges.append([cursor, duration])
        merged: list[list[int]] = []
        for start, end in ranges:
            if merged and start - merged[-1][1] < _MERGE_GAP_MS:
                merged[-1][1] = end
            else:
                merged.append([start, end])
        return [(start, end) for start, end in merged]

    def _refresh_autocut_bar(self) -> None:
        total, picked = self._timeline.proposal_state()
        self._autocut_label.setText(tr('video.clip.autocut.bar', n=total, m=picked))
        self._autocut_apply.setEnabled(picked > 0)

    def _apply_proposals(self) -> None:
        if self._model is None:
            return
        picked = self._timeline.proposal_selection()
        self._timeline.clear_proposals()
        self._autocut_bar.setVisible(False)
        if picked and self._model.replace_segments(picked):
            self._timeline.update()
        self._refresh_clip_state()

    def _cancel_proposals(self) -> None:
        if self._silence_cancel is not None:
            self._silence_cancel.set()
        self._timeline.clear_proposals()
        self._autocut_bar.setVisible(False)
        self._refresh_clip_state()

    # ---------------------------------------------------------------- I/O 选区

    def _mark_in(self) -> None:
        """I 设入点（剪映同键位）：只记标记，成对后才落成时间轴选区。"""
        if self._model is None:
            return
        self._region_in = self._model.playhead_ms
        self._set_status(tr('video.clip.region.in', tc=format_tc(self._region_in)))
        self._sync_region()

    def _mark_out(self) -> None:
        """O 设出点（剪映同键位）：与入点顺序无关，成对即选区。"""
        if self._model is None:
            return
        self._region_out = self._model.playhead_ms
        if self._region_in is None:
            self._set_status(tr('video.clip.region.out', tc=format_tc(self._region_out)))
        self._sync_region()

    def _sync_region(self) -> None:
        if self._model is None:
            return
        if self._region_in is not None and self._region_out is not None:
            start = min(self._region_in, self._region_out)
            end = max(self._region_in, self._region_out)
            if end - start >= MIN_SEGMENT_MS:
                self._timeline.set_region(start, end)
                self._set_status(tr('video.clip.region.set',
                                    a=format_tc(start), b=format_tc(end)))
                return
        self._timeline.clear_region()

    def _clear_region(self, *, quiet: bool = False) -> None:
        self._region_in = None
        self._region_out = None
        self._timeline.clear_region()
        if not quiet and self._model is not None:
            self._set_status(tr('video.clip.region.cleared'))

    def _keep_region(self) -> None:
        """仅保留选区：全部保留段与 I/O 选区求交，一步可撤销（剪映区域剪辑）。"""
        region = self._timeline.region()
        if self._model is None or region is None:
            return
        start, end = region
        clipped = [
            (max(segment.start_ms, start), min(segment.end_ms, end))
            for segment in self._model.segments
            if min(segment.end_ms, end) - max(segment.start_ms, start) >= MIN_SEGMENT_MS
        ]
        if not clipped or not self._model.replace_segments(clipped):
            self._set_status(tr('video.clip.region.empty'))
            return
        self._clear_region(quiet=True)
        self._timeline.update()
        self._refresh_clip_state()

    def _on_edit_action(self, action: str, ms: int) -> None:
        """时间轴右键菜单动作：与工具条/快捷键同一条模型路径，语义只有一份。"""
        if self._model is None:
            return
        if action == "undo":
            self._undo()
            return
        if action == "redo":
            self._redo()
            return
        if action == "keep_region":
            self._keep_region()
            return
        hit = self._model.segment_at(ms)
        if hit is None:
            return
        self._model.selected = hit
        if action == "split":
            self._timeline.seek(ms)  # 寻址同步预览，再按播放头分割
            if self._model.split_at():
                self._timeline.update()
        elif action == "delete":
            if self._model.delete_selected():
                self._timeline.update()
        self._refresh_clip_state()

    def _export_default(self) -> None:
        """Ctrl+E（剪映同键位）：有选中段导选中段，否则导出全部保留段。"""
        if self._model is None:
            return
        if self._model.selected_segment is not None:
            self._export_selected()
        elif self._model.segments:
            self._export_all_segments()
        else:
            self._set_status(tr('video.clip.no_selection'))

    # ---------------------------------------------------------------- 快捷键

    def keyPressEvent(self, event) -> None:
        """剪辑快捷键：工具条按钮 NoFocus，空格不会被截走。"""
        key = event.key()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        if ctrl and key == Qt.Key.Key_Z:
            self._redo() if shift else self._undo()
        elif ctrl and key == Qt.Key.Key_Y:
            self._redo()
        elif ctrl and key == Qt.Key.Key_B:
            self._split_center()  # 剪映同款分割键位，与本页 S 并存
        elif ctrl and key == Qt.Key.Key_E:
            self._export_default()  # 剪映同款导出键位
        elif ctrl and key == Qt.Key.Key_I:
            self._add_videos()  # 剪映同款导入键位
        elif alt and key == Qt.Key.Key_X:
            self._clear_region()  # 剪映同款取消选区
        elif key == Qt.Key.Key_Space:
            self._toggle_play()
        elif key == Qt.Key.Key_S:
            self._split_center()
        elif key == Qt.Key.Key_I:
            self._mark_in()
        elif key == Qt.Key.Key_O:
            self._mark_out()
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._delete_selected()
        elif key == Qt.Key.Key_Left:
            self._timeline.nudge(-1000 if shift else -_FRAME_MS)
        elif key == Qt.Key.Key_Right:
            self._timeline.nudge(1000 if shift else _FRAME_MS)
        elif key == Qt.Key.Key_Up:
            self._timeline.jump_cut_point(-1)  # 剪映 ↑/↓：上一/下一分割点
        elif key == Qt.Key.Key_Down:
            self._timeline.jump_cut_point(1)
        elif key == Qt.Key.Key_Home:
            self._timeline.seek(0)
        elif key == Qt.Key.Key_End:
            self._jump_end()
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._timeline.zoom_in()
        elif key == Qt.Key.Key_Minus:
            self._timeline.zoom_out()
        elif key == Qt.Key.Key_F:
            self._fit_timeline()
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    # ---------------------------------------------------------------- 导出

    def _purpose_hint_text(self) -> str:
        if self._purpose == "训练素材":
            return tr('video.clip.purpose.train.hint')
        return tr('video.clip.purpose.use.hint')

    def _select_purpose(self, name: str) -> None:
        self._purpose = name
        for button in self._purpose_buttons:
            button.setChecked(button.text() == name)
        self._purpose_hint.setText(self._purpose_hint_text())
        self._on_target_scope_changed()

    def _on_target_scope_changed(self) -> None:
        """切换说话人/用途：目标已换，上次导出那份不再代表眼前这个目标。

        不清的话，「打开位置」会把人带到上一次导出的旧文件上——目标都换了还
        停在原处，比不给按钮更让人困惑。
        """
        self._last_exported = None
        self._refresh_target_label()

    def _export_target_dir(self) -> Path:
        row = max(0, self._folder_list.currentRow())
        speaker = self._speakers[min(row, len(self._speakers) - 1)]
        return speaker / self._purpose

    def _refresh_target_label(self) -> None:
        """目标路径用面包屑显示，完整绝对路径进 tooltip；瞬时状态拼在后面。

        导出目标与"导入失败/已导出"曾抢同一个标签：先写的被
        后写的整条覆盖掉，用户看不到刚发生的事。常驻目标路径与瞬时状态合并
        输出，谁也不会被刷掉。

        直接打绝对路径时，盘符到说话人之间那段会被省略号吃掉
        （素材库根目录本身就不短），用户只看到一串 `...\\训练素材`——路径改按
        素材库相对化成面包屑，再加「打开位置」按钮，不必靠肉眼认路径。
        """
        target = self._export_target_dir() if self._speakers else None
        self._target_dir = target
        self._open_target_btn.setEnabled(target is not None)
        lead = tr('video.clip.target',
                  path=describe_clip_path(target)) if target else ""
        text = lead
        tip = str(target) if target else ""
        if self._status_text:
            text = f"{text}    {self._status_text}" if text else self._status_text
            tip = f"{tip}\n{self._status_text}" if tip else self._status_text
        if not text:
            self._speaker_hint.setText("")
            self._speaker_hint.setToolTip("")
            return
        self._speaker_hint.setToolTip(tip)
        room = max(60, self._speaker_hint.width())
        self._speaker_hint.setText(QFontMetrics(self._speaker_hint.font())
                                   .elidedText(text, Qt.TextElideMode.ElideMiddle,
                                               room))
        # 目标一变，命名预览跟着变（序号是按这个目录的既有文件算的）
        self._refresh_name_preview()

    def _open_target_folder(self) -> None:
        """在系统文件管理器里定位导出目标：单个文件时直接选中它本身。

        导出后不必让用户照着一条长路径自己找——点了就直接站在文件面前。
        """
        candidate = self._last_exported or self._target_dir
        if candidate is None:
            return
        candidate = Path(candidate)
        folder = candidate if candidate.is_dir() else candidate.parent
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self._set_status(tr('video.clip.open_fail',
                                detail=str(error)[-160:]))
            return
        # Windows 的 explorer /select, 能把文件本身高亮出来；其余平台（以及
        # 目标是目录时）走通用的 openUrl，落在所在文件夹上。
        # 进程句柄存到实例上：裸丢弃的 Popen 在子进程存活期被 GC 会发
        # ResourceWarning（explorer 启动即代理给已有实例，窗口期虽短但真实）
        if os.name == "nt" and candidate.is_file():
            self._explorer_proc = subprocess.Popen(["explorer", f"/select,{candidate}"])
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _set_status(self, text: str) -> None:
        """写一条瞬时状态（与目标路径合并显示）。"""
        self._status_text = text
        self._refresh_target_label()

    def _refresh_import_hint(self) -> None:
        """素材面板计数：导入进行中改显示待探测数，让用户知道界面没卡住。"""
        if self._probe_pending:
            self._media_chip.setText(
                tr('video.clip.importing', n=self._probe_pending))
        else:
            self._media_chip.setText(
                tr('video.clip.media.count', n=len(self._assets)))

    def _select_format(self, name: str) -> None:
        self._export_format = name
        for button, value in self._format_buttons:
            button.setChecked(value == name)
        self._refresh_name_preview()

    # —— 导出命名（自动编号 / 沿用源文件名） ——

    def _select_naming(self, mode: str) -> None:
        self._export_naming = mode
        for button, value in self._naming_buttons:
            button.setChecked(value == mode)
        self._prefix_edit.setEnabled(mode == 'auto')
        self._prefix_reset_btn.setEnabled(mode == 'auto')
        self._refresh_name_preview()

    def _reset_prefix(self) -> None:
        """把前缀退回默认：配置被写脏时的自愈入口。

        前缀是持久化的，一旦写脏（早期测试未打桩，把一串
        "ppp…" 真写进了 config/settings.ini）就会跨会话生效，用户只能在界面
        里看到一堆 p 却无从改起——持久化值必须配一个就地恢复默认的路子。
        """
        self._prefix_edit.setText(DEFAULT_CLIP_PREFIX)
        self._on_prefix_committed()
        self._set_status(tr('video.clip.name.reset_done',
                            prefix=DEFAULT_CLIP_PREFIX))

    def _prefix_now(self) -> str:
        """输入框当下的前缀（净化后）：还没提交也按它预览，所见即所得。"""
        return sanitize_clip_prefix(self._prefix_edit.text())

    def _on_prefix_committed(self) -> None:
        """提交前缀：净化后回写输入框并记进偏好。"""
        cleaned = self._prefix_now()
        self._clip_prefix = cleaned
        if cleaned != self._prefix_edit.text():
            # 回写净化结果：用户看得见斜杠/冒号是被去掉还是被换掉
            self._prefix_edit.blockSignals(True)
            self._prefix_edit.setText(cleaned)
            self._prefix_edit.blockSignals(False)
        set_preference(CLIP_PREFIX_SETTING, cleaned)
        self._refresh_name_preview()

    def _export_suffix(self) -> str:
        """导出后缀：wav 导出固定 .wav，原样复制沿用源容器。"""
        if self._export_format == 'wav':
            return '.wav'
        return self._current.path.suffix if self._current else _FALLBACK_SUFFIX

    def _refresh_name_preview(self) -> None:
        """预览下一个落盘文件名：导出前就能看出这批素材会被叫什么。

        序号按目标目录已有文件顺延，所以切换说话人/用途/格式、导出完成都要
        重算——不然预览停在旧号上，反而误导。
        """
        if self._target_dir is None:
            self._name_preview.setText("")
            self._name_preview.setToolTip("")
            return
        suffix = self._export_suffix()
        if self._export_naming == 'source':
            self._name_preview.setText(tr('video.clip.name.source.hint'))
            self._name_preview.setToolTip(tr('video.clip.name.source.hint'))
            return
        pending = next_clip_paths(self._target_dir, self._prefix_now(),
                                  suffix, 1)
        name = pending[0].name if pending else f"{self._prefix_now()}-1{suffix}"
        self._name_preview.setToolTip(name)
        room = max(60, self._name_preview.width())
        self._name_preview.setText(QFontMetrics(self._name_preview.font())
                                   .elidedText(tr('video.clip.name.next', name=name),
                                               Qt.TextElideMode.ElideRight, room))

    def _export_selected(self) -> None:
        segment = self._model.selected_segment if self._model else None
        if segment is None:
            self._set_status(tr('video.clip.no_selection'))
            return
        self._start_export([(segment.start_ms, segment.end_ms)])

    def _export_all_segments(self) -> None:
        if self._model is None or not self._model.segments:
            return
        self._start_export([(s.start_ms, s.end_ms) for s in self._model.segments])

    def _start_export(self, ranges: list[tuple[int, int]]) -> None:
        if self._export_thread is not None or self._current is None:
            return
        # 说话人目录建不出来时 `_export_target_dir()` 会按空
        # 列表取下标炸 IndexError——先拦一道，提示降级而不是崩
        if not self._speakers:
            self._set_status(tr('video.clip.target_missing'))
            return
        folder = self._export_target_dir()
        folder.mkdir(parents=True, exist_ok=True)
        suffix = self._export_suffix()
        if self._export_naming == 'auto':
            # 一批一段号：raw-footage-1 / -2 / -3，序号按目录已有文件顺延。
            # 取输入框当下值：编辑到一半就点导出，也按看见的那个前缀落
            prefix = self._prefix_now()
            self._clip_prefix = prefix
            targets = next_clip_paths(folder, prefix, suffix, len(ranges))
        else:
            stamp = datetime.now(tz=timezone.utc).strftime('%H%M%S%f')[:-3]
            targets: list[Path] = []
            for index, _range in enumerate(ranges):
                tag = f"_{index + 1:02d}" if len(ranges) > 1 else ""
                targets.append(
                    folder / f"{self._current.path.stem}_{stamp}{tag}{suffix}")
        jobs = [(start_ms, end_ms, target)
                for (start_ms, end_ms), target in zip(ranges, targets)]
        self._export_thread = threading.Thread(
            target=self._export_work,
            args=(self._current.path, jobs, self._export_format),
            name='video-clip-export', daemon=True)
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._export_thread.start()

    def _export_work(self, source: Path, jobs: list[tuple[int, int, Path]],
                     fmt: str) -> None:
        total = len(jobs)

        def progress(ratio: float, index: int) -> None:
            self._export_report.emit(int((index + ratio) * 100 / total))

        try:
            for index, (start_ms, end_ms, target) in enumerate(jobs):
                if fmt == 'wav':
                    cut_audio_segment(source, start_ms, end_ms, target)
                    progress(1.0, index)
                else:
                    cut_segment(source, start_ms, end_ms, target,
                                on_progress=lambda ratio, i=index: progress(ratio, i))
            if total == 1:
                written = jobs[0][2]
                # 记住就这一次：下次「打开位置」直接带到这个文件上
                self._last_exported = written
                text = tr('video.clip.export_done',
                          name=written.name,
                          path=describe_clip_path(written.parent))
            else:
                folder = jobs[0][2].parent
                self._last_exported = folder
                text = tr('video.clip.export_all_done', n=total,
                          path=describe_clip_path(folder))
        except (OSError, RuntimeError, ValueError) as exc:
            self._errorlog.record("export", str(exc), source=str(source))
            text = tr('video.clip.export_fail', detail=str(exc)[-300:])
        self._export_finish.emit(text)

    @Slot(str)
    def _on_export_finished(self, text: str) -> None:
        # 线程引用曾在工作线程里复位，与 GUI 线程的
        # is_busy 读取构成竞态——复位收敛到信号回传的 GUI 线程侧
        self._export_thread = None
        self._progress.setVisible(False)
        self._set_status(text)
        # 导出落盘后序号已前进：预览停在新号上，下一次导出才知道会叫什么
        self._refresh_name_preview()

    @Slot(int, str)
    def _on_player_error(self, error: int, error_string: str) -> None:
        self._errorlog.record("playback", f"{error}: {error_string}")

    # ---------------------------------------------------------------- 文件夹

    def _refresh_speakers(self) -> None:
        self._folder_list.clear()
        for speaker in self._speakers:
            self._folder_list.addItem(QListWidgetItem(speaker.name))
        if self._speakers:
            self._folder_list.setCurrentRow(0)
        self._refresh_target_label()

    # —— 说话人管理（自定义命名 / 增删；目录即身份，素材随目录走） ——

    def _selected_speaker(self) -> Path | None:
        row = self._folder_list.currentRow()
        if 0 <= row < len(self._speakers):
            return self._speakers[row]
        return None

    def _reload_speakers(self, *, select: Path | None = None) -> None:
        """重扫说话人目录并恢复选择（优先 select 指向的目录）。"""
        try:
            self._speakers = list_speaker_folders()
        except OSError as error:
            self._set_status(tr('video.clip.speaker_init_fail',
                                detail=str(error)[-200:]))
            return
        self._refresh_speakers()
        if select is not None:
            for row, speaker in enumerate(self._speakers):
                if speaker == select:
                    self._folder_list.setCurrentRow(row)
                    break

    def _rename_speaker(self) -> None:
        speaker = self._selected_speaker()
        if speaker is None:
            return
        if self.is_busy:
            self._set_status(tr('video.clip.speaker.busy'))
            return
        name, accepted = QInputDialog.getText(
            self, tr('video.clip.speaker.rename'),
            tr('video.clip.speaker.rename.prompt'), text=speaker.name)
        if not accepted:
            return
        try:
            renamed = rename_speaker_folder(speaker, name)
        except ValueError as error:
            self._set_status(str(error))
            return
        except OSError as error:
            self._set_status(tr('video.clip.speaker.failed',
                                detail=str(error)[-160:]))
            return
        self._reload_speakers(select=renamed)
        self._set_status(tr('video.clip.speaker.renamed',
                            old=speaker.name, new=renamed.name))

    def _add_speaker(self) -> None:
        if self.is_busy:
            self._set_status(tr('video.clip.speaker.busy'))
            return
        suggested = next_speaker_name()
        name, accepted = QInputDialog.getText(
            self, tr('video.clip.speaker.add'),
            tr('video.clip.speaker.add.prompt'), text=suggested)
        if not accepted:
            return
        try:
            added = add_speaker_folder(name)
        except ValueError as error:
            self._set_status(str(error))
            return
        except OSError as error:
            self._set_status(tr('video.clip.speaker.failed',
                                detail=str(error)[-160:]))
            return
        self._reload_speakers(select=added)
        self._set_status(tr('video.clip.speaker.added', name=added.name))

    def _remove_speaker(self) -> None:
        speaker = self._selected_speaker()
        if speaker is None:
            return
        if self.is_busy:
            self._set_status(tr('video.clip.speaker.busy'))
            return
        answer = QMessageBox.question(
            self, tr('video.clip.speaker.remove'),
            tr('video.clip.speaker.remove.confirm',
               name=speaker.name, path=str(speaker)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            remove_speaker_folder(speaker)
        except OSError as error:
            self._set_status(tr('video.clip.speaker.failed',
                                detail=str(error)[-160:]))
            return
        self._reload_speakers()
        self._set_status(tr('video.clip.speaker.removed', name=speaker.name))

    # ---------------------------------------------------------------- 页面态

    @property
    def is_busy(self) -> bool:
        return self._export_thread is not None

    def has_active_workers(self) -> bool:
        """任意视频页工作线程仍在飞行时返回 True（GC 安全局判定用）。"""
        return (self._probe_pool.busy() or self._preview_pool.busy()
                or self._wave_pool.busy()
                or any(thread is not None and thread.is_alive()
                       for thread in (self._strip_thread,
                                      self._silence_thread, self._export_thread)))

    def can_navigate_away(self) -> bool:
        if self.is_busy:
            return False
        self._player.pause()
        return True

    def request_safe_close(self) -> bool:
        return self.can_navigate_away()

    def hideEvent(self, event) -> None:
        # 页面切走时暂停播放器：视频渲染管线持续绘制与全局重打磨并发
        # 会把 backing store 打成 painter 活跃态，随后重绘可原生崩溃；
        # 页面不可见即停渲染，是这条竞态的釜底抽薪修法
        super().hideEvent(event)
        self._player.pause()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._timeline.update()
        self._refresh_target_label()

    def resizeEvent(self, event) -> None:
        # 省略宽度是按构造时的标签宽度算死的：面板变宽变窄后不重算，短路径会
        # 一直顶着刚建视图时的那点宽度被砍尾巴（宽了也留白，窄了溢出到看不见）
        super().resizeEvent(event)
        # 构造期就可能来一次 resize：那时面板里的标签还没建出来
        if hasattr(self, '_speaker_hint'):
            self._refresh_target_label()
