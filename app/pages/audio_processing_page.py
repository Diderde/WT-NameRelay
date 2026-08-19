from __future__ import annotations

import logging
import os
import threading
from uuid import uuid4
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QSettings, QThread, QTimer, Qt, Signal, QUrl
from PySide6.QtGui import QAction
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSlider,
    QSpinBox, QVBoxLayout, QWidget, QDialog, QDialogButtonBox, QDoubleSpinBox, QRadioButton,
    QMenu, QStyle,
)

from app.audio import (
    AudioExportService,
    AudioMatrixExportService,
    AudioPreviewService,
    AudioProjectService,
    ExportSettings,
    ProjectGroupRepository,
    TimelineClipKind,
    TimelineEditKind,
    TimelineModel,
    WaveformWorker,
)
from app.audio.project_service import CREW_CATEGORIES, RADIO_CATEGORIES, ProjectGroup
from app.contracts import TaskState, TaskStatusSnapshot
from app.models import (
    ConflictPolicy, CopyBatchResult, CopyResultStatus,
    CopyPlan,
    CopyTask,
    ManualCopyMode,
    RadioStagedCopyPlan,
    RadioTargetConflictKind,
    RadioTargetOperation,
)
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


LOGGER = logging.getLogger("wt_name_relay")


class PlaybackState(str, Enum):
    EMPTY = "empty"
    PREPARING = "preparing"
    READY = "ready"
    PLAYING = "playing"
    STOPPED = "stopped"
    ERROR = "error"


class PlaybackEndReason(str, Enum):
    NATURAL_END = "natural_end"
    USER_STOP = "user_stop"
    ERROR = "error"
    TIMELINE_CHANGED = "timeline_changed"
    SEEK = "seek"


