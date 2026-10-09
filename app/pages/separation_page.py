# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""人声/背景音分离工作台：批量排队 + 多模型切换绑定 + 许可证明示。

音频素材（动漫片段/音乐素材均可）添加时绑定当前选中模型，一批队列可
混多个模型按各自绑定执行；推理走 MSST 子进程。模型权重不随仓库分发：
选中未就绪的模型后首次启动任务时自动下载；每个模型在界面上明示来源
与许可证。

页面含两个常驻模块（对齐 TTS 工作台的"训练模型/语音生成列表"双模块
形态，切换不丢状态）：
- 分离任务：素材 → 模型 → 批量分离；
- 切点候选：对分离产出的对白轨跑静音检测，产出"语音区段"候选清单，
  一键送入视频裁剪页挂为候选（对应 audioprep 契约 R2 的
  EnhancementCandidate → 候选确认决策流：候选只提议，应用仍由用户在
  裁剪页确认，与页面既有 autocut 候选同一纪律）。
"""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.audio.ffmpeg_service import FfmpegLocator
from app.audio.silence_service import SilenceDetectWorker
from app.i18n import i18n_text, tr
from app.pages.base_tool_page import BaseToolPage
from app.pages.video_clip_page import (
    _MERGE_GAP_MS,
    _MIN_SPEECH_MS,
    _SILENCE_DB,
    _SILENCE_MIN_MS,
)
from app.paths import config_dir
from app.services.separation_service import (
    MODEL_REGISTRY,
    ModelSpec,
    SeparationQueue,
    is_model_ready,
    model_by_key,
)
from app.services.video_clip_service import (
    CLIPS_ROOT,
    PURPOSE_FOLDERS,
    describe_clip_path,
)

#: 推理子进程的 Python：与 TTS 训练同一配置习惯，缺省走系统 python
_PYTHON_KEY = "separate/python_exec"
_MODEL_KEY = "separate/model"
#: 联动导出（视频裁剪页说话人素材目录）的持久化键
_SPEAKER_KEY = "separate/speaker"
_PURPOSE_KEY = "separate/purpose"

_CAND_AUDIO_EXT = (".wav", ".flac", ".mp3", ".ogg", ".m4a", ".opus")


def _speech_ranges(silences: list[tuple[int, int]],
                   duration_ms: int) -> list[tuple[int, int]]:
    """静音区间的补集即语音段：掐掉过短的，再把挨得近的合并成一句。

    与视频裁剪页 autocut 的既有口径一致（同组常量），保证两边候选语义
    相同：同样的门限喂进去，得到同样的切点。
    """
    ranges: list[list[int]] = []
    cursor = 0
    for start, end in sorted(silences):
        if start - cursor >= _MIN_SPEECH_MS:
            ranges.append([cursor, start])
        cursor = max(cursor, end)
    if duration_ms - cursor >= _MIN_SPEECH_MS:
        ranges.append([cursor, duration_ms])
    merged: list[list[int]] = []
    for start, end in ranges:
        if merged and start - merged[-1][1] < _MERGE_GAP_MS:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


class SeparationPage(BaseToolPage):
    """左侧导航独立页：素材 → 模型 → 批量分离 → 切点候选 → 裁剪页。"""

    close_ready = Signal()
    #: 队列事件（工作线程 → GUI 线程）：job_id
    _job_event = Signal(int)
    #: 切点候选就绪（源素材名, [(start_ms, end_ms), ...]）→ MainWindow 转交裁剪页
    candidates_ready = Signal(str, list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("separate", i18n_text("page.separate.title"), parent)
        self._titled: list[tuple[QLabel, str]] = []
        self._settings = QSettings()
        self._queue = SeparationQueue(
            output_root=config_dir() / "separations",
            python_exec=self._settings.value(_PYTHON_KEY, "", str) or "",
        )
        self._close_pending = False
        self._cand_running = False
        self._cand_worker = None
        self._cand_worker_cancel = None
        self._cand_metas: dict[str, int] = {}
        self._candidate_sets: list[tuple[str, list[tuple[int, int]]]] = []
        # 工作线程 → GUI 线程走页面信号（queued），回调里才触碰控件
        self._job_event.connect(self._on_job_event)
        self._queue.on_event = self._on_worker_event
        self._build_body()
        self._refresh_model_state()
        self._sync_buttons()

    # ---------------------------------------------------------------- signals

    def _on_worker_event(self, job) -> None:
        """工作线程回调：只投递 job_id，实际刷新在 GUI 线程。"""
        self._job_event.emit(job.job_id)

    @Slot(int)
    def _on_job_event(self, _job_id: int) -> None:
        self._refresh_queue_rows()
        self._sync_buttons()
        self._maybe_close_ready()

    # ---------------------------------------------------------------- UI

    def _build_body(self) -> None:
        host = QWidget()
        root = QVBoxLayout(host)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(8)
        self.tasks_module_button = QPushButton(
            i18n_text("separate.module.tasks"))
        self.tasks_module_button.setObjectName("moduleSwitchButton")
        self.tasks_module_button.setProperty("audioNavigation", True)
        self.tasks_module_button.setCheckable(True)
        self.candidate_module_button = QPushButton(
            i18n_text("separate.module.candidates"))
        self.candidate_module_button.setObjectName("moduleSwitchButton")
        self.candidate_module_button.setProperty("audioNavigation", True)
        self.candidate_module_button.setCheckable(True)
        self._module_group = QButtonGroup(self)
        self._module_group.setExclusive(True)
        self._module_group.addButton(self.tasks_module_button)
        self._module_group.addButton(self.candidate_module_button)
        self.tasks_module_button.setChecked(True)
        bar.addWidget(self.tasks_module_button)
        bar.addWidget(self.candidate_module_button)
        bar.addStretch(1)
        root.addLayout(bar)

        self._module_panes = QStackedWidget()
        self._module_panes.addWidget(self._build_tasks_pane())  # 0：分离任务
        self._module_panes.addWidget(self._build_candidates_pane())  # 1：切点候选
        root.addWidget(self._module_panes, 1)

        self.tasks_module_button.clicked.connect(lambda: self._show_module(0))
        self.candidate_module_button.clicked.connect(
            lambda: self._show_module(1))
        self.set_body_widget(host)
        self.setAcceptDrops(True)

    def _show_module(self, index: int) -> None:
        self._module_panes.setCurrentIndex(index)
        self.tasks_module_button.setChecked(index == 0)
        self.candidate_module_button.setChecked(index == 1)

    # ------------------------------------------------------ 模块一：分离任务

    def _build_tasks_pane(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        model_panel, model_layout = self._panel("separate.panel.model")
        self._model_combo = QListWidget()
        self._model_combo.setObjectName("separateModelList")
        self._model_combo.setUniformItemSizes(True)
        self._model_combo.setMaximumHeight(148)
        for spec in MODEL_REGISTRY:
            ready = "✓" if is_model_ready(spec) else "…"
            item = QListWidgetItem(
                tr("separate.model.item", title=spec.display_title(),
                   license=spec.license, ready=ready))
            item.setData(Qt.ItemDataRole.UserRole, spec.key)
            item.setToolTip(f"{spec.display_note()}\n"
                            f"{spec.source} ({spec.license})")
            self._model_combo.addItem(item)
        self._model_combo.setCurrentRow(self._current_model_row())
        self._model_combo.currentRowChanged.connect(self._on_model_changed)
        model_layout.addWidget(self._model_combo)
        self._model_hint = QLabel("")
        self._model_hint.setObjectName("mutedLabel")
        self._model_hint.setWordWrap(True)
        model_layout.addWidget(self._model_hint)

        # 联动视频裁剪页：选中说话人后，分离出的人声/对白轨以「原名-vocal」
        # 自动复制进该说话人的素材目录（裁剪页导出/训练同源，双向打通）
        link_row = QHBoxLayout()
        link_row.setSpacing(6)
        self._speaker_label = QLabel(i18n_text("separate.speaker"))
        self._speaker_label.setObjectName("mutedLabel")
        self._titled.append((self._speaker_label, "separate.speaker"))
        link_row.addWidget(self._speaker_label)
        self._speaker_combo = QComboBox()
        self._speaker_combo.setToolTip(i18n_text("separate.speaker.tip"))
        self._speaker_combo.currentIndexChanged.connect(
            self._on_speaker_changed)
        link_row.addWidget(self._speaker_combo, 1)
        self._purpose_combo = QComboBox()
        for purpose in PURPOSE_FOLDERS:
            self._purpose_combo.addItem(purpose, purpose)
        self._purpose_combo.setToolTip(i18n_text("separate.speaker.tip"))
        self._purpose_combo.currentIndexChanged.connect(
            self._on_purpose_changed)
        self._restore_purpose()
        link_row.addWidget(self._purpose_combo)
        model_layout.addLayout(link_row)
        self._refresh_speakers()
        layout.addWidget(model_panel)

        queue_panel, queue_layout = self._panel("separate.panel.queue")
        self._file_list = QListWidget()
        self._file_list.setObjectName("separateQueueList")
        self._file_list.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection)
        queue_layout.addWidget(self._file_list, 1)

        buttons = QHBoxLayout()
        self._add_button = QPushButton(i18n_text("separate.add"))
        self._add_button.clicked.connect(self._add_files_dialog)
        buttons.addWidget(self._add_button)
        self._add_folder_button = QPushButton(
            i18n_text("separate.add.folder"))
        self._add_folder_button.setToolTip(
            i18n_text("separate.add.folder.tip"))
        self._add_folder_button.clicked.connect(self._add_folder_dialog)
        buttons.addWidget(self._add_folder_button)
        self._start_button = QPushButton(i18n_text("separate.start"))
        self._start_button.clicked.connect(self._start_queue)
        buttons.addWidget(self._start_button)
        self._cancel_button = QPushButton(i18n_text("separate.cancel"))
        self._cancel_button.clicked.connect(self._cancel_pending)
        buttons.addWidget(self._cancel_button)
        self._remove_button = QPushButton(i18n_text("separate.remove"))
        self._remove_button.clicked.connect(self._remove_selected)
        buttons.addWidget(self._remove_button)
        buttons.addStretch(1)
        self._tta_check = QCheckBox(i18n_text("separate.tta"))
        self._tta_check.setToolTip(i18n_text("separate.tta.tip"))
        buttons.addWidget(self._tta_check)
        queue_layout.addLayout(buttons)

        self._progress = QProgressBar()
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        queue_layout.addWidget(self._progress)
        self._status = QLabel("")
        self._status.setObjectName("mutedLabel")
        self._status.setWordWrap(True)
        queue_layout.addWidget(self._status)
        layout.addWidget(queue_panel, 1)
        return body

    def _panel(self, title_key: str) -> tuple[QWidget, QVBoxLayout]:
        panel = QWidget()
        panel.setObjectName("placeholderPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        title = QLabel(i18n_text(title_key))
        title.setObjectName("crewPanelTitle")
        self._titled.append((title, title_key))
        layout.addWidget(title)
        return panel, layout

    # ------------------------------------------------------ 模块二：切点候选

    def _build_candidates_pane(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        source_panel, source_layout = self._panel("separate.panel.candidates")
        self._cand_list = QListWidget()
        self._cand_list.setObjectName("separateCandidateList")
        self._cand_list.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection)
        source_layout.addWidget(self._cand_list, 1)

        cand_buttons = QHBoxLayout()
        self._cand_scan_button = QPushButton(i18n_text("separate.cand.scan"))
        self._cand_scan_button.clicked.connect(self._scan_separation_outputs)
        cand_buttons.addWidget(self._cand_scan_button)
        self._cand_add_button = QPushButton(i18n_text("separate.cand.add"))
        self._cand_add_button.clicked.connect(self._cand_add_dialog)
        cand_buttons.addWidget(self._cand_add_button)
        self._cand_remove_button = QPushButton(
            i18n_text("separate.cand.remove"))
        self._cand_remove_button.clicked.connect(self._cand_remove_selected)
        cand_buttons.addWidget(self._cand_remove_button)
        self._cand_generate_button = QPushButton(
            i18n_text("separate.cand.generate"))
        self._cand_generate_button.clicked.connect(self._generate_candidates)
        cand_buttons.addWidget(self._cand_generate_button)
        self._cand_send_button = QPushButton(i18n_text("separate.cand.send"))
        self._cand_send_button.setEnabled(False)
        self._cand_send_button.clicked.connect(self._send_candidates)
        cand_buttons.addWidget(self._cand_send_button)
        cand_buttons.addStretch(1)
        source_layout.addLayout(cand_buttons)

        self._cand_status = QLabel(i18n_text("separate.cand.hint"))
        self._cand_status.setObjectName("mutedLabel")
        self._cand_status.setWordWrap(True)
        source_layout.addWidget(self._cand_status)
        layout.addWidget(source_panel, 1)
        return body

    def _cand_add_row(self, path: Path, stem: str) -> bool:
        existing = {self._cand_list.item(row).data(Qt.ItemDataRole.UserRole)
                    for row in range(self._cand_list.count())}
        if str(path) in existing:
            return False
        item = QListWidgetItem(f"{stem}  ·  {path.name}")
        item.setData(Qt.ItemDataRole.UserRole, str(path))
        item.setData(Qt.ItemDataRole.UserRole + 1, stem)
        self._cand_list.addItem(item)
        return True

    def _scan_separation_outputs(self) -> None:
        """扫描分离产出目录：每个素材子目录取对白轨（无则第一个音轨）。"""
        root = config_dir() / "separations"
        found = 0
        if root.is_dir():
            for model_dir in sorted(root.iterdir()):
                if not model_dir.is_dir() or model_dir.name == "_staging":
                    continue
                for stem_dir in sorted(model_dir.iterdir()):
                    if not stem_dir.is_dir():
                        continue
                    pick = self._pick_dialogue_stem(stem_dir)
                    if pick is not None and self._cand_add_row(
                            pick, stem_dir.name):
                        found += 1
        self._cand_status.setText(
            tr("separate.cand.scanned", n=found) if found
            else i18n_text("separate.cand.scan_none"))

    @staticmethod
    def _pick_dialogue_stem(stem_dir: Path) -> Path | None:
        preferred = [p for p in sorted(stem_dir.iterdir())
                     if p.name.lower() in ("dialogue.wav", "dialogue.flac")]
        if preferred:
            return preferred[0]
        for p in sorted(stem_dir.iterdir()):
            if p.suffix.lower() in _CAND_AUDIO_EXT:
                return p
        return None

    def _cand_add_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, i18n_text("separate.cand.add"), "",
            "Audio (*.wav *.flac *.mp3 *.ogg *.m4a *.opus)")
        added = 0
        for file in files:
            path = Path(file)
            if self._cand_add_row(path, path.stem):
                added += 1
        if added:
            self._cand_status.setText(
                tr("separate.cand.scanned", n=added))

    def _cand_remove_selected(self) -> None:
        for item in self._cand_list.selectedItems():
            self._cand_list.takeItem(self._cand_list.row(item))

    def _cand_selected_rows(self) -> list[int]:
        rows = sorted(self._cand_list.row(item)
                      for item in self._cand_list.selectedItems())
        return rows or list(range(self._cand_list.count()))

    def _generate_candidates(self) -> None:
        """对选中（未选则全部）对白轨后台跑 silencedetect，产出语音区段候选。"""
        if self._cand_running:
            return
        metas: list[tuple[str, Path, int]] = []
        for row in self._cand_selected_rows():
            item = self._cand_list.item(row)
            path = Path(item.data(Qt.ItemDataRole.UserRole))
            stem = item.data(Qt.ItemDataRole.UserRole + 1)
            try:
                duration = FfmpegLocator.probe_duration_ms(path)
            except (OSError, RuntimeError) as exc:
                self._cand_status.setText(
                    tr("separate.cand.probe_fail", name=path.name,
                       detail=str(exc)[-160:]))
                return
            if duration <= 0:
                continue
            metas.append((stem, path, duration))
        if not metas:
            self._cand_status.setText(i18n_text("separate.cand.none"))
            return
        self._cand_worker_cancel = threading.Event()
        worker = SilenceDetectWorker(
            tuple((stem, 0, path, 0, duration)
                  for stem, path, duration in metas),
            _SILENCE_DB, _SILENCE_MIN_MS, self._cand_worker_cancel)
        worker.finished.connect(self._on_candidates_detected)
        self._cand_worker = worker
        self._cand_metas = {stem: duration for stem, _, duration in metas}
        self._cand_running = True
        self._cand_generate_button.setEnabled(False)
        self._cand_status.setText(i18n_text("separate.cand.running"))
        threading.Thread(target=worker.run,
                         name="separate-candidate", daemon=True).start()

    @Slot(object, str)
    def _on_candidates_detected(self, results: object, error: str) -> None:
        self._cand_running = False
        self._cand_generate_button.setEnabled(True)
        if error:
            self._cand_status.setText(
                tr("separate.cand.fail", detail=error[-200:]))
            return
        grouped: dict[str, list[tuple[int, int]]] = {}
        for item in results or []:
            grouped.setdefault(str(item["clip_id"]), []).append(
                (int(item["start_ms"]), int(item["end_ms"])))
        self._candidate_sets = []
        total = 0
        for stem, duration in self._cand_metas.items():
            ranges = _speech_ranges(grouped.get(stem, []), duration)
            if ranges:
                self._candidate_sets.append((stem, ranges))
                total += len(ranges)
        if not self._candidate_sets:
            self._cand_status.setText(i18n_text("separate.cand.no_speech"))
            return
        self._cand_send_button.setEnabled(True)
        self._cand_status.setText(
            tr("separate.cand.ready", sources=len(self._candidate_sets),
               total=total))

    def _send_candidates(self) -> None:
        """把候选语音区段发往视频裁剪页（同名素材已加载时才可挂载）。

        源列表选中几条就发几条，未选则全部发送；裁剪页同时只有一个当前
        素材，MainWindow 侧只会有同名的那条真正挂载，其余回报无匹配。
        """
        if not self._candidate_sets:
            return
        selected_stems = {
            self._cand_list.item(row).data(Qt.ItemDataRole.UserRole + 1)
            for row in self._cand_selected_rows()
            if row < self._cand_list.count()}
        targets = [(stem, ranges) for stem, ranges in self._candidate_sets
                   if not selected_stems or stem in selected_stems]
        if not targets:
            self._cand_status.setText(i18n_text("separate.cand.none"))
            return
        for stem, ranges in targets:
            self.candidates_ready.emit(stem, ranges)
        self._cand_status.setText(tr("separate.cand.sent", n=len(targets)))

    def notify_candidates_applied(self, stem: str, applied: bool) -> None:
        """MainWindow 转交结果回执：挂载成功/视频页无同名素材。"""
        if applied:
            self._cand_status.setText(
                tr("separate.cand.applied", stem=stem))
        else:
            self._cand_status.setText(
                tr("separate.cand.no_match", stem=stem))

    # ---------------------------------------------------------------- model

    def _current_spec(self) -> ModelSpec | None:
        item = self._model_combo.currentItem()
        if item is None:
            return None
        return model_by_key(item.data(Qt.ItemDataRole.UserRole))

    def _current_model_row(self) -> int:
        saved = self._settings.value(_MODEL_KEY, MODEL_REGISTRY[0].key, str)
        for row, spec in enumerate(MODEL_REGISTRY):
            if spec.key == saved:
                return row
        return 0

    def _on_model_changed(self, row: int) -> None:
        if 0 <= row < len(MODEL_REGISTRY):
            self._settings.setValue(_MODEL_KEY, MODEL_REGISTRY[row].key)
        self._refresh_model_state()
        self._sync_buttons()

    def _refresh_model_state(self) -> None:
        spec = self._current_spec()
        if spec is None:
            self._model_hint.setText("")
            return
        ready = is_model_ready(spec)
        state = i18n_text("separate.model.ready" if ready
                          else "separate.model.need_download")
        self._model_hint.setText(
            tr("separate.model.hint", state=state, license=spec.license,
               source=spec.source))

    # ---------------------------------------------------------------- queue

    # ------------------------------------------------ 联动：说话人素材目录

    def _scan_speakers(self) -> list[str]:
        """只读扫描视频裁剪页的说话人目录（不建目录、不补用途子目录）。

        list_speaker_folders() 会顺带 mkdir：从分离页路过一下就凭空造出
        素材库结构不合适——目录是否存在由裁剪页负责。
        """
        if not CLIPS_ROOT.is_dir():
            return []
        try:
            names = [p.name for p in CLIPS_ROOT.iterdir() if p.is_dir()]
        except OSError:
            return []
        return sorted(names, key=str.casefold)

    def _refresh_speakers(self) -> None:
        """重建说话人下拉：保留当前选择，恢复持久化的上次选择。"""
        current = self._speaker_combo.currentData()
        if current is None:
            current = self._settings.value(_SPEAKER_KEY, "", str) or ""
        self._speaker_combo.blockSignals(True)
        self._speaker_combo.clear()
        self._speaker_combo.addItem(i18n_text("separate.speaker.none"), None)
        for name in self._scan_speakers():
            self._speaker_combo.addItem(name, name)
        index = self._speaker_combo.findData(current or None)
        self._speaker_combo.setCurrentIndex(max(0, index))
        self._speaker_combo.blockSignals(False)
        self._restore_purpose()

    def _restore_purpose(self) -> None:
        saved = self._settings.value(_PURPOSE_KEY, "", str)
        if saved:
            index = self._purpose_combo.findData(saved)
            if index >= 0:
                self._purpose_combo.setCurrentIndex(index)

    def _on_speaker_changed(self, _index: int) -> None:
        name = self._speaker_combo.currentData()
        # "不联动"也要落盘：否则重启又会恢复到上次的说话人
        self._settings.setValue(_SPEAKER_KEY, name or "")
        if name:
            self._restore_purpose()

    def _on_purpose_changed(self, _index: int) -> None:
        purpose = self._purpose_combo.currentData()
        if purpose:
            self._settings.setValue(_PURPOSE_KEY, purpose)

    def _selected_export_dir(self) -> Path | None:
        """当前联动目标：说话人/用途都没选（不联动）时返回 None。"""
        name = self._speaker_combo.currentData()
        if not name:
            return None
        purpose = self._purpose_combo.currentData() or PURPOSE_FOLDERS[0]
        return CLIPS_ROOT / name / purpose

    def showEvent(self, event) -> None:
        # 说话人可能在视频裁剪页增删：每次亮起这页都重扫一遍
        super().showEvent(event)
        self._refresh_speakers()

    def _add_folder_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, i18n_text("separate.add.folder"))
        if not folder:
            return
        root = Path(folder)
        try:
            entries = sorted(p for p in root.iterdir() if p.is_file())
        except OSError as exc:
            self._status.setText(
                tr("separate.folder.fail", detail=str(exc)[-160:]))
            return
        self._add_paths(entries)

    def _add_paths(self, paths: list[Path]) -> None:
        spec = self._current_spec()
        if spec is None:
            return
        existing = {(item.data(Qt.ItemDataRole.UserRole + 1),
                     item.data(Qt.ItemDataRole.UserRole))
                    for row in range(self._file_list.count())
                    for item in [self._file_list.item(row)]}
        audio = [p for p in paths if p.suffix.lower() in
                 (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".opus")]
        for path in audio:
            # 同文件同模型重复添加会重复推理并互相覆盖产出
            if (str(path), spec.key) in existing:
                continue
            existing.add((str(path), spec.key))
            item = QListWidgetItem(f"{path.name}  ·  {spec.display_title()}")
            # 模型在添加时刻绑定到条目：切换选中只影响之后新加的文件，
            # 一批队列可混多个模型按各自绑定执行
            item.setData(Qt.ItemDataRole.UserRole, spec.key)
            item.setData(Qt.ItemDataRole.UserRole + 1, str(path))
            item.setToolTip(f"{spec.display_note()}\n"
                            f"{spec.source} ({spec.license})")
            self._file_list.addItem(item)

    def _remove_selected(self) -> None:
        for item in self._file_list.selectedItems():
            self._file_list.takeItem(self._file_list.row(item))

    def _add_files_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, i18n_text("separate.add"), "",
            "Audio (*.wav *.mp3 *.flac *.ogg *.m4a *.opus)")
        self._add_paths([Path(f) for f in files])

    def _start_queue(self) -> None:
        if self._file_list.count() == 0:
            return
        # 按条目各自绑定的模型分组入队：一次批量可混多个模型，保持顺序
        groups: dict[str, list[Path]] = {}
        for row in range(self._file_list.count()):
            item = self._file_list.item(row)
            key = item.data(Qt.ItemDataRole.UserRole)
            if model_by_key(key) is None:
                continue
            groups.setdefault(key, []).append(
                Path(item.data(Qt.ItemDataRole.UserRole + 1)))
        self._file_list.clear()
        self._queue.use_tta = self._tta_check.isChecked()
        # 联动导出按入队时刻的选择定格：跑批途中改下拉不影响这一轮
        self._queue.export_dir = self._selected_export_dir()
        self._queue.exported = []
        for key, paths in groups.items():
            self._queue.enqueue(paths, model_by_key(key))
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._sync_buttons()

    def _cancel_pending(self) -> None:
        dropped = self._queue.cancel_pending()
        for row in range(self._file_list.count() - 1, -1, -1):
            self._file_list.takeItem(row)
        if dropped or not self._queue.is_busy():
            self._progress.setVisible(False)
        self._status.setText(tr("separate.cancelled", n=dropped))
        self._sync_buttons()
        self._maybe_close_ready()

    def _refresh_queue_rows(self) -> None:
        done = sum(1 for job in self._queue.jobs if job.status == "done")
        failed = sum(1 for job in self._queue.jobs if job.status == "failed")
        total = len(self._queue.jobs)
        self._status.setText(tr(
            "separate.status", done=done, failed=failed, total=total))
        if self._queue.is_busy():
            return
        self._progress.setRange(0, 1)
        self._progress.setValue(1)
        self._progress.setVisible(False)
        exported = self._queue.exported
        if exported:
            self._status.setText(
                self._status.text() + "\n"
                + tr("separate.export.done", n=len(exported),
                     path=describe_clip_path(exported[-1].parent)))
        last = self._queue.jobs[-1] if self._queue.jobs else None
        if last is not None and last.status == "failed":
            self._status.setText(self._status.text() + "\n" + last.detail)

    # ---------------------------------------------------------------- state

    def _sync_buttons(self) -> None:
        busy = self.is_busy
        spec = self._current_spec()
        self._add_button.setEnabled(bool(spec))
        self._start_button.setEnabled(
            self._file_list.count() > 0 and not busy)
        self._cancel_button.setEnabled(busy or self._file_list.count() > 0)
        self._remove_button.setEnabled(
            self._file_list.count() > 0 and not busy)

    @property
    def is_busy(self) -> bool:
        return self._queue.is_busy()

    def can_navigate_away(self) -> bool:
        if self.is_busy:
            self._close_pending = True
            return False
        return True

    def request_safe_close(self) -> bool:
        return self.can_navigate_away()

    def _maybe_close_ready(self) -> None:
        if self._close_pending and not self.is_busy:
            self._close_pending = False
            self.close_ready.emit()

    # ---------------------------------------------------------------- dnd

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()
                 if url.toLocalFile()]
        self._add_paths(paths)
        event.acceptProposedAction()

    # ---------------------------------------------------------------- i18n

    def retranslate(self) -> None:
        super().retranslate()
        for label, key in self._titled:
            label.setText(i18n_text(key))
        self.tasks_module_button.setText(i18n_text("separate.module.tasks"))
        self.candidate_module_button.setText(
            i18n_text("separate.module.candidates"))
        for row, spec in enumerate(MODEL_REGISTRY):
            if row >= self._model_combo.count():
                break
            ready = "✓" if is_model_ready(spec) else "…"
            self._model_combo.item(row).setText(
                tr("separate.model.item", title=spec.display_title(),
                   license=spec.license, ready=ready))
        self._add_button.setText(i18n_text("separate.add"))
        self._add_folder_button.setText(i18n_text("separate.add.folder"))
        self._add_folder_button.setToolTip(
            i18n_text("separate.add.folder.tip"))
        self._start_button.setText(i18n_text("separate.start"))
        self._cancel_button.setText(i18n_text("separate.cancel"))
        self._remove_button.setText(i18n_text("separate.remove"))
        self._tta_check.setText(i18n_text("separate.tta"))
        self._tta_check.setToolTip(i18n_text("separate.tta.tip"))
        self._cand_scan_button.setText(i18n_text("separate.cand.scan"))
        self._cand_add_button.setText(i18n_text("separate.cand.add"))
        self._cand_remove_button.setText(i18n_text("separate.cand.remove"))
        self._cand_generate_button.setText(
            i18n_text("separate.cand.generate"))
        self._cand_send_button.setText(i18n_text("separate.cand.send"))
        self._refresh_speakers()
        self._refresh_model_state()
        self._refresh_queue_rows()
