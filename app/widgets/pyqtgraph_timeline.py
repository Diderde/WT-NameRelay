from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import pyqtgraph as pg
from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QRectF,
    Qt,
    QAbstractAnimation,
    QTimer,
    Signal,
    QVariantAnimation,
    QSize,
)
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QGraphicsItem, QSizePolicy, QVBoxLayout, QWidget

from app.audio.models import AudioClip, TimelineClipKind, TimelineItem, TimelineModel

# PyQtGraph's global ViewBox cleanup can emit a harmless disconnect warning during
# PySide6 interpreter shutdown. Qt owns these scene objects, so OS/Qt cleanup is used.
pg.setConfigOption("exitCleanup", False)


@dataclass(frozen=True, slots=True)
class TimelineHoverInfo:
    timeline_ms: int
    clip_id: str
    clip_kind: TimelineClipKind
    clip_offset_ms: int
    source_ms: int | None


class AdaptiveTimeAxisItem(pg.AxisItem):
    """A seconds/milliseconds ruler whose labelled ticks remain readable."""

    CANDIDATES = (0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10)

    def __init__(self) -> None:
        super().__init__(orientation="top", maxTickLength=7)
        self._visible_span = 60.0
        self._major_step = 5.0
        self.setTickFont(QApplication.font())
        self.setTextPen(pg.mkPen("#9eb3c2"))
        self.setPen(pg.mkPen("#63798b"))
        self.setHeight(42)
        self.setStyle(tickTextOffset=8, autoExpandTextSpace=False, tickTextHeight=20)

    @property
    def unit_text(self) -> str:
        return "ms" if self._visible_span < 1.0 else "s"

    @property
    def major_step(self) -> float:
        return self._major_step

    def tickValues(self, minVal: float, maxVal: float, size: float):  # noqa: N802 - Qt API
        self._visible_span = max(0.001, maxVal - minVal)
        font = getattr(self, "_tickFont", None) or QApplication.font()
        metrics = QFontMetricsF(font)
        example = "10000 ms" if self._visible_span < 1 else "100.0 s"
        minimum_pixels = max(80.0, metrics.horizontalAdvance(example) + 18.0)
        minimum_step = self._visible_span / max(1.0, size) * minimum_pixels
        self._major_step = next(
            (step for step in self.CANDIDATES if step >= minimum_step),
            self.CANDIDATES[-1],
        )
        minor = self._major_step / 5
        return [
            (self._major_step, self._ticks(minVal, maxVal, self._major_step)),
            (minor, self._ticks(minVal, maxVal, minor)),
        ]

    @staticmethod
    def _ticks(start: float, end: float, spacing: float) -> list[float]:
        first = math.ceil(start / spacing) * spacing
        count = max(0, int(math.floor((end - first) / spacing)) + 1)
        return [first + index * spacing for index in range(count)]

    def tickStrings(self, values, scale, spacing):  # noqa: N802 - Qt API
        if not values:
            return []
        # Only the major level receives text. Minor ticks remain short lines.
        if not math.isclose(spacing, self._major_step, rel_tol=1e-6, abs_tol=1e-9):
            return ["" for _ in values]
        if self._visible_span >= 10:
            return [f"{value:g} s" for value in values]
        if self._visible_span >= 1:
            return [f"{value:.1f} s" for value in values]
        return [f"{round(value * 1000):g} ms" for value in values]


class TimelineViewBox(pg.ViewBox):
    """Horizontal-only interaction with explicit Ctrl zoom and Shift pan."""

    zoom_requested = Signal(float)
    horizontal_pan_requested = Signal(float)

    def wheelEvent(self, event, axis=None) -> None:  # noqa: N802 - Qt API
        modifiers = event.modifiers()
        delta = event.delta()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            self.zoom_requested.emit(1.18 if delta > 0 else 1 / 1.18)
            event.accept()
            return
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            self.horizontal_pan_requested.emit(-1.0 if delta > 0 else 1.0)
            event.accept()
            return
        # A plain wheel is the primary timeline zoom gesture. Page scrolling is
        # routed before the event reaches the ViewBox when the pointer is outside
        # the drawing area or inside the page's right-edge hot zone.
        self.zoom_requested.emit(1.18 if delta > 0 else 1 / 1.18)
        event.accept()


