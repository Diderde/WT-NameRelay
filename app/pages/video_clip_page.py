# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""视频裁剪工作台：剪映/PR 式编辑器布局。

顶部三面板（素材库 / 播放器 / 说话人文件夹与导出），底部全宽时间轴
（工具条 + 时间标尺 + 视频轨 + 音频轨 + 轨道头 + 跨轨播放头）。
时间轴支持 Ctrl+滚轮横轴缩放、滚轮平移、片段边缘拖拽修边；选中片段
带 45° 斜切角白框。落盘走 `cut_segment`（`-c copy`，LGPL 基线能力）。
"""
from __future__ import annotations

import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPixmap, QPolygon
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.audio.waveform_service import WaveformWorker
from app.i18n import i18n_text, tr
from app.pages.base_tool_page import BaseToolPage
from app.services.video_clip_service import (
    PURPOSE_FOLDERS,
    ClipTimelineModel,
    VideoAsset,
    cut_segment,
    ensure_speaker_folders,
    make_thumbnail,
    probe_video,
)
from app.styles.theme import off_mode_changed, on_mode_changed

_SPEEDS = (0.5, 1.0, 2.0, 4.0, 8.0)
_ZOOM_STEP = 1.25
_MS_PER_PX_MIN = 2.0
_MS_PER_PX_MAX = 400.0
_HEADER_W = 52
_RULER_H = 24
_VIDEO_H = 76
_AUDIO_H = 62
_TRACK_GAP = 6
_EDGE_GRAB_PX = 7
_THUMB_DIR = Path(tempfile.gettempdir()) / "wt_video_thumbs"

_RULER_STEPS = (100, 250, 500, 1000, 2000, 5000, 10000, 15000, 30000,
                60000, 120000, 300000)


def _format_tc(ms: int) -> str:
    """剪辑器风格时码：HH:MM:SS:CC（百分秒）。"""
    total_cs = max(0, ms) // 10
    cs = total_cs % 100
    total_s = total_cs // 100
    return (f"{total_s // 3600:02d}:{total_s // 60 % 60:02d}:"
            f"{total_s % 60:02d}:{cs:02d}")


def _choose_ruler_step(ms_per_px: float) -> int:
    """按当前缩放选择标尺主刻度步长（目标主刻度间距 ≥ 70px）。"""
    for step in _RULER_STEPS:
        if step / ms_per_px >= 70.0:
            return step
    return _RULER_STEPS[-1]


class _WaveformLoader(QObject):
    """波形解码工作线程的回传桥（工作线程 → GUI 线程走 Qt 信号）。"""

    finished = Signal(str, int, object, str)

    def __init__(self) -> None:
        super().__init__()
        self._worker: WaveformWorker | None = None
        self._thread: threading.Thread | None = None

    def load(self, clip_id: str, path: Path, on_done) -> None:
        worker = WaveformWorker(clip_id, path)

        def run() -> None:
            worker.run()

        def bind(clip: str, duration: int, peaks: object, error: str) -> None:
            worker.finished.disconnect(bind)
            on_done(clip, duration, peaks, error)

        worker.finished.connect(bind)
        self._worker = worker
        self._thread = threading.Thread(target=run, name="clip-waveform", daemon=True)
        self._thread.start()


class _TimelinePanel(QWidget):
    """全宽时间轴：时间标尺 + 视频轨 + 音频轨 + 轨道头 + 跨轨播放头。"""

    seek_requested = Signal(int)
    selection_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(200)
        self._model: ClipTimelineModel | None = None
        self._peaks: tuple[tuple[float, float], ...] = ()
        self._ms_per_px = 40.0
        self._offset_ms = 0.0
        self._drag_mode = ""  # '' | 'trim_l' | 'trim_r'
        self.setMouseTracking(True)

    # ---------------------------------------------------------------- data

    def set_model(self, model: ClipTimelineModel | None) -> None:
        self._model = model
        self._offset_ms = 0.0
        self.update()

    def set_peaks(self, peaks: tuple[tuple[float, float], ...]) -> None:
        self._peaks = peaks
        self.update()

    def ms_per_px(self) -> float:
        return self._ms_per_px

    def fit(self) -> None:
        if self._model is None:
            return
        usable = max(1, self.width() - _HEADER_W - 8)
        self._ms_per_px = max(_MS_PER_PX_MIN, self._model.duration_ms / usable)
        self._offset_ms = 0.0
        self.update()

    def set_ms_per_px(self, value: float) -> None:
        self._ms_per_px = max(_MS_PER_PX_MIN, min(_MS_PER_PX_MAX, value))
        self._clamp_offset()
        self.update()

    # ---------------------------------------------------------------- coords

    def _visible_ms(self) -> float:
        return max(1.0, self._ms_per_px * max(1, self.width() - _HEADER_W))

    def _x_to_ms(self, x: int) -> int:
        return int(self._offset_ms + max(0, x - _HEADER_W) * self._ms_per_px)

    def _ms_to_x(self, position_ms: float) -> int:
        return _HEADER_W + int((position_ms - self._offset_ms) / self._ms_per_px)

    def _clamp_offset(self) -> None:
        if self._model is None:
            self._offset_ms = 0.0
            return
        limit = max(0.0, self._model.duration_ms - self._visible_ms())
        self._offset_ms = max(0.0, min(limit, self._offset_ms))

    def _video_band(self) -> QRect:
        return QRect(0, _RULER_H, self.width(), _VIDEO_H)

    def _audio_band(self) -> QRect:
        return QRect(0, _RULER_H + _VIDEO_H + _TRACK_GAP,
                     self.width(), _AUDIO_H)

    # ---------------------------------------------------------------- events

    def wheelEvent(self, event) -> None:
        if self._model is None:
            return
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            anchor = self._x_to_ms(int(event.position().x()))
            factor = _ZOOM_STEP if delta > 0 else 1.0 / _ZOOM_STEP
            self._ms_per_px = max(_MS_PER_PX_MIN,
                                  min(_MS_PER_PX_MAX, self._ms_per_px * factor))
            self._offset_ms = max(0.0, anchor - (event.position().x() - _HEADER_W)
                                  * self._ms_per_px)
            self._clamp_offset()
        else:
            pan = self._visible_ms() * (0.15 if delta < 0 else -0.15)
            self._offset_ms += pan
            self._clamp_offset()
        self.update()

    def mousePressEvent(self, event) -> None:
        if self._model is None or event.button() != Qt.MouseButton.LeftButton:
            return
        position = self._x_to_ms(int(event.position().x()))
        self._model.seek(position)
        self._model.select_at(position)
        self._drag_mode = self._edge_mode_at(int(event.position().x()))
        self.seek_requested.emit(position)
        self.selection_changed.emit()
        self.update()

    def _edge_mode_at(self, x: int) -> str:
        segment = self._model.selected_segment if self._model else None
        if segment is None:
            return ""
        left = self._ms_to_x(segment.start_ms)
        right = self._ms_to_x(segment.end_ms)
        if abs(x - left) <= _EDGE_GRAB_PX:
            return "trim_l"
        if abs(x - right) <= _EDGE_GRAB_PX:
            return "trim_r"
        return ""

    def mouseMoveEvent(self, event) -> None:
        if self._model is None:
            return
        x = int(event.position().x())
        if self._drag_mode:
            position = self._x_to_ms(x)
            segment = self._model.selected_segment
            if segment is not None:
                position = max(0, min(self._model.duration_ms, position))
                if self._drag_mode == "trim_l":
                    segment.start_ms = min(position, segment.end_ms - 50)
                elif self._drag_mode == "trim_r":
                    segment.end_ms = max(position, segment.start_ms + 50)
                self._model.seek(position)
                self.selection_changed.emit()
            self.update()
            return
        if self._edge_mode_at(x):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_mode = ""

    # ---------------------------------------------------------------- paint

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(24, 26, 31))
        if self._model is None:
            painter.setPen(QColor(128, 134, 144))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             i18n_text('video.clip.empty'))
            return
        self._paint_headers(painter)
        self._paint_ruler(painter)
        self._paint_track(painter, self._video_band(),
                          QColor(34, 40, 38), QColor(52, 118, 88), "video")
        self._paint_track(painter, self._audio_band(),
                          QColor(36, 34, 42), QColor(84, 72, 118), "audio")
        self._paint_playhead(painter)

    def _paint_headers(self, painter: QPainter) -> None:
        painter.fillRect(0, 0, _HEADER_W - 4, self.height(), QColor(30, 32, 38))
        painter.setPen(QColor(150, 156, 166))
        font = QFont(self.font())
        font.setPointSizeF(max(7.0, self.font().pointSizeF() - 1))
        painter.setFont(font)
        video_band = self._video_band()
        painter.drawText(QRect(0, video_band.y(), _HEADER_W - 6, video_band.height()),
                         Qt.AlignmentFlag.AlignCenter,
                         i18n_text('video.clip.track_video'))
        audio_band = self._audio_band()
        painter.drawText(QRect(0, audio_band.y(), _HEADER_W - 6, audio_band.height()),
                         Qt.AlignmentFlag.AlignCenter,
                         i18n_text('video.clip.track_audio'))

    def _paint_ruler(self, painter: QPainter) -> None:
        painter.fillRect(_HEADER_W, 0, self.width() - _HEADER_W,
                         _RULER_H - 2, QColor(30, 32, 38))
        step = _choose_ruler_step(self._ms_per_px)
        painter.setPen(QColor(140, 146, 156))
        first = int(self._offset_ms // step) * step
        position = first
        while position <= min(self._model.duration_ms,
                              self._offset_ms + self._visible_ms()) + step:
            x = self._ms_to_x(position)
            if x >= _HEADER_W:
                painter.drawLine(x, _RULER_H - 8, x, _RULER_H - 2)
                painter.drawText(QPoint(x + 4, _RULER_H - 8),
                                 f"{position // 60000:02d}:{position // 1000 % 60:02d}")
            position += step

    def _paint_track(self, painter: QPainter, band: QRect, empty_color: QColor,
                     fill_color: QColor, kind: str) -> None:
        inner = band.adjusted(_HEADER_W, 3, -2, -3)
        painter.fillRect(inner, empty_color)
        model = self._model
        for index, segment in enumerate(model.segments):
            left = max(inner.left(), self._ms_to_x(segment.start_ms))
            right = min(inner.right(), self._ms_to_x(segment.end_ms))
            if right <= left:
                continue
            rect = QRect(left, inner.y(), right - left, inner.height())
            selected = index == model.selected
            block = QColor(64, 152, 112) if selected else fill_color
            painter.fillRect(rect, block)
            if kind == "video":
                painter.setPen(QColor(226, 232, 240))
                painter.drawText(rect.adjusted(6, 2, -6, -2),
                                 Qt.AlignmentFlag.AlignLeft
                                 | Qt.AlignmentFlag.AlignTop,
                                 tr('video.clip.segment', n=index + 1))
                painter.drawText(rect.adjusted(6, 2, -6, -2),
                                 Qt.AlignmentFlag.AlignRight
                                 | Qt.AlignmentFlag.AlignBottom,
                                 _format_tc(segment.end_ms - segment.start_ms))
            else:
                self._paint_wave_slice(painter, rect, segment)
            if selected:
                cut = max(6, min(12, rect.width() // 4, rect.height() // 4))
                polygon = QPolygon([
                    QPoint(rect.x() + cut, rect.y()),
                    QPoint(rect.right() - cut, rect.y()),
                    QPoint(rect.right(), rect.y() + cut),
                    QPoint(rect.right(), rect.bottom() - cut),
                    QPoint(rect.right() - cut, rect.bottom()),
                    QPoint(rect.x() + cut, rect.bottom()),
                    QPoint(rect.x(), rect.bottom() - cut),
                    QPoint(rect.x(), rect.y() + cut),
                ])
                painter.setPen(QColor(255, 255, 255))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolygon(polygon)

    def _paint_wave_slice(self, painter: QPainter, rect: QRect,
                          segment) -> None:
        if not self._peaks:
            return
        total = len(self._peaks)
        duration = max(1, self._model.duration_ms)
        middle = rect.y() + rect.height() / 2.0
        painter.setPen(QColor(178, 164, 226))
        for x in range(rect.x(), rect.right() + 1, 2):
            position = self._offset_ms + (x - _HEADER_W) * self._ms_per_px
            if position < segment.start_ms or position > segment.end_ms:
                continue
            index = int(position / duration * total)
            if not 0 <= index < total:
                continue
            low, high = self._peaks[index]
            painter.drawLine(
                QPoint(x, int(middle - high * rect.height() * 0.46)),
                QPoint(x, int(middle - low * rect.height() * 0.46) + 1))

    def _paint_playhead(self, painter: QPainter) -> None:
        x = self._ms_to_x(self._model.playhead_ms)
        if not _HEADER_W <= x <= self.width():
            return
        painter.setPen(QColor(255, 96, 96))
        painter.drawLine(x, 0, x, self.height())
        painter.setBrush(QColor(255, 96, 96))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygon([QPoint(x - 5, 0), QPoint(x + 5, 0),
                                      QPoint(x, 8)]))


class VideoClipPage(BaseToolPage):
    """视频裁剪工作台页面。"""

    #: 导出进度/完成回传（工作线程 → GUI 线程）
    _export_report = Signal(int)
    _export_finish = Signal(str)
    #: 缩略图就绪（工作线程 → GUI 线程）：(素材行号, png 路径)
    _thumb_ready = Signal(int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__('video', i18n_text('page.video.title'), parent)
        self._labeled: list[tuple[QWidget, str]] = []
        self._assets: list[VideoAsset] = []
        self._current: VideoAsset | None = None
        self._model: ClipTimelineModel | None = None
        self._export_thread: threading.Thread | None = None
        self._thumb_thread: threading.Thread | None = None
        self._waveform_loader = _WaveformLoader()
        self._speakers: list[Path] = []
        self._purpose = PURPOSE_FOLDERS[0]
        self.status_panel.setVisible(False)
        self.setAcceptDrops(True)
        self._apply_page_style()
        self._build_body()
        self._export_report.connect(self._progress.setValue)
        self._export_finish.connect(self._on_export_finished)
        self._thumb_ready.connect(self._on_thumb_ready)
        self._speakers = ensure_speaker_folders()
        self._refresh_speakers()
        on_mode_changed(self._on_mode_changed)
        self.destroyed.connect(lambda: off_mode_changed(self._on_mode_changed))

    def _apply_page_style(self) -> None:
        """页内字号收紧（全局 crewPanelTitle 18px 对本页过大）。

        注意：不得在此样式表中写 QVideoWidget 选择器——app 级样式表重打磨
        （昼夜切换）时与原生视频组件冲突会导致进程原生崩溃（实测）；
        预览底色改用容器 Palette 黑底实现。
        """
        self.setStyleSheet(
            "VideoClipPage QLabel#crewPanelTitle { font-size: 13px; }"
            "VideoClipPage QPushButton { font-size: 12px; padding: 4px 10px; }"
            "VideoClipPage QListWidget { font-size: 12px; }"
            "VideoClipPage QComboBox { font-size: 12px; }"
            "VideoClipPage QLabel { font-size: 12px; }")

    def _on_mode_changed(self, mode: str) -> None:
        _ = mode
        # 主题通知在全局重打磨中途派发，同步触碰自绘控件会原生崩溃；
        # 延后到下一轮事件循环再重绘
        QTimer.singleShot(0, self._timeline.update)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local:
                self.import_video(Path(local))
        event.acceptProposedAction()

    # ---------------------------------------------------------------- UI build

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

    def _panel_frame(self, title_key: str) -> tuple[QWidget, QVBoxLayout, QLabel]:
        panel = QWidget()
        panel.setObjectName('placeholderPanel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        title = QLabel(i18n_text(title_key))
        title.setObjectName('crewPanelTitle')
        self._labeled.append((title, title_key))
        layout.addWidget(title)
        return panel, layout, title

    def _build_media_panel(self) -> QWidget:
        panel, layout, _title = self._panel_frame('video.clip.upload')
        self._add_button = QPushButton(i18n_text('video.clip.add'))
        self._add_button.clicked.connect(self._add_videos)
        layout.addWidget(self._add_button)
        self._asset_list = QListWidget()
        self._asset_list.setUniformItemSizes(False)
        self._asset_list.currentRowChanged.connect(self._on_asset_selected)
        layout.addWidget(self._asset_list, 1)
        return panel

    def _build_player_panel(self) -> QWidget:
        panel, layout, self._player_title = self._panel_frame('video.clip.player')
        # 预览不用原生合成窗口：它与昼夜切换的全局重打磨并发会把 backing
        # store 打成 painter 活跃态，随后重绘随机 SIGSEGV（对照实验：
        # 原生形态崩、QVideoSink 软件取帧形态稳定）。改走手动取帧。
        self._preview_label = QLabel(i18n_text('video.clip.preview_empty'))
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumHeight(190)
        self._preview_label.setAutoFillBackground(True)
        palette = self._preview_label.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor('#000000'))
        palette.setColor(QPalette.ColorRole.WindowText, QColor('#6b7280'))
        self._preview_label.setPalette(palette)
        self._preview_label.setScaledContents(False)
        self._video_widget = self._preview_label
        self._preview_sink = QVideoSink(self)
        self._preview_sink.videoFrameChanged.connect(self._on_video_frame)
        layout.addWidget(self._preview_label, 1)

        transport = QHBoxLayout()
        self._clock_left = QLabel("00:00:00:00")
        self._clock_left.setObjectName('mutedLabel')
        transport.addWidget(self._clock_left)
        transport.addStretch(1)
        self._play_button = QPushButton(i18n_text('video.clip.play'))
        self._play_button.clicked.connect(self._toggle_play)
        transport.addWidget(self._play_button)
        transport.addStretch(1)
        self._speed_combo = QComboBox()
        for speed in _SPEEDS:
            self._speed_combo.addItem(f"{speed:g}×", speed)
        self._speed_combo.setCurrentIndex(1)
        self._speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        transport.addWidget(self._speed_combo)
        self._clock_right = QLabel("00:00:00:00")
        self._clock_right.setObjectName('mutedLabel')
        transport.addWidget(self._clock_right)
        layout.addLayout(transport)

        self._player = QMediaPlayer()
        self._player.setVideoSink(self._preview_sink)
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._on_position_changed)
        return panel

    @Slot(object)
    def _on_video_frame(self, frame) -> None:
        if not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        self._preview_label.setPixmap(QPixmap.fromImage(image).scaled(
            self._preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def _build_export_panel(self) -> QWidget:
        panel, layout, _title = self._panel_frame('video.clip.speakers')
        self._folder_list = QListWidget()
        self._folder_list.currentRowChanged.connect(
            lambda _row: self._refresh_target_label())
        layout.addWidget(self._folder_list, 0)

        purpose_row = QHBoxLayout()
        purpose_row.setSpacing(6)
        self._purpose_buttons: list[QPushButton] = []
        for purpose in PURPOSE_FOLDERS:
            button = QPushButton(purpose)
            button.setCheckable(True)
            button.setChecked(purpose == self._purpose)
            button.clicked.connect(
                lambda _checked, name=purpose: self._select_purpose(name))
            self._purpose_buttons.append(button)
            purpose_row.addWidget(button)
        purpose_row.addStretch(1)
        layout.addLayout(purpose_row)

        self._purpose_hint = QLabel(self._purpose_hint_text())
        self._purpose_hint.setObjectName('mutedLabel')
        self._purpose_hint.setWordWrap(True)
        layout.addWidget(self._purpose_hint)

        self._speaker_hint = QLabel("")
        self._speaker_hint.setObjectName('mutedLabel')
        self._speaker_hint.setWordWrap(True)
        layout.addWidget(self._speaker_hint)

        self._export_btn = self._op_button('video.clip.export', self._export_selected)
        layout.addWidget(self._export_btn)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)
        layout.addStretch(1)
        return panel

    def _purpose_hint_text(self) -> str:
        if self._purpose == "训练素材":
            return i18n_text('video.clip.purpose.train.hint')
        return i18n_text('video.clip.purpose.use.hint')

    def _select_purpose(self, name: str) -> None:
        self._purpose = name
        for button in self._purpose_buttons:
            button.setChecked(button.text() == name)
        self._purpose_hint.setText(self._purpose_hint_text())
        self._refresh_target_label()

    def _export_target_dir(self) -> Path:
        row = max(0, self._folder_list.currentRow())
        speaker = self._speakers[min(row, len(self._speakers) - 1)]
        return speaker / self._purpose

    def _refresh_target_label(self) -> None:
        if self._speakers:
            self._speaker_hint.setText(
                tr('video.clip.target', path=str(self._export_target_dir())))

    def _build_timeline_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName('placeholderPanel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(6)

        toolbar = QHBoxLayout()
        self._trim_left_btn = self._op_button('video.clip.trim_left', self._trim_left)
        self._trim_right_btn = self._op_button('video.clip.trim_right', self._trim_right)
        self._split_btn = self._op_button('video.clip.split', self._split_center)
        self._delete_btn = self._op_button('video.clip.delete', self._delete_selected)
        for button in (self._trim_left_btn, self._trim_right_btn,
                       self._split_btn, self._delete_btn):
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        self._fit_btn = self._op_button('video.clip.fit', self._fit_timeline)
        toolbar.addWidget(self._fit_btn)
        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setRange(0, 100)
        self._zoom_slider.setValue(50)
        self._zoom_slider.setFixedWidth(180)
        self._zoom_slider.valueChanged.connect(self._on_zoom_slider)
        toolbar.addWidget(self._zoom_slider)
        self._zoom_label = QLabel("")
        self._zoom_label.setObjectName('mutedLabel')
        toolbar.addWidget(self._zoom_label)
        layout.addLayout(toolbar)

        self._timeline = _TimelinePanel()
        self._timeline.seek_requested.connect(self._on_timeline_seek)
        self._timeline.selection_changed.connect(self._on_timeline_selection)
        layout.addWidget(self._timeline, 1)
        return panel

    def _op_button(self, key: str, handler) -> QPushButton:
        button = QPushButton(i18n_text(key))
        button.clicked.connect(handler)
        self._labeled.append((button, key))
        return button

    # ---------------------------------------------------------------- i18n

    def retranslate(self) -> None:
        super().retranslate()
        for widget, key in self._labeled:
            widget.setText(i18n_text(key))
        self._play_button.setText(i18n_text('video.clip.play'))

    # ---------------------------------------------------------------- assets

    def _add_videos(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, i18n_text('video.clip.add'), '',
            'Video (*.mp4 *.mov *.mkv *.avi *.webm *.wav)')
        for name in files:
            self.import_video(Path(name))

    def import_video(self, path: Path) -> None:
        """编程入口（测试/拖拽扩展用）。"""
        self._import_video(Path(path))

    def _import_video(self, path: Path) -> None:
        try:
            asset = probe_video(path)
        except (OSError, ValueError) as exc:
            self._speaker_hint.setText(
                tr('video.clip.import_fail', detail=str(exc)[-200:]))
            return
        self._assets.append(asset)
        row = len(self._assets) - 1
        item = QListWidgetItem(f"{path.name}  ·  {_format_tc(asset.duration_ms)}")
        item.setData(Qt.ItemDataRole.UserRole, row)
        self._asset_list.addItem(item)
        self._asset_list.setCurrentRow(self._asset_list.count() - 1)
        self._thumb_thread = threading.Thread(
            target=self._thumb_work, args=(row, path),
            name='video-thumb', daemon=True)
        self._thumb_thread.start()

    def _thumb_work(self, row: int, path: Path) -> None:
        try:
            thumb = make_thumbnail(path, _THUMB_DIR)
            self._thumb_ready.emit(row, str(thumb))
        except (OSError, RuntimeError):
            pass

    @Slot(int, str)
    def _on_thumb_ready(self, row: int, thumb_path: str) -> None:
        if not 0 <= row < self._asset_list.count():
            return
        self._asset_list.item(row).setIcon(QIcon(thumb_path))

    def _on_asset_selected(self, row: int) -> None:
        if not 0 <= row < len(self._assets):
            return
        self._current = self._assets[row]
        self._model = ClipTimelineModel(self._current.duration_ms)
        self._model.selected = 0
        self._timeline.set_model(self._model)
        self._timeline.set_peaks(())
        self._player_title.setText(
            tr('video.clip.player_file', name=self._current.path.name))
        self._clock_right.setText(_format_tc(self._current.duration_ms))
        self._player.setSource(QUrl.fromLocalFile(str(self._current.path)))
        self._player.pause()
        self._waveform_loader.load(self._current.path.name, self._current.path,
                                   self._on_waveform)
        QTimer.singleShot(60, self._timeline.fit)
        QTimer.singleShot(80, self._sync_zoom_label)

    def _on_waveform(self, clip_id: str, duration_ms: int, peaks: object,
                     error: str) -> None:
        _ = clip_id, duration_ms
        if error or self._model is None:
            return
        self._timeline.set_peaks(tuple(peaks))

    def _on_timeline_seek(self, position_ms: int) -> None:
        self._player.setPosition(position_ms)
        self._clock_left.setText(_format_tc(position_ms))
        self._timeline.update()

    @Slot()
    def _on_timeline_selection(self) -> None:
        if self._model is not None:
            self._clock_left.setText(_format_tc(self._model.playhead_ms))

    # ---------------------------------------------------------------- playback

    def _toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self._play_button.setText(i18n_text('video.clip.play'))
        else:
            self._player.play()
            self._play_button.setText(i18n_text('video.clip.pause'))

    def _on_speed_changed(self, index: int) -> None:
        speed = self._speed_combo.itemData(index)
        if speed is not None:
            self._player.setPlaybackRate(float(speed))

    def _on_position_changed(self, position_ms: int) -> None:
        if self._model is not None:
            self._model.seek(position_ms)
            self._timeline.update()
        self._clock_left.setText(_format_tc(position_ms))

    # ---------------------------------------------------------------- clip ops

    def _trim_left(self) -> None:
        if self._model and self._model.trim_left():
            self._timeline.update()

    def _trim_right(self) -> None:
        if self._model and self._model.trim_right():
            self._timeline.update()

    def _split_center(self) -> None:
        if self._model and self._model.split_at():
            self._timeline.update()

    def _delete_selected(self) -> None:
        if self._model and self._model.delete_selected():
            self._timeline.update()

    def _fit_timeline(self) -> None:
        self._timeline.fit()
        self._sync_zoom_label()

    def _on_zoom_slider(self, value: int) -> None:
        ratio = value / 100.0
        ms_per_px = _MS_PER_PX_MAX * (_MS_PER_PX_MIN / _MS_PER_PX_MAX) ** ratio
        self._timeline.set_ms_per_px(ms_per_px)
        self._sync_zoom_label()

    def _sync_zoom_label(self) -> None:
        self._zoom_label.setText(f"{self._timeline.ms_per_px():.0f} ms/px")

    # ---------------------------------------------------------------- export

    def _export_selected(self) -> None:
        if self._export_thread is not None:
            return
        if self._current is None or self._model is None:
            return
        segment = self._model.selected_segment
        if segment is None:
            return
        folder = self._export_target_dir()
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(tz=timezone.utc).strftime('%H%M%S%f')[:-3]
        target = folder / f"{self._current.path.stem}_{stamp}{self._current.path.suffix}"
        source = self._current.path
        start_ms, end_ms = segment.start_ms, segment.end_ms
        self._export_thread = threading.Thread(
            target=self._export_work,
            args=(source, start_ms, end_ms, target),
            name='video-clip-export', daemon=True)
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._export_thread.start()

    def _export_work(self, source: Path, start_ms: int, end_ms: int,
                     target: Path) -> None:
        def progress(ratio: float) -> None:
            self._export_report.emit(int(ratio * 100))

        try:
            cut_segment(source, start_ms, end_ms, target, on_progress=progress)
            text = tr('video.clip.export_done', path=str(target))
        except (OSError, RuntimeError, ValueError) as exc:
            text = tr('video.clip.export_fail', detail=str(exc)[-300:])
        self._export_thread = None
        self._export_finish.emit(text)

    @Slot(str)
    def _on_export_finished(self, text: str) -> None:
        self._progress.setVisible(False)
        self._speaker_hint.setText(text)

    # ---------------------------------------------------------------- folders

    def _refresh_speakers(self) -> None:
        self._folder_list.clear()
        for speaker in self._speakers:
            self._folder_list.addItem(QListWidgetItem(speaker.name))
        if self._speakers:
            self._folder_list.setCurrentRow(0)
        self._refresh_target_label()

    # ---------------------------------------------------------------- page ops

    @property
    def is_busy(self) -> bool:
        return self._export_thread is not None

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
