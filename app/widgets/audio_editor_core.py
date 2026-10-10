# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""单链音频编辑核心：从音频处理页提取的能力面（时间轴/试听/处理选项/导出）。

语音工作台"进行处理"小窗需要嵌入与音频处理页同源的编辑能力。
本模块承载该能力面：时间轴（修剪/拆分/撤销/静音切分）、试听引擎（含
会话化播访态机与循环区间）、处理选项（响度/降噪/修复/修饰）与导出渲染。
工程级外壳（根目录/模块/分类/目标组/矩阵拷贝）仍留在音频处理页；
页面迁移到本核心属遗留待办。
"""

from __future__ import annotations

import logging
import os
import threading
from enum import Enum
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QSettings, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.audio import (
    AudioClip,
    AudioExportService,
    AudioPreviewService,
    ExportSettings,
    LoudnessScanWorker,
    SilenceDetectWorker,
    SpectrumWorker,
    TimelineClipKind,
    TimelineEditKind,
    TimelineModel,
    WaveformWorker,
)
from app.audio.models import format_ms
from app.i18n import mark as _i18n_mark
from app.i18n import refresh as _i18n_refresh
from app.i18n import tr
from app.paths import config_dir, temp_dir
from app.widgets.pyqtgraph_timeline import PyQtGraphTimeline

LOGGER = logging.getLogger('wt_name_relay')


class PlaybackState(str, Enum):
    EMPTY = 'empty'
    PREPARING = 'preparing'
    READY = 'ready'
    PLAYING = 'playing'
    STOPPED = 'stopped'
    ERROR = 'error'


class PlaybackEndReason(str, Enum):
    NATURAL_END = 'natural_end'
    USER_STOP = 'user_stop'
    ERROR = 'error'
    TIMELINE_CHANGED = 'timeline_changed'
    SEEK = 'seek'


class EveWakamiya(QWidget):
    """时间轴编辑 + 试听 + 处理选项 + 渲染导出的无外壳能力控件。

    导出目标由调用方给点（request_save），本控件不关心产物语义；
    输出格式/质量为构造期固定值（小窗按"跟随该行产物"锁定为 wav）。
    """

    #: 用户可见状态随忙闲变化（保存按钮启停 / 关窗守卫都挂这里）
    state_changed = Signal()
    #: 渲染导出结束（成功与否、消息）
    save_finished = Signal(bool, str)

    def __init__(self, parent: QWidget | None = None, *, output_format: str = 'wav', quality: str = '') -> None:
        super().__init__(parent)
        self._settings = QSettings(str(config_dir() / 'settings.ini'), QSettings.IniFormat)
        self._output_format = output_format
        self._quality = quality
        self._timeline = TimelineModel()
        self._selected: set[str] = set()
        self._export_cancel_event = threading.Event()
        self._preview_cancel_event = threading.Event()
        self._save_thread: QThread | None = None
        self._save_worker: AudioExportService | None = None
        self._preview_thread: QThread | None = None
        self._preview_worker: AudioPreviewService | None = None
        self._preview_path: Path | None = None
        self._preview_version: int | None = None
        self._pending_play_start_ms: int | None = None
        self._playback_session_id = 0
        self._active_playback_session_id: int | None = None
        self._finalizing_playback = False
        self._waveform_threads: dict[str, tuple[QThread, WaveformWorker]] = {}
        self._pending_audio_paths: dict[str, Path] = {}
        self._playback_state = PlaybackState.EMPTY
        self.playhead_time_ms = 0
        self._audio_output = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._play_position)
        self._player.playbackStateChanged.connect(self._play_state)
        self._player.mediaStatusChanged.connect(self._media_status_changed)
        self._player.errorOccurred.connect(self._playback_error)
        self._normalize_mode: str | None = self._settings.value('audio/normalize_mode', None, str) or None
        self._normalize_target = float(self._settings.value('audio/normalize_target', -1.0))
        self._fade_ms: int = int(self._settings.value('audio/fade_ms', 0))
        self._trim_silence: str = self._settings.value('audio/trim_silence', 'off', str) or 'off'
        self._denoise: str = self._settings.value('audio/denoise', 'off', str) or 'off'
        self._denoise_strength: int = int(self._settings.value('audio/denoise_strength', 12))
        self._declick: bool = self._settings.value('audio/declick', False, bool)
        self._deesser: bool = self._settings.value('audio/deesser', False, bool)
        self._voice_preset: str = self._settings.value('audio/voice_preset', 'off', str) or 'off'
        self._gain_db: float = float(self._settings.value('audio/gain_db', 0.0))
        self._loudness_cache: dict = {}
        self._silence_thread: QThread | None = None
        self._silence_worker: SilenceDetectWorker | None = None
        self._silence_cancel = threading.Event()
        self._analysis_thread: QThread | None = None
        self._analysis_worker: LoudnessScanWorker | SpectrumWorker | None = None
        self._analysis_cancel = threading.Event()
        self._analysis_items: tuple = ()
        self._analysis_results: list = []
        self._build()
        self._update_loudness_status()
        self._sync()

    # —— 界面构建 ——

    def _panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName('crewManualPanel')
        return panel

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        actions = QFrame()
        actions.setObjectName('crewActionBar')
        action_layout = QHBoxLayout(actions)
        self.remove_button = _i18n_mark(QPushButton(tr('ui.142')), 'text', 'ui.142')
        self.split_button = _i18n_mark(QPushButton(tr('ui.143')), 'text', 'ui.143')
        self.undo_button = _i18n_mark(QPushButton(tr('ui.144')), 'text', 'ui.144')
        self.silence_button = _i18n_mark(QPushButton(tr('audio.button.silence')), 'text', 'audio.button.silence')
        self.analyze_button = _i18n_mark(QPushButton(tr('audio.button.analyze')), 'text', 'audio.button.analyze')
        self.preview_button = _i18n_mark(QPushButton(tr('ui.145')), 'text', 'ui.145')
        self.stop_button = _i18n_mark(QPushButton(tr('ui.146')), 'text', 'ui.146')
        self.loop_selected = _i18n_mark(QCheckBox(tr('ui.147')), 'text', 'ui.147')
        self.remove_button.clicked.connect(self._delete_selected)
        self.split_button.clicked.connect(self._split_audio)
        self.undo_button.clicked.connect(self._undo)
        self.silence_button.clicked.connect(self._detect_silence)
        self.analyze_button.clicked.connect(self._analyze_clips)
        self.preview_button.clicked.connect(self._preview)
        self.stop_button.clicked.connect(self._stop)
        for button in (self.remove_button, self.split_button, self.undo_button, self.silence_button, self.analyze_button, self.preview_button, self.stop_button, self.loop_selected):
            action_layout.addWidget(button)
        action_layout.addStretch(1)
        layout.addWidget(actions)
        self.timeline_view = PyQtGraphTimeline()
        self.timeline_view.selection_changed.connect(self._set_selection)
        self.timeline_view.playhead_requested.connect(self._seek)
        self.timeline_view.playhead_drag_started.connect(self._playhead_drag_started)
        self.timeline_view.playhead_preview.connect(self._playhead_drag_preview)
        self.timeline_view.trim_preview.connect(self._trim_preview)
        self.timeline_view.trim_committed.connect(self._trim_committed)
        self.timeline_view.move_committed.connect(self._move_committed)
        self.timeline_view.zoom_requested.connect(self._relative_zoom)
        layout.addWidget(self.timeline_view)
        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(_i18n_mark(QLabel(tr('ui.148')), 'text', 'ui.148'))
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(0, 1000)
        self.zoom.setValue(210)
        self.zoom.valueChanged.connect(self._set_zoom_from_slider)
        self.time_label = QLabel('00:00.000 / 00:00.000')
        zoom_layout.addWidget(self.zoom, 1)
        zoom_layout.addWidget(self.time_label)
        layout.addLayout(zoom_layout)
        export_panel = self._panel()
        export_layout = QVBoxLayout(export_panel)
        export_layout.addWidget(_i18n_mark(QLabel(tr('ui.149')), 'text', 'ui.149'))
        export_layout.addWidget(_i18n_mark(QLabel(tr('dialog.processing.loudness_group')), 'text', 'dialog.processing.loudness_group'))
        loudness_row = QHBoxLayout()
        self.normalize_mode_combo = QComboBox()
        for value, key in (('off', 'dialog.processing.off'), ('peak', 'dialog.processing.peak'), ('loudness', 'dialog.processing.loudness'), ('speech', 'dialog.processing.speech')):
            self.normalize_mode_combo.addItem(tr(key), value)
        self.normalize_mode_combo.setCurrentIndex(max(0, self.normalize_mode_combo.findData(self._normalize_mode or 'off')))
        self.normalize_mode_combo.currentIndexChanged.connect(self._on_normalize_mode_changed)
        self.loudness_target_spin = QDoubleSpinBox()
        self.loudness_target_spin.setRange(-30.0, -5.0)
        self.loudness_target_spin.setDecimals(1)
        self.loudness_target_spin.setSingleStep(0.5)
        self.loudness_target_spin.setSuffix(' LUFS')
        self.loudness_target_spin.valueChanged.connect(self._on_loudness_target_changed)
        self.loudness_target_spin.setValue(max(-30.0, min(-5.0, self._normalize_target)))
        self.gain_spin = QDoubleSpinBox()
        self.gain_spin.setRange(-24.0, 24.0)
        self.gain_spin.setDecimals(1)
        self.gain_spin.setSingleStep(0.5)
        self.gain_spin.setSuffix(' dB')
        self.gain_spin.setValue(self._gain_db)
        self.gain_spin.valueChanged.connect(self._on_gain_changed)
        loudness_row.addWidget(self.normalize_mode_combo, 1)
        loudness_row.addWidget(self.loudness_target_spin)
        loudness_row.addWidget(self.gain_spin)
        export_layout.addLayout(loudness_row)
        export_layout.addWidget(_i18n_mark(QLabel(tr('dialog.processing.repair_group')), 'text', 'dialog.processing.repair_group'))
        denoise_row = QHBoxLayout()
        self.denoise_combo = QComboBox()
        for value, key in (('off', 'dialog.processing.off'), ('afftdn', 'dialog.processing.denoise_fft'), ('anlmdn', 'dialog.processing.denoise_nl')):
            self.denoise_combo.addItem(tr(key), value)
        self.denoise_combo.setCurrentIndex(max(0, self.denoise_combo.findData(self._denoise)))
        self.denoise_combo.currentIndexChanged.connect(self._on_denoise_changed)
        self.denoise_strength_spin = QSpinBox()
        self.denoise_strength_spin.setRange(1, 48)
        self.denoise_strength_spin.setValue(self._denoise_strength)
        self.denoise_strength_spin.setSuffix(' dB')
        self.denoise_strength_spin.valueChanged.connect(self._on_denoise_strength_changed)
        denoise_row.addWidget(self.denoise_combo, 1)
        denoise_row.addWidget(_i18n_mark(QLabel(tr('dialog.processing.strength')), 'text', 'dialog.processing.strength'))
        denoise_row.addWidget(self.denoise_strength_spin)
        export_layout.addLayout(denoise_row)
        repair_row = QHBoxLayout()
        self.declick_check = _i18n_mark(QCheckBox(tr('dialog.processing.declick')), 'text', 'dialog.processing.declick')
        self.declick_check.setChecked(self._declick)
        self.declick_check.toggled.connect(self._on_declick_changed)
        self.deesser_check = _i18n_mark(QCheckBox(tr('dialog.processing.deesser')), 'text', 'dialog.processing.deesser')
        self.deesser_check.setChecked(self._deesser)
        self.deesser_check.toggled.connect(self._on_deesser_changed)
        repair_row.addWidget(self.declick_check)
        repair_row.addWidget(self.deesser_check)
        repair_row.addStretch(1)
        export_layout.addLayout(repair_row)
        preset_row = QHBoxLayout()
        self.preset_combo = QComboBox()
        for value, key in (('off', 'dialog.processing.preset_off'), ('low_cut', 'dialog.processing.preset_lowcut'), ('voice', 'dialog.processing.preset_voice'), ('broadcast', 'dialog.processing.preset_broadcast')):
            self.preset_combo.addItem(tr(key), value)
        self.preset_combo.setCurrentIndex(max(0, self.preset_combo.findData(self._voice_preset)))
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        preset_row.addWidget(_i18n_mark(QLabel(tr('dialog.processing.preset_group')), 'text', 'dialog.processing.preset_group'))
        preset_row.addWidget(self.preset_combo, 1)
        export_layout.addLayout(preset_row)
        polish_row = QHBoxLayout()
        self.fade_spin = QSpinBox()
        self.fade_spin.setRange(0, 500)
        self.fade_spin.setValue(self._fade_ms)
        self.fade_spin.setSuffix(' ms')
        self.fade_spin.valueChanged.connect(self._on_fade_changed)
        self.trim_edges_check = _i18n_mark(QCheckBox(tr('dialog.processing.trim_edges')), 'text', 'dialog.processing.trim_edges')
        self.trim_edges_check.setChecked(self._trim_silence == 'edges')
        self.trim_edges_check.toggled.connect(self._on_trim_edges_changed)
        polish_row.addWidget(_i18n_mark(QLabel(tr('dialog.processing.fade')), 'text', 'dialog.processing.fade'))
        polish_row.addWidget(self.fade_spin)
        polish_row.addWidget(self.trim_edges_check)
        polish_row.addStretch(1)
        export_layout.addLayout(polish_row)
        option_row = QHBoxLayout()
        self.sample_rate = QComboBox()
        self.sample_rate.addItems(['22050', '32000', '44100', '48000', '96000'])
        self.sample_rate.setCurrentText('48000')
        self.channels = QComboBox()
        self.channels.addItems([tr('ui.150'), tr('ui.151')])
        self.bit_depth = QComboBox()
        self.bit_depth.addItems(['16-bit PCM', '24-bit PCM', '32-bit Float'])
        self.worker_count = QSpinBox()
        self.worker_count.setRange(1, max(1, (os.cpu_count() or 2) - 1))
        self.worker_count.setValue(1)
        for widget in (self.sample_rate, self.channels, self.bit_depth):
            option_row.addWidget(widget)
        option_row.addWidget(_i18n_mark(QLabel(tr('ui.155')), 'text', 'ui.155'))
        option_row.addWidget(self.worker_count)
        option_row.addStretch(1)
        export_layout.addLayout(option_row)
        self.loudness_status = QLabel()
        self.loudness_status.setObjectName('mutedLabel')
        export_layout.addWidget(self.loudness_status)
        layout.addWidget(export_panel)
        self.status_label = QLabel('—')
        self.status_label.setObjectName('mutedLabel')
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def retranslate(self) -> None:
        _i18n_refresh(self)
        self._update_loudness_status()

    # —— 对外能力 ——

    @property
    def is_busy(self) -> bool:
        return self._save_thread is not None or self._preview_thread is not None or bool(self._waveform_threads) or (self._silence_thread is not None) or (self._analysis_thread is not None)

    @property
    def exporting(self) -> bool:
        return self._save_thread is not None

    @property
    def has_clips(self) -> bool:
        return bool(self._timeline.items)

    def load_paths(self, paths: list[str]) -> None:
        """载入音频并构建波形（与页面 _add_audio_paths 同链路）。"""
        for raw in paths:
            path = Path(raw)
            if not path.is_file():
                self._set_status(tr('ui.183').format(path.name))
                continue
            request_id = uuid4().hex
            self._pending_audio_paths[request_id] = path
            self._build_waveform(request_id, path)
        if self._pending_audio_paths and (not self._timeline.items):
            self._playback_state = PlaybackState.PREPARING
            self._set_status(tr('ui.184'))
        self._sync()

    def settings_snapshot(self) -> ExportSettings:
        return ExportSettings(sample_rate=int(self.sample_rate.currentText()), channels=1 if self.channels.currentIndex() == 0 else 2, bit_depth=self.bit_depth.currentText(), normalize_mode=self._normalize_mode, normalize_target=self._normalize_target, keep_timeline=False, worker_threads=self.worker_count.value(), output_format=self._output_format, quality=self._quality, fade_ms=self._fade_ms, trim_silence=self._trim_silence, denoise=self._denoise, denoise_strength=self._denoise_strength, declick=self._declick, deesser=self._deesser, voice_preset=self._voice_preset, gain_db=self._gain_db)

    def request_save(self, target: Path) -> None:
        """把当前时间轴按当前选项渲染到 target（覆盖写，原子替换）。"""
        if self.is_busy or (not self._timeline.items):
            return
        settings = self.settings_snapshot()
        snapshot = self._timeline.snapshot(settings.sample_rate, settings.channels)
        self._export_cancel_event = threading.Event()
        thread = QThread(self)
        worker = AudioExportService(snapshot, settings, target, self._export_cancel_event)
        worker.measurement_cache = self._loudness_cache
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._save_progress)
        worker.finished.connect(self._save_done)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._save_thread_done)
        self._save_thread = thread
        self._save_worker = worker
        thread.start()
        self._sync()

    def request_safe_close(self) -> bool:
        """关窗守卫：闲则收尾放行，忙则取消可取消任务并等下一轮状态。"""
        if not self.is_busy:
            self._stop()
            return True
        self._export_cancel_event.set()
        self._preview_cancel_event.set()
        self._silence_cancel.set()
        self._analysis_cancel.set()
        self._finalize_playback(PlaybackEndReason.TIMELINE_CHANGED, reset_playhead=False)
        if self._preview_path is not None:
            self._preview_path.unlink(missing_ok=True)
            self._preview_path = None
        return False

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    # —— 波形载入 ——

    def _build_waveform(self, clip_id: str, path: Path) -> None:
        thread = QThread(self)
        worker = WaveformWorker(clip_id, path)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._waveform_done)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(lambda key=clip_id: self._waveform_thread_done(key))
        self._waveform_threads[clip_id] = (thread, worker)
        thread.start()

    def _waveform_thread_done(self, request_id: str) -> None:
        self._waveform_threads.pop(request_id, None)
        self._sync()

    def _waveform_done(self, request_id: str, duration_ms: int, waveform: object, error: str) -> None:
        path = self._pending_audio_paths.pop(request_id, None)
        if path is None:
            return
        if duration_ms > 0:
            clip = self._timeline.add_audio(path, duration_ms / 1000)
            if waveform is not None:
                self._timeline.set_waveform(clip.clip_id, waveform)
            self._render_timeline()
            self._invalidate_preview()
            self._set_status(tr('ui.185').format(path.name))
        else:
            self._set_status(tr('ui.186').format(path.name, error))
            self._playback_state = PlaybackState.READY if self._timeline.items else PlaybackState.EMPTY
            self._sync()

    # —— 时间轴编辑 ——

    def _set_selection(self, ids: set[str]) -> None:
        self._selected = ids
        self._sync()

    def _trim_preview(self, _clip_id: str, start_ms: int, end_ms: int) -> None:
        self._set_status(tr('ui.187').format(format_ms(start_ms), format_ms(end_ms), format_ms(end_ms - start_ms)))

    def _trim_committed(self, clip_id: str, start_ms: int, end_ms: int) -> None:
        self._timeline.trim_ms(clip_id, start_ms, end_ms)
        self._render_timeline()
        self._invalidate_preview()

    def _move_committed(self, ids: set[str], index: int) -> None:
        self._timeline.move(ids, index)
        self._render_timeline()
        self._invalidate_preview()

    def _relative_zoom(self, multiplier: float) -> None:
        import math
        ratio = math.log(self.timeline_view.pixels_per_second * multiplier / 2) / math.log(1000 / 2) * 1000
        self.zoom.setValue(max(self.zoom.minimum(), min(self.zoom.maximum(), round(ratio))))

    def _set_zoom_from_slider(self, value: int) -> None:
        pps = 2 * (1000 / 2) ** (value / 1000)
        self.timeline_view.animate_pixels_per_second(pps)

    def _delete_selected(self) -> None:
        self._timeline.remove(self._selected)
        self._selected.clear()
        self._render_timeline()
        self._invalidate_preview()

    def _undo(self) -> None:
        result = self._timeline.undo()
        if result is not None and result.kind is TimelineEditKind.SPLIT and (result.split is not None):
            self._selected = {result.split.original_clip_id}
            self.playhead_time_ms = result.split.timeline_position_ms
        else:
            existing = {item.clip_id for item in self._timeline.items}
            self._selected.intersection_update(existing)
        self._render_timeline()
        self._invalidate_preview()

    def _split_audio(self) -> None:
        location = self._timeline.locate(self.playhead_time_ms)
        if location is None or location.kind is not TimelineClipKind.AUDIO or location.offset_ms < 1 or (self._timeline.items[location.index].duration_ms - location.offset_ms < 1):
            self._set_status(tr('ui.188'))
            return
        if self.is_busy:
            self._set_status(tr('ui.189'))
            return
        if self._playback_state is PlaybackState.PLAYING:
            self._finalize_playback(PlaybackEndReason.TIMELINE_CHANGED, reset_playhead=False)
        try:
            result = self._timeline.split_audio_at(location.clip_id, self.playhead_time_ms)
        except ValueError as error:
            self._set_status(str(error))
            self._sync()
            return
        self._selected = {result.right_clip_id}
        self._render_timeline()
        self.timeline_view.flash_split_at(result.timeline_position_ms)
        self._invalidate_preview()
        self._set_status(tr('ui.190').format(result.timeline_position_ms / 1000))

    def _seek(self, position: float) -> None:
        position_ms = max(0, min(self._timeline.duration_ms, int(position)))
        self.playhead_time_ms = position_ms
        self.timeline_view.set_playhead_ms(position_ms)
        if self._playback_state is PlaybackState.PLAYING:
            self._player.setPosition(position_ms)
        self.time_label.setText(f'{format_ms(position_ms)} / {format_ms(self._timeline.duration_ms)}')
        self._sync()

    def _playhead_drag_started(self) -> None:
        if self._playback_state is PlaybackState.PLAYING:
            self._finalize_playback(PlaybackEndReason.SEEK, reset_playhead=False)

    def _playhead_drag_preview(self, position_ms: int) -> None:
        self.playhead_time_ms = max(0, min(self._timeline.duration_ms, position_ms))
        self.time_label.setText(f'{format_ms(self.playhead_time_ms)} / {format_ms(self._timeline.duration_ms)}')
        self._sync()

    def _render_timeline(self) -> None:
        self.playhead_time_ms = max(0, min(self.playhead_time_ms, self._timeline.duration_ms))
        self.timeline_view.set_timeline(self._timeline, self._selected)
        self.timeline_view.set_playhead_ms(self.playhead_time_ms)
        self.time_label.setText(f'{format_ms(self.playhead_time_ms)} / {format_ms(self._timeline.duration_ms)}')
        self._sync()

    # —— 渲染导出 ——

    def _save_progress(self, step: str, percent: int, filename: str) -> None:
        self._set_status(f'{step}：{filename}')

    def _save_done(self, ok: bool, message: str, _target: object) -> None:
        self._set_status(message)
        self.save_finished.emit(ok, message)

    def _save_thread_done(self) -> None:
        self._save_thread = None
        self._save_worker = None
        self._sync()

    # —— 试听引擎（自音频处理页原样迁移的状态机） ——

    def _preview(self) -> None:
        LOGGER.info('Editor preview play request: state=%s playhead_ms=%s total_ms=%s', self._playback_state.value, self.playhead_time_ms, self._timeline.duration_ms)
        if not self._timeline.items:
            self._set_status(tr('ui.202'))
            return
        settings = self.settings_snapshot()
        snapshot = self._timeline.snapshot(settings.sample_rate, settings.channels)
        if self.loop_selected.isChecked() and (not self._selected):
            self._set_status(tr('ui.203'))
            return
        if self._preview_path and self._preview_path.is_file() and (self._preview_version == snapshot.version):
            self._queue_preview_playback(self._preview_path, self._preview_start_position(snapshot.total_duration_ms))
            return
        self._playback_state = PlaybackState.PREPARING
        self._preview_cancel_event = threading.Event()
        target = temp_dir() / f'wt_editor_preview_{id(self)}_{snapshot.version}.wav'
        thread = QThread(self)
        worker = AudioPreviewService(snapshot, settings, target, self._preview_cancel_event)
        worker.measurement_cache = self._loudness_cache
        worker.moveToThread(thread)
        self._preview_version = snapshot.version
        thread.started.connect(worker.run)
        worker.progress.connect(lambda step, _p, _f: self._set_status(tr('ui.204').format(step)))
        worker.finished.connect(self._preview_done)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._preview_thread_done)
        self._preview_thread = thread
        self._preview_worker = worker
        thread.start()
        self._sync()

    def _preview_done(self, ok: bool, message: str, target: object) -> None:
        if ok and isinstance(target, Path):
            if self._preview_version != self._timeline.snapshot().version:
                target.unlink(missing_ok=True)
                self._playback_state = PlaybackState.READY
                return
            self._preview_path = target
            self._queue_preview_playback(target, self._preview_start_position(self._timeline.duration_ms))
        else:
            self._set_status(message)
            self._playback_state = PlaybackState.ERROR

    def _preview_thread_done(self) -> None:
        self._preview_thread = None
        self._preview_worker = None
        self._sync()

    def _preview_start_position(self, total_duration_ms: int) -> int:
        position = self.playhead_time_ms
        if position >= max(0, total_duration_ms - 1):
            position = 0
            self.playhead_time_ms = 0
            self.timeline_view.set_playhead_ms(0)
        loop_range = self._loop_range()
        if loop_range is not None and (not loop_range[0] <= position < loop_range[1]):
            position = loop_range[0]
            self.playhead_time_ms = position
            self.timeline_view.set_playhead_ms(position)
        return position

    def _queue_preview_playback(self, path: Path, position_ms: int) -> None:
        self._pending_play_start_ms = max(0, min(self._timeline.duration_ms, position_ms))
        source = QUrl.fromLocalFile(str(path))
        same_source = self._player.source() == source
        if not same_source:
            self._player.setSource(source)
        if same_source or self._player.mediaStatus() in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self._start_pending_playback()
        else:
            self._playback_state = PlaybackState.PREPARING
            self._sync()

    def _start_pending_playback(self) -> None:
        if self._pending_play_start_ms is None:
            return
        position = self._pending_play_start_ms
        self._pending_play_start_ms = None
        self._playback_session_id += 1
        self._active_playback_session_id = self._playback_session_id
        self._player.setPosition(position)
        self._player.play()
        self._playback_state = PlaybackState.PLAYING
        self._sync()

    def _stop(self) -> None:
        if self._playback_state is PlaybackState.PREPARING:
            self._preview_cancel_event.set()
        self._finalize_playback(PlaybackEndReason.USER_STOP, reset_playhead=True)

    def _finalize_playback(self, reason: PlaybackEndReason, *, reset_playhead: bool) -> None:
        if self._finalizing_playback:
            return
        if reason is PlaybackEndReason.NATURAL_END and self._active_playback_session_id is None:
            return
        self._finalizing_playback = True
        if reason is PlaybackEndReason.NATURAL_END:
            visual_position = self._timeline.duration_ms
        elif reset_playhead:
            visual_position = 0
        else:
            visual_position = max(0, min(self.playhead_time_ms, self._timeline.duration_ms))
        try:
            self._pending_play_start_ms = None
            self._active_playback_session_id = None
            self._player.stop()
            self._player.setPosition(0)
            self.playhead_time_ms = visual_position
            self.timeline_view.set_playhead_ms(visual_position)
            self.time_label.setText(f'{format_ms(visual_position)} / {format_ms(self._timeline.duration_ms)}')
            if not self._timeline.items:
                self._playback_state = PlaybackState.EMPTY
            elif reason is PlaybackEndReason.ERROR:
                self._playback_state = PlaybackState.ERROR
            elif reason is PlaybackEndReason.USER_STOP:
                self._playback_state = PlaybackState.STOPPED
            else:
                self._playback_state = PlaybackState.READY
            self._sync()
        finally:
            self._finalizing_playback = False

    def _play_position(self, position: int) -> None:
        if self._finalizing_playback:
            return
        self.playhead_time_ms = max(0, min(self._timeline.duration_ms, position))
        self.timeline_view.set_playhead_ms(self.playhead_time_ms)
        self.time_label.setText(f'{format_ms(self.playhead_time_ms)} / {format_ms(self._timeline.duration_ms)}')
        loop_range = self._loop_range()
        if loop_range is not None and position >= loop_range[1]:
            self._player.setPosition(loop_range[0])
            self._player.play()

    def _loop_range(self) -> tuple[int, int] | None:
        if not self.loop_selected.isChecked() or not self._selected:
            return None
        indexes = [index for index, item in enumerate(self._timeline.items) if item.clip_id in self._selected]
        if not indexes:
            return None
        first, last = (min(indexes), max(indexes))
        start = sum(item.duration_ms for item in self._timeline.items[:first])
        end = sum(item.duration_ms for item in self._timeline.items[:last + 1])
        return (start, end)

    def _play_state(self, state: object) -> None:
        if self._finalizing_playback:
            return
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._playback_state = PlaybackState.PLAYING
        elif self._active_playback_session_id is None and self._pending_play_start_ms is None and (self._playback_state not in (PlaybackState.ERROR, PlaybackState.PREPARING)):
            self._playback_state = PlaybackState.STOPPED if self._timeline.items else PlaybackState.EMPTY
        self._sync()

    def _media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self._start_pending_playback()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            loop_range = self._loop_range()
            if loop_range is not None and self._active_playback_session_id is not None:
                self.playhead_time_ms = loop_range[0]
                self.timeline_view.set_playhead_ms(self.playhead_time_ms)
                self._player.setPosition(loop_range[0])
                self._player.play()
                self._playback_state = PlaybackState.PLAYING
                self._sync()
                return
            if self._active_playback_session_id is None:
                return
            tolerance_ms = 5
            observed_position = max(self.playhead_time_ms, self._player.position())
            if observed_position < self._timeline.duration_ms - tolerance_ms:
                return
            self._finalize_playback(PlaybackEndReason.NATURAL_END, reset_playhead=False)

    def _playback_error(self, _error: QMediaPlayer.Error, message: str) -> None:
        if not message:
            return
        self._set_status(tr('ui.205').format(message))
        LOGGER.error('Editor preview playback error: %s', message)
        self._finalize_playback(PlaybackEndReason.ERROR, reset_playhead=False)

    def _invalidate_preview(self) -> None:
        self._preview_cancel_event.set()
        self._finalize_playback(PlaybackEndReason.TIMELINE_CHANGED, reset_playhead=False)
        if self._preview_path is not None:
            self._preview_path.unlink(missing_ok=True)
            self._preview_path = None
        self._preview_version = None

    # —— 静音切分 / 响度分析 ——

    def _audio_scan_items(self) -> tuple[tuple[str, int, str, Path, int, int], ...]:
        items: list[tuple[str, int, str, Path, int, int]] = []
        timeline_start = 0
        for item in self._timeline.items:
            if isinstance(item, AudioClip) and item.source_path is not None:
                items.append((item.clip_id, timeline_start, f'{timeline_start / 1000:.3f}s {item.source_path.name}', item.source_path, item.trim_start_ms, item.effective_end_ms))
            timeline_start += item.duration_ms
        return tuple(items)

    def _detect_silence(self) -> None:
        if self.is_busy or not self._audio_scan_items():
            self._set_status(tr('ui.202'))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('audio.button.silence'))
        layout = QVBoxLayout(dialog)
        threshold = QSpinBox()
        threshold.setRange(-60, -20)
        threshold.setValue(-35)
        threshold.setSuffix(' dB')
        min_duration = QSpinBox()
        min_duration.setRange(100, 5000)
        min_duration.setValue(400)
        min_duration.setSuffix(' ms')
        threshold_row = QHBoxLayout()
        threshold_row.addWidget(_i18n_mark(QLabel(tr('dialog.silence.threshold')), 'text', 'dialog.silence.threshold'))
        threshold_row.addWidget(threshold)
        duration_row = QHBoxLayout()
        duration_row.addWidget(_i18n_mark(QLabel(tr('dialog.silence.min_duration')), 'text', 'dialog.silence.min_duration'))
        duration_row.addWidget(min_duration)
        layout.addLayout(threshold_row)
        layout.addLayout(duration_row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._silence_cancel = threading.Event()
        items = tuple(((clip_id, timeline_start, source, trim_start, trim_end) for clip_id, timeline_start, _label, source, trim_start, trim_end in self._audio_scan_items()))
        worker = SilenceDetectWorker(items, threshold.value(), min_duration.value(), self._silence_cancel)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._silence_done)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._silence_thread_done)
        self._silence_thread = thread
        self._silence_worker = worker
        self._set_status(tr('dialog.silence.scanning'))
        self._sync()
        thread.start()

    def _silence_thread_done(self) -> None:
        self._silence_thread = None
        self._silence_worker = None
        self._sync()

    def _silence_done(self, results: object, error: str) -> None:
        if error:
            self._set_status(error)
            return
        if not results:
            self._set_status(tr('dialog.silence.none'))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('audio.button.silence'))
        layout = QVBoxLayout(dialog)
        layout.addWidget(_i18n_mark(QLabel(tr('dialog.silence.results')), 'text', 'dialog.silence.results'))
        checks: list[tuple[QCheckBox, int]] = []
        for item in results:
            start_ms, end_ms = (item['start_ms'], item['end_ms'])
            checkbox = QCheckBox(f'{start_ms / 1000:.3f}s - {end_ms / 1000:.3f}s  ({end_ms - start_ms} ms)')
            checkbox.setChecked(True)
            checks.append((checkbox, (start_ms + end_ms) // 2))
            layout.addWidget(checkbox)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr('dialog.silence.apply'))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        midpoints = [midpoint for checkbox, midpoint in checks if checkbox.isChecked()]
        count = self._timeline.split_at_silences(midpoints)
        self._render_timeline()
        self._invalidate_preview()
        self._set_status(tr('ui.207').format(count))

    def _analyze_clips(self) -> None:
        items = self._audio_scan_items()
        if self.is_busy or not items:
            self._set_status(tr('ui.202'))
            return
        # LoudnessScanWorker 吃 5 元组，_audio_scan_items 是
        # 6 元组——直传会在 worker 里 ValueError 且 finished 永不发出，整页
        # 卡忙（静音检测那边本就有映射，分析这边漏了）
        mapped = tuple((c[0], c[2], c[3], c[4], c[5]) for c in items)
        self._analysis_cancel = threading.Event()
        worker = LoudnessScanWorker(mapped, self._analysis_cancel)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._analysis_done)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._analysis_thread_done)
        self._analysis_thread = thread
        self._analysis_worker = worker
        self._analysis_items = items
        self._set_status(tr('dialog.analyze.scanning'))
        self._sync()
        thread.start()

    def _analysis_thread_done(self) -> None:
        self._analysis_thread = None
        self._analysis_worker = None
        self._sync()

    def _analysis_done(self, results: object, error: str) -> None:
        if error:
            self._set_status(error)
            return
        assert isinstance(results, list)
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('dialog.analyze.title'))
        layout = QVBoxLayout(dialog)
        table = QTableWidget(len(results), 5)
        table.setHorizontalHeaderLabels([tr('dialog.analyze.column_clip'), tr('dialog.analyze.column_duration'), tr('dialog.analyze.column_lufs'), tr('dialog.analyze.column_peak'), tr('dialog.analyze.spectrum')])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, item in enumerate(results):
            table.setItem(row, 0, QTableWidgetItem(str(item['label'])))
            table.setItem(row, 1, QTableWidgetItem(format_ms(int(item['duration_ms']))))
            table.setItem(row, 2, QTableWidgetItem(f"{item['lufs']:.1f}"))
            table.setItem(row, 3, QTableWidgetItem('' if item['peak_dbfs'] is None else f"{item['peak_dbfs']:.1f}"))
            spectrum_button = _i18n_mark(QPushButton(tr('dialog.analyze.spectrum')), 'text', 'dialog.analyze.spectrum')
            spectrum_button.clicked.connect(lambda _checked=False, row=row: self._show_spectrum(row))
            table.setCellWidget(row, 4, spectrum_button)
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(table)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        self._analysis_results = results
        dialog.resize(760, 420)
        dialog.exec()

    def _show_spectrum(self, row: int) -> None:
        if self._analysis_thread is not None:
            self._set_status(tr('ui.208'))
            return
        results = getattr(self, '_analysis_results', [])
        if not 0 <= row < len(results):
            return
        clip_id = results[row]['clip_id']
        item = next((entry for entry in self._audio_scan_items() if entry[0] == clip_id), None)
        if item is None:
            return
        _clip_id, _timeline_start, _label, source, trim_start, trim_end = item
        target = temp_dir() / f'spectrum_{clip_id[:8]}.png'
        self._analysis_cancel = threading.Event()
        worker = SpectrumWorker(source, trim_start, trim_end, target, self._analysis_cancel)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._spectrum_done)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._analysis_thread_done)
        self._analysis_thread = thread
        self._analysis_worker = worker
        self._sync()
        thread.start()

    def _spectrum_done(self, path: object, error: str) -> None:
        if error:
            self._set_status(error)
            return
        assert isinstance(path, Path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # —— 处理选项（与页面共用同一组 QSettings 键） ——

    def _update_loudness_status(self) -> None:
        if not hasattr(self, 'loudness_status'):
            return
        if self._normalize_mode == 'peak':
            self.loudness_status.setText(tr('ui.209').format(self._normalize_target))
        elif self._normalize_mode == 'loudness':
            self.loudness_status.setText(tr('ui.210').format(self._normalize_target))
        elif self._normalize_mode == 'speech':
            self.loudness_status.setText(tr('dialog.processing.speech'))
        else:
            self.loudness_status.setText(tr('ui.211'))

    def _on_loudness_target_changed(self, value: float) -> None:
        self._normalize_target = value
        self._settings.setValue('audio/normalize_target', value)
        if self._normalize_mode == 'loudness':
            self._loudness_cache.clear()
        self._update_loudness_status()

    def _on_gain_changed(self, value: float) -> None:
        self._gain_db = value
        self._settings.setValue('audio/gain_db', value)

    def _invalidate_loudness_cache(self) -> None:
        self._loudness_cache.clear()

    def _on_normalize_mode_changed(self, index: int) -> None:
        value = self.normalize_mode_combo.itemData(index)
        self._normalize_mode = None if value == 'off' else value
        self._settings.setValue('audio/normalize_mode', self._normalize_mode or '')
        self._invalidate_loudness_cache()
        self._update_loudness_status()

    def _on_denoise_changed(self, index: int) -> None:
        self._denoise = self.denoise_combo.itemData(index) or 'off'
        self._settings.setValue('audio/denoise', self._denoise)
        self._invalidate_loudness_cache()

    def _on_denoise_strength_changed(self, value: int) -> None:
        self._denoise_strength = value
        self._settings.setValue('audio/denoise_strength', value)
        self._invalidate_loudness_cache()

    def _on_declick_changed(self, checked: bool) -> None:
        self._declick = checked
        self._settings.setValue('audio/declick', checked)
        self._invalidate_loudness_cache()

    def _on_deesser_changed(self, checked: bool) -> None:
        self._deesser = checked
        self._settings.setValue('audio/deesser', checked)
        self._invalidate_loudness_cache()

    def _on_preset_changed(self, index: int) -> None:
        self._voice_preset = self.preset_combo.itemData(index) or 'off'
        self._settings.setValue('audio/voice_preset', self._voice_preset)
        self._invalidate_loudness_cache()

    def _on_fade_changed(self, value: int) -> None:
        self._fade_ms = value
        self._settings.setValue('audio/fade_ms', value)
        self._invalidate_loudness_cache()

    def _on_trim_edges_changed(self, checked: bool) -> None:
        self._trim_silence = 'edges' if checked else 'off'
        self._settings.setValue('audio/trim_silence', self._trim_silence)
        self._invalidate_loudness_cache()

    def _sync(self, *_args: object) -> None:
        busy = self.is_busy
        can_preview = self._playback_state in (PlaybackState.READY, PlaybackState.STOPPED, PlaybackState.ERROR) and bool(self._timeline.items) and (not busy)
        self.preview_button.setEnabled(can_preview)
        self.preview_button.setToolTip(tr('ui.202') if self._playback_state is PlaybackState.EMPTY else '')
        self.stop_button.setEnabled(self._playback_state in (PlaybackState.PREPARING, PlaybackState.PLAYING))
        location = self._timeline.locate(self.playhead_time_ms)
        can_split = not busy and location is not None and (location.kind is TimelineClipKind.AUDIO) and (location.offset_ms >= 1) and (self._timeline.items[location.index].duration_ms - location.offset_ms >= 1)
        self.split_button.setEnabled(can_split)
        self.split_button.setToolTip('' if can_split else tr('ui.188'))
        self.silence_button.setEnabled(not busy and bool(self._timeline.items))
        self.analyze_button.setEnabled(not busy and bool(self._timeline.items))
        self.state_changed.emit()
