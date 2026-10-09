# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""剪辑时间轴：视频胶片带轨 + 音频波形轨的自绘控件。

语义与"源时间轴 + 保留段"对齐：轨道上只有 `ClipTimelineModel.segments`
覆盖的区间是保留内容，其余为空洞。交互含标尺擦洗、边缘修边、整段平移、
空洞框选新增段、边沿吸附、Ctrl+滚轮缩放。取色全部走 `clip_*` 主题令牌，
并在绘制期解析（不在主题广播回调里碰 QPainter），昼夜切换不留深色残影。
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QMenu, QWidget

from app.i18n import current_language, i18n_live
from app.services.video_clip_service import ClipSegment, ClipTimelineModel
from app.styles import theme

HEADER_W = 58
RULER_H = 28
LANE_GAP = 8
EDGE_GRAB_PX = 8
SNAP_PX = 5
DRAG_THRESHOLD_PX = 3
MIN_CLIP_MS = 50
ZOOM_STEP = 1.25
MS_PER_PX_MIN = 2.0
MS_PER_PX_MAX = 400.0
RADIUS = 7
CELL_PX = 96  # 胶片带单帧宽，与 `make_filmstrip` 对齐

RULER_STEPS = (100, 250, 500, 1000, 2000, 5000, 10000, 15000, 30000,
               60000, 120000, 300000)

CLIP_KEYS = (
    "clip_canvas", "clip_empty", "clip_ruler", "clip_ruler_text",
    "clip_ruler_major", "clip_ruler_minor", "clip_header", "clip_header_text",
    "clip_grid", "clip_video", "clip_video_top", "clip_video_bottom",
    "clip_video_text", "clip_audio", "clip_audio_top", "clip_audio_bottom",
    "clip_wave", "clip_selected", "clip_selected_glow", "clip_hover",
    "clip_playhead", "clip_playhead_text", "clip_scrim", "clip_badge",
    "clip_handle", "clip_muted",
)
_PALETTE_CACHE: dict[str, dict[str, QColor]] = {}


def palette() -> dict[str, QColor]:
    """按当前昼夜模式取色（绘制期调用；调色板静态，按模式缓存一次）。"""
    mode = theme.current_mode()
    cached = _PALETTE_CACHE.get(mode)
    if cached is None:
        table = theme.PALETTES[mode]
        cached = {key: QColor(table[key]) for key in CLIP_KEYS}
        _PALETTE_CACHE[mode] = cached
    return cached


def _tint(color: QColor, alpha: int) -> QColor:
    out = QColor(color)
    out.setAlpha(alpha)
    return out


def format_tc(ms: int) -> str:
    """剪辑器风格时码：HH:MM:SS:CC（百分秒）。"""
    total_cs = max(0, ms) // 10
    cs = total_cs % 100
    total_s = total_cs // 100
    return (f"{total_s // 3600:02d}:{total_s // 60 % 60:02d}:"
            f"{total_s % 60:02d}:{cs:02d}")


def format_clock(ms: int) -> str:
    """紧凑时码 MM:SS.CC，用于播放头胶囊与悬停提示。"""
    total = max(0, ms)
    return (f"{total // 60000:02d}:{total // 1000 % 60:02d}"
            f".{total % 1000 // 10:02d}")


def choose_ruler_step(ms_per_px: float) -> int:
    """按当前缩放选择标尺主刻度步长（目标主刻度间距 ≥ 70px）。"""
    for step in RULER_STEPS:
        if step / ms_per_px >= 70.0:
            return step
    return RULER_STEPS[-1]


def ruler_label(ms: int, step: int) -> str:
    """刻度文字随步长走：粗缩放读分秒，细缩放读秒百分位。"""
    if step >= 1000:
        return f"{ms // 60000:02d}:{ms // 1000 % 60:02d}"
    return format_clock(ms)