class AudioProcessingPage(BaseToolPage):
    """Project-scoped, non-destructive single-track voice processing page."""

    close_ready = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("audio", "\u8bed\u97f3\u5904\u7406", parent)
        self.status_panel.setVisible(False)
        self._settings = QSettings("Beiku", "WT-NameRelay")
        self._project = AudioProjectService()
        self._groups = ProjectGroupRepository()
        self._timeline = TimelineModel()
        self._selected: set[str] = set()
        self._active_module = "crew"
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
        self._audio_output = QAudioOutput(self); self._player = QMediaPlayer(self); self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._play_position)
        self._player.playbackStateChanged.connect(self._play_state)
        self._player.mediaStatusChanged.connect(self._media_status_changed)
        self._player.errorOccurred.connect(self._playback_error)
        self._normalize_mode: str | None = self._settings.value("audio/normalize_mode", None, str) or None
        self._normalize_target = float(self._settings.value("audio/normalize_target", -1.0))
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

    @property
    def is_busy(self) -> bool:
        return (
            self._export_thread is not None
            or self._preview_thread is not None
            or bool(self._waveform_threads)
            or self._copy_service.is_busy
            or self._matrix_copy_service.is_busy
        )

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
        self._finalize_playback(PlaybackEndReason.TIMELINE_CHANGED, reset_playhead=False)
        if self._preview_path is not None: self._preview_path.unlink(missing_ok=True); self._preview_path=None
        self._copy_service.cancel()
        self._matrix_copy_service.cancel()
        return False

    def set_navigation_enabled(self, enabled: bool) -> None:
        self._navigation_enabled = enabled
        self.back_button.setEnabled(enabled and not self.is_busy)

    def _panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("crewManualPanel")
        return panel

    def _build(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("audioProcessingScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSpacing(12)

        project_panel = self._panel()
        project_row = QHBoxLayout(project_panel)
        project_row.addWidget(QLabel("\u9879\u76ee\u76ee\u5f55"))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("\u9009\u62e9\u8bed\u97f3\u5236\u4f5c\u9879\u76ee\u6839\u76ee\u5f55")
        project_row.addWidget(self.path_edit, 1)
        choose_root = QPushButton("\u9009\u62e9")
        rescan = QPushButton("\u91cd\u65b0\u626b\u63cf")
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
        for module, label in (("crew", "\u8f66\u7ec4"), ("radio", "\u65e0\u7ebf\u7535")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("audioNavigation", True)
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
        target_layout.addWidget(QLabel("\u76ee\u6807\u6587\u4ef6\u540d"))
        self.target_edit = QLineEdit()
        self.target_edit.setPlaceholderText("\u7c98\u8d34\u540d\u79f0\u3001\u5e26\u6269\u5c55\u540d\u7684\u540d\u79f0\u6216\u5b8c\u6574\u8def\u5f84")
        self.target_info = QLabel("\u8bf7\u8f93\u5165\u9700\u8981\u5236\u4f5c\u7684\u76ee\u6807\u6587\u4ef6\u540d\u3002")
        self.target_info.setObjectName("mutedLabel")
        self.target_menu_action = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown),
            "同组待制作项目",
            self.target_edit,
        )
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
        actions.setObjectName("crewActionBar")
        action_layout = QHBoxLayout(actions)
        self.add_audio_button = QPushButton("\u6dfb\u52a0\u97f3\u9891")
        self.blank_button = QPushButton("\u63d2\u51652\u79d2\u7a7a\u767d")
        self.remove_button = QPushButton("\u5220\u9664\u9009\u4e2d")
        self.split_button = QPushButton("\u97f3\u9891\u88c1\u526a")
        self.undo_button = QPushButton("\u64a4\u9500")
        self.preview_button = QPushButton("\u8bd5\u542c\u97f3\u8f68")
        self.stop_button = QPushButton("\u505c\u6b62")
        self.loop_selected = QCheckBox("\u5faa\u73af\u9009\u4e2d")
        self.add_audio_button.clicked.connect(self._choose_audio)
        self.blank_button.clicked.connect(self._add_blank)
        self.remove_button.clicked.connect(self._delete_selected)
        self.split_button.clicked.connect(self._split_audio)
        self.undo_button.clicked.connect(self._undo)
        self.preview_button.clicked.connect(self._preview)
        self.stop_button.clicked.connect(self._stop)
        for button in (
            self.add_audio_button,
            self.blank_button,
            self.remove_button,
            self.split_button,
            self.undo_button,
            self.preview_button,
            self.stop_button,
            self.loop_selected,
        ):
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
        zoom_layout.addWidget(QLabel("\u65f6\u95f4\u8f74\u7f29\u653e"))
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(0, 1000)
        self.zoom.setValue(210)
        self.zoom.valueChanged.connect(self._set_zoom_from_slider)
        self.time_label = QLabel("00:00.000 / 00:00.000")
        zoom_layout.addWidget(self.zoom, 1)
        zoom_layout.addWidget(self.time_label)
        layout.addLayout(zoom_layout)

        lower = QHBoxLayout()
        export_panel = self._panel()
        export_layout = QVBoxLayout(export_panel)
        export_layout.addWidget(QLabel("\u5bfc\u51fa\u8bbe\u7f6e"))
        self.sample_rate = QComboBox()
        self.sample_rate.addItems(["22050", "32000", "44100", "48000", "96000"])
        self.sample_rate.setCurrentText("48000")
        self.channels = QComboBox()
        self.channels.addItems(["\u5355\u58f0\u9053", "\u7acb\u4f53\u58f0"])
        self.bit_depth = QComboBox()
        self.bit_depth.addItems(["16-bit PCM", "24-bit PCM", "32-bit Float"])
        self.keep_timeline = QCheckBox("\u5bfc\u51fa\u540e\u4fdd\u7559\u97f3\u8f68")
        self.worker_count = QSpinBox()
        self.worker_count.setRange(1, max(1, (os.cpu_count() or 2) - 1))
        self.worker_count.setValue(1)
        self.loudness_button = QPushButton("\u8c03\u6574\u54cd\u5ea6")
        self.loudness_status = QLabel()
        self.output_label = QLabel("\u8f93\u51fa\uff1a\u2014")
        self.output_label.setWordWrap(True)
        self.audio_copy_mode_switch = CopyModeSwitch(export_panel)
        self.audio_copy_mode_switch.setVisible(False)
        self.audio_copy_mode_switch.mode_changed.connect(self._change_audio_copy_mode)
        self.export_button = QPushButton("\u5f00\u59cb\u5bfc\u51fa")
        self.cancel_button = QPushButton("\u53d6\u6d88\u4efb\u52a1")
        self.export_button.clicked.connect(self._export)
        self.cancel_button.clicked.connect(self._cancel_export)
        for widget in (
            self.sample_rate, self.channels, self.bit_depth, QLabel("\u5de5\u4f5c\u7ebf\u7a0b\u6570"),
            self.worker_count, self.loudness_button, self.loudness_status, self.keep_timeline, self.output_label,
        ):
            export_layout.addWidget(widget)
        mode_row = QHBoxLayout()
        mode_row.addStretch(1)
        mode_row.addWidget(self.audio_copy_mode_switch)
        export_layout.addLayout(mode_row)
        export_layout.addWidget(self.export_button)
        export_layout.addWidget(self.cancel_button)
        self.loudness_button.clicked.connect(self._show_loudness_dialog)
        self._update_loudness_status()
        lower.addWidget(export_panel, 1)

        group_panel = self._panel()
        group_layout = QVBoxLayout(group_panel)
        group_layout.addWidget(QLabel("\u5f53\u524d\u9879\u76ee\u7ec4\u8fdb\u5ea6"))
        self.group_detail = QLabel("\u8bf7\u8f93\u5165\u76ee\u6807\u6587\u4ef6\u540d\u3002")
        self.group_detail.setWordWrap(True)
        self.fill_button = QPushButton("\u4e00\u952e\u590d\u5236\u8865\u9f50")
        self.fill_button.clicked.connect(self._fill)
        group_layout.addWidget(self.group_detail)
        group_layout.addWidget(self.fill_button)
        group_layout.addStretch(1)
        lower.addWidget(group_panel, 1)
        layout.addLayout(lower)

        self.copy_status = TaskStatusPanel()
        self.copy_status.set_title("\u4efb\u52a1\u8fdb\u5ea6\u8be6\u60c5")
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
        focus_text = ""
        if focus is not None and hasattr(focus, "text"):
            try:
                focus_text = str(focus.text())
            except (RuntimeError, TypeError):
                focus_text = ""
        body = scroll.widget()
        LOGGER.debug(
            "Audio task UI state: operation=%s scroll=%s/%s focus=%s object=%s text=%r "
            "content_height=%s group_panel_height=%s",
            operation,
            scroll.verticalScrollBar().value(),
            scroll.verticalScrollBar().maximum(),
            type(focus).__name__ if focus is not None else "None",
            focus.objectName() if focus is not None else "",
            focus_text,
            body.height() if body is not None else -1,
            self.group_detail.parentWidget().height() if self.group_detail.parentWidget() is not None else -1,
        )

    def _begin_task_ui_transition(self, operation: str) -> None:
        """Freeze one task-start layout transition without locking later user scrolling."""
        self._scroll_guard.begin_hold()
        self._task_first_progress_logged = False
        self._log_task_ui_state(f"{operation}:before")
        scroll = self._body_widget
        if isinstance(scroll, QScrollArea):
            # Disabling a focused lower-page button otherwise moves focus to the first
            # enabled category button and makes QScrollArea reveal that top control.
            scroll.setFocus(Qt.FocusReason.OtherFocusReason)

    def _end_task_ui_transition(self, operation: str) -> None:
        self._scroll_guard.end_hold()
        self._log_task_ui_state(f"{operation}:submitted")

    def _task_progress_observed(self, _snapshot: object) -> None:
        if self._task_first_progress_logged:
            return
        self._task_first_progress_logged = True
        self._log_task_ui_state("first-progress")

    def _restore_settings(self) -> None:
        path = self._settings.value("audio/project_root", "", str)
        self.path_edit.setText(path)
        if path:
            self._set_root()

    def _choose_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "\u9009\u62e9\u5236\u4f5c\u9879\u76ee\u6839\u76ee\u5f55", self.path_edit.text())
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
            self._settings.setValue("audio/project_root", raw)
            self._watch_directories()
            self._refresh_group()
            self.target_info.setText("\u9879\u76ee\u76ee\u5f55\u5df2\u5c31\u7eea\u3002")
        except OSError as error:
            self.target_info.setText(f"\u521b\u5efa\u9879\u76ee\u76ee\u5f55\u5931\u8d25\uff1a{error}")

    def _build_categories(self) -> None:
        for button in self.category_buttons.buttons():
            self.category_buttons.removeButton(button)
        self._category_button_by_id.clear()
        while self.category_layout.count():
            item = self.category_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        categories = CREW_CATEGORIES if self._active_module == "crew" else RADIO_CATEGORIES
        for category in categories:
            button = QPushButton(category)
            button.setCheckable(True)
            button.setProperty("audioNavigation", True)
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
        self._active_category = (CREW_CATEGORIES if module == "crew" else RADIO_CATEGORIES)[0]
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
            self.target_info.setText("\u76ee\u6807\u540d\u79f0\u542b\u6709 Windows \u4e0d\u5141\u8bb8\u7684\u5b57\u7b26\u3002")
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
                self._active_module, self._active_category = group.module, group.category
                if self._root is not None:
                    self._project.ensure_layout(self._root)
                self._build_categories()
                self._watch_directories()
            self._sync_navigation_selection()
            self.target_info.setText(f"\u5df2\u8bc6\u522b\uff1a{group.module} / {group.category} / {group.base_name}")
        elif self._current_group:
            group = self._current_group
            if group.module != self._active_module:
                self._active_module = group.module
                self._active_category = (
                    CREW_CATEGORIES[0] if group.module == "crew" else RADIO_CATEGORIES[0]
                )
                self._build_categories()
                self._watch_directories()
            self._sync_navigation_selection()
            self.target_info.setText("\u8be5\u540d\u79f0\u5df2\u6536\u5f55\uff0c\u4f46\u672a\u5206\u7c7b\uff1b\u5c06\u6309\u5f53\u524d\u5206\u7c7b\u5bfc\u51fa\u3002")
        else:
            self.target_info.setText("\u8be5\u540d\u79f0\u672a\u6536\u5f55\uff1b\u5c06\u6309\u5f53\u524d\u5206\u7c7b\u5bfc\u51fa\u3002")
        self._refresh_group()

    def _matrix_layout(self):
        group = self._current_group
        if group is None:
            return None
        return self._matrix_planner.analyze(
            group.group_key,
            group.names,
            lambda name: (
                owner.group_key if (owner := self._groups.lookup(name)) is not None else None
            ),
        )

    def _set_audio_copy_mode(self, mode: ManualCopyMode) -> None:
        self._audio_copy_mode = mode
        if hasattr(self, "audio_copy_mode_switch"):
            self.audio_copy_mode_switch.set_average_checked(
                mode is ManualCopyMode.AVERAGE,
                emit=False,
            )

    def _change_audio_copy_mode(self, average: bool) -> None:
        if self.is_busy:
            self.audio_copy_mode_switch.set_average_checked(
                self._audio_copy_mode is ManualCopyMode.AVERAGE,
                emit=False,
            )
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
                action = menu.addAction(
                    f"第 {subgroup.index + 1} 组：{subgroup.names[0]} ～ {subgroup.names[-1]}（{completed}/3）"
                )
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
            self.group_detail.setText("\u8bf7\u8f93\u5165\u5df2\u6536\u5f55\u7684\u76ee\u6807\u6587\u4ef6\u540d\u3002")
            self.output_label.setText("\u8f93\u51fa\uff1a\u2014")
            self.fill_button.setEnabled(False)
            self._fill_available = False
            self._target_menu_has_items = False
            self.target_menu_action.setEnabled(False)
            self.audio_copy_mode_switch.setVisible(False)
            return
        present, formats = self._project.group_progress(directory, self._current_group)
        missing = [name for name in self._current_group.names if name not in present]
        duplicates = [name for name, paths in formats.items() if name in self._current_group.names and len(paths) > 1]
        completed_text = ", ".join(sorted(present)) or "\u2014"
        missing_text = ", ".join(missing) or "\u2014"
        lines = [
            self._current_group.base_name,
            f"\u5b8c\u6210\u5ea6\uff1a{len(present)} / {len(self._current_group.names)}",
            f"\u5df2\u5236\u4f5c\uff1a{completed_text}",
            f"\u5f85\u5236\u4f5c\uff1a{missing_text}",
        ]
        matrix_layout = self._matrix_layout()
        eligible = matrix_layout is not None
        self.audio_copy_mode_switch.setVisible(eligible)
        if not eligible and self._audio_copy_mode is ManualCopyMode.AVERAGE:
            self._set_audio_copy_mode(ManualCopyMode.SEQUENTIAL)
        if eligible and matrix_layout is not None:
            complete_subgroups = sum(
                all(name in present for name in subgroup.names)
                for subgroup in matrix_layout.subgroups
            )
            lines.append(f"完整小组：{complete_subgroups} / {len(matrix_layout.subgroups)}")
        if duplicates:
            lines.append("\u540c\u540d\u591a\u683c\u5f0f\uff1a" + ", ".join(duplicates))
        self.group_detail.setText("\n".join(lines))
        target_name = self._project.parse_target(self.target_edit.text())
        self.output_label.setText(f"\u8f93\u51fa\uff1a{directory / (target_name + '.wav')}")
        if self._audio_copy_mode is ManualCopyMode.AVERAGE and matrix_layout is not None:
            subgroup = matrix_layout.subgroup_for(target_name)
            if subgroup is not None:
                self.output_label.setText(
                    "平均分配目标：\n" + "\n".join(str(directory / f"{name}.wav") for name in subgroup.names)
                )
        if self._audio_copy_mode is ManualCopyMode.AVERAGE and matrix_layout is not None:
            has_pending = any(
                not all(name in present for name in subgroup.names)
                for subgroup in matrix_layout.subgroups
            )
        else:
            has_pending = bool(missing)
        self._target_menu_has_items = has_pending
        self.target_menu_action.setEnabled(has_pending and not self.is_busy)
        if self._audio_copy_mode is ManualCopyMode.AVERAGE and matrix_layout is not None:
            complete_count = sum(
                all(name in present for name in subgroup.names)
                for subgroup in matrix_layout.subgroups
            )
            self._fill_available = 0 < complete_count < len(matrix_layout.subgroups)
        else:
            self._fill_available = bool(present and missing)
        self.fill_button.setEnabled(bool(present and missing) and not self.is_busy)
        if not missing and present and not self._completion_announced:
            self.target_info.setText("\u5f53\u524d\u9879\u76ee\u7ec4\u5df2\u5b8c\u6574\u3002")
            self._completion_announced = True
            self._completion_message_timer.start()
        elif missing:
            self._completion_announced = False

    def _restore_project_ready_status(self) -> None:
        self.target_info.setText("\u9879\u76ee\u76ee\u5f55\u5df2\u5c31\u7eea\u3002")

    def _watch_directories(self) -> None:
        self._watcher.removePaths(self._watcher.directories())
        if self._root is None:
            return
        paths = [self._root, self._root / "\u8f66\u7ec4", self._root / "\u65e0\u7ebf\u7535"]
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
            LOGGER.warning("Audio average fill returned an unexpected result: %r", result)
            return
        LOGGER.info(
            "Audio average fill finished: state=%s total=%s created=%s overwritten=%s "
            "skipped=%s failed=%s cancelled=%s",
            result.state.value,
            len(result.results),
            result.created,
            result.overwritten,
            result.skipped,
            result.failed,
            result.cancelled,
        )
        failures = [item for item in result.results if item.status is CopyResultStatus.FAILED]
        if not failures:
            return
        details = "\n".join(
            f"{item.task.target_path}：{item.reason or '未知错误'}" for item in failures
        )
        self.target_info.setText(f"平均分配补齐有 {len(failures)} 个文件失败。")
        QMessageBox.warning(
            self,
            "平均分配补齐未全部完成",
            f"有 {len(failures)} 个目标文件复制失败：\n{details}",
        )

    def _choose_audio(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "\u9009\u62e9\u97f3\u9891", "", "\u97f3\u9891\u6587\u4ef6 (*.wav *.flac *.mp3 *.ogg *.m4a *.aac *.opus)")
        self._add_audio_paths(paths)

    def _add_audio_paths(self, paths: list[str]) -> None:
        for raw in paths:
            path = Path(raw)
            if not path.is_file():
                self.target_info.setText(f"无法导入 {path.name}：文件不存在")
                continue
            request_id = uuid4().hex
            self._pending_audio_paths[request_id] = path
            self._build_waveform(request_id, path)
        if self._pending_audio_paths and not self._timeline.items:
            self._playback_state = PlaybackState.PREPARING
            self.target_info.setText("正在解析音频时长与波形……")
        self._sync()

    def _build_waveform(self, clip_id: str, path: Path) -> None:
        thread=QThread(self);worker=WaveformWorker(clip_id,path);worker.moveToThread(thread);thread.started.connect(worker.run);worker.finished.connect(self._waveform_done);worker.finished.connect(thread.quit);thread.finished.connect(worker.deleteLater);thread.finished.connect(lambda key=clip_id:self._waveform_thread_done(key));self._waveform_threads[clip_id]=(thread,worker);thread.start()

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
            self.target_info.setText(f"已导入：{path.name}")
        else:
            self.target_info.setText(f"无法导入 {path.name}：{error}")
            self._playback_state = PlaybackState.READY if self._timeline.items else PlaybackState.EMPTY
            self._sync()

    def _add_blank(self) -> None:
        self._timeline.add_blank()
        self._render_timeline(); self._invalidate_preview()

    def _set_selection(self, ids: set[str]) -> None:
        self._selected = ids
        self._sync()

    def _trim_preview(self, _clip_id: str, start_ms: int, end_ms: int) -> None:
        from app.audio.models import format_ms
        self.target_info.setText(f"\u88c1\u5207\uff1a{format_ms(start_ms)} - {format_ms(end_ms)}\uff0c{format_ms(end_ms-start_ms)}")

    def _trim_committed(self, clip_id: str, start_ms: int, end_ms: int) -> None:
        self._timeline.trim_ms(clip_id, start_ms, end_ms); self._render_timeline(); self._invalidate_preview()

    def _move_committed(self, ids: set[str], index: int) -> None:
        self._timeline.move(ids, index); self._render_timeline(); self._invalidate_preview()

    def _relative_zoom(self, multiplier: float) -> None:
        import math
        ratio=(math.log(self.timeline_view.pixels_per_second*multiplier/2)/math.log(1000/2))*1000
        self.zoom.setValue(max(self.zoom.minimum(), min(self.zoom.maximum(), round(ratio))))

    def _set_zoom_from_slider(self, value: int) -> None:
        pps=2*((1000/2)**(value/1000))
        self.timeline_view.animate_pixels_per_second(pps)

    def _delete_selected(self) -> None:
        self._timeline.remove(self._selected)
        self._selected.clear()
        self._render_timeline(); self._invalidate_preview()

    def _undo(self) -> None:
        result = self._timeline.undo()
        if result is not None and result.kind is TimelineEditKind.SPLIT and result.split is not None:
            self._selected = {result.split.original_clip_id}
            self.playhead_time_ms = result.split.timeline_position_ms
        else:
            existing = {item.clip_id for item in self._timeline.items}
            self._selected.intersection_update(existing)
        self._render_timeline(); self._invalidate_preview()

    def _split_audio(self) -> None:
        location = self._timeline.locate(self.playhead_time_ms)
        if (
            location is None
            or location.kind is not TimelineClipKind.AUDIO
            or location.offset_ms < 1
            or self._timeline.items[location.index].duration_ms - location.offset_ms < 1
        ):
            self.target_info.setText("请先点击音频片段中的裁剪位置。")
            return
        if self.is_busy:
            self.target_info.setText("当前有后台任务运行，请稍后再执行音频裁剪。")
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
        self.target_info.setText(
            f"已在 {result.timeline_position_ms / 1000:.3f} s 处将音频切分为两段。"
        )

    def _seek(self, position: float) -> None:
        position_ms = max(0, min(self._timeline.duration_ms, int(position)))
        self.playhead_time_ms = position_ms
        self.timeline_view.set_playhead_ms(position_ms)
        if self._playback_state is PlaybackState.PLAYING:
            self._player.setPosition(position_ms)
        from app.audio.models import format_ms
        self.time_label.setText(f"{format_ms(position_ms)} / {format_ms(self._timeline.duration_ms)}")
        self._sync()

    def _playhead_drag_started(self) -> None:
        if self._playback_state is PlaybackState.PLAYING:
            self._finalize_playback(PlaybackEndReason.SEEK, reset_playhead=False)

    def _playhead_drag_preview(self, position_ms: int) -> None:
        self.playhead_time_ms = max(0, min(self._timeline.duration_ms, position_ms))
        from app.audio.models import format_ms
        self.time_label.setText(
            f"{format_ms(self.playhead_time_ms)} / {format_ms(self._timeline.duration_ms)}"
        )
        self._sync()

    def _render_timeline(self) -> None:
        from app.audio.models import format_ms
        self.playhead_time_ms = max(0, min(self.playhead_time_ms, self._timeline.duration_ms))
        self.timeline_view.set_timeline(self._timeline, self._selected)
        self.timeline_view.set_playhead_ms(self.playhead_time_ms)
        self.time_label.setText(f"{format_ms(self.playhead_time_ms)} / {format_ms(self._timeline.duration_ms)}")
        self._sync()

    def _settings_snapshot(self) -> ExportSettings:
        return ExportSettings(
            sample_rate=int(self.sample_rate.currentText()),
            channels=1 if self.channels.currentIndex() == 0 else 2,
            bit_depth=self.bit_depth.currentText(),
            normalize_mode=self._normalize_mode,
            normalize_target=self._normalize_target,
            keep_timeline=self.keep_timeline.isChecked(),
            worker_threads=self.worker_count.value(),
        )

    def _export(self) -> None:
        self._begin_task_ui_transition("export")
        try:
            self._export_impl()
        finally:
            self._end_task_ui_transition("export")

    def _export_impl(self) -> None:
        directory = self._directory()
        name = self._project.parse_target(self.target_edit.text())
        if directory is None or not self._project.valid_filename(name) or not self._timeline.items:
            self.target_info.setText("\u8bf7\u5148\u8bbe\u7f6e\u9879\u76ee\u76ee\u5f55\u3001\u5408\u6cd5\u76ee\u6807\u540d\u79f0\u548c\u81f3\u5c11\u4e00\u4e2a\u97f3\u8f68\u3002")
            return
        if self._audio_copy_mode is ManualCopyMode.AVERAGE:
            self._export_average(directory, name)
            return
        target = directory / f"{name}.wav"
        if target.exists() and QMessageBox.question(self, "\u76ee\u6807\u5df2\u5b58\u5728", "\u662f\u5426\u8986\u76d6\u73b0\u6709 WAV \u6587\u4ef6\uff1f") != QMessageBox.StandardButton.Yes:
            return
        settings = self._settings_snapshot()
        snapshot = self._timeline.snapshot(settings.sample_rate, settings.channels)
        self._export_cancel_event = threading.Event()
        thread = QThread(self)
        worker = AudioExportService(snapshot, settings, target, self._export_cancel_event)
        self._start_export_worker(thread, worker)

    def _start_export_worker(
        self,
        thread: QThread,
        worker: AudioExportService | AudioMatrixExportService,
    ) -> None:
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._export_progress)
        worker.finished.connect(self._export_done)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._export_thread_done)
        self._export_thread = thread; self._export_worker = worker
        self._watch_suspended = True
        thread.start()
        self._sync()

    def _export_average(self, directory: Path, name: str) -> None:
        layout = self._matrix_layout()
        if layout is None:
            self.target_info.setText("当前项目组不符合平均分配条件，已保持顺序复制。")
            self._set_audio_copy_mode(ManualCopyMode.SEQUENTIAL)
            self._refresh_group()
            return
        subgroup = layout.subgroup_for(name)
        if subgroup is None:
            self.target_info.setText("目标名称不属于当前矩阵项目组。")
            return
        present, formats = self._project.group_progress(directory, self._current_group)
        if all(member in present for member in subgroup.names):
            self.target_info.setText("该三成员小组已经完成，请从待制作下拉列表选择其他小组。")
            return
        cross_format = [
            path
            for member in subgroup.names
            for path in formats.get(member, [])
            if path.suffix.casefold() != ".wav"
        ]
        if cross_format:
            QMessageBox.warning(
                self,
                "存在其他音频格式",
                "平均分配不会删除或改写非 WAV 文件。请先处理以下同名文件：\n"
                + "\n".join(str(path) for path in cross_format),
            )
            return
        existing_wav = [
            path
            for member in subgroup.names
            for path in formats.get(member, [])
            if path.suffix.casefold() == ".wav"
        ]
        if existing_wav:
            answer = QMessageBox.question(
                self,
                "重新生成未完整小组",
                "平均分配将覆盖以下已有成员：\n"
                + "\n".join(str(path) for path in existing_wav)
                + "\n\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            LOGGER.info(
                "Audio average export confirmation: reply=%r type=%s group=%s targets=%s",
                answer,
                type(answer).__name__,
                self._current_group.group_key if self._current_group is not None else "",
                len(subgroup.names),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        settings = self._settings_snapshot()
        snapshot = self._timeline.snapshot(settings.sample_rate, settings.channels)
        targets = tuple(directory / f"{member}.wav" for member in subgroup.names)
        self._export_cancel_event = threading.Event()
        thread = QThread(self)
        worker = AudioMatrixExportService(snapshot, settings, targets, self._export_cancel_event)
        self._start_export_worker(thread, worker)

    def _export_progress(self, step: str, percent: int, filename: str) -> None:
        self._task_progress_observed(None)
        self.target_info.setText(f"{step}：{filename}")
        total = 4 if self._audio_copy_mode is ManualCopyMode.AVERAGE else 1
        processed = min(total, round(percent / 100 * total))
        self.copy_status.set_snapshot(
            TaskStatusSnapshot(
                state=TaskState.RUNNING,
                progress=percent,
                processed=processed,
                total=total,
                current_file=filename,
                message=step,
            )
        )

    def _export_done(self, ok: bool, message: str, _target: object) -> None:
        self.target_info.setText(message)
        if ok:
            self._watch_refresh_pending = True
            if not self.keep_timeline.isChecked():
                self._timeline.reset()
                self._selected.clear()
                self._render_timeline()

    def _export_thread_done(self) -> None:
        self._export_thread = None; self._export_worker = None
        self._watch_suspended = False
        self._watch_refresh_pending = False
        self._watch_timer.start(500)
        self._sync()

    def _cancel_export(self) -> None:
        self._export_cancel_event.set()

    def _preview(self) -> None:
        LOGGER.info(
            "Audio preview play request: state=%s playhead_ms=%s total_ms=%s "
            "media_status=%s player_position_ms=%s active_session=%s",
            self._playback_state.value,
            self.playhead_time_ms,
            self._timeline.duration_ms,
            self._player.mediaStatus().name,
            self._player.position(),
            self._active_playback_session_id,
        )
        if not self._timeline.items:
            self.target_info.setText("请先向音轨中导入音频。")
            return
        settings = self._settings_snapshot()
        snapshot = self._timeline.snapshot(settings.sample_rate, settings.channels)
        if self.loop_selected.isChecked() and not self._selected:
            self.target_info.setText("请先选择需要循环的片段。")
            return
        if self._preview_path and self._preview_path.is_file() and self._preview_version == snapshot.version:
            self._queue_preview_playback(
                self._preview_path,
                self._preview_start_position(snapshot.total_duration_ms),
            )
            return
        import tempfile
        self._playback_state=PlaybackState.PREPARING
        self._preview_cancel_event = threading.Event()
        target=Path(tempfile.gettempdir()) / f"wt_name_relay_preview_{id(self)}_{snapshot.version}.wav"
        thread=QThread(self)
        worker=AudioPreviewService(snapshot,settings,target,self._preview_cancel_event)
        worker.moveToThread(thread)
        self._preview_version = snapshot.version
        thread.started.connect(worker.run);worker.progress.connect(lambda step,_p,_f:self.target_info.setText(f"\u6b63\u5728\u51c6\u5907\u8bd5\u542c\uff1a{step}"));worker.finished.connect(self._preview_done);worker.finished.connect(thread.quit);thread.finished.connect(worker.deleteLater);thread.finished.connect(self._preview_thread_done)
        self._preview_thread=thread;self._preview_worker=worker;thread.start();self._sync()

    def _preview_done(self, ok: bool, message: str, target: object) -> None:
        if ok and isinstance(target,Path):
            if self._preview_version != self._timeline.snapshot().version:
                target.unlink(missing_ok=True)
                self._playback_state = PlaybackState.READY
                return
            self._preview_path=target
            self._queue_preview_playback(
                target,
                self._preview_start_position(self._timeline.duration_ms),
            )
        else:
            self.target_info.setText(message)
            self._playback_state=PlaybackState.ERROR

    def _preview_thread_done(self) -> None:self._preview_thread=None;self._preview_worker=None;self._sync()

    def _preview_start_position(self, total_duration_ms: int) -> int:
        position = self.playhead_time_ms
        if position >= max(0, total_duration_ms - 1):
            position = 0
            self.playhead_time_ms = 0
            self.timeline_view.set_playhead_ms(0)
        loop_range = self._loop_range()
        if loop_range is not None and not (loop_range[0] <= position < loop_range[1]):
            position = loop_range[0]
            self.playhead_time_ms = position
            self.timeline_view.set_playhead_ms(position)
        return position

    def _queue_preview_playback(self, path: Path, position_ms: int) -> None:
        self._pending_play_start_ms = max(0, min(self._timeline.duration_ms, position_ms))
        source = QUrl.fromLocalFile(str(path))
        same_source = self._player.source() == source
        LOGGER.info(
            "Audio preview source queued: same_source=%s start_ms=%s media_status=%s",
            same_source,
            self._pending_play_start_ms,
            self._player.mediaStatus().name,
        )
        if not same_source:
            self._player.setSource(source)
        if same_source or self._player.mediaStatus() in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
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
        LOGGER.info(
            "Audio preview session created: session=%s start_ms=%s total_ms=%s "
            "media_status=%s",
            self._active_playback_session_id,
            position,
            self._timeline.duration_ms,
            self._player.mediaStatus().name,
        )
        self._sync()

    def _stop(self) -> None:
        if self._playback_state is PlaybackState.PREPARING:
            self._preview_cancel_event.set()
        self._finalize_playback(PlaybackEndReason.USER_STOP, reset_playhead=True)

    def _finalize_playback(
        self,
        reason: PlaybackEndReason,
        *,
        reset_playhead: bool,
    ) -> None:
        if self._finalizing_playback:
            LOGGER.info("Duplicate audio preview finalization ignored: reason=%s", reason.value)
            return
        if reason is PlaybackEndReason.NATURAL_END and self._active_playback_session_id is None:
            LOGGER.info("Stale natural-end callback ignored: no active playback session")
            return
        self._finalizing_playback = True
        session_id = self._active_playback_session_id
        if reason is PlaybackEndReason.NATURAL_END:
            visual_position = self._timeline.duration_ms
        elif reset_playhead:
            visual_position = 0
        else:
            visual_position = max(0, min(self.playhead_time_ms, self._timeline.duration_ms))
        LOGGER.info(
            "Audio preview finalizing: reason=%s session=%s state=%s "
            "playhead_ms=%s total_ms=%s player_position_ms=%s media_status=%s",
            reason.value,
            session_id,
            self._playback_state.value,
            self.playhead_time_ms,
            self._timeline.duration_ms,
            self._player.position(),
            self._player.mediaStatus().name,
        )
        try:
            self._pending_play_start_ms = None
            self._active_playback_session_id = None
            self._player.stop()
            # QMediaPlayer keeps EndOfMedia after natural completion. Rewinding its
            # internal position clears the EOF-like terminal state for the next play.
            self._player.setPosition(0)
            self.playhead_time_ms = visual_position
            self.timeline_view.set_playhead_ms(visual_position)
            from app.audio.models import format_ms
            self.time_label.setText(
                f"{format_ms(visual_position)} / {format_ms(self._timeline.duration_ms)}"
            )
            if not self._timeline.items:
                self._playback_state = PlaybackState.EMPTY
            elif reason is PlaybackEndReason.ERROR:
                self._playback_state = PlaybackState.ERROR
            elif reason is PlaybackEndReason.USER_STOP:
                self._playback_state = PlaybackState.STOPPED
            else:
                self._playback_state = PlaybackState.READY
            self._sync()
            LOGGER.info(
                "Audio preview reset completed: reason=%s session=%s "
                "visual_playhead_ms=%s player_position_ms=%s next_state=%s",
                reason.value,
                session_id,
                visual_position,
                self._player.position(),
                self._playback_state.value,
            )
        finally:
            self._finalizing_playback = False

    def _play_position(self, position: int) -> None:
        if self._finalizing_playback:
            return
        self.playhead_time_ms = max(0, min(self._timeline.duration_ms, position))
        self.timeline_view.set_playhead_ms(self.playhead_time_ms)
        from app.audio.models import format_ms
        self.time_label.setText(f"{format_ms(self.playhead_time_ms)} / {format_ms(self._timeline.duration_ms)}")
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
        first, last = min(indexes), max(indexes)
        start = sum(item.duration_ms for item in self._timeline.items[:first])
        end = sum(item.duration_ms for item in self._timeline.items[: last + 1])
        return start, end

    def _play_state(self, state: object) -> None:
        if self._finalizing_playback:
            return
        if state == QMediaPlayer.PlaybackState.PlayingState:self._playback_state=PlaybackState.PLAYING
        elif self._active_playback_session_id is None and self._pending_play_start_ms is None and self._playback_state not in (PlaybackState.ERROR, PlaybackState.PREPARING):self._playback_state=PlaybackState.STOPPED if self._timeline.items else PlaybackState.EMPTY
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
                LOGGER.info("Stale EndOfMedia callback ignored")
                return
            tolerance_ms = 5
            observed_position = max(self.playhead_time_ms, self._player.position())
            if observed_position < self._timeline.duration_ms - tolerance_ms:
                LOGGER.info(
                    "Stale or premature EndOfMedia ignored: "
                    "session=%s observed_ms=%s total_ms=%s",
                    self._active_playback_session_id,
                    observed_position,
                    self._timeline.duration_ms,
                )
                return
            LOGGER.info(
                "Audio preview natural end detected: session=%s observed_ms=%s total_ms=%s",
                self._active_playback_session_id,
                observed_position,
                self._timeline.duration_ms,
            )
            self._finalize_playback(PlaybackEndReason.NATURAL_END, reset_playhead=False)

    def _playback_error(self, _error: QMediaPlayer.Error, message: str) -> None:
        if not message:
            return
        self.target_info.setText(f"试听失败：{message}")
        LOGGER.error("Audio preview playback error: %s", message)
        self._finalize_playback(PlaybackEndReason.ERROR, reset_playhead=False)

    def _invalidate_preview(self) -> None:
        self._preview_cancel_event.set()
        self._finalize_playback(PlaybackEndReason.TIMELINE_CHANGED, reset_playhead=False)
        if self._preview_path is not None:
            self._preview_path.unlink(missing_ok=True)
            self._preview_path=None
        self._preview_version = None

    def _update_loudness_status(self) -> None:
        if self._normalize_mode=="peak":self.loudness_status.setText(f"\u5cf0\u503c\u5f52\u4e00\u5316\uff1a{self._normalize_target:.1f} dBFS")
        elif self._normalize_mode=="loudness":self.loudness_status.setText(f"\u54cd\u5ea6\u5f52\u4e00\u5316\uff1a{self._normalize_target:.1f} LUFS")
        else:self.loudness_status.setText("\u54cd\u5ea6\u5904\u7406\uff1a\u5173\u95ed")

    def _show_loudness_dialog(self) -> None:
        dialog=QDialog(self);dialog.setWindowTitle("\u8c03\u6574\u54cd\u5ea6");layout=QVBoxLayout(dialog);enabled=QCheckBox("\u542f\u7528\u54cd\u5ea6\u5904\u7406");enabled.setChecked(self._normalize_mode is not None);peak=QRadioButton("\u5cf0\u503c\u5f52\u4e00\u5316");loud=QRadioButton("\u54cd\u5ea6\u5f52\u4e00\u5316");peak_value=QDoubleSpinBox();peak_value.setRange(-12,0);peak_value.setDecimals(1);peak_value.setValue(self._normalize_target if self._normalize_mode=="peak" else -1);loud_value=QDoubleSpinBox();loud_value.setRange(-30,-5);loud_value.setDecimals(1);loud_value.setValue(self._normalize_target if self._normalize_mode=="loudness" else -10);peak.setChecked(self._normalize_mode!="loudness");layout.addWidget(enabled);layout.addWidget(peak);layout.addWidget(peak_value);layout.addWidget(loud);layout.addWidget(loud_value);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(buttons)
        def apply()->None:
            self._normalize_mode="loudness" if enabled.isChecked() and loud.isChecked() else "peak" if enabled.isChecked() else None;self._normalize_target=loud_value.value() if self._normalize_mode=="loudness" else peak_value.value();self._settings.setValue("audio/normalize_mode",self._normalize_mode or "");self._settings.setValue("audio/normalize_target",self._normalize_target);self._update_loudness_status();dialog.accept()
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(apply);buttons.rejected.connect(dialog.reject);dialog.exec()

    def _fill(self) -> None:
        self._begin_task_ui_transition("fill")
        try:
            self._fill_impl()
        finally:
            self._end_task_ui_transition("fill")

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
        tasks = tuple(
            CopyTask(self._current_group.base_name, source_paths[index % len(source_paths)], directory / f"{name}{source_paths[index % len(source_paths)].suffix}", name)
            for index, name in enumerate(missing)
        )
        if self._copy_service.start_copy(CopyPlan(tasks), ConflictPolicy.SKIP_EXISTING):
            self.copy_status.set_snapshot(TaskStatusSnapshot(total=len(tasks), message="\u6b63\u5728\u51c6\u5907\u8865\u9f50"))
            self._sync()

    def _fill_average(self, directory: Path) -> None:
        """Build and execute the shared, full-group average plan."""
        layout = self._matrix_layout()
        group = self._current_group
        if layout is None or group is None or self._matrix_copy_service.is_busy:
            return
        _present, files = self._project.group_progress(directory, group)
        source_paths = tuple(
            path
            for member_name in group.names
            for path in files.get(member_name, ())
        )
        try:
            distribution = self._average_source_adapter.build(
                group,
                source_paths,
                directory,
                lambda name: (
                    owner.group_key if (owner := self._groups.lookup(name)) is not None else None
                ),
            )
        except (OSError, ValueError) as error:
            LOGGER.warning("Audio average fill planning failed: group=%s error=%s", group.group_key, error)
            QMessageBox.warning(self, "无法平均补齐", str(error))
            return

        cross_format: list[Path] = []
        for operation in distribution.operations:
            for existing in files.get(operation.target_member_name, ()):
                if existing.suffix.casefold() != operation.target_path.suffix.casefold():
                    cross_format.append(existing)
        if cross_format:
            QMessageBox.warning(
                self,
                "存在不同格式的同名文件",
                "平均补齐不会删除或制造同名多格式。请先处理：\n"
                + "\n".join(str(path) for path in sorted(set(cross_format))),
            )
            return

        operations = tuple(
            RadioTargetOperation(
                module=operation.module,
                group_id=operation.group_id,
                group_display_name=operation.group_display_name,
                source_original_path=operation.source.original_path,
                source_snapshot_key=operation.source.source_id,
                source_member_name=operation.source.canonical_basename,
                target_member_name=operation.target_member_name,
                target_path=operation.target_path,
                copy_mode=ManualCopyMode.AVERAGE,
                will_overwrite=operation.will_overwrite,
                conflict_kind=operation.conflict_kind,
                source_content_hash=operation.source.content_hash,
            )
            for operation in distribution.operations
        )
        confirmed_plan = RadioStagedCopyPlan(
            operations,
            imported_source_paths=distribution.all_source_paths,
        )
        displayed_conflicts = frozenset(confirmed_plan.current_external_conflicts())
        mapping_lines = [
            f"{source.original_path.name} → 第{bucket.index + 1}组"
            for bucket, source in zip(
                distribution.buckets, distribution.bucket_sources, strict=True
            )
        ]
        details = (
            "来源到目标映射：\n"
            + "\n".join(mapping_lines)
            + f"\n\n将重写 {distribution.source_target_count} 个来源目标"
            + f"\n将新建 {distribution.generated_count} 个目标"
            + f"\n外部冲突 {distribution.external_conflict_count} 个"
            + f"\n最终分配：{distribution.final_pattern}"
        )
        if distribution.warnings:
            details += "\n\n提示：\n" + "\n".join(distribution.warnings)
        answer = QMessageBox.question(
            self,
            "确认平均分配补齐",
            details + "\n\n是否开始？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        LOGGER.info(
            "Audio shared average confirmation: reply=%r group=%s sources=%s buckets=%s "
            "operations=%s pattern=%s source_targets=%s external_conflicts=%s",
            answer,
            group.group_key,
            len(distribution.sources),
            len(distribution.buckets),
            confirmed_plan.total,
            distribution.final_pattern,
            distribution.source_target_count,
            distribution.external_conflict_count,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        current_conflicts = frozenset(confirmed_plan.current_external_conflicts())
        new_conflicts = tuple(
            sorted(current_conflicts - displayed_conflicts, key=lambda path: str(path).casefold())
        )
        if new_conflicts:
            QMessageBox.warning(
                self,
                "目标文件状态已变化",
                "确认期间出现了新的目标文件，请检查后重新确认：\n"
                + "\n".join(str(path) for path in new_conflicts),
            )
            return
        policy = (
            ConflictPolicy.OVERWRITE_EXISTING
            if displayed_conflicts
            else ConflictPolicy.SKIP_EXISTING
        )
        try:
            started = self._matrix_copy_service.start_copy(confirmed_plan, policy)
        except Exception as error:
            LOGGER.exception("Audio shared average worker could not start: group=%s", group.group_key)
            self.target_info.setText(f"平均分配补齐未能启动：{error}")
            self._sync()
            QMessageBox.critical(self, "无法启动复制任务", f"平均分配补齐未能启动：\n{error}")
            return
        if started:
            self.copy_status.set_snapshot(
                TaskStatusSnapshot(total=confirmed_plan.total, message="正在暂存平均分配来源")
            )
            self._sync()
            return
        self.target_info.setText("平均分配补齐未启动：复制服务正忙，请稍后重试。")
        self._sync()
        QMessageBox.warning(self, "复制任务未启动", "复制服务正忙，请稍后重试。")

    def _fill_average_legacy(self, directory: Path) -> None:
        """Deprecated implementation retained temporarily for source-history comparison."""
        layout = self._matrix_layout()
        group = self._current_group
        if layout is None or group is None or self._matrix_copy_service.is_busy:
            return
        present, files = self._project.group_progress(directory, group)
        complete = [
            subgroup.index
            for subgroup in layout.subgroups
            if all(name in present for name in subgroup.names)
        ]
        targets = [subgroup.index for subgroup in layout.subgroups if subgroup.index not in complete]
        if not complete:
            QMessageBox.information(self, "无法平均补齐", "当前项目组还没有完整的三成员来源小组。")
            return
        if not targets:
            return
        mappings = layout.cyclic_sources(complete, targets)
        operations: list[RadioTargetOperation] = []
        imported_sources: set[str] = set()
        overwrite_paths: list[Path] = []
        cross_format: list[Path] = []
        mapping_lines: list[str] = []
        for target_index, source_index in mappings:
            source_group = layout.subgroups[source_index]
            target_group = layout.subgroups[target_index]
            source_paths = files.get(source_group.names[0], [])
            if not source_paths:
                QMessageBox.warning(
                    self,
                    "来源文件缺失",
                    f"完整来源小组的首个成员已不存在：{source_group.names[0]}",
                )
                return
            source_path = source_paths[0]
            source_key = os.path.normcase(os.path.abspath(os.fspath(source_path)))
            imported_sources.add(source_key)
            mapping_lines.append(
                f"第 {source_index + 1} 组（{source_path.name}） → 第 {target_index + 1} 组"
            )
            for target_name in target_group.names:
                existing = files.get(target_name, [])
                for path in existing:
                    if path.suffix.casefold() == source_path.suffix.casefold():
                        overwrite_paths.append(path)
                    else:
                        cross_format.append(path)
                target_path = directory / f"{target_name}{source_path.suffix}"
                operations.append(
                    RadioTargetOperation(
                        module=group.module,
                        group_id=group.group_key,
                        group_display_name=group.base_name,
                        source_original_path=source_path,
                        source_snapshot_key=source_key,
                        source_member_name=source_group.names[0],
                        target_member_name=target_name,
                        target_path=target_path,
                        copy_mode=ManualCopyMode.AVERAGE,
                        will_overwrite=target_path.exists(),
                        conflict_kind=(
                            RadioTargetConflictKind.EXTERNAL_CONFLICT
                            if target_path.exists()
                            else RadioTargetConflictKind.GENERATED_TARGET
                        ),
                    )
                )
        if cross_format:
            QMessageBox.warning(
                self,
                "存在不同格式的同名文件",
                "平均补齐不会删除或制造同名多格式。请先处理：\n"
                + "\n".join(str(path) for path in cross_format),
            )
            return
        confirmed_plan = RadioStagedCopyPlan(
            tuple(operations), imported_source_paths=frozenset(imported_sources)
        )
        displayed_conflicts = frozenset(confirmed_plan.current_external_conflicts())
        details = "来源到目标映射：\n" + "\n".join(mapping_lines)
        if overwrite_paths:
            details += "\n\n将覆盖：\n" + "\n".join(str(path) for path in overwrite_paths)
        answer = QMessageBox.question(
            self,
            "确认平均分配补齐",
            details + "\n\n是否开始？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        LOGGER.info(
            "Audio average fill confirmation: reply=%r type=%s mode=%s group=%s "
            "source_groups=%s target_groups=%s operations=%s snapshots=%s conflicts=%s",
            answer,
            type(answer).__name__,
            self._audio_copy_mode.value,
            group.group_key,
            len(complete),
            len(targets),
            confirmed_plan.total,
            len(imported_sources),
            len(displayed_conflicts),
        )
        if answer != QMessageBox.StandardButton.Yes:
            LOGGER.info("Audio average fill cancelled before worker creation: group=%s", group.group_key)
            return

        current_conflicts = frozenset(confirmed_plan.current_external_conflicts())
        new_conflicts = tuple(
            sorted(current_conflicts - displayed_conflicts, key=lambda path: str(path).casefold())
        )
        if new_conflicts:
            LOGGER.warning(
                "Audio average fill not started because targets changed during confirmation: "
                "group=%s files=%s",
                group.group_key,
                [str(path) for path in new_conflicts],
            )
            QMessageBox.warning(
                self,
                "目标文件状态已变化",
                "确认期间出现了新的目标文件，任务尚未启动。请检查后重新确认：\n"
                + "\n".join(str(path) for path in new_conflicts),
            )
            return

        policy = (
            ConflictPolicy.OVERWRITE_EXISTING
            if displayed_conflicts
            else ConflictPolicy.SKIP_EXISTING
        )
        try:
            started = self._matrix_copy_service.start_copy(confirmed_plan, policy)
        except Exception as error:
            LOGGER.exception(
                "Audio average fill worker could not start: group=%s operations=%s",
                group.group_key,
                confirmed_plan.total,
            )
            self.target_info.setText(f"平均分配补齐未能启动：{error}")
            self._sync()
            QMessageBox.critical(self, "无法启动复制任务", f"平均分配补齐未能启动：\n{error}")
            return
        if started:
            LOGGER.info(
                "Audio average fill worker started: group=%s operations=%s snapshots=%s",
                group.group_key,
                confirmed_plan.total,
                len(imported_sources),
            )
            self.copy_status.set_snapshot(
                TaskStatusSnapshot(total=confirmed_plan.total, message="正在暂存平均分配来源")
            )
            self._sync()
            return

        LOGGER.warning(
            "Audio average fill service rejected start: group=%s operations=%s busy=%s",
            group.group_key,
            confirmed_plan.total,
            self._matrix_copy_service.is_busy,
        )
        self.target_info.setText("平均分配补齐未启动：复制服务正忙，请稍后重试。")
        self._sync()
        QMessageBox.warning(self, "复制任务未启动", "复制服务正忙，请稍后重试。")

    def _can_fill_current_group(self) -> bool:
        return self._fill_available and not self.is_busy

    def _sync(self, *_args: object) -> None:
        busy = self.is_busy
        self.export_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        can_preview=(
            self._playback_state in (PlaybackState.READY,PlaybackState.STOPPED,PlaybackState.ERROR)
            and bool(self._timeline.items)
            and not busy
        )
        self.preview_button.setEnabled(can_preview)
        self.preview_button.setToolTip("\u8bf7\u5148\u5411\u97f3\u8f68\u4e2d\u5bfc\u5165\u97f3\u9891\u3002" if self._playback_state is PlaybackState.EMPTY else "")
        self.stop_button.setEnabled(self._playback_state in (PlaybackState.PREPARING,PlaybackState.PLAYING))
        location = self._timeline.locate(self.playhead_time_ms)
        can_split = (
            not busy
            and location is not None
            and location.kind is TimelineClipKind.AUDIO
            and location.offset_ms >= 1
            and self._timeline.items[location.index].duration_ms - location.offset_ms >= 1
        )
        self.split_button.setEnabled(can_split)
        self.split_button.setToolTip("" if can_split else "\u8bf7\u5148\u70b9\u51fb\u97f3\u9891\u7247\u6bb5\u4e2d\u7684\u88c1\u526a\u4f4d\u7f6e\u3002")
        self.back_button.setEnabled(self._navigation_enabled and not busy)
        self.fill_button.setEnabled(self._can_fill_current_group())
        self.audio_copy_mode_switch.setEnabled(not busy)
        self.target_menu_action.setEnabled(self._target_menu_has_items and not busy)
        if self._close_pending and not busy:
            self._close_pending = False
            self.close_ready.emit()