class ClipGraphicsItem(pg.GraphicsObject):
    trim_preview = Signal(str, int, int)
    trim_committed = Signal(str, int, int)
    selected = Signal(str, object)
    move_committed = Signal(str, float)
    activated = Signal(str, int)
    hovered = Signal(object)

    HEIGHT = 1.0
    HANDLE_PX = 10.0

    def __init__(self, item: TimelineItem, start_seconds: float, index: int) -> None:
        super().__init__()
        self.item = item
        self.index = index
        self.start_seconds = start_seconds
        self._preview_start_ms: int | None = None
        self._preview_end_ms: int | None = None
        self._drag_mode = ""
        self._press_local_x = 0.0
        self._press_scene_x = 0.0
        self._last_scene_x = 0.0
        self._selected = False
        self.setPos(start_seconds, 0)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        name = self.item.source_path.name if isinstance(self.item, AudioClip) else "空白片段"
        self.label = pg.TextItem(
            f"{name}  {self.item.duration_ms / 1000:.3f} s",
            color="#dce7ef",
            anchor=(0, 0),
        )
        self.label.setParentItem(self)
        self.label.setPos(0.015, 0.04)

    @property
    def duration_seconds(self) -> float:
        if self._preview_start_ms is not None and self._preview_end_ms is not None:
            return max(0.001, (self._preview_end_ms - self._preview_start_ms) / 1000)
        return self.item.duration_ms / 1000

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.duration_seconds, self.HEIGHT)

    def _handle_scene_width(self) -> float:
        return max(0.001, self.pixelWidth() * self.HANDLE_PX)

    def _hit_mode(self, x: float) -> str:
        handle = min(self.duration_seconds / 3, self._handle_scene_width())
        if x <= handle:
            return "trim_left"
        if x >= self.duration_seconds - handle:
            return "trim_right"
        return "move_or_select"

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.update()

    def hoverMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        mode = self._hit_mode(event.pos().x())
        cursor = Qt.CursorShape.SizeHorCursor if mode.startswith("trim") else Qt.CursorShape.OpenHandCursor
        self.setCursor(cursor)
        local_ms = max(0, min(self.item.duration_ms, round(event.pos().x() * 1000)))
        self.hovered.emit((self.item.clip_id, round(self.start_seconds * 1000) + local_ms))
        event.accept()

    def hoverLeaveEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.unsetCursor()
        self.hovered.emit(None)
        event.accept()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._drag_mode = self._hit_mode(event.pos().x())
        self._press_local_x = event.pos().x()
        self._press_scene_x = event.scenePos().x()
        self._last_scene_x = self._press_scene_x
        self.selected.emit(self.item.clip_id, event.modifiers())
        cursor = Qt.CursorShape.SizeHorCursor if self._drag_mode.startswith("trim") else Qt.CursorShape.ClosedHandCursor
        self.setCursor(cursor)
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._last_scene_x = event.scenePos().x()
        # Item-local X is expressed in ViewBox seconds; scene X is pixels.
        delta_ms = round((event.pos().x() - self._press_local_x) * 1000)
        if isinstance(self.item, AudioClip):
            original_start, original_end = self.item.trim_start_ms, self.item.effective_end_ms
            limit = self.item.source_duration_ms
        else:
            original_start, original_end, limit = 0, self.item.duration_ms, 86_400_000
        if self._drag_mode == "trim_left":
            start = max(0, min(original_start + delta_ms, original_end - 1))
            end = original_end
        elif self._drag_mode == "trim_right":
            start = original_start
            end = max(start + 1, min(original_end + delta_ms, limit))
        else:
            event.accept()
            return
        self.prepareGeometryChange()
        self._preview_start_ms, self._preview_end_ms = start, end
        self.label.setText(
            f"{self.item.source_path.name if isinstance(self.item, AudioClip) else '空白片段'}  "
            f"{(end - start) / 1000:.3f} s"
        )
        self.trim_preview.emit(self.item.clip_id, start, end)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._preview_start_ms is not None and self._preview_end_ms is not None:
            self.trim_committed.emit(self.item.clip_id, self._preview_start_ms, self._preview_end_ms)
        elif self._drag_mode == "move_or_select" and abs(self._last_scene_x - self._press_scene_x) > 4:
            self.move_committed.emit(self.item.clip_id, self._last_scene_x)
        elif self._drag_mode == "move_or_select":
            local_ms = max(0, min(self.item.duration_ms, round(event.pos().x() * 1000)))
            self.activated.emit(self.item.clip_id, round(self.start_seconds * 1000) + local_ms)
        self._drag_mode = ""
        self.unsetCursor()
        event.accept()

    def _waveform_slice(self, visible: QRectF, pixel_width: int) -> list[tuple[float, float, float]]:
        envelope = getattr(self.item, "waveform", None)
        if envelope is None or not isinstance(self.item, AudioClip):
            return []
        waveform = envelope.level_for_width(pixel_width)
        if not waveform:
            return []
        source_duration = max(1, self.item.source_duration_ms)
        effective_start = self._preview_start_ms if self._preview_start_ms is not None else self.item.trim_start_ms
        effective_end = self._preview_end_ms if self._preview_end_ms is not None else self.item.effective_end_ms
        start_ratio = effective_start / source_duration
        end_ratio = effective_end / source_duration
        source_first = round(start_ratio * (len(waveform) - 1))
        source_last = max(source_first + 1, round(end_ratio * (len(waveform) - 1)))
        visible_first_ratio = max(0.0, visible.left() / max(self.duration_seconds, 1e-9))
        visible_last_ratio = min(1.0, visible.right() / max(self.duration_seconds, 1e-9))
        first = source_first + round((source_last - source_first) * visible_first_ratio)
        last = source_first + round((source_last - source_first) * visible_last_ratio)
        step = max(1, (last - first) // max(1, pixel_width))
        points: list[tuple[float, float, float]] = []
        for source_index in range(first, min(last + 1, len(waveform)), step):
            local_ratio = (source_index - source_first) / max(1, source_last - source_first)
            low, high = waveform[source_index]
            points.append((local_ratio * self.duration_seconds, low, high))
        return points

    def paint(self, painter: QPainter, option, widget=None) -> None:
        rect = self.boundingRect()
        selected = self._selected
        painter.fillRect(rect, QColor("#b97838" if selected else "#334351"))
        pen = QPen(QColor("#e3a353" if selected else "#63798b"))
        pen.setCosmetic(True)
        pen.setWidth(2 if selected else 1)
        painter.setPen(pen)
        painter.drawRect(rect)

        mid = rect.center().y()
        painter.setPen(QPen(QColor("#d7edf6" if selected else "#91b8cc"), 0))
        visible = option.exposedRect.intersected(rect)
        pixel_width = max(1, round(visible.width() / max(self.pixelWidth(), 1e-9)))
        points = self._waveform_slice(visible, pixel_width)
        if points:
            for x, low, high in points:
                painter.drawLine(QPointF(x, mid - high * 0.38), QPointF(x, mid - low * 0.38))
        else:
            painter.drawLine(rect.left(), mid, rect.right(), mid)

        handle = min(rect.width() / 3, self._handle_scene_width())
        handle_color = QColor(227, 163, 83, 175)
        painter.fillRect(QRectF(0, 0, handle, rect.height()), handle_color)
        painter.fillRect(QRectF(rect.right() - handle, 0, handle, rect.height()), handle_color)


class PlayheadHandleItem(pg.GraphicsObject):
    """A constant-pixel triangular handle; the vertical line remains click-through."""

    drag_started = Signal()
    position_preview = Signal(int)
    position_committed = Signal(int)

    def __init__(self, view_box: pg.ViewBox) -> None:
        super().__init__()
        self._view_box = view_box
        self._dragging = False
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setZValue(102)

    def _dimensions(self) -> tuple[float, float]:
        return max(0.001, self.pixelWidth() * 7), max(0.01, self.pixelHeight() * 11)

    def boundingRect(self) -> QRectF:
        half_width, height = self._dimensions()
        return QRectF(-half_width, 1.0 - height, half_width * 2, height)

    def shape(self) -> QPainterPath:
        half_width, height = self._dimensions()
        path = QPainterPath()
        path.moveTo(-half_width, 1.0 - height)
        path.lineTo(half_width, 1.0 - height)
        path.lineTo(0, 1.0)
        path.closeSubpath()
        return path

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#e3a353"))
        painter.drawPath(self.shape())

    def hoverEnterEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        event.accept()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._dragging = True
        self.drag_started.emit()
        event.accept()

    def _position_from_event(self, event) -> int:
        seconds = self._view_box.mapSceneToView(event.scenePos()).x()
        return max(0, round(seconds * 1000))

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._dragging:
            self.position_preview.emit(self._position_from_event(event))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._dragging:
            self.position_committed.emit(self._position_from_event(event))
        self._dragging = False
        event.accept()


class PyQtGraphTimeline(QWidget):
    selection_changed = Signal(set)
    seek_requested = Signal(int)
    playhead_requested = Signal(int)
    playhead_drag_started = Signal()
    playhead_preview = Signal(int)
    hover_changed = Signal(object)
    trim_preview = Signal(str, int, int)
    trim_committed = Signal(str, int, int)
    move_committed = Signal(set, int)
    zoom_requested = Signal(float)

    MIN_PPS = 2.0
    MAX_PPS = 1000.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: tuple[TimelineItem, ...] = ()
        self._clip_items: list[ClipGraphicsItem] = []
        self._selected: set[str] = set()
        self._playhead_ms = 0
        self._pending_hover: TimelineHoverInfo | None = None
        self._pps = 10.0
        self._target_pps = self._pps
        self._zoom_animation = QVariantAnimation(self)
        self._zoom_animation.setDuration(150)
        self._zoom_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._zoom_animation.valueChanged.connect(
            lambda value: self.set_pixels_per_second(float(value))
        )
        self.axis = AdaptiveTimeAxisItem()
        self.view_box = TimelineViewBox(enableMenu=False)
        self.graph = pg.GraphicsLayoutWidget()
        self.plot = self.graph.addPlot(axisItems={"top": self.axis}, viewBox=self.view_box)
        self.plot.showAxis("top")
        self.plot.hideAxis("bottom")
        self.plot.hideAxis("left")
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=True, y=False)
        self.plot.disableAutoRange()
        self.plot.setYRange(0, 1, padding=0)
        self.view_box.setLimits(xMin=0, yMin=0, yMax=1, minXRange=0.001)
        self.view_box.zoom_requested.connect(self.zoom_requested)
        self.view_box.horizontal_pan_requested.connect(self._pan)
        self.view_box.sigXRangeChanged.connect(self._range_changed)
        self.playhead = pg.InfiniteLine(
            pos=0,
            angle=90,
            movable=False,
            pen=pg.mkPen("#e3a353", width=2),
        )
        self.playhead.setZValue(100)
        self.plot.addItem(self.playhead)
        self.playhead_label = pg.TextItem("00:00.000", color="#f0b66a", anchor=(0.5, 1))
        self.playhead_label.setZValue(103)
        self.plot.addItem(self.playhead_label)
        self.playhead_handle = PlayheadHandleItem(self.view_box)
        self.playhead_handle.drag_started.connect(self.playhead_drag_started)
        self.playhead_handle.position_preview.connect(self._preview_playhead_drag)
        self.playhead_handle.position_committed.connect(self._commit_playhead_drag)
        self.plot.addItem(self.playhead_handle)
        self.hover_line = pg.InfiniteLine(
            pos=0,
            angle=90,
            movable=False,
            pen=pg.mkPen(QColor(143, 190, 214, 155), width=1, style=Qt.PenStyle.DashLine),
        )
        self.hover_line.setZValue(80)
        self.hover_line.hide()
        self.plot.addItem(self.hover_line)
        self.hover_label = pg.TextItem("", color="#a9cddd", anchor=(0, 1))
        self.hover_label.setZValue(81)
        self.hover_label.hide()
        self.plot.addItem(self.hover_label)
        self.split_flash = pg.InfiniteLine(
            pos=0,
            angle=90,
            movable=False,
            pen=pg.mkPen(QColor(227, 163, 83, 190), width=4),
        )
        self.split_flash.setZValue(99)
        self.split_flash.hide()
        self.plot.addItem(self.split_flash)
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(16)
        self._hover_timer.timeout.connect(self._flush_hover)
        self._split_flash_timer = QTimer(self)
        self._split_flash_timer.setSingleShot(True)
        self._split_flash_timer.setInterval(200)
        self._split_flash_timer.timeout.connect(self.split_flash.hide)
        self.plot.scene().sigMouseClicked.connect(self._scene_clicked)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.graph)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(220)
        self.setMaximumHeight(340)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(900, 300)

    @property
    def pixels_per_second(self) -> float:
        return self._pps

    @property
    def visible_left_seconds(self) -> float:
        return max(0.0, self.view_box.viewRange()[0][0])

    def set_timeline(
        self,
        source: TimelineModel | Sequence[TimelineItem],
        selected: set[str] | None = None,
    ) -> None:
        items = source.items if isinstance(source, TimelineModel) else tuple(source)
        self._items = tuple(items)
        self._selected = set(selected or ())
        for clip in self._clip_items:
            self.plot.removeItem(clip)
        self._clip_items.clear()
        start = 0.0
        for index, item in enumerate(self._items):
            clip = ClipGraphicsItem(item, start, index)
            clip.set_selected(item.clip_id in self._selected)
            clip.selected.connect(self._select_clip)
            clip.trim_preview.connect(self.trim_preview)
            clip.trim_committed.connect(self.trim_committed)
            clip.move_committed.connect(self._move_clip)
            clip.activated.connect(self._activate_clip)
            clip.hovered.connect(self._queue_hover)
            self.plot.addItem(clip)
            self._clip_items.append(clip)
            start += item.duration_ms / 1000
        self.view_box.setLimits(xMax=max(60.0, start))
        self._apply_view_width(left_time=self.visible_left_seconds)
        self.set_playhead_ms(self._playhead_ms)

    def set_position(self, position_ms: int) -> None:
        self.set_playhead_ms(position_ms)

    def set_playhead_ms(self, position_ms: int) -> None:
        total_ms = sum(item.duration_ms for item in self._items)
        self._playhead_ms = max(0, min(total_ms, int(position_ms)))
        seconds = self._playhead_ms / 1000
        self.playhead.setValue(seconds)
        self.playhead_handle.setPos(seconds, 0)
        minutes, remainder = divmod(self._playhead_ms, 60_000)
        second, millisecond = divmod(remainder, 1000)
        self.playhead_label.setText(f"{minutes:02d}:{second:02d}.{millisecond:03d}")
        self.playhead_label.setPos(seconds, 0.98)

    @property
    def playhead_time_ms(self) -> int:
        return self._playhead_ms

    def flash_split_at(self, position_ms: int) -> None:
        self.split_flash.setValue(max(0, position_ms) / 1000)
        self.split_flash.show()
        self._split_flash_timer.start()

    def set_pixels_per_second(self, pps: float) -> None:
        left_time = self.visible_left_seconds
        self._pps = max(self.MIN_PPS, min(self.MAX_PPS, pps))
        self._apply_view_width(left_time=left_time)

    def animate_pixels_per_second(self, pps: float) -> None:
        self._target_pps = max(self.MIN_PPS, min(self.MAX_PPS, pps))
        if self._zoom_animation.state() == QAbstractAnimation.State.Running:
            self._zoom_animation.stop()
        self._zoom_animation.setStartValue(self._pps)
        self._zoom_animation.setEndValue(self._target_pps)
        self._zoom_animation.start()

    def _apply_view_width(self, left_time: float) -> None:
        viewport_width = max(1.0, self.view_box.width())
        visible_seconds = viewport_width / self._pps
        self.view_box.setXRange(left_time, left_time + visible_seconds, padding=0)

    def _pan(self, direction: float) -> None:
        left, right = self.view_box.viewRange()[0]
        amount = (right - left) * 0.12 * direction
        maximum = max(0.0, sum(item.duration_ms for item in self._items) / 1000 - (right - left))
        new_left = max(0.0, min(maximum, left + amount))
        self.view_box.setXRange(new_left, new_left + (right - left), padding=0)

    def _range_changed(self, _view_box, ranges) -> None:
        self.axis.setLabel(text=f"单位：{self.axis.unit_text}")

    def _select_clip(self, clip_id: str, modifiers: object) -> None:
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            self._selected.symmetric_difference_update({clip_id})
        else:
            self._selected = {clip_id}
        for clip in self._clip_items:
            clip.set_selected(clip.item.clip_id in self._selected)
        self.selection_changed.emit(set(self._selected))

    def _activate_clip(self, clip_id: str, position_ms: int) -> None:
        del clip_id
        self.playhead_requested.emit(self._clamp_time(position_ms))
        self.seek_requested.emit(self._clamp_time(position_ms))

    def _move_clip(self, clip_id: str, scene_x: float) -> None:
        view_x = self.view_box.mapSceneToView(QPointF(scene_x, 0)).x()
        starts: list[float] = []
        total = 0.0
        for item in self._items:
            starts.append(total)
            total += item.duration_ms / 1000
        target = min(range(len(starts)), key=lambda i: abs(starts[i] - view_x)) if starts else 0
        self.move_committed.emit({clip_id}, target)

    def _scene_clicked(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if any(item.isUnderMouse() for item in self._clip_items) or self.playhead_handle.isUnderMouse():
            return
        point = self.view_box.mapSceneToView(event.scenePos())
        position_ms = self._clamp_time(round(point.x() * 1000))
        self.playhead_requested.emit(position_ms)
        self.seek_requested.emit(position_ms)

    def _clamp_time(self, position_ms: int) -> int:
        return max(0, min(sum(item.duration_ms for item in self._items), position_ms))

    def _preview_playhead_drag(self, position_ms: int) -> None:
        position_ms = self._clamp_time(position_ms)
        self.set_playhead_ms(position_ms)
        self.playhead_preview.emit(position_ms)

    def _commit_playhead_drag(self, position_ms: int) -> None:
        position_ms = self._clamp_time(position_ms)
        self.set_playhead_ms(position_ms)
        self.playhead_requested.emit(position_ms)
        self.seek_requested.emit(position_ms)

    def _queue_hover(self, payload: object) -> None:
        if payload is None:
            self._pending_hover = None
        else:
            clip_id, position_ms = payload
            clip = next((item for item in self._items if item.clip_id == clip_id), None)
            if clip is None:
                self._pending_hover = None
            else:
                start_ms = 0
                for item in self._items:
                    if item.clip_id == clip_id:
                        break
                    start_ms += item.duration_ms
                offset_ms = max(0, min(clip.duration_ms, position_ms - start_ms))
                self._pending_hover = TimelineHoverInfo(
                    timeline_ms=start_ms + offset_ms,
                    clip_id=clip_id,
                    clip_kind=TimelineClipKind.AUDIO if isinstance(clip, AudioClip) else TimelineClipKind.BLANK,
                    clip_offset_ms=offset_ms,
                    source_ms=clip.trim_start_ms + offset_ms if isinstance(clip, AudioClip) else None,
                )
        if not self._hover_timer.isActive():
            self._hover_timer.start()

    def _flush_hover(self) -> None:
        info = self._pending_hover
        if info is None:
            self.hover_line.hide()
            self.hover_label.hide()
            self.hover_changed.emit(None)
            return
        seconds = info.timeline_ms / 1000
        self.hover_line.setValue(seconds)
        span = self.view_box.viewRange()[0][1] - self.view_box.viewRange()[0][0]
        primary = f"{info.timeline_ms} ms" if span < 1 else f"{seconds:.3f} s"
        source = "" if info.source_ms is None else f"<br>源音频位置：{info.source_ms / 1000:.3f} s"
        self.hover_label.setHtml(
            "<span style='color:#a9cddd'>"
            f"{primary}<br>音轨位置：{seconds:.3f} s"
            f"<br>片段位置：{info.clip_offset_ms / 1000:.3f} s"
            f"{source}</span>"
        )
        self.hover_label.setPos(seconds, 0.96)
        self.hover_line.show()
        self.hover_label.show()
        self.hover_changed.emit(info)