class ClipTimeline(QWidget):
    """全宽双轨时间轴：标尺 + 视频胶片带 + 音频波形 + 轨道头 + 播放头。"""

    #: 用户定位播放头（擦洗/点击/键盘）→ 页面驱动播放器
    seek_requested = Signal(int)
    #: 选中段或段边界变化 → 页面刷新时码与按钮态
    selection_changed = Signal()
    #: 缩放变化 → 页面同步缩放滑条与倍率文字
    zoom_changed = Signal()
    #: 右键菜单动作（动作名, 触发位置 ms）→ 页面统一执行，按钮态与撤销栈一致
    edit_action = Signal(str, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(210)
        self.setMouseTracking(True)
        # 键盘快捷键由页面 keyPressEvent 统一处理：时间轴需要能吃焦点并
        # 在不处理时把事件冒泡给父级，工具条按钮则设 NoFocus 防止抢空格
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._model: ClipTimelineModel | None = None
        self._peaks: tuple[tuple[float, float], ...] = ()
        self._peak_scale = 1.0
        self._fit_mode = False
        self._strip: QPixmap | None = None
        self._strip_frames = 0
        self._ms_per_px = 40.0
        self._offset_ms = 0.0
        self._drag_mode = ""  # '' | scrub | trim_l | trim_r | pending_move | move | marquee
        self._press_x = 0
        self._press_ms = 0
        self._move_delta = 0
        self._hover_ms: int | None = None
        self._marquee: tuple[int, int] | None = None
        # 分层重绘：轨道/胶片带/波形/标尺是"静态层"，缓存成离屏图，
        # 播放头/悬停/框选做叠层。播放时 positionChanged 每 tick 都 update()，
        # 全量重绘实测 27~47ms，会把 GUI 线程打满；缓存后每 tick 只剩 blit+画线
        self._layer: QPixmap | None = None
        self._layer_key: tuple = ()
        self._proposals: tuple[tuple[int, int], ...] = ()
        self._proposal_on: set[int] = set()
        self._proposal_mode = False
        self._gesture_open = False
        #: I/O 选区（入点/出点，对齐剪映）：只影响渲染与「仅保留选区」，不进模型
        self._region: tuple[int, int] | None = None

    # ---------------------------------------------------------------- data

    def set_model(self, model: ClipTimelineModel | None) -> None:
        self._model = model
        self._offset_ms = 0.0
        self._drag_mode = ""
        self._marquee = None
        self._region = None  # 换素材即换时间轴：选区不跨素材残留
        self._fit_mode = model is not None
        if model is not None:
            self.fit()  # 新素材默认整段铺满；宽度未定时由 resizeEvent 再补一次
        self.update()

    def model(self) -> ClipTimelineModel | None:
        return self._model

    def set_peaks(self, peaks: tuple[tuple[float, float], ...]) -> None:
        """收下全时长峰值层，并按本素材最大峰归一化。

        不归一化时轻素材（如 -20dB 配音）的波形只有几像素高，整条音轨
        看着像空的；拉到满幅后剪辑可读性一致，代价只是丢掉绝对响度信息。
        """
        self._peaks = peaks
        loudest = max((max(high, -low) for low, high in peaks), default=0.0)
        self._peak_scale = 1.0 / loudest if loudest > 1e-6 else 1.0
        self.update()

    def set_filmstrip(self, strip: QPixmap | None, frames: int) -> None:
        """挂载整条胶片带；帧数决定时间→列的线性映射，缩放时零重抽。"""
        self._strip = strip
        self._strip_frames = max(0, frames)
        self.update()

    # ---------------------------------------------------------- 静音切句提案

    def set_proposals(self, proposals: list[tuple[int, int]], *,
                      on: set[int] | None = None, mode: bool = True) -> None:
        """候选语音段：确认模式下画成可勾选色带，点一下勾/取消一段。"""
        self._proposals = tuple((int(a), int(b)) for a, b in proposals)
        self._proposal_on = (set(range(len(self._proposals))) if on is None
                             else set(on))
        self._proposal_mode = mode
        self.update()

    def clear_proposals(self) -> None:
        self._proposals = ()
        self._proposal_on = set()
        self._proposal_mode = False
        self.update()

    def proposal_selection(self) -> list[tuple[int, int]]:
        return [self._proposals[index]
                for index in sorted(self._proposal_on)
                if index < len(self._proposals)]

    def proposal_state(self) -> tuple[int, int]:
        """(候选总数, 已勾选数)：确认条文案用。"""
        return len(self._proposals), len(self._proposal_on)

    def _proposal_at(self, ms: int) -> int | None:
        for index, (start, end) in enumerate(self._proposals):
            if start <= ms < end:
                return index
        return None

    # ---------------------------------------------------------- 选区（入点/出点）

    def set_region(self, start_ms: int, end_ms: int) -> None:
        """设置 I/O 选区（对齐剪映）：仅作显示与「仅保留选区」依据，不改模型。"""
        if self._model is None:
            return
        start = max(0, min(self._model.duration_ms, int(start_ms)))
        end = max(0, min(self._model.duration_ms, int(end_ms)))
        if end - start < MIN_CLIP_MS:
            return
        self._region = (start, end)
        self.update()

    def clear_region(self) -> None:
        if self._region is not None:
            self._region = None
            self.update()

    def region(self) -> tuple[int, int] | None:
        return self._region

    def jump_cut_point(self, direction: int) -> None:
        """跳到上一/下一个分割点（段边界与素材首尾；对齐剪映 ↑/↓ 走切点）。"""
        if self._model is None:
            return
        points = {0, self._model.duration_ms}
        for segment in self._model.segments:
            points.add(segment.start_ms)
            points.add(segment.end_ms)
        playhead = self._model.playhead_ms
        if direction < 0:
            before = [point for point in points if point < playhead]
            target = max(before) if before else 0
        else:
            after = [point for point in points if point > playhead]
            target = min(after) if after else self._model.duration_ms
        self.seek(target)

    # ---------------------------------------------------------------- view

    def ms_per_px(self) -> float:
        return self._ms_per_px

    def _lane_w(self) -> int:
        return max(1, self.width() - HEADER_W - 2)

    def _visible_ms(self) -> float:
        return max(1.0, self._ms_per_px * self._lane_w())

    def _x_to_ms(self, x: int) -> int:
        return int(self._offset_ms + max(0, x - HEADER_W) * self._ms_per_px)

    def _ms_to_x(self, position_ms: float) -> int:
        return HEADER_W + int((position_ms - self._offset_ms) / self._ms_per_px)

    def _ms_to_fx(self, position_ms: float) -> float:
        return HEADER_W + (position_ms - self._offset_ms) / self._ms_per_px

    def _clamp_offset(self) -> None:
        if self._model is None:
            self._offset_ms = 0.0
            return
        limit = max(0.0, self._model.duration_ms - self._visible_ms())
        self._offset_ms = max(0.0, min(limit, self._offset_ms))

    def fit(self) -> None:
        """整段素材铺满轨道，并留在适应态：随后拉伸窗口继续跟着铺满。"""
        if self._model is None:
            return
        self._fit_mode = True
        self._apply_fit()
        self.zoom_changed.emit()
        self.update()

    def _apply_fit(self) -> None:
        self._ms_per_px = max(MS_PER_PX_MIN,
                              self._model.duration_ms / self._lane_w())
        self._offset_ms = 0.0

    def set_ms_per_px(self, value: float, anchor_ms: int | None = None) -> None:
        """改缩放：默认把播放头钉在屏幕原位，Ctrl+滚轮时以光标为锚。"""
        if self._model is None:
            return
        anchor = self._model.playhead_ms if anchor_ms is None else anchor_ms
        anchor_x = self._ms_to_fx(anchor)
        self._ms_per_px = max(MS_PER_PX_MIN, min(MS_PER_PX_MAX, value))
        self._fit_mode = False
        self._offset_ms = anchor - (anchor_x - HEADER_W) * self._ms_per_px
        self._clamp_offset()
        self.zoom_changed.emit()
        self.update()

    def zoom_in(self) -> None:
        self.set_ms_per_px(self._ms_per_px / ZOOM_STEP)

    def zoom_out(self) -> None:
        self.set_ms_per_px(self._ms_per_px * ZOOM_STEP)

    def zoom_ratio(self) -> float:
        """0..1 的缩放档位，供页面滑条回显（对数刻度）。"""
        span = MS_PER_PX_MAX / MS_PER_PX_MIN
        ratio = (MS_PER_PX_MAX / max(self._ms_per_px, MS_PER_PX_MIN) - 1.0) / (span - 1.0)
        return max(0.0, min(1.0, ratio))

    def reveal_playhead(self) -> None:
        """播放头被挤出视口时把它滚回来（键盘步进/修边后）。"""
        if self._model is None:
            return
        playhead = self._model.playhead_ms
        right = self._offset_ms + self._visible_ms()
        if playhead < self._offset_ms:
            self._offset_ms = max(0.0, playhead - self._visible_ms() * 0.1)
        elif playhead > right - self._ms_per_px * 16:
            self._offset_ms = playhead - self._visible_ms() * 0.85
        self._clamp_offset()

    def seek(self, ms: int, *, emit: bool = True) -> None:
        if self._model is None:
            return
        self._model.seek(ms)
        self.reveal_playhead()
        if emit:
            self.seek_requested.emit(self._model.playhead_ms)
        self.update()

    def nudge(self, delta_ms: int) -> None:
        if self._model is None:
            return
        self.seek(self._model.playhead_ms + delta_ms)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._model is None:
            return
        if self._fit_mode:
            # 适应态：宽度一变就重新铺满，"0 ms/px / 半屏空白"就是这么来的
            self._apply_fit()
            self.zoom_changed.emit()
        else:
            self._clamp_offset()
        self.update()

    # ---------------------------------------------------------------- hit

    def _edge_mode_at(self, x: int) -> str:
        segment = self._model.selected_segment if self._model else None
        if segment is None:
            return ""
        if abs(x - self._ms_to_x(segment.start_ms)) <= EDGE_GRAB_PX:
            return "trim_l"
        if abs(x - self._ms_to_x(segment.end_ms)) <= EDGE_GRAB_PX:
            return "trim_r"
        return ""

    def _snap(self, ms: int, moving: ClipSegment | None = None) -> int:
        """吸附到段边界与素材首尾；容差按像素折算，缩放后手感一致。"""
        if self._model is None:
            return ms
        tolerance = SNAP_PX * self._ms_per_px
        best, dist = ms, tolerance
        edges: list[int] = [0, self._model.duration_ms]
        for segment in self._model.segments:
            if segment is moving:
                continue
            edges.extend((segment.start_ms, segment.end_ms))
        for edge in edges:
            gap = abs(edge - ms)
            if gap <= dist:
                best, dist = edge, gap
        return best

    # ---------------------------------------------------------------- events

    def wheelEvent(self, event) -> None:
        if self._model is None:
            return
        delta = event.angleDelta().y() or event.angleDelta().x()
        if not delta:
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # 滚轮向上 = 放大（ms/px 变小）并与缩放按钮方向一致；
            # 此前取反，手感是"向上越看越远"
            self.set_ms_per_px(self._ms_per_px * (1.0 / ZOOM_STEP if delta > 0
                                                  else ZOOM_STEP),
                               anchor_ms=self._x_to_ms(int(event.position().x())))
            return
        self._fit_mode = False
        self._offset_ms += self._visible_ms() * (0.15 if delta < 0 else -0.15)
        self._clamp_offset()
        self.update()

    def mousePressEvent(self, event) -> None:
        if self._model is None or event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        x = int(event.position().x())
        if x < HEADER_W:
            return
        self._press_x = x
        self._press_ms = self._x_to_ms(x)
        if event.position().y() <= RULER_H:
            self._drag_mode = "scrub"
            self._apply_scrub(self._press_ms, snap=not event.modifiers()
                              & Qt.KeyboardModifier.ControlModifier)
            self.update()
            return
        if self._proposal_mode:
            # 确认模式：点击只负责勾/取消候选段，编辑手势一律让位
            hit = self._proposal_at(self._press_ms)
            if hit is not None:
                if hit in self._proposal_on:
                    self._proposal_on.discard(hit)
                else:
                    self._proposal_on.add(hit)
                self.selection_changed.emit()
                self.update()
                return
        self._gesture_open = False
        self._drag_mode = self._edge_mode_at(x)
        if self._drag_mode:
            self.update()
            return
        hit = self._model.segment_at(self._press_ms)
        if hit is None:
            self._drag_mode = "marquee"
            self._marquee = (self._press_ms, self._press_ms)
            self._apply_scrub(self._press_ms, snap=False)
        else:
            if hit != self._model.selected:
                self._model.selected = hit
                self.selection_changed.emit()
            self._drag_mode = "pending_move"
            self._apply_scrub(self._press_ms)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._model is None:
            return
        x = int(event.position().x())
        self._hover_ms = self._x_to_ms(x) if (x >= HEADER_W
                                              and event.position().y() > RULER_H) else None
        ms = self._x_to_ms(x)
        # 对齐剪映「按住 Ctrl 临时取消吸附」：修边/擦洗需要脱吸精修时不必进设置
        bypass = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if self._drag_mode == "scrub":
            self._apply_scrub(ms, snap=not bypass)
        elif self._drag_mode in ("trim_l", "trim_r"):
            self._apply_trim(ms, snap=not bypass)
        elif self._drag_mode == "pending_move":
            if abs(x - self._press_x) > DRAG_THRESHOLD_PX:
                self._drag_mode = "move"
                segment = self._model.selected_segment
                self._move_delta = (self._press_ms - segment.start_ms
                                    if segment else 0)
            self.update()
            return
        elif self._drag_mode == "move":
            self._apply_move(ms)
        elif self._drag_mode == "marquee" and self._marquee is not None:
            self._marquee = (self._marquee[0], ms)
            self._apply_scrub(ms, snap=False)
        elif not self._drag_mode:
            self._update_cursor(x, event.position().y())
        self.update()

    def _update_cursor(self, x: int, y: float) -> None:
        """光标即 affordance：标尺擦洗、边缘修边、段上拖动、空洞框选。"""
        if y <= RULER_H:
            self.setCursor(Qt.CursorShape.IBeamCursor)
        elif self._edge_mode_at(x):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif self._model is not None and self._model.segment_at(self._x_to_ms(x)) is not None:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:
        if self._model is None:
            return
        self._model.end_gesture()
        self._gesture_open = False
        if self._drag_mode == "marquee" and self._marquee is not None:
            start, end = sorted(self._marquee)
            self._marquee = None
            if (end - start > self._ms_per_px * DRAG_THRESHOLD_PX
                    and self._model.add_segment(start, end) is not None):
                self.selection_changed.emit()
        self._drag_mode = ""
        self.update()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._hover_ms = None
        self.update()

    def contextMenuEvent(self, event) -> None:
        """轨道右键菜单（对齐剪映）：编辑动作统一发信号给页面，不走旁路。

        动作可用性在此裁定（段上才能分割/删除、有选区才能仅保留、有历史
        才能撤销重做），执行全部交页面——撤销栈、按钮态、播放器寻址才能
        与工具条/快捷键路径保持同一份语义。
        """
        if self._model is None:
            return
        ms = self._x_to_ms(int(event.pos().x()))
        on_segment = self._model.segment_at(ms) is not None
        menu = QMenu(self)
        split = menu.addAction(i18n_live("video.clip.menu.split"))
        split.setEnabled(on_segment)
        delete = menu.addAction(i18n_live("video.clip.menu.delete"))
        delete.setEnabled(on_segment)
        keep = menu.addAction(i18n_live("video.clip.menu.keep_region"))
        keep.setEnabled(self._region is not None)
        menu.addSeparator()
        undo = menu.addAction(i18n_live("video.clip.menu.undo"))
        undo.setEnabled(self._model.can_undo)
        redo = menu.addAction(i18n_live("video.clip.menu.redo"))
        redo.setEnabled(self._model.can_redo)
        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return
        action_by_item = {
            split: "split", delete: "delete", keep: "keep_region",
            undo: "undo", redo: "redo",
        }
        action = action_by_item.get(chosen)
        if action is not None:
            self.edit_action.emit(action, ms)

    # ---------------------------------------------------------------- drags

    def _apply_scrub(self, ms: int, *, snap: bool = True) -> None:
        if self._model is None:
            return
        self._model.seek(self._snap(ms) if snap else ms)
        self.reveal_playhead()
        self.seek_requested.emit(self._model.playhead_ms)

    def _apply_trim(self, ms: int, *, snap: bool = True) -> None:
        segment = self._model.selected_segment if self._model else None
        if segment is None:
            return
        if not self._gesture_open:
            self._model.begin_gesture("trim")
            self._gesture_open = True
        snapped = self._snap(ms, moving=segment) if snap else ms
        if self._drag_mode == "trim_l":
            segment.start_ms = max(0, min(snapped, segment.end_ms - MIN_CLIP_MS))
        else:
            segment.end_ms = min(self._model.duration_ms,
                                 max(snapped, segment.start_ms + MIN_CLIP_MS))
        self._model.seek(snapped)
        self.seek_requested.emit(snapped)
        self.selection_changed.emit()

    def _apply_move(self, ms: int) -> None:
        if self._model is None:
            return
        if not self._gesture_open:
            self._model.begin_gesture("move")
            self._gesture_open = True
        if self._model.move_selected(ms - self._move_delta, record=False):
            self.selection_changed.emit()

    # ---------------------------------------------------------------- paint

    def paintEvent(self, event) -> None:
        colors = palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if self._model is None:
            painter.fillRect(self.rect(), colors["clip_canvas"])
            self._paint_empty(painter, colors)
            return
        # 静态层（轨道/胶片带/波形/切线/标尺/轨道头/提案带）缓存成离屏图：
        # 播放与擦洗每 tick 只改播放头，全量重绘实测 27~47ms，缓存后每 tick
        # 只剩一次 blit + 叠层画线
        key = self._static_key()
        if self._layer is None or self._layer_key != key:
            self._render_layer(colors, key)
        painter.drawPixmap(0, 0, self._layer)
        self._paint_marquee(painter, colors)
        self._paint_hover(painter, colors)
        self._paint_playhead(painter, colors)
        painter.setPen(QPen(_tint(colors["clip_grid"], 200), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def _static_key(self) -> tuple:
        """静态层失效键：任何影响轨道内容的状态都在里面，播放头故意不在。"""
        model = self._model
        return (self.width(), self.height(), round(self._ms_per_px, 4),
                round(self._offset_ms, 2), theme.current_mode(),
                current_language(), id(self._strip), self._strip_frames,
                id(self._peaks), model.selected,
                tuple((s.start_ms, s.end_ms) for s in model.segments),
                self._proposals, frozenset(self._proposal_on),
                self._proposal_mode, self._region)

    def _render_layer(self, colors: dict[str, QColor], key: tuple) -> None:
        dpr = max(1.0, self.devicePixelRatioF())
        layer = QPixmap(int(max(1, self.width()) * dpr),
                        int(max(1, self.height()) * dpr))
        layer.setDevicePixelRatio(dpr)
        layer.fill(Qt.GlobalColor.transparent)
        painter = QPainter(layer)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.fillRect(self.rect(), colors["clip_canvas"])
        self._paint_lanes(painter, colors)
        self._paint_track(painter, colors, self._video_lane(), "video")
        self._paint_track(painter, colors, self._audio_lane(), "audio")
        self._paint_cut_lines(painter, colors)
        self._paint_proposals(painter, colors)
        self._paint_region(painter, colors)
        self._paint_ruler(painter, colors)
        self._paint_headers(painter, colors)
        painter.end()
        self._layer = layer
        self._layer_key = key

    def sizeHint(self) -> QSize:
        return QSize(900, 260)

    def _paint_empty(self, painter: QPainter, colors: dict[str, QColor]) -> None:
        box = QRectF(self.rect().adjusted(16, 16, -17, -17))
        painter.setPen(QPen(colors["clip_grid"], 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(box, 10, 10)
        middle = box.center().y()
        title_font = QFont(self.font())
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(colors["clip_header_text"])
        painter.drawText(QRectF(box.left(), middle - 30, box.width(), 22),
                         Qt.AlignmentFlag.AlignCenter,
                         i18n_live("video.clip.empty"))
        hint_font = QFont(title_font)
        hint_font.setBold(False)
        hint_font.setPointSizeF(max(7.5, hint_font.pointSizeF() - 2))
        painter.setFont(hint_font)
        painter.setPen(colors["clip_muted"])
        painter.drawText(QRectF(box.left(), middle + 2, box.width(), 20),
                         Qt.AlignmentFlag.AlignCenter,
                         i18n_live("video.clip.empty.hint"))

    def _paint_lanes(self, painter: QPainter, colors: dict[str, QColor]) -> None:
        """轨道底 = 空洞色：保留段随后覆盖，未覆盖处天然读作"已裁掉"。

        有意保留 1px 描边（drawRoundedRect 顺带描笔）：无边轨在浅色主题下
        会和卡片底糊成一片，看不出这里有两条轨。
        """
        painter.setPen(QPen(_tint(colors["clip_grid"], 170), 1))
        painter.setBrush(colors["clip_empty"])
        for lane in (self._video_lane(), self._audio_lane()):
            painter.drawRoundedRect(QRectF(lane).adjusted(0.5, 0.5, -1.5, -1.5),
                                    RADIUS, RADIUS)

    def _lane_geometry(self) -> tuple[int, int, int, int]:
        """轨道区高度自适应：吃掉面板剩余空间，不留黑底空白。

        返回 (top, gap, video_h, audio_h)。两轨间距只在这一处决定，
        此前 `_audio_lane` 用 `video_h > 58` 反推 gap，与 `_lane_geometry`
        的 `body > 130` 判据不一致，窗口拉伸时轨间距会跳变。
        """
        top = RULER_H + 4
        body = max(76, self.height() - top - 6)
        gap = LANE_GAP if body > 130 else 5
        video_h = max(58, int((body - gap) * 0.58)) if body > 130 else (body - gap) // 2
        return top, gap, video_h, body - gap - video_h

    def _video_lane(self) -> QRect:
        top, _gap, video_h, _audio_h = self._lane_geometry()
        return QRect(HEADER_W, top, self.width() - HEADER_W - 2, video_h)

    def _audio_lane(self) -> QRect:
        top, gap, video_h, audio_h = self._lane_geometry()
        return QRect(HEADER_W, top + video_h + gap,
                     self.width() - HEADER_W - 2, audio_h)

    def _segment_rects(self, lane: QRect) -> list[tuple[int, QRectF]]:
        out: list[tuple[int, QRectF]] = []
        for index, segment in enumerate(self._model.segments):
            left = max(float(lane.left()), self._ms_to_fx(segment.start_ms))
            right = min(float(lane.right()), self._ms_to_fx(segment.end_ms))
            if right <= left:
                continue
            out.append((index, QRectF(left, lane.y() + 1,
                                      max(1.0, right - left), lane.height() - 2)))
        return out

    def _paint_track(self, painter: QPainter, colors: dict[str, QColor],
                     lane: QRect, kind: str) -> None:
        selected = self._model.selected
        for index, rect in self._segment_rects(lane):
            path = QPainterPath()
            path.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5),
                                RADIUS, RADIUS)
            painter.save()
            painter.setClipPath(path)
            painter.fillPath(path, self._clip_brush(colors, kind, rect))
            if kind == "video":
                self._paint_filmstrip(painter, colors, rect, index,
                                      index == selected)
            else:
                self._paint_wave(painter, colors, rect, index, index == selected)
            painter.restore()
            self._paint_chrome(painter, colors, rect, index, kind,
                               index == selected)

    def _clip_brush(self, colors: dict[str, QColor], kind: str,
                    rect: QRectF) -> QLinearGradient:
        """片段底永远是本轨渐变色：选中态交给描边与轻纱，不靠整块换色。

        曾经选中即整块铺 `clip_selected` 实色，结果音频轨糊成一条纯色带、
        视频轨胶片带被盖掉——"选中"反而最难读。
        """
        if kind == "video":
            top, mid, bottom = (colors["clip_video_top"], colors["clip_video"],
                                colors["clip_video_bottom"])
        else:
            top, mid, bottom = (colors["clip_audio_top"], colors["clip_audio"],
                                colors["clip_audio_bottom"])
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, top)
        grad.setColorAt(0.5, mid)
        grad.setColorAt(1.0, bottom)
        return grad

    def _paint_filmstrip(self, painter: QPainter, colors: dict[str, QColor],
                         rect: QRectF, index: int, selected: bool) -> None:
        """时间→帧列线性切片；单帧窄于一像素时退回纯色，避免摩尔纹。"""
        strip = self._strip
        if (strip is None or self._strip_frames <= 0 or strip.isNull()
                or rect.width() < 2):
            return
        duration = max(1, self._model.duration_ms)
        per_ms = duration / self._strip_frames
        if self._ms_per_px > per_ms * 0.9:
            return
        segment = self._model.segments[index]
        column_w = strip.width() / self._strip_frames
        for frame in range(self._strip_frames):
            first, last = frame * per_ms, (frame + 1) * per_ms
            start = max(first, segment.start_ms)
            end = min(last, segment.end_ms)
            if end <= start:
                continue
            left, right = self._ms_to_fx(start), self._ms_to_fx(end)
            if right < rect.left() or left > rect.right():
                continue
            source = QRectF(frame * column_w + (start - first) / per_ms * column_w,
                            0.0, (end - start) / per_ms * column_w,
                            float(strip.height()))
            painter.drawPixmap(QRectF(left, rect.y(), right - left, rect.height()),
                               strip, source)
        # 胶片带之上只压一层轻纱：选中给强调色、未选中给一点点暗纱统一色调，
        # 压重了会把画面盖成色块，胶片带就白画了
        wash = _tint(colors["clip_selected"], 54) if selected else _tint(
            colors["clip_scrim"], 18)
        painter.fillRect(rect, wash)

    def _paint_wave(self, painter: QPainter, colors: dict[str, QColor],
                    rect: QRectF, index: int, selected: bool) -> None:
        segment = self._model.segments[index]
        mid = rect.center().y()
        if not self._peaks:
            painter.setPen(QPen(_tint(colors["clip_wave"], 110), 1,
                                Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(rect.left(), mid), QPointF(rect.right(), mid))
            return
        total = len(self._peaks)
        duration = max(1, self._model.duration_ms)
        amp = max(2.0, rect.height() * 0.44)
        scale = self._peak_scale * amp
        step = 1 if rect.width() < 1600 else 2
        upper: list[QPointF] = []
        lower: list[QPointF] = []
        x = rect.left()
        while x <= rect.right():
            ms = self._x_to_ms(int(x))
            if segment.start_ms <= ms <= segment.end_ms:
                slot = min(total - 1, max(0, int(ms / duration * total)))
                low, high = self._peaks[slot]
                upper.append(QPointF(x, mid - max(0.7, high * scale)))
                lower.append(QPointF(x, mid + max(0.7, -low * scale)))
            x += step
        if not upper:
            return
        path = QPainterPath()
        path.moveTo(upper[0])
        for point in upper[1:]:
            path.lineTo(point)
        for point in reversed(lower):
            path.lineTo(point)
        path.closeSubpath()
        # 选中用 clip_selected（浅色主题里是深蓝），glow 是淡蓝压在淡紫底上
        # 几乎看不见
        color = colors["clip_selected"] if selected else colors["clip_wave"]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillPath(path, _tint(color, 240 if selected else 205))
        painter.setPen(QPen(_tint(color, 90), 1))
        painter.drawLine(QPointF(rect.left(), mid), QPointF(rect.right(), mid))

    def _paint_chrome(self, painter: QPainter, colors: dict[str, QColor],
                      rect: QRectF, index: int, kind: str,
                      selected: bool) -> None:
        """描边 + 边缘握把 + 四角手柄 + 序号/时长角标。"""
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if selected:
            # 外层柔光 + 内层实描：选中态在两轨上都一眼可辨
            painter.setPen(QPen(_tint(colors["clip_selected_glow"], 90), 4))
            painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), RADIUS, RADIUS)
            painter.setPen(QPen(colors["clip_selected"], 2))
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1),
                                    RADIUS - 1, RADIUS - 1)
        else:
            painter.setPen(QPen(_tint(colors["clip_grid"], 220), 1))
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5),
                                    RADIUS, RADIUS)
        if rect.width() < 24:
            return
        if selected:
            self._paint_handles(painter, colors, rect)
        if kind == "video":
            self._paint_labels(painter, colors, rect, index,
                               self._model.segments[index])

    def _paint_handles(self, painter: QPainter, colors: dict[str, QColor],
                       rect: QRectF) -> None:
        grip_h = min(26.0, max(14.0, rect.height() * 0.44))
        for edge_x in (rect.left(), rect.right()):
            bar = QRectF(edge_x - 2.0, rect.center().y() - grip_h / 2.0, 4.0,
                         grip_h)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colors["clip_handle"])
            painter.drawRoundedRect(bar, 2, 2)
            painter.setPen(QPen(colors["clip_selected"], 1))
            painter.drawLine(QPointF(bar.center().x(), bar.top() + 3.0),
                             QPointF(bar.center().x(), bar.bottom() - 3.0))
        if rect.width() < 46:
            return
        size = 6.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colors["clip_handle"])
        for corner in (rect.topLeft(), rect.topRight(), rect.bottomLeft(),
                       rect.bottomRight()):
            painter.drawRoundedRect(QRectF(corner.x() - size / 2.0,
                                           corner.y() - size / 2.0, size, size),
                                    2, 2)

    def _paint_labels(self, painter: QPainter, colors: dict[str, QColor],
                      rect: QRectF, index: int,
                      segment: ClipSegment) -> None:
        font = QFont(self.font())
        font.setPointSizeF(max(6.5, font.pointSizeF() - 2.5))
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        badge = _tint(colors["clip_badge"], 196)
        number = str(index + 1)
        width = metrics.horizontalAdvance(number) + 12
        if rect.width() > width + 12:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(badge)
            painter.drawRoundedRect(QRectF(rect.left() + 4, rect.top() + 4,
                                           width, 15), 7.5, 7.5)
            painter.setPen(colors["clip_video_text"])
            painter.drawText(QRectF(rect.left() + 4, rect.top() + 4, width, 15),
                             Qt.AlignmentFlag.AlignCenter, number)
        # 角标用紧凑时码：HH:MM:SS:CC 在小片段上会顶满角标、读起来也累
        duration = format_clock(segment.end_ms - segment.start_ms)
        text_w = metrics.horizontalAdvance(duration) + 10
        if rect.width() > text_w + 14 and rect.height() > 32:
            box = QRectF(rect.right() - text_w - 5, rect.bottom() - 19,
                         text_w, 15)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(badge)
            painter.drawRoundedRect(box, 7.5, 7.5)
            painter.setPen(colors["clip_video_text"])
            painter.drawText(box.adjusted(5, 0, -5, 0),
                             Qt.AlignmentFlag.AlignCenter, duration)

    def _paint_cut_lines(self, painter: QPainter,
                         colors: dict[str, QColor]) -> None:
        """段边界贯穿两轨的切线：一眼看清哪里下过刀。"""
        if len(self._model.segments) < 2:
            return
        painter.setPen(QPen(_tint(colors["clip_grid"], 210), 1,
                            Qt.PenStyle.DashLine))
        top = self._video_lane().top() - 3
        bottom = self._audio_lane().bottom() + 3
        for segment in self._model.segments[1:]:
            x = self._ms_to_x(segment.start_ms)
            if HEADER_W < x < self.width() - 1:
                painter.drawLine(x, top, x, bottom)

    def _paint_region(self, painter: QPainter, colors: dict[str, QColor]) -> None:
        """I/O 选区：标尺下沿到轨道底的轻纱 + 边界竖线（对齐剪映选区带）。"""
        if self._region is None:
            return
        start, end = self._region
        left = self._ms_to_fx(start)
        right = self._ms_to_fx(end)
        top = float(RULER_H + 2)
        bottom = float(self.height() - 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_tint(colors["clip_selected"], 52))
        painter.drawRect(QRectF(left, top, max(1.0, right - left), bottom - top))
        painter.setPen(QPen(colors["clip_selected"], 2))
        painter.drawLine(QPointF(left, top), QPointF(left, bottom))
        painter.drawLine(QPointF(right, top), QPointF(right, bottom))

    def _paint_proposals(self, painter: QPainter,
                         colors: dict[str, QColor]) -> None:
        """静音切句候选带：勾选=强调色实边，未勾=灰虚边，跨两轨一眼可读。"""
        if not self._proposal_mode or not self._proposals:
            return
        top = self._video_lane().top()
        bottom = self._audio_lane().bottom()
        for index, (start, end) in enumerate(self._proposals):
            left = max(float(HEADER_W), self._ms_to_fx(start))
            right = min(float(self.width() - 1), self._ms_to_fx(end))
            if right <= left:
                continue
            on = index in self._proposal_on
            color = colors["clip_selected"] if on else colors["clip_muted"]
            rect = QRectF(left, top, right - left, bottom - top)
            # 胶片带本身很花，候选带不压重一点在视频轨上根本看不见
            painter.fillRect(rect, _tint(color, 74 if on else 30))
            painter.setPen(QPen(_tint(color, 235 if on else 140),
                                1.6 if on else 1.0,
                                Qt.PenStyle.SolidLine if on
                                else Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

    def _paint_marquee(self, painter: QPainter, colors: dict[str, QColor]) -> None:
        if self._marquee is None:
            return
        start, end = sorted(self._marquee)
        left = max(float(HEADER_W), self._ms_to_fx(start))
        right = min(float(self.width() - 2), self._ms_to_fx(end))
        if right <= left:
            return
        box = QRectF(left, self._video_lane().top(), right - left,
                     self._audio_lane().bottom() - self._video_lane().top())
        painter.setPen(QPen(colors["clip_selected"], 1, Qt.PenStyle.DashLine))
        painter.setBrush(_tint(colors["clip_selected"], 60))
        painter.drawRoundedRect(box, RADIUS, RADIUS)

    def _paint_ruler(self, painter: QPainter, colors: dict[str, QColor]) -> None:
        model = self._model
        area = QRect(HEADER_W, 0, self.width() - HEADER_W, RULER_H)
        painter.fillRect(area, colors["clip_ruler"])
        painter.fillRect(QRect(area.left(), RULER_H - 1, area.width(), 1),
                         colors["clip_grid"])
        segment = model.selected_segment
        if segment is not None:
            left = max(area.left(), self._ms_to_x(segment.start_ms))
            right = min(area.right(), self._ms_to_x(segment.end_ms))
            if right > left:
                painter.fillRect(QRect(left, 0, right - left, RULER_H - 1),
                                 _tint(colors["clip_selected"], 74))
        step = choose_ruler_step(self._ms_per_px)
        minor = max(1, step // 5)
        last_ms = min(model.duration_ms, self._offset_ms + self._visible_ms())
        font = QFont(self.font())
        font.setPointSizeF(max(6.5, font.pointSizeF() - 2.5))
        painter.setFont(font)
        metrics = QFontMetrics(font)
        label_right = -10 ** 9
        position = int(self._offset_ms // minor) * minor
        while position <= last_ms + minor:
            x = self._ms_to_x(position)
            if x >= area.left():
                major = position % step == 0
                painter.setPen(colors["clip_ruler_major"] if major
                               else colors["clip_ruler_minor"])
                painter.drawLine(x, RULER_H - 5, x,
                                 RULER_H - (12 if major else 7))
                if major and x + 4 > label_right + 1:
                    painter.setPen(colors["clip_ruler_text"])
                    text = ruler_label(position, step)
                    painter.drawText(QPoint(x + 4, RULER_H - 13), text)
                    label_right = x + 4 + metrics.horizontalAdvance(text)
            position += minor

    def _paint_hover(self, painter: QPainter, colors: dict[str, QColor]) -> None:
        if self._hover_ms is None or self._drag_mode:
            return
        x = self._ms_to_x(self._hover_ms)
        if x < HEADER_W or x > self.width() - 1:
            return
        painter.setPen(QPen(_tint(colors["clip_hover"], 130), 1,
                            Qt.PenStyle.DashLine))
        painter.drawLine(x, RULER_H, x, self.height() - 2)

    def _paint_playhead(self, painter: QPainter, colors: dict[str, QColor]) -> None:
        x = self._ms_to_x(self._model.playhead_ms)
        if x < HEADER_W - 1 or x > self.width() + 1:
            return
        painter.setPen(QPen(colors["clip_playhead"], 2))
        painter.drawLine(x, RULER_H - 1, x, self.height() - 2)
        font = QFont(self.font())
        font.setPointSizeF(max(6.5, font.pointSizeF() - 2.5))
        font.setBold(True)
        painter.setFont(font)
        text = format_clock(self._model.playhead_ms)
        width = QFontMetrics(font).horizontalAdvance(text) + 14
        pill = QRectF(min(max(x - width / 2, HEADER_W),
                          self.width() - width - 1), 3, width, 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colors["clip_playhead"])
        painter.drawRoundedRect(pill, 9, 9)
        painter.setPen(colors["clip_playhead_text"])
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_headers(self, painter: QPainter, colors: dict[str, QColor]) -> None:
        """左侧轨道头列：色点在上、轨名在下，随主题走。"""
        painter.fillRect(0, 0, HEADER_W - 1, self.height(), colors["clip_header"])
        painter.fillRect(HEADER_W - 1, 0, 1, self.height(), colors["clip_grid"])
        painter.fillRect(0, 0, HEADER_W - 1, RULER_H, colors["clip_ruler"])
        font = QFont(self.font())
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1.5))
        font.setBold(True)
        painter.setFont(font)
        # 圆点取"两套色板都够深"的键：clip_video_* 在浅色主题里是淡彩，
        # 当轨道标记用几乎看不见
        rows = ((self._video_lane(), "video.clip.track_video",
                 colors["clip_selected"]),
                (self._audio_lane(), "video.clip.track_audio",
                 colors["clip_wave"]))
        for lane, key, dot in rows:
            center = (HEADER_W - 1) // 2
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_tint(dot, 235))
            painter.drawEllipse(QPointF(center, lane.top() + 10.0), 3.6, 3.6)
            painter.setPen(colors["clip_header_text"])
            painter.drawText(QRect(0, lane.top() + 15, HEADER_W - 6,
                                   max(14, lane.height() - 19)),
                             Qt.AlignmentFlag.AlignCenter, i18n_live(key))
