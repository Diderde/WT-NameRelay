from __future__ import annotations

import logging
import os
import threading
from enum import Enum
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import (
    QFileSystemWatcher,
    QSettings,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.audio import (
    AudioClip,
    AudioExportService,
    AudioMatrixExportService,
    AudioPreviewService,
    AudioProjectService,
    ExportSettings,
    LoudnessScanWorker,
    ProjectGroupRepository,
    SilenceDetectWorker,
    SpectrumWorker,
    TimelineClipKind,
    TimelineEditKind,
    TimelineModel,
    WaveformWorker,
    output_extension,
)
from app.audio.models import format_ms
from app.audio.project_service import CREW_CATEGORIES, RADIO_CATEGORIES, ProjectGroup
from app.contracts import TaskState, TaskStatusSnapshot
from app.i18n import i18n_live, i18n_text, tr
from app.i18n import mark as _i18n_mark
from app.i18n import refresh as _i18n_refresh
from app.models import (
    ConflictPolicy,
    CopyBatchResult,
    CopyPlan,
    CopyResultStatus,
    CopyTask,
    ManualCopyMode,
    RadioStagedCopyPlan,
    RadioTargetOperation,
)
from app.paths import config_dir, temp_dir
from app.services import (
    AudioProcessingSourceAdapter,
    CrewFileService,
    DistributionFileCopyService,
    MatrixGroupPlanner,
)
from app.widgets import (
    AudioPageScrollRouter,
    CopyModeSwitch,
    FileDropArea,
    ScrollPositionGuard,
    TaskStatusPanel,
)
from app.widgets.pyqtgraph_timeline import PyQtGraphTimeline

from .base_tool_page import BaseToolPage

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

class AudioProcessingPage(BaseToolPage):
    """Project-scoped, non-destructive single-track voice processing page."""
    close_ready = Signal()

    def __init__(self, parent: QWidget | None=None) -> None:
        super().__init__('audio', i18n_text('ui.130'), parent)
        self.status_panel.setVisible(False)
        self._settings = QSettings(str(config_dir() / 'settings.ini'), QSettings.IniFormat)
        self._project = AudioProjectService()
        self._groups = ProjectGroupRepository()
        self._timeline = TimelineModel()
        self._selected: set[str] = set()
        self._active_module = 'crew'
        self._active_category = CREW_CATEGORIES[0]
        self._current_group: ProjectGroup | None = None
        self._root: Path | None = None
        self._watcher = QFileSystemWatcher(self)
        self._watch_timer = QTimer(self)
        self._watch_timer.setSingleShot(True)
        self._watch_timer.setInterval(500)
        self._watch_timer.timeout.connect(self._refresh_group)
        self._completion_message_timer = QTimer(self)
        self._completion_message_timer.setSingleShot(True)
        self._completion_message_timer.setInterval(2000)
        self._completion_message_timer.timeout.connect(self._restore_project_ready_status)
        self._export_cancel_event = threading.Event()
        self._preview_cancel_event = threading.Event()
        self._export_thread: QThread | None = None
        self._export_worker: AudioExportService | AudioMatrixExportService | None = None
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
        self._output_format: str = self._settings.value('audio/output_format', 'wav', str) or 'wav'
        self._quality: str = self._settings.value('audio/quality', '', str) or ''
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
        self._copy_service = CrewFileService()
        self._matrix_copy_service = DistributionFileCopyService()
        self._matrix_copy_service.setParent(self)
        self._matrix_planner = MatrixGroupPlanner()
        self._average_source_adapter = AudioProcessingSourceAdapter()
        self._audio_copy_mode = ManualCopyMode.SEQUENTIAL
        self._resolved_group_key: str | None = None
        self._navigation_enabled = True
        self._completion_announced = False
        self._close_pending = False
        self._watch_suspended = False
        self._watch_refresh_pending = False
        self._fill_available = False
        self._target_menu_has_items = False
        self._task_first_progress_logged = False
        self.set_body_widget(self._build())
        self._watcher.directoryChanged.connect(self._on_watched_directory_changed)
        self._copy_service.snapshot_changed.connect(self.copy_status.set_snapshot)
        self._copy_service.snapshot_changed.connect(self._task_progress_observed)
        self._copy_service.busy_changed.connect(self._sync)
        self._copy_service.batch_finished.connect(lambda _result: self._refresh_group())
        self._matrix_copy_service.snapshot_changed.connect(self.copy_status.set_snapshot)
        self._matrix_copy_service.snapshot_changed.connect(self._task_progress_observed)
        self._matrix_copy_service.busy_changed.connect(self._matrix_copy_busy_changed)
        self._matrix_copy_service.batch_finished.connect(self._matrix_copy_finished)
        self._restore_settings()
        self._sync()
        _i18n_mark(self.target_info, 'scope', None)
        _i18n_mark(self.group_detail, 'scope', None)
        _i18n_mark(self.output_label, 'scope', None)
        _i18n_mark(self.loudness_status, 'scope', None)
        _i18n_mark(self.copy_status, 'scope', None)

    def retranslate(self) -> None:
        super().retranslate()
        _i18n_refresh(self)
        getattr(getattr(self, 'drop_area', None), 'retranslate', None) and self.drop_area.retranslate()
        getattr(getattr(self, 'copy_status', None), 'retranslate', None) and self.copy_status.retranslate()
        self._build_categories()
        self._update_loudness_status()
        for _btn_id, _btn in getattr(self, '_module_button_by_id', {}).items():
            _btn.setText(i18n_live('ui.134' if _btn_id == 'crew' else 'ui.135'))

    @property
    def is_busy(self) -> bool:
        return self._export_thread is not None or self._preview_thread is not None or bool(self._waveform_threads) or self._copy_service.is_busy or self._matrix_copy_service.is_busy or (self._silence_thread is not None) or (self._analysis_thread is not None)

    def can_navigate_away(self) -> bool:
        if self.is_busy:
            return False
        self._stop()
        return True

    def request_safe_close(self) -> bool:
        if not self.is_busy:
            self._stop()
            return True
        self._close_pending = True
        self._export_cancel_event.set()
        self._preview_cancel_event.set()
        self._silence_cancel.set()
        self._analysis_cancel.set()
        self._finalize_playback(PlaybackEndReason.TIMELINE_CHANGED, reset_playhead=False)
        if self._preview_path is not None:
            self._preview_path.unlink(missing_ok=True)
            self._preview_path = None
        self._copy_service.cancel()
        self._matrix_copy_service.cancel()
        return False

    def set_navigation_enabled(self, enabled: bool) -> None:
        self._navigation_enabled = enabled
        self.back_button.setEnabled(enabled and (not self.is_busy))

    def _panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName('crewManualPanel')
        return panel

    def _build(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName('audioProcessingScroll')
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSpacing(12)
        project_panel = self._panel()
        project_row = QHBoxLayout(project_panel)
        project_row.addWidget(_i18n_mark(_i18n_mark(QLabel(i18n_text('ui.243')), 'text', 'ui.243'), 'text', 'ui.243'))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(i18n_text('ui.131'))
        project_row.addWidget(self.path_edit, 1)
        choose_root = _i18n_mark(_i18n_mark(QPushButton(i18n_text('ui.132')), 'text', 'ui.132'), 'text', 'ui.132')
        rescan = _i18n_mark(_i18n_mark(QPushButton(i18n_text('ui.133')), 'text', 'ui.133'), 'text', 'ui.133')
        choose_root.clicked.connect(self._choose_root)
        rescan.clicked.connect(self._set_root)
        project_row.addWidget(choose_root)
        project_row.addWidget(rescan)
        layout.addWidget(project_panel)
        module_panel = QFrame()
        module_layout = QHBoxLayout(module_panel)
        self.module_buttons = QButtonGroup(self)
        self.module_buttons.setExclusive(True)
        self._module_button_by_id: dict[str, QPushButton] = {}
        for module, label in (('crew', i18n_live('ui.134')), ('radio', i18n_live('ui.135'))):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty('audioNavigation', True)
            button.setChecked(module == self._active_module)
            button.clicked.connect(lambda _checked=False, value=module: self._change_module(value))
            self.module_buttons.addButton(button)
            self._module_button_by_id[module] = button
            module_layout.addWidget(button)
        module_layout.addStretch(1)
        layout.addWidget(module_panel)
        self.category_panel = QFrame()
        self.category_layout = QHBoxLayout(self.category_panel)
        self.category_buttons = QButtonGroup(self)
        self.category_buttons.setExclusive(True)
        self._category_button_by_id: dict[str, QPushButton] = {}
        self.category_layout.setContentsMargins(8, 6, 8, 6)
        layout.addWidget(self.category_panel)
        self._build_categories()
        target_panel = self._panel()
        target_layout = QVBoxLayout(target_panel)
        target_layout.addWidget(_i18n_mark(_i18n_mark(QLabel(i18n_text('ui.136')), 'text', 'ui.136'), 'text', 'ui.136'))
        self.target_edit = QLineEdit()
        self.target_edit.setPlaceholderText(i18n_text('ui.137'))
        self.target_info = _i18n_mark(_i18n_mark(QLabel(i18n_text('ui.138')), 'text', 'ui.138'), 'text', 'ui.138')
        self.target_info.setObjectName('mutedLabel')
        self.target_menu_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown), i18n_text('ui.139'), self.target_edit)
        self.target_menu_action.setEnabled(False)
        self.target_menu_action.triggered.connect(self._show_target_menu)
        self.target_edit.addAction(self.target_menu_action, QLineEdit.ActionPosition.TrailingPosition)
        target_layout.addWidget(self.target_edit)
        target_layout.addWidget(self.target_info)
        layout.addWidget(target_panel)
        self._target_timer = QTimer(self)
        self._target_timer.setSingleShot(True)
        self._target_timer.setInterval(300)
        self._target_timer.timeout.connect(self._resolve_target)
        self.target_edit.textChanged.connect(lambda _text: self._target_timer.start())
        actions = QFrame()
        actions.setObjectName('crewActionBar')
        action_layout = QHBoxLayout(actions)
        self.add_audio_button = _i18n_mark(_i18n_mark(QPushButton(i18n_text('ui.140')), 'text', 'ui.140'), 'text', 'ui.140')
        self.blank_button = _i18n_mark(_i18n_mark(QPushButton(i18n_text('ui.141')), 'text', 'ui.141'), 'text', 'ui.141')
        self.remove_button = _i18n_mark(_i18n_mark(QPushButton(i18n_text('ui.142')), 'text', 'ui.142'), 'text', 'ui.142')
        self.split_button = _i18n_mark(_i18n_mark(QPushButton(i18n_text('ui.143')), 'text', 'ui.143'), 'text', 'ui.143')
        self.undo_button = _i18n_mark(_i18n_mark(QPushButton(i18n_text('ui.144')), 'text', 'ui.144'), 'text', 'ui.144')
        self.silence_button = _i18n_mark(QPushButton(i18n_text('audio.button.silence')), 'text', 'audio.button.silence')
        self.analyze_button = _i18n_mark(QPushButton(i18n_text('audio.button.analyze')), 'text', 'audio.button.analyze')
        self.preview_button = _i18n_mark(_i18n_mark(QPushButton(i18n_text('ui.145')), 'text', 'ui.145'), 'text', 'ui.145')
        self.stop_button = _i18n_mark(_i18n_mark(QPushButton(i18n_text('ui.146')), 'text', 'ui.146'), 'text', 'ui.146')
        self.loop_selected = _i18n_mark(_i18n_mark(QCheckBox(i18n_text('ui.147')), 'text', 'ui.147'), 'text', 'ui.147')
        self.add_audio_button.clicked.connect(self._choose_audio)
        self.blank_button.clicked.connect(self._add_blank)
        self.remove_button.clicked.connect(self._delete_selected)
        self.split_button.clicked.connect(self._split_audio)
        self.undo_button.clicked.connect(self._undo)
        self.silence_button.clicked.connect(self._detect_silence)
        self.analyze_button.clicked.connect(self._analyze_clips)
        self.preview_button.clicked.connect(self._preview)
        self.stop_button.clicked.connect(self._stop)
        for button in (self.add_audio_button, self.blank_button, self.remove_button, self.split_button, self.undo_button, self.silence_button, self.analyze_button, self.preview_button, self.stop_button, self.loop_selected):
            action_layout.addWidget(button)
        action_layout.addStretch(1)
        layout.addWidget(actions)
        self.drop_area = FileDropArea()
        self.drop_area.files_dropped.connect(self._add_audio_paths)
        self.drop_area.choose_requested.connect(self._choose_audio)
        layout.addWidget(self.drop_area)
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
        zoom_layout.addWidget(_i18n_mark(_i18n_mark(QLabel(i18n_text('ui.148')), 'text', 'ui.148'), 'text', 'ui.148'))
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(0, 1000)
        self.zoom.setValue(210)
        self.zoom.valueChanged.connect(self._set_zoom_from_slider)
        self.time_label = QLabel('00:00.000 / 00:00.000')
        zoom_layout.addWidget(self.zoom, 1)
        zoom_layout.addWidget(self.time_label)
        layout.addLayout(zoom_layout)
        lower = QHBoxLayout()
        export_panel = self._panel()
        export_layout = QVBoxLayout(export_panel)
        export_layout.addWidget(_i18n_mark(_i18n_mark(QLabel(i18n_text('ui.149')), 'text', 'ui.149'), 'text', 'ui.149'))
        format_row = QHBoxLayout()
        self.format_label = _i18n_mark(QLabel(i18n_text('audio.export.format')), 'text', 'audio.export.format')
        self.format_combo = QComboBox()
        self._format_items = (('wav', 'WAV'), ('mp3', 'MP3'), ('flac', 'FLAC'), ('opus', 'Opus'), ('m4a', 'M4A'))
        for _value, label in self._format_items:
            self.format_combo.addItem(label, _value)
        self.format_combo.setCurrentIndex(max(0, self.format_combo.findData(self._output_format)))
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        self.quality_combo = QComboBox()
        self.quality_label = _i18n_mark(QLabel(i18n_text('audio.export.quality')), 'text', 'audio.export.quality')
        format_row.addWidget(self.format_label)
        format_row.addWidget(self.format_combo, 1)
        format_row.addWidget(self.quality_label)
        format_row.addWidget(self.quality_combo, 1)
        export_layout.addLayout(format_row)
        self.matrix_notice = _i18n_mark(QLabel(i18n_text('audio.export.matrix_wav_notice')), 'text', 'audio.export.matrix_wav_notice')
        self.matrix_notice.setObjectName('mutedLabel')
        self.matrix_notice.setVisible(False)
        export_layout.addWidget(self.matrix_notice)
        export_layout.addWidget(_i18n_mark(QLabel(i18n_text('dialog.processing.loudness_group')), 'text', 'dialog.processing.loudness_group'))
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
        export_layout.addWidget(_i18n_mark(QLabel(i18n_text('dialog.processing.repair_group')), 'text', 'dialog.processing.repair_group'))
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
        denoise_row.addWidget(_i18n_mark(QLabel(i18n_text('dialog.processing.strength')), 'text', 'dialog.processing.strength'))
        denoise_row.addWidget(self.denoise_strength_spin)
        export_layout.addLayout(denoise_row)
        repair_row = QHBoxLayout()
        self.declick_check = _i18n_mark(QCheckBox(i18n_text('dialog.processing.declick')), 'text', 'dialog.processing.declick')
        self.declick_check.setChecked(self._declick)
        self.declick_check.toggled.connect(self._on_declick_changed)
        self.deesser_check = _i18n_mark(QCheckBox(i18n_text('dialog.processing.deesser')), 'text', 'dialog.processing.deesser')
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
        preset_row.addWidget(_i18n_mark(QLabel(i18n_text('dialog.processing.preset_group')), 'text', 'dialog.processing.preset_group'))
        preset_row.addWidget(self.preset_combo, 1)
        export_layout.addLayout(preset_row)
        polish_row = QHBoxLayout()
        self.fade_spin = QSpinBox()
        self.fade_spin.setRange(0, 500)
        self.fade_spin.setValue(self._fade_ms)
        self.fade_spin.setSuffix(' ms')
        self.fade_spin.valueChanged.connect(self._on_fade_changed)
        self.trim_edges_check = _i18n_mark(QCheckBox(i18n_text('dialog.processing.trim_edges')), 'text', 'dialog.processing.trim_edges')
        self.trim_edges_check.setChecked(self._trim_silence == 'edges')
        self.trim_edges_check.toggled.connect(self._on_trim_edges_changed)
        polish_row.addWidget(_i18n_mark(QLabel(i18n_text('dialog.processing.fade')), 'text', 'dialog.processing.fade'))
        polish_row.addWidget(self.fade_spin)
        polish_row.addWidget(self.trim_edges_check)
        polish_row.addStretch(1)
        export_layout.addLayout(polish_row)
        self.sample_rate = QComboBox()
        self.sample_rate.addItems(['22050', '32000', '44100', '48000', '96000'])
        self.sample_rate.setCurrentText('48000')
        self.channels = QComboBox()
        self.channels.addItems([i18n_text('ui.150'), i18n_text('ui.151')])
        self.bit_depth = QComboBox()
        self.bit_depth.addItems(['16-bit PCM', '24-bit PCM', '32-bit Float'])
        self.keep_timeline = _i18n_mark(_i18n_mark(QCheckBox(i18n_text('ui.152')), 'text', 'ui.152'), 'text', 'ui.152')
        self.worker_count = QSpinBox()
        self.worker_count.setRange(1, max(1, (os.cpu_count() or 2) - 1))
        self.worker_count.setValue(1)
        self.loudness_status = QLabel()
        self.output_label = _i18n_mark(_i18n_mark(QLabel(i18n_text('ui.153')), 'text', 'ui.153'), 'text', 'ui.153')
        self.output_label.setWordWrap(True)
        self.audio_copy_mode_switch = CopyModeSwitch(export_panel)
        self.audio_copy_mode_switch.setVisible(False)
        self.audio_copy_mode_switch.mode_changed.connect(self._change_audio_copy_mode)
        self.export_button = _i18n_mark(_i18n_mark(QPushButton(i18n_text('ui.154')), 'text', 'ui.154'), 'text', 'ui.154')
        self.cancel_button = _i18n_mark(_i18n_mark(QPushButton(i18n_text('ui.031')), 'text', 'ui.031'), 'text', 'ui.031')
        self.export_button.clicked.connect(self._export)
        self.cancel_button.clicked.connect(self._cancel_export)
        for widget in (self.sample_rate, self.channels, self.bit_depth, _i18n_mark(_i18n_mark(QLabel(i18n_text('ui.155')), 'text', 'ui.155'), 'text', 'ui.155'), self.worker_count, self.loudness_status, self.keep_timeline, self.output_label):
            export_layout.addWidget(widget)
        self._on_format_changed(self.format_combo.currentIndex())
        mode_row = QHBoxLayout()
        mode_row.addStretch(1)
        mode_row.addWidget(self.audio_copy_mode_switch)
        export_layout.addLayout(mode_row)
        export_layout.addWidget(self.export_button)
        export_layout.addWidget(self.cancel_button)
        self._update_loudness_status()
        lower.addWidget(export_panel, 1)
        group_panel = self._panel()
        group_layout = QVBoxLayout(group_panel)
        group_layout.addWidget(_i18n_mark(_i18n_mark(QLabel(i18n_text('ui.156')), 'text', 'ui.156'), 'text', 'ui.156'))
        self.group_detail = _i18n_mark(_i18n_mark(QLabel(i18n_text('ui.157')), 'text', 'ui.157'), 'text', 'ui.157')
        self.group_detail.setWordWrap(True)
        self.fill_button = _i18n_mark(_i18n_mark(QPushButton(i18n_text('ui.158')), 'text', 'ui.158'), 'text', 'ui.158')
        self.fill_button.clicked.connect(self._fill)
        group_layout.addWidget(self.group_detail)
        group_layout.addWidget(self.fill_button)
        group_layout.addStretch(1)
        lower.addWidget(group_panel, 1)
        layout.addLayout(lower)
        self.copy_status = TaskStatusPanel()
        self.copy_status.set_title(i18n_text('ui.159'))
        self.copy_status.set_controls_visible(False)
        layout.addWidget(self.copy_status)
        layout.addStretch(1)
        scroll.setWidget(body)
        self._scroll_guard = ScrollPositionGuard(scroll)
        self._scroll_router = AudioPageScrollRouter(self, scroll, self.timeline_view, hot_zone_width=40)
        return scroll

    def _log_task_ui_state(self, operation: str) -> None:
        scroll = self._body_widget
        if not isinstance(scroll, QScrollArea):
            return
        focus = QApplication.focusWidget()
        focus_text = ''
        if focus is not None and hasattr(focus, 'text'):
            try:
                focus_text = str(focus.text())
            except (RuntimeError, TypeError):
                focus_text = ''
        body = scroll.widget()
        LOGGER.debug('Audio task UI state: operation=%s scroll=%s/%s focus=%s object=%s text=%r content_height=%s group_panel_height=%s', operation, scroll.verticalScrollBar().value(), scroll.verticalScrollBar().maximum(), type(focus).__name__ if focus is not None else 'None', focus.objectName() if focus is not None else '', focus_text, body.height() if body is not None else -1, self.group_detail.parentWidget().height() if self.group_detail.parentWidget() is not None else -1)

    def _begin_task_ui_transition(self, operation: str) -> None:
        """Freeze one task-start layout transition without locking later user scrolling."""
        self._scroll_guard.begin_hold()
        self._task_first_progress_logged = False
        self._log_task_ui_state(f'{operation}:before')
        scroll = self._body_widget
        if isinstance(scroll, QScrollArea):
            scroll.setFocus(Qt.FocusReason.OtherFocusReason)

    def _end_task_ui_transition(self, operation: str) -> None:
        self._scroll_guard.end_hold()
        self._log_task_ui_state(f'{operation}:submitted')

    def _task_progress_observed(self, _snapshot: object) -> None:
        if self._task_first_progress_logged:
            return
        self._task_first_progress_logged = True
        self._log_task_ui_state('first-progress')

    def _restore_settings(self) -> None:
        path = self._settings.value('audio/project_root', '', str)
        self.path_edit.setText(path)
        if path:
            self._set_root()

    def _choose_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, i18n_text('ui.160'), self.path_edit.text())
        if path:
            self.path_edit.setText(path)
            self._set_root()

    def _set_root(self) -> None:
        raw = self.path_edit.text().strip()
        if not raw:
            return
        try:
            self._root = Path(raw)
            self._project.ensure_layout(self._root)
            self._settings.setValue('audio/project_root', raw)
            self._watch_directories()
            self._refresh_group()
            self.target_info.setText(i18n_text('ui.161'))
        except OSError as error:
            self.target_info.setText(i18n_text('ui.162').format(error))

    def _category_display(self, category: str) -> str:
        keys = {CREW_CATEGORIES[0]: 'ui.134', RADIO_CATEGORIES[0]: 'ui.135'}
        return i18n_live(keys.get(category, category))

    def _build_categories(self) -> None:
        for button in self.category_buttons.buttons():
            self.category_buttons.removeButton(button)
        self._category_button_by_id.clear()
        while self.category_layout.count():
            item = self.category_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        categories = CREW_CATEGORIES if self._active_module == 'crew' else RADIO_CATEGORIES
        for category in categories:
            button = QPushButton(self._category_display(category))
            button.setCheckable(True)
            button.setProperty('audioNavigation', True)
            button.setChecked(category == self._active_category)
            button.clicked.connect(lambda _checked=False, value=category: self._change_category(value))
            self.category_buttons.addButton(button)
            self._category_button_by_id[category] = button
            self.category_layout.addWidget(button)
        self.category_layout.addStretch(1)
        self._sync_navigation_selection()

    def _sync_navigation_selection(self) -> None:
        for module, button in self._module_button_by_id.items():
            button.setChecked(module == self._active_module)
        for category, button in self._category_button_by_id.items():
            button.setChecked(category == self._active_category)

    def _change_module(self, module: str) -> None:
        self._active_module = module
        self._active_category = (CREW_CATEGORIES if module == 'crew' else RADIO_CATEGORIES)[0]
        if self._root is not None:
            self._project.ensure_layout(self._root)
        self._build_categories()
        self._sync_navigation_selection()
        self._watch_directories()
        self._refresh_group()

    def _change_category(self, category: str) -> None:
        self._active_category = category
        if self._root is not None:
            self._project.ensure_layout(self._root)
        self._build_categories()
        self._sync_navigation_selection()
        self._watch_directories()
        self._refresh_group()

    def _resolve_target(self) -> None:
        name = self._project.parse_target(self.target_edit.text())
        if not name:
            self._current_group = None
            self._set_audio_copy_mode(ManualCopyMode.SEQUENTIAL)
            self._resolved_group_key = None
            self._refresh_group()
            return
        if not self._project.valid_filename(name):
            self.target_info.setText(i18n_text('ui.163'))
            return
        resolved = self._groups.lookup(name)
        new_group_key = resolved.group_key if resolved is not None else None
        if new_group_key != self._resolved_group_key:
            self._set_audio_copy_mode(ManualCopyMode.SEQUENTIAL)
        self._resolved_group_key = new_group_key
        self._current_group = resolved
        if self._current_group and self._current_group.category:
            group = self._current_group
            if (group.module, group.category) != (self._active_module, self._active_category):
                self._active_module, self._active_category = (group.module, group.category)
                if self._root is not None:
                    self._project.ensure_layout(self._root)
                self._build_categories()
                self._watch_directories()
            self._sync_navigation_selection()
            self.target_info.setText(i18n_text('ui.164').format(group.module, group.category, group.base_name))
        elif self._current_group:
            group = self._current_group
            if group.module != self._active_module:
                self._active_module = group.module
                self._active_category = CREW_CATEGORIES[0] if group.module == 'crew' else RADIO_CATEGORIES[0]
                self._build_categories()
                self._watch_directories()
            self._sync_navigation_selection()
            self.target_info.setText(i18n_text('ui.165'))
        else:
            self.target_info.setText(i18n_text('ui.166'))
        self._refresh_group()

    def _matrix_layout(self):
        group = self._current_group
        if group is None:
            return None
        return self._matrix_planner.analyze(group.group_key, group.names, lambda name: owner.group_key if (owner := self._groups.lookup(name)) is not None else None)

    def _set_audio_copy_mode(self, mode: ManualCopyMode) -> None:
        self._audio_copy_mode = mode
        if hasattr(self, 'audio_copy_mode_switch'):
            self.audio_copy_mode_switch.set_average_checked(mode is ManualCopyMode.AVERAGE, emit=False)
        if hasattr(self, 'format_combo'):
            self._update_format_controls()

    def _change_audio_copy_mode(self, average: bool) -> None:
        if self.is_busy:
            self.audio_copy_mode_switch.set_average_checked(self._audio_copy_mode is ManualCopyMode.AVERAGE, emit=False)
            return
        requested = ManualCopyMode.AVERAGE if average else ManualCopyMode.SEQUENTIAL
        if requested is ManualCopyMode.AVERAGE and self._matrix_layout() is None:
            requested = ManualCopyMode.SEQUENTIAL
        self._set_audio_copy_mode(requested)
        self._refresh_group()

    def _show_target_menu(self) -> None:
        if not self.target_menu_action.isEnabled() or self._current_group is None:
            return
        directory = self._directory()
        if directory is None:
            return
        present, _formats = self._project.group_progress(directory, self._current_group)
        menu = QMenu(self.target_edit)
        layout = self._matrix_layout()
        if self._audio_copy_mode is ManualCopyMode.AVERAGE and layout is not None:
            for subgroup in layout.subgroups:
                completed = sum(name in present for name in subgroup.names)
                if completed == 3:
                    continue
                action = menu.addAction(i18n_text('ui.167').format(subgroup.index + 1, subgroup.names[0], subgroup.names[-1], completed))
                action.setData(subgroup.names[0])
        else:
            for member in self._current_group.names:
                if member not in present:
                    action = menu.addAction(member)
                    action.setData(member)
        if menu.isEmpty():
            return
        selected = menu.exec(self.target_edit.mapToGlobal(self.target_edit.rect().bottomRight()))
        if selected is not None and selected.data():
            self.target_edit.setText(str(selected.data()))
            self._target_timer.stop()
            self._resolve_target()

    def _directory(self) -> Path | None:
        return self._project.directory(self._root, self._active_module, self._active_category) if self._root else None

    def _refresh_group(self) -> None:
        self._scroll_guard.preserve()
        directory = self._directory()
        if not self._current_group or directory is None:
            self.group_detail.setText(i18n_text('ui.168'))
            self.output_label.setText(i18n_text('ui.153'))
            self.fill_button.setEnabled(False)
            self._fill_available = False
            self._target_menu_has_items = False
            self.target_menu_action.setEnabled(False)
            self.audio_copy_mode_switch.setVisible(False)
            return
        present, formats = self._project.group_progress(directory, self._current_group)
        missing = [name for name in self._current_group.names if name not in present]
        duplicates = [name for name, paths in formats.items() if name in self._current_group.names and len(paths) > 1]
        completed_text = ', '.join(sorted(present)) or '—'
        missing_text = ', '.join(missing) or '—'
        lines = [self._current_group.base_name, i18n_text('ui.169').format(len(present), len(self._current_group.names)), i18n_text('ui.170').format(completed_text), i18n_text('ui.171').format(missing_text)]
        matrix_layout = self._matrix_layout()
        eligible = matrix_layout is not None
        self.audio_copy_mode_switch.setVisible(eligible)
        if not eligible and self._audio_copy_mode is ManualCopyMode.AVERAGE:
            self._set_audio_copy_mode(ManualCopyMode.SEQUENTIAL)
        if eligible and matrix_layout is not None:
            complete_subgroups = sum(all(name in present for name in subgroup.names) for subgroup in matrix_layout.subgroups)
            lines.append(i18n_text('ui.172').format(complete_subgroups, len(matrix_layout.subgroups)))
        if duplicates:
            lines.append(i18n_text('ui.173') + ', '.join(duplicates))
        self.group_detail.setText('\n'.join(lines))
        target_name = self._project.parse_target(self.target_edit.text())
        self.output_label.setText(i18n_text('ui.174').format(directory / (target_name + '.wav')))
        if self._audio_copy_mode is ManualCopyMode.AVERAGE and matrix_layout is not None:
            subgroup = matrix_layout.subgroup_for(target_name)
            if subgroup is not None:
                self.output_label.setText(i18n_text('ui.175') + '\n'.join(str(directory / f'{name}.wav') for name in subgroup.names))
        if self._audio_copy_mode is ManualCopyMode.AVERAGE and matrix_layout is not None:
            has_pending = any(not all(name in present for name in subgroup.names) for subgroup in matrix_layout.subgroups)
        else:
            has_pending = bool(missing)
        self._target_menu_has_items = has_pending
        self.target_menu_action.setEnabled(has_pending and (not self.is_busy))
        if self._audio_copy_mode is ManualCopyMode.AVERAGE and matrix_layout is not None:
            complete_count = sum(all(name in present for name in subgroup.names) for subgroup in matrix_layout.subgroups)
            self._fill_available = 0 < complete_count < len(matrix_layout.subgroups)
        else:
            self._fill_available = bool(present and missing)
        self.fill_button.setEnabled(bool(present and missing) and (not self.is_busy))
        if not missing and present and (not self._completion_announced):
            self.target_info.setText(i18n_text('ui.176'))
            self._completion_announced = True
            self._completion_message_timer.start()
        elif missing:
            self._completion_announced = False

    def _restore_project_ready_status(self) -> None:
        self.target_info.setText(i18n_text('ui.161'))

    def _watch_directories(self) -> None:
        self._watcher.removePaths(self._watcher.directories())
        if self._root is None:
            return
        paths = [self._root, self._root / '车组', self._root / '无线电']
        directory = self._directory()
        if directory is not None:
            paths.append(directory)
        self._watcher.addPaths([str(path) for path in paths if path.is_dir()])

    def _on_watched_directory_changed(self, _path: str) -> None:
        if self._watch_suspended:
            self._watch_refresh_pending = True
            return
        self._watch_timer.start()

    def _matrix_copy_busy_changed(self, busy: bool) -> None:
        if busy:
            self._watch_suspended = True
        else:
            self._watch_suspended = False
            self._watch_refresh_pending = False
            self._watch_timer.start(500)
        self._sync()

    def _matrix_copy_finished(self, result: object) -> None:
        self._watch_refresh_pending = True
        if not isinstance(result, CopyBatchResult):
            LOGGER.warning('Audio average fill returned an unexpected result: %r', result)
            return
        LOGGER.info('Audio average fill finished: state=%s total=%s created=%s overwritten=%s skipped=%s failed=%s cancelled=%s', result.state.value, len(result.results), result.created, result.overwritten, result.skipped, result.failed, result.cancelled)
        failures = [item for item in result.results if item.status is CopyResultStatus.FAILED]
        if not failures:
            return
        details = '\n'.join(f"{item.task.target_path}：{item.reason or i18n_text('ui.177')}" for item in failures)
        self.target_info.setText(i18n_text('ui.178').format(len(failures)))
        QMessageBox.warning(self, i18n_text('ui.179'), i18n_text('ui.180').format(len(failures), details))

    def _choose_audio(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, i18n_text('ui.181'), '', i18n_text('ui.182'))
        self._add_audio_paths(paths)

    def _add_audio_paths(self, paths: list[str]) -> None:
        for raw in paths:
            path = Path(raw)
            if not path.is_file():
                self.target_info.setText(i18n_text('ui.183').format(path.name))
                continue
            request_id = uuid4().hex
            self._pending_audio_paths[request_id] = path
            self._build_waveform(request_id, path)
        if self._pending_audio_paths and (not self._timeline.items):
            self._playback_state = PlaybackState.PREPARING
            self.target_info.setText(i18n_text('ui.184'))
        self._sync()

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
            self.target_info.setText(i18n_text('ui.185').format(path.name))
        else:
            self.target_info.setText(i18n_text('ui.186').format(path.name, error))
            self._playback_state = PlaybackState.READY if self._timeline.items else PlaybackState.EMPTY
            self._sync()

    def _add_blank(self) -> None:
        self._timeline.add_blank()
        self._render_timeline()
        self._invalidate_preview()

    def _set_selection(self, ids: set[str]) -> None:
        self._selected = ids
        self._sync()

    def _trim_preview(self, _clip_id: str, start_ms: int, end_ms: int) -> None:
        from app.audio.models import format_ms
        self.target_info.setText(i18n_text('ui.187').format(format_ms(start_ms), format_ms(end_ms), format_ms(end_ms - start_ms)))

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
            self.target_info.setText(i18n_text('ui.188'))
            return
        if self.is_busy:
            self.target_info.setText(i18n_text('ui.189'))
            return
        if self._playback_state is PlaybackState.PLAYING:
            self._finalize_playback(PlaybackEndReason.TIMELINE_CHANGED, reset_playhead=False)
        try:
            result = self._timeline.split_audio_at(location.clip_id, self.playhead_time_ms)
        except ValueError as error:
            self.target_info.setText(str(error))
            self._sync()
            return
        self._selected = {result.right_clip_id}
        self._render_timeline()
        self.timeline_view.flash_split_at(result.timeline_position_ms)
        self._invalidate_preview()
        self.target_info.setText(i18n_text('ui.190').format(result.timeline_position_ms / 1000))

    def _seek(self, position: float) -> None:
        position_ms = max(0, min(self._timeline.duration_ms, int(position)))
        self.playhead_time_ms = position_ms
        self.timeline_view.set_playhead_ms(position_ms)
        if self._playback_state is PlaybackState.PLAYING:
            self._player.setPosition(position_ms)
        from app.audio.models import format_ms
        self.time_label.setText(f'{format_ms(position_ms)} / {format_ms(self._timeline.duration_ms)}')
        self._sync()

    def _playhead_drag_started(self) -> None:
        if self._playback_state is PlaybackState.PLAYING:
            self._finalize_playback(PlaybackEndReason.SEEK, reset_playhead=False)

    def _playhead_drag_preview(self, position_ms: int) -> None:
        self.playhead_time_ms = max(0, min(self._timeline.duration_ms, position_ms))
        from app.audio.models import format_ms
        self.time_label.setText(f'{format_ms(self.playhead_time_ms)} / {format_ms(self._timeline.duration_ms)}')
        self._sync()

    def _render_timeline(self) -> None:
        from app.audio.models import format_ms
        self.playhead_time_ms = max(0, min(self.playhead_time_ms, self._timeline.duration_ms))
        self.timeline_view.set_timeline(self._timeline, self._selected)
        self.timeline_view.set_playhead_ms(self.playhead_time_ms)
        self.time_label.setText(f'{format_ms(self.playhead_time_ms)} / {format_ms(self._timeline.duration_ms)}')
        self._sync()

    def _settings_snapshot(self) -> ExportSettings:
        return ExportSettings(sample_rate=int(self.sample_rate.currentText()), channels=1 if self.channels.currentIndex() == 0 else 2, bit_depth=self.bit_depth.currentText(), normalize_mode=self._normalize_mode, normalize_target=self._normalize_target, keep_timeline=self.keep_timeline.isChecked(), worker_threads=self.worker_count.value(), output_format=self._output_format, quality=self._quality, fade_ms=self._fade_ms, trim_silence=self._trim_silence, denoise=self._denoise, denoise_strength=self._denoise_strength, declick=self._declick, deesser=self._deesser, voice_preset=self._voice_preset, gain_db=self._gain_db)

    def _export(self) -> None:
        self._begin_task_ui_transition('export')
        try:
            self._export_impl()
        finally:
            self._end_task_ui_transition('export')

    def _export_impl(self) -> None:
        directory = self._directory()
        name = self._project.parse_target(self.target_edit.text())
        if directory is None or not self._project.valid_filename(name) or (not self._timeline.items):
            self.target_info.setText(i18n_text('ui.191'))
            return
        if self._audio_copy_mode is ManualCopyMode.AVERAGE:
            self._export_average(directory, name)
            return
        settings = self._settings_snapshot()
        target = directory / f'{name}.{output_extension(settings)}'
        if target.exists() and QMessageBox.question(self, i18n_text('ui.192'), i18n_text('ui.193')) != QMessageBox.StandardButton.Yes:
            return
        snapshot = self._timeline.snapshot(settings.sample_rate, settings.channels)
        self._export_cancel_event = threading.Event()
        thread = QThread(self)
        worker = AudioExportService(snapshot, settings, target, self._export_cancel_event)
        self._start_export_worker(thread, worker)

    def _start_export_worker(self, thread: QThread, worker: AudioExportService | AudioMatrixExportService) -> None:
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._export_progress)
        worker.finished.connect(self._export_done)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._export_thread_done)
        worker.measurement_cache = self._loudness_cache
        self._export_thread = thread
        self._export_worker = worker
        self._watch_suspended = True
        thread.start()
        self._sync()

    def _export_average(self, directory: Path, name: str) -> None:
        layout = self._matrix_layout()
        if layout is None:
            self.target_info.setText(i18n_text('ui.194'))
            self._set_audio_copy_mode(ManualCopyMode.SEQUENTIAL)
            self._refresh_group()
            return
        subgroup = layout.subgroup_for(name)
        if subgroup is None:
            self.target_info.setText(i18n_text('ui.195'))
            return
        present, formats = self._project.group_progress(directory, self._current_group)
        if all(member in present for member in subgroup.names):
            self.target_info.setText(i18n_text('ui.196'))
            return
        cross_format = [path for member in subgroup.names for path in formats.get(member, []) if path.suffix.casefold() != '.wav']
        if cross_format:
            QMessageBox.warning(self, i18n_text('ui.197'), i18n_text('ui.198') + '\n'.join(str(path) for path in cross_format))
            return
        existing_wav = [path for member in subgroup.names for path in formats.get(member, []) if path.suffix.casefold() == '.wav']
        if existing_wav:
            answer = QMessageBox.question(self, i18n_text('ui.199'), i18n_text('ui.200') + '\n'.join(str(path) for path in existing_wav) + i18n_text('ui.201'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            LOGGER.info('Audio average export confirmation: reply=%r type=%s group=%s targets=%s', answer, type(answer).__name__, self._current_group.group_key if self._current_group is not None else '', len(subgroup.names))
            if answer != QMessageBox.StandardButton.Yes:
                return
        settings = self._settings_snapshot()
        snapshot = self._timeline.snapshot(settings.sample_rate, settings.channels)
        targets = tuple(directory / f'{member}.wav' for member in subgroup.names)
        self._export_cancel_event = threading.Event()
        thread = QThread(self)
        worker = AudioMatrixExportService(snapshot, settings, targets, self._export_cancel_event)
        self._start_export_worker(thread, worker)

    def _export_progress(self, step: str, percent: int, filename: str) -> None:
        self._task_progress_observed(None)
        self.target_info.setText(f'{step}：{filename}')
        total = 4 if self._audio_copy_mode is ManualCopyMode.AVERAGE else 1
        processed = min(total, round(percent / 100 * total))
        self.copy_status.set_snapshot(TaskStatusSnapshot(state=TaskState.RUNNING, progress=percent, processed=processed, total=total, current_file=filename, message=step))

    def _export_done(self, ok: bool, message: str, _target: object) -> None:
        self.target_info.setText(message)
        if ok:
            self._watch_refresh_pending = True
            if not self.keep_timeline.isChecked():
                self._timeline.reset()
                self._selected.clear()
                self._render_timeline()

    def _export_thread_done(self) -> None:
        self._export_thread = None
        self._export_worker = None
        self._watch_suspended = False
        self._watch_refresh_pending = False
        self._watch_timer.start(500)
        self._sync()

    def _cancel_export(self) -> None:
        self._export_cancel_event.set()

    def _preview(self) -> None:
        LOGGER.info('Audio preview play request: state=%s playhead_ms=%s total_ms=%s media_status=%s player_position_ms=%s active_session=%s', self._playback_state.value, self.playhead_time_ms, self._timeline.duration_ms, self._player.mediaStatus().name, self._player.position(), self._active_playback_session_id)
        if not self._timeline.items:
            self.target_info.setText(i18n_text('ui.202'))
            return
        settings = self._settings_snapshot()
        snapshot = self._timeline.snapshot(settings.sample_rate, settings.channels)
        if self.loop_selected.isChecked() and (not self._selected):
            self.target_info.setText(i18n_text('ui.203'))
            return
        if self._preview_path and self._preview_path.is_file() and (self._preview_version == snapshot.version):
            self._queue_preview_playback(self._preview_path, self._preview_start_position(snapshot.total_duration_ms))
            return
        self._playback_state = PlaybackState.PREPARING
        self._preview_cancel_event = threading.Event()
        target = temp_dir() / f'wt_name_relay_preview_{id(self)}_{snapshot.version}.wav'
        thread = QThread(self)
        worker = AudioPreviewService(snapshot, settings, target, self._preview_cancel_event)
        worker.measurement_cache = self._loudness_cache
        worker.moveToThread(thread)
        self._preview_version = snapshot.version
        thread.started.connect(worker.run)
        worker.progress.connect(lambda step, _p, _f: self.target_info.setText(i18n_text('ui.204').format(step)))
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
            self.target_info.setText(message)
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
        LOGGER.info('Audio preview source queued: same_source=%s start_ms=%s media_status=%s', same_source, self._pending_play_start_ms, self._player.mediaStatus().name)
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
        LOGGER.info('Audio preview session created: session=%s start_ms=%s total_ms=%s media_status=%s', self._active_playback_session_id, position, self._timeline.duration_ms, self._player.mediaStatus().name)
        self._sync()

    def _stop(self) -> None:
        if self._playback_state is PlaybackState.PREPARING:
            self._preview_cancel_event.set()
        self._finalize_playback(PlaybackEndReason.USER_STOP, reset_playhead=True)

    def _finalize_playback(self, reason: PlaybackEndReason, *, reset_playhead: bool) -> None:
        if self._finalizing_playback:
            LOGGER.info('Duplicate audio preview finalization ignored: reason=%s', reason.value)
            return
        if reason is PlaybackEndReason.NATURAL_END and self._active_playback_session_id is None:
            LOGGER.info('Stale natural-end callback ignored: no active playback session')
            return
        self._finalizing_playback = True
        session_id = self._active_playback_session_id
        if reason is PlaybackEndReason.NATURAL_END:
            visual_position = self._timeline.duration_ms
        elif reset_playhead:
            visual_position = 0
        else:
            visual_position = max(0, min(self.playhead_time_ms, self._timeline.duration_ms))
        LOGGER.info('Audio preview finalizing: reason=%s session=%s state=%s playhead_ms=%s total_ms=%s player_position_ms=%s media_status=%s', reason.value, session_id, self._playback_state.value, self.playhead_time_ms, self._timeline.duration_ms, self._player.position(), self._player.mediaStatus().name)
        try:
            self._pending_play_start_ms = None
            self._active_playback_session_id = None
            self._player.stop()
            self._player.setPosition(0)
            self.playhead_time_ms = visual_position
            self.timeline_view.set_playhead_ms(visual_position)
            from app.audio.models import format_ms
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
            LOGGER.info('Audio preview reset completed: reason=%s session=%s visual_playhead_ms=%s player_position_ms=%s next_state=%s', reason.value, session_id, visual_position, self._player.position(), self._playback_state.value)
        finally:
            self._finalizing_playback = False

    def _play_position(self, position: int) -> None:
        if self._finalizing_playback:
            return
        self.playhead_time_ms = max(0, min(self._timeline.duration_ms, position))
        self.timeline_view.set_playhead_ms(self.playhead_time_ms)
        from app.audio.models import format_ms
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
                LOGGER.info('Stale EndOfMedia callback ignored')
                return
            tolerance_ms = 5
            observed_position = max(self.playhead_time_ms, self._player.position())
            if observed_position < self._timeline.duration_ms - tolerance_ms:
                LOGGER.info('Stale or premature EndOfMedia ignored: session=%s observed_ms=%s total_ms=%s', self._active_playback_session_id, observed_position, self._timeline.duration_ms)
                return
            LOGGER.info('Audio preview natural end detected: session=%s observed_ms=%s total_ms=%s', self._active_playback_session_id, observed_position, self._timeline.duration_ms)
            self._finalize_playback(PlaybackEndReason.NATURAL_END, reset_playhead=False)

    def _playback_error(self, _error: QMediaPlayer.Error, message: str) -> None:
        if not message:
            return
        self.target_info.setText(i18n_text('ui.205').format(message))
        LOGGER.error('Audio preview playback error: %s', message)
        self._finalize_playback(PlaybackEndReason.ERROR, reset_playhead=False)

    def _invalidate_preview(self) -> None:
        self._preview_cancel_event.set()
        self._finalize_playback(PlaybackEndReason.TIMELINE_CHANGED, reset_playhead=False)
        if self._preview_path is not None:
            self._preview_path.unlink(missing_ok=True)
            self._preview_path = None
        self._preview_version = None

    def _audio_scan_items(self) -> tuple[tuple[str, int, str, Path, int, int], ...]:
        i18n_text('ui.206')
        items: list[tuple[str, int, str, Path, int, int]] = []
        timeline_start = 0
        for item in self._timeline.items:
            if isinstance(item, AudioClip) and item.source_path is not None:
                items.append((item.clip_id, timeline_start, f'{timeline_start / 1000:.3f}s {item.source_path.name}', item.source_path, item.trim_start_ms, item.effective_end_ms))
            timeline_start += item.duration_ms
        return tuple(items)

    def _detect_silence(self) -> None:
        if self.is_busy or not self._audio_scan_items():
            self.target_info.setText(i18n_text('ui.202'))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(i18n_text('audio.button.silence'))
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
        threshold_row.addWidget(_i18n_mark(QLabel(i18n_text('dialog.silence.threshold')), 'text', 'dialog.silence.threshold'))
        threshold_row.addWidget(threshold)
        duration_row = QHBoxLayout()
        duration_row.addWidget(_i18n_mark(QLabel(i18n_text('dialog.silence.min_duration')), 'text', 'dialog.silence.min_duration'))
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
        self.target_info.setText(i18n_text('dialog.silence.scanning'))
        self._sync()
        thread.start()

    def _silence_thread_done(self) -> None:
        self._silence_thread = None
        self._silence_worker = None
        self._sync()

    def _silence_done(self, results: object, error: str) -> None:
        if error:
            self.target_info.setText(error)
            return
        if not results:
            self.target_info.setText(i18n_text('dialog.silence.none'))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(i18n_text('audio.button.silence'))
        layout = QVBoxLayout(dialog)
        layout.addWidget(_i18n_mark(QLabel(i18n_text('dialog.silence.results')), 'text', 'dialog.silence.results'))
        checks: list[tuple[QCheckBox, int]] = []
        for item in results:
            start_ms, end_ms = (item['start_ms'], item['end_ms'])
            checkbox = QCheckBox(f'{start_ms / 1000:.3f}s - {end_ms / 1000:.3f}s  ({end_ms - start_ms} ms)')
            checkbox.setChecked(True)
            checks.append((checkbox, (start_ms + end_ms) // 2))
            layout.addWidget(checkbox)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(i18n_text('dialog.silence.apply'))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        midpoints = [midpoint for checkbox, midpoint in checks if checkbox.isChecked()]
        count = self._timeline.split_at_silences(midpoints)
        self._render_timeline()
        self._invalidate_preview()
        self.target_info.setText(i18n_text('ui.207').format(count))

    def _analyze_clips(self) -> None:
        items = self._audio_scan_items()
        if self.is_busy or not items:
            self.target_info.setText(i18n_text('ui.202'))
            return
        self._analysis_cancel = threading.Event()
        worker = LoudnessScanWorker(items, self._analysis_cancel)
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
        self.target_info.setText(i18n_text('dialog.analyze.scanning'))
        self._sync()
        thread.start()

    def _analysis_thread_done(self) -> None:
        self._analysis_thread = None
        self._analysis_worker = None
        self._sync()

    def _analysis_done(self, results: object, error: str) -> None:
        if error:
            self.target_info.setText(error)
            return
        assert isinstance(results, list)
        dialog = QDialog(self)
        dialog.setWindowTitle(i18n_text('dialog.analyze.title'))
        layout = QVBoxLayout(dialog)
        table = QTableWidget(len(results), 5)
        table.setHorizontalHeaderLabels([i18n_text('dialog.analyze.column_clip'), i18n_text('dialog.analyze.column_duration'), i18n_text('dialog.analyze.column_lufs'), i18n_text('dialog.analyze.column_peak'), i18n_text('dialog.analyze.spectrum')])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, item in enumerate(results):
            table.setItem(row, 0, QTableWidgetItem(str(item['label'])))
            table.setItem(row, 1, QTableWidgetItem(format_ms(int(item['duration_ms']))))
            table.setItem(row, 2, QTableWidgetItem(f"{item['lufs']:.1f}"))
            table.setItem(row, 3, QTableWidgetItem('' if item['peak_dbfs'] is None else f"{item['peak_dbfs']:.1f}"))
            spectrum_button = _i18n_mark(QPushButton(i18n_text('dialog.analyze.spectrum')), 'text', 'dialog.analyze.spectrum')
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
            self.target_info.setText(i18n_text('ui.208'))
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
            self.target_info.setText(error)
            return
        assert isinstance(path, Path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _update_loudness_status(self) -> None:
        if not hasattr(self, 'loudness_status'):
            return
        if self._normalize_mode == 'peak':
            self.loudness_status.setText(i18n_text('ui.209').format(self._normalize_target))
        elif self._normalize_mode == 'loudness':
            self.loudness_status.setText(i18n_text('ui.210').format(self._normalize_target))
        elif self._normalize_mode == 'speech':
            self.loudness_status.setText(i18n_text('dialog.processing.speech'))
        else:
            self.loudness_status.setText(i18n_text('ui.211'))

    def _on_loudness_target_changed(self, value: float) -> None:
        i18n_text('ui.212')
        self._normalize_target = value
        self._settings.setValue('audio/normalize_target', value)
        if self._normalize_mode == 'loudness':
            self._loudness_cache.clear()
        self._update_loudness_status()

    def _on_gain_changed(self, value: float) -> None:
        self._gain_db = value
        self._settings.setValue('audio/gain_db', value)

    def _invalidate_loudness_cache(self) -> None:
        i18n_text('ui.213')
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

    def _on_format_changed(self, index: int) -> None:
        i18n_text('ui.214')
        fmt = self.format_combo.itemData(index) if 0 <= index < self.format_combo.count() else 'wav'
        self._output_format = fmt if fmt in ('wav', 'mp3', 'flac', 'opus', 'm4a') else 'wav'
        self.quality_combo.clear()
        if self._output_format in ('mp3', 'm4a'):
            for item in ('128k', '192k', '256k', '320k'):
                self.quality_combo.addItem(item, item)
            self.quality_combo.setCurrentIndex(max(0, self.quality_combo.findData(self._quality or '192k')))
        elif self._output_format == 'opus':
            for item in ('64k', '96k', '128k', '192k'):
                self.quality_combo.addItem(item, item)
            self.quality_combo.setCurrentIndex(max(0, self.quality_combo.findData(self._quality or '96k')))
        elif self._output_format == 'flac':
            for item in ('3', '5', '8'):
                self.quality_combo.addItem(i18n_text('audio.export.flac_level') + ' ' + item, item)
            self.quality_combo.setCurrentIndex(max(0, self.quality_combo.findData(self._quality or '5')))
        self.quality_combo.setVisible(self._output_format in ('mp3', 'flac', 'opus', 'm4a'))
        self.quality_label.setVisible(self._output_format in ('mp3', 'flac', 'opus', 'm4a'))
        self.bit_depth.setVisible(self._output_format == 'wav')
        allowed_rates = {'48000', '24000', '16000', '12000', '8000'} if self._output_format == 'opus' else None
        current = self.sample_rate.currentText()
        if allowed_rates is not None:
            self.sample_rate.clear()
            self.sample_rate.addItems(['48000', '24000', '16000'])
            if current not in ('48000', '24000', '16000'):
                self.sample_rate.setCurrentText('48000')
        elif self.sample_rate.count() < 5:
            self.sample_rate.clear()
            self.sample_rate.addItems(['22050', '32000', '44100', '48000', '96000'])
            self.sample_rate.setCurrentText('48000')
        self._quality = self.quality_combo.currentData() or ''
        self._settings.setValue('audio/output_format', self._output_format)
        self._settings.setValue('audio/quality', self._quality)

    def _update_format_controls(self) -> None:
        i18n_text('ui.215')
        matrix = self._audio_copy_mode is ManualCopyMode.AVERAGE
        self.matrix_notice.setVisible(matrix)
        self.format_combo.setEnabled(not matrix and (not self.is_busy))
        if matrix:
            self.format_combo.setCurrentIndex(max(0, self.format_combo.findData('wav')))

    def _fill(self) -> None:
        self._begin_task_ui_transition('fill')
        try:
            self._fill_impl()
        finally:
            self._end_task_ui_transition('fill')

    def _fill_impl(self) -> None:
        directory = self._directory()
        if directory is None or self._current_group is None or self._copy_service.is_busy:
            return
        if self._audio_copy_mode is ManualCopyMode.AVERAGE:
            self._fill_average(directory)
            return
        present, files = self._project.group_progress(directory, self._current_group)
        source_paths = [path for name in present for path in files.get(name, [])]
        missing = [name for name in self._current_group.names if name not in present]
        if not source_paths or not missing:
            return
        tasks = tuple((CopyTask(self._current_group.base_name, source_paths[index % len(source_paths)], directory / f'{name}{source_paths[index % len(source_paths)].suffix}', name) for index, name in enumerate(missing)))
        if self._copy_service.start_copy(CopyPlan(tasks), ConflictPolicy.SKIP_EXISTING):
            self.copy_status.set_snapshot(TaskStatusSnapshot(total=len(tasks), message=i18n_text('ui.216')))
            self._sync()

    def _fill_average(self, directory: Path) -> None:
        """Build and execute the shared, full-group average plan."""
        layout = self._matrix_layout()
        group = self._current_group
        if layout is None or group is None or self._matrix_copy_service.is_busy:
            return
        _present, files = self._project.group_progress(directory, group)
        source_paths = tuple(path for member_name in group.names for path in files.get(member_name, ()))
        try:
            distribution = self._average_source_adapter.build(group, source_paths, directory, lambda name: owner.group_key if (owner := self._groups.lookup(name)) is not None else None)
        except (OSError, ValueError) as error:
            LOGGER.warning('Audio average fill planning failed: group=%s error=%s', group.group_key, error)
            QMessageBox.warning(self, i18n_text('ui.217'), str(error))
            return
        cross_format: list[Path] = []
        for operation in distribution.operations:
            for existing in files.get(operation.target_member_name, ()):
                if existing.suffix.casefold() != operation.target_path.suffix.casefold():
                    cross_format.append(existing)
        if cross_format:
            QMessageBox.warning(self, i18n_text('ui.218'), i18n_text('ui.219') + '\n'.join(str(path) for path in sorted(set(cross_format))))
            return
        operations = tuple(RadioTargetOperation(module=operation.module, group_id=operation.group_id, group_display_name=operation.group_display_name, source_original_path=operation.source.original_path, source_snapshot_key=operation.source.source_id, source_member_name=operation.source.canonical_basename, target_member_name=operation.target_member_name, target_path=operation.target_path, copy_mode=ManualCopyMode.AVERAGE, will_overwrite=operation.will_overwrite, conflict_kind=operation.conflict_kind, source_content_hash=operation.source.content_hash) for operation in distribution.operations)
        confirmed_plan = RadioStagedCopyPlan(operations, imported_source_paths=distribution.all_source_paths)
        displayed_conflicts = frozenset(confirmed_plan.current_external_conflicts())
        mapping_lines = [i18n_text('ui.220').format(source.original_path.name, bucket.index + 1) for bucket, source in zip(distribution.buckets, distribution.bucket_sources, strict=True)]
        details = i18n_text('ui.221') + '\n'.join(mapping_lines) + i18n_text('ui.222').format(distribution.source_target_count) + i18n_text('ui.223').format(distribution.generated_count) + i18n_text('ui.224').format(distribution.external_conflict_count) + i18n_text('ui.225').format(distribution.final_pattern)
        if distribution.warnings:
            details += i18n_text('ui.226') + '\n'.join(distribution.warnings)
        answer = QMessageBox.question(self, i18n_text('ui.227'), details + i18n_text('ui.228'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        LOGGER.info('Audio shared average confirmation: reply=%r group=%s sources=%s buckets=%s operations=%s pattern=%s source_targets=%s external_conflicts=%s', answer, group.group_key, len(distribution.sources), len(distribution.buckets), confirmed_plan.total, distribution.final_pattern, distribution.source_target_count, distribution.external_conflict_count)
        if answer != QMessageBox.StandardButton.Yes:
            return
        current_conflicts = frozenset(confirmed_plan.current_external_conflicts())
        new_conflicts = tuple(sorted(current_conflicts - displayed_conflicts, key=lambda path: str(path).casefold()))
        if new_conflicts:
            QMessageBox.warning(self, i18n_text('ui.229'), i18n_text('ui.230') + '\n'.join(str(path) for path in new_conflicts))
            return
        policy = ConflictPolicy.OVERWRITE_EXISTING if displayed_conflicts else ConflictPolicy.SKIP_EXISTING
        try:
            started = self._matrix_copy_service.start_copy(confirmed_plan, policy)
        except Exception as error:
            LOGGER.exception('Audio shared average worker could not start: group=%s', group.group_key)
            self.target_info.setText(i18n_text('ui.231').format(error))
            self._sync()
            QMessageBox.critical(self, i18n_text('ui.233'), i18n_text('ui.232').format(error))
            return
        if started:
            self.copy_status.set_snapshot(TaskStatusSnapshot(total=confirmed_plan.total, message=i18n_text('ui.234')))
            self._sync()
            return
        self.target_info.setText(i18n_text('ui.235'))
        self._sync()
        QMessageBox.warning(self, i18n_text('ui.236'), i18n_text('ui.237'))

    def _can_fill_current_group(self) -> bool:
        return self._fill_available and (not self.is_busy)

    def _sync(self, *_args: object) -> None:
        busy = self.is_busy
        self.export_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        can_preview = self._playback_state in (PlaybackState.READY, PlaybackState.STOPPED, PlaybackState.ERROR) and bool(self._timeline.items) and (not busy)
        self.preview_button.setEnabled(can_preview)
        self.preview_button.setToolTip(i18n_text('ui.202') if self._playback_state is PlaybackState.EMPTY else '')
        self.stop_button.setEnabled(self._playback_state in (PlaybackState.PREPARING, PlaybackState.PLAYING))
        location = self._timeline.locate(self.playhead_time_ms)
        can_split = not busy and location is not None and (location.kind is TimelineClipKind.AUDIO) and (location.offset_ms >= 1) and (self._timeline.items[location.index].duration_ms - location.offset_ms >= 1)
        self.split_button.setEnabled(can_split)
        self.split_button.setToolTip('' if can_split else i18n_text('ui.188'))
        self.back_button.setEnabled(self._navigation_enabled and (not busy))
        self.fill_button.setEnabled(self._can_fill_current_group())
        self.audio_copy_mode_switch.setEnabled(not busy)
        self.target_menu_action.setEnabled(self._target_menu_has_items and (not busy))
        self.silence_button.setEnabled(not busy and bool(self._timeline.items))
        self.analyze_button.setEnabled(not busy and bool(self._timeline.items))
        matrix_mode = self._audio_copy_mode is ManualCopyMode.AVERAGE
        if hasattr(self, 'format_combo'):
            self.matrix_notice.setVisible(matrix_mode)
            self.format_combo.setEnabled(not busy and (not matrix_mode))
            self.quality_combo.setEnabled(not busy)
        if self._close_pending and (not busy):
            self._close_pending = False
            self.close_ready.emit()