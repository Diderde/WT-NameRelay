# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""三级页：TTS 批量生成工作台（W3）。

- 行身份与状态语义见 docs/voice-batch-spec.md（row_id 永久；JobState × ArtifactState 双轴）；
- 生成走 ``SerialTtsRunner``（串行、子进程/HTTP 后端），在工作线程执行，
  结果经线程安全队列回主线程刷新（避免跨线程直接改 UI）；
- 试听复用 QMediaPlayer（同音频处理页用法）。
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.i18n import i18n_text, tr
from app.models.voice_table import (
    HASH_BACKEND,
    ArtifactState,
    JobState,
    VoiceRow,
    VoiceTable,
)
from app.services import vt_key_store, vt_manifest, vt_project
from app.services.save_coordinator import SaveCoordinator
from app.services.tts_runner import (
    SerialTtsRunner,
    TtsBackend,
    TtsError,
    TtsRequest,
    TtsResult,
)
from app.services.voice_filename_validator import VoiceFilenameValidator
from app.services.vt_trust_store import TrustDecision, TrustStore
from app.widgets.cosyvoice_info_panel import CosyVoiceInfoPanel
from app.widgets.flow_layout import FlowLayout
from app.widgets.tts_params_panel import BACKEND_COSY, BACKEND_GPT, TtsParamsPanel
from app.widgets.tts_train_panel import TtsTrainPanel
from app.widgets.voice_table_model import VoiceColumn, VoiceRowDelegate, VoiceTableModel
from app.widgets.vt_key_dialog import VtKeyDialog

from .base_tool_page import BaseToolPage


def _key_store_dir() -> Path:
    """签名密钥的存放目录（项目内 `config/`，已 gitignore；测试可整体替换）。"""

    from app.paths import config_dir

    return config_dir()


class VoiceBatchPage(BaseToolPage):
    """语音批量生成工作台：表格编辑 + 串行生成 + 试听 + 状态徽章。"""

    close_ready = Signal()

    def __init__(self, backend: TtsBackend, parent: QWidget | None = None) -> None:
        super().__init__("voice_batch", tr("page.voice_batch.title"), parent)
        # 两栏布局高度紧张：通用状态面板本页不使用（进度在左栏阶段区与右侧汇总行），隐藏让位
        self.status_panel.setVisible(False)
        self._validator = VoiceFilenameValidator()
        self._runner = SerialTtsRunner(backend)
        self._model = VoiceTableModel(VoiceTable())
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        #: 权重热切换的工作线程（阻塞 HTTP，不能在 GUI 线程做）
        self._weights_worker: threading.Thread | None = None
        self._preview_path: Path | None = None
        #: 当前工程文件（`None` = 尚未打开，使用项目内默认路径；打开后自动保存写回该文件）
        self._project_file: Path | None = None
        #: 最近打开的工程文件（可能是已签名的只读文件；解锁动作以它为目标）
        self._project_view: Path | None = None
        #: 后端装配中（由路由侧的工作线程完成；期间禁用生成并提示"正在连接"）
        self._backend_pending = False
        #: 两栏标题（按 i18n key 索引，供 retranslate 更新）
        self._pane_titles: dict[str, QLabel] = {}

        self.set_body_widget(self._build_body())
        self._coordinator = SaveCoordinator(self._project_path, self._model.table, parent=self)
        self._model.rows_changed.connect(self._coordinator.mark_dirty)
        self._model.row_edited.connect(lambda _row_id: self._coordinator.mark_dirty())
        self.delegate.commitData.connect(lambda _editor: self._coordinator.flush())
        self._coordinator.failed.connect(self._on_save_failed)
        self.train_panel.weights_discovered.connect(self._on_weights_discovered)
        self._save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self._save_shortcut.activated.connect(self._coordinator.flush)
        self._load_existing_project()
        self._pump = QTimer(self)
        self._pump.setInterval(120)
        self._pump.timeout.connect(self._drain_events)
        self._pump.start()
        self.retranslate()

    # —— 契约 ——
    @property
    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def can_navigate_away(self) -> bool:
        return not self.is_busy and not self.train_panel.is_running

    def request_safe_close(self) -> bool:
        if not self.is_busy and not self.train_panel.is_running:
            return True
        self._stop_generation()
        self.train_panel.runner.stop()
        return False

    def set_navigation_enabled(self, enabled: bool) -> None:
        self.back_button.setEnabled(enabled and not self.is_busy)

    def table_model(self) -> VoiceTableModel:
        return self._model

    # —— 构建 ——
    def _build_body(self) -> QWidget:
        """左右两栏：左「微调」（上游 GPT-SoVITS 链路），右「推理」（原有工作台能力）。"""

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("voiceWorkbenchSplit")
        left_pane = self._build_train_pane()
        left_pane.setMinimumWidth(380)
        cosy_pane = self._build_cosy_pane()
        cosy_pane.setMinimumWidth(380)
        right_pane = self._build_inference_pane()
        right_pane.setMinimumWidth(400)
        # 左栏随所选模型切换：GPT-SoVITS=微调面板 / CosyVoice 3=模型信息面板
        self._model_panes = QStackedWidget()
        self._model_panes.addWidget(left_pane)
        self._model_panes.addWidget(cosy_pane)
        splitter.addWidget(self._model_panes)
        splitter.addWidget(right_pane)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([560, 560])
        return splitter

    def _pane(self, title_key: str, body: QWidget) -> QFrame:
        """带标题的分栏容器。"""

        frame = QFrame()
        frame.setObjectName("voicePane")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        pane_title = QLabel(i18n_text(title_key))
        pane_title.setObjectName("crewPanelTitle")
        self._pane_titles[title_key] = pane_title
        layout.addWidget(pane_title)
        layout.addWidget(body, 1)
        return frame

    def _build_train_pane(self) -> QFrame:
        self.train_panel = TtsTrainPanel()
        return self._pane("voice.pane.train", self.train_panel)

    def _build_cosy_pane(self) -> QFrame:
        self.cosy_panel = CosyVoiceInfoPanel()
        return self._pane("voice.pane.model", self.cosy_panel)

    # —— 模型感知 ——
    MODEL_GPT = "tts_gpt_sovits"
    MODEL_COSY = "tts_cosyvoice"

    def set_model_kind(self, model_key: str) -> None:
        """按模型选择页的卡片键切换左栏（进入工作台时与装配后端时调用）。"""

        self._model_panes.setCurrentIndex(1 if model_key == self.MODEL_COSY else 0)
        self.cosy_panel.refresh_status()

    def _build_inference_pane(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("crewManualPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 14, 15, 14)
        layout.setSpacing(10)

        title = QLabel(i18n_text("voice.table.title"))
        title.setObjectName("crewPanelTitle")
        layout.addWidget(title)

        hint = QLabel(i18n_text("voice.table.hint"))
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 主要操作：单行流式布局；低频操作收进「更多」下拉，避免按钮行堆叠挤压布局
        edit_bar = FlowLayout(spacing=10)
        self.add_button = QPushButton(i18n_text("voice.action.add"))
        self.generate_button = QPushButton(i18n_text("voice.action.generate_selected"))
        self.regenerate_all_button = QPushButton(i18n_text("voice.action.generate_stale"))
        self.stop_button = QPushButton(i18n_text("voice.action.stop"))
        self.stop_button.setEnabled(False)
        for widget in (self.add_button, self.generate_button, self.regenerate_all_button, self.stop_button):
            edit_bar.addWidget(widget)
        layout.addLayout(edit_bar)

        # 「更多」下拉：行操作与工程/签名（`.vt` 容器 / 密钥 / 信任校验 / 整包清单）
        self.more_button = QPushButton(i18n_text("voice.action.more"))
        more_menu = QMenu(self.more_button)
        self.more_button.setMenu(more_menu)
        self._more_actions: list[tuple[QAction, str]] = []

        def add_more_action(key: str, slot: Callable[[], None]) -> QAction:
            action = QAction(i18n_text(key), self.more_button)
            action.triggered.connect(slot)
            more_menu.addAction(action)
            self._more_actions.append((action, key))
            return action

        self.duplicate_action = add_more_action("voice.action.duplicate", self._duplicate_selected)
        self.remove_action = add_more_action("voice.action.remove", self._remove_selected)
        more_menu.addSeparator()
        self.open_action = add_more_action("voice.action.open_project", self._open_project_clicked)
        self.unlock_action = add_more_action("voice.action.unlock_project", self._unlock_project_clicked)
        self.unlock_action.setEnabled(False)
        self.export_button = add_more_action("voice.action.export_vt", self._export_vt_clicked)
        self.sign_export_button = add_more_action("voice.action.export_vt_signed", self._sign_export_clicked)
        self.verify_vt_action = add_more_action("voice.action.verify_vt", self._verify_vt_clicked)
        self.export_manifest_action = add_more_action("voice.action.export_manifest", self._export_manifest_clicked)
        self.verify_package_action = add_more_action("voice.action.verify_package", self._verify_package_clicked)
        self.keys_button = add_more_action("voice.action.keys", self._keys_clicked)
        self._crypto_actions = (
            self.export_button,
            self.sign_export_button,
            self.verify_vt_action,
            self.export_manifest_action,
            self.verify_package_action,
            self.keys_button,
        )
        for action in self._crypto_actions:
            action.setEnabled(HASH_BACKEND == "vtcore")
            if HASH_BACKEND != "vtcore":
                action.setToolTip(i18n_text("voice.export.unavailable"))
        layout.addWidget(self.more_button)

        # 模型权重：微调完成后自动回填路径；运行时热切换（api_v2 权重端点，仅 GPT-SoVITS）
        self.weights_holder = QWidget()
        weights_row = FlowLayout(self.weights_holder, spacing=8)
        self.gpt_weights_input = QLineEdit()
        self.gpt_weights_input.setPlaceholderText(i18n_text("voice.weights.gpt_hint"))
        self.sovits_weights_input = QLineEdit()
        self.sovits_weights_input.setPlaceholderText(i18n_text("voice.weights.sovits_hint"))
        self.apply_weights_button = QPushButton(i18n_text("voice.weights.apply"))
        self.apply_weights_button.clicked.connect(self._apply_weights_clicked)
        weights_row.addWidget(self.apply_weights_button)
        weights_row.addWidget(self.gpt_weights_input)
        weights_row.addWidget(self.sovits_weights_input)
        layout.addWidget(self.weights_holder)
        self.weights_holder.setVisible(False)

        # 推理参数：默认折叠（8 行表单会把主表格压垮），展开后限高滚动；随合成请求下发给后端
        self.params_toggle = QToolButton()
        self.params_toggle.setObjectName("voiceParamsToggle")
        self.params_toggle.setCheckable(True)
        self.params_toggle.setChecked(False)
        self._update_params_toggle_text()
        self.params_toggle.clicked.connect(self._on_params_toggled)
        layout.addWidget(self.params_toggle)

        self.params_panel = TtsParamsPanel()
        self.params_scroll = QScrollArea()
        self.params_scroll.setObjectName("voiceParamsScroll")
        self.params_scroll.setWidgetResizable(True)
        self.params_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.params_scroll.setWidget(self.params_panel)
        self.params_scroll.setMaximumHeight(230)
        self.params_scroll.setVisible(False)
        layout.addWidget(self.params_scroll)

        self.table = QTableView()
        self.table.setObjectName("voiceTable")
        self.table.setModel(self._model)
        self.delegate = VoiceRowDelegate(self.table)
        self.table.setItemDelegate(self.delegate)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(int(VoiceColumn.STATUS), QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(int(VoiceColumn.NAME), QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(int(VoiceColumn.TEXT), QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(int(VoiceColumn.VOICE), QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(int(VoiceColumn.DURATION), QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(int(VoiceColumn.ACTIONS), QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(int(VoiceColumn.NAME), 160)
        self.table.setColumnWidth(int(VoiceColumn.VOICE), 150)
        self.table.setColumnWidth(int(VoiceColumn.ACTIONS), 150)
        self.table.setMinimumHeight(180)
        layout.addWidget(self.table, 1)

        self.summary_label = QLabel()
        self.summary_label.setObjectName("mutedLabel")
        layout.addWidget(self.summary_label)

        # 锁状态徽章：只有当前导出/打开的是已签名（只读锁定）的 `.vt` 时才显示内容
        self.lock_label = QLabel()
        self.lock_label.setObjectName("mutedLabel")
        self.lock_label.setWordWrap(True)
        layout.addWidget(self.lock_label)

        self._player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_out)

        self.add_button.clicked.connect(lambda: self._add_row())
        self.generate_button.clicked.connect(lambda: self._start_generation(self._selected_row_ids()))
        self.regenerate_all_button.clicked.connect(self._start_regeneration_for_stale)
        self.stop_button.clicked.connect(self._stop_generation)
        self.delegate.preview_requested.connect(self._preview)
        self.delegate.regenerate_requested.connect(lambda row_id: self._start_generation([row_id]))
        self._model.rows_changed.connect(self._update_summary)
        self._model.row_edited.connect(lambda _row_id: self._update_summary())
        return panel

    # —— 行操作 ——
    def _add_row(self) -> None:
        row = self._model.add_row(name="", text="", voice="")
        self._update_summary()
        index = self._model.index(self._model.index_of(row.row_id), int(VoiceColumn.NAME))
        self.table.setCurrentIndex(index)
        self.table.edit(index)

    def _selected_row_id(self) -> str:
        index = self.table.currentIndex()
        return self._model.row_id_at(index.row()) if index.isValid() else ""

    def _selected_row_ids(self) -> list[str]:
        row_id = self._selected_row_id()
        if row_id:
            return [row_id]
        return [row.row_id for row in self._model.rows()]

    def _duplicate_selected(self) -> None:
        row_id = self._selected_row_id()
        if not row_id:
            return
        clone = self._model.duplicate_row(row_id)
        if clone is not None:
            self._update_summary()

    def _remove_selected(self) -> None:
        row_id = self._selected_row_id()
        if row_id:
            self._model.remove_row(row_id)
            self._update_summary()

    # —— 生成 ——
    def _start_regeneration_for_stale(self) -> None:
        stale = [row.row_id for row in self._model.rows() if row.needs_regeneration or row.artifact is ArtifactState.MISSING]
        if stale:
            self._start_generation(stale)

    def _start_generation(self, row_ids: Sequence[str]) -> None:
        if self.is_busy or not row_ids:
            return
        requests: list[TtsRequest] = []
        for row_id in row_ids:
            row = self._model.table().row(row_id)
            if row is None:
                continue
            result = self._validator.validate(row.name, existing=())
            if not result.ok:
                self._set_summary(tr(result.i18n_key))
                continue
            row.name = result.normalized[: -len(self._validator.profile.extension)]
            row.job = JobState.QUEUED
            row.artifact = row.artifact if row.artifact is not ArtifactState.MISSING else ArtifactState.MISSING
            self._model.refresh_row(row_id)
            requests.append(
                TtsRequest(
                    row_id=row.row_id,
                    text=row.text,
                    output_path=self._output_path(row),
                    language=row.language,
                    voice=row.voice,
                    params=self.params_panel.params(),
                )
            )
        if not requests:
            self._update_summary()
            return
        self._cancel.clear()
        self._worker = threading.Thread(
            target=self._run_requests, args=(requests,), name="voice-batch", daemon=True
        )
        self._worker.start()
        self.generate_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    def _output_path(self, row: VoiceRow) -> Path:
        root = Path(self._output_dir())
        name = row.name or row.row_id
        return root / f"{name}{self._validator.profile.extension}"

    def _output_dir(self) -> str:
        """M1 默认输出目录：项目内 temp/voice-output（W4 接入工程文件后改为工程内目录）。"""

        from app.paths import temp_dir

        return str(temp_dir() / "voice-output")

    def _run_requests(self, requests: Sequence[TtsRequest]) -> None:
        def on_started(request: TtsRequest) -> None:
            self._events.put(("started", request.row_id))

        def on_finished(result: TtsResult) -> None:
            self._events.put(("finished", result))

        def on_failed(row_id: str, error: TtsError) -> None:
            self._events.put(("failed", (row_id, error)))

        try:
            self._runner.run_batch(
                requests, cancel_event=self._cancel, on_started=on_started, on_finished=on_finished, on_failed=on_failed
            )
        finally:
            self._events.put(("done", None))

    def _stop_generation(self) -> None:
        if self.is_busy:
            self._cancel.set()

    def _drain_events(self) -> None:
        while True:
            try:
                kind, payload = self._events.get_nowait()
            except queue.Empty:
                break
            if kind == "started":
                row = self._model.table().row(str(payload))
                if row is not None:
                    row.job = JobState.GENERATING
                    self._model.refresh_row(row.row_id)
                self._set_summary(tr("voice.status.running"))
            elif kind == "finished":
                self._apply_result(payload)  # type: ignore[arg-type]
            elif kind == "failed":
                if not isinstance(payload, tuple) or len(payload) != 2:
                    continue
                row_id, error = payload
                if not isinstance(row_id, str) or not isinstance(error, TtsError):
                    continue
                row = self._model.table().row(row_id)
                if row is not None:
                    row.job = JobState.CANCELLED if error.code == "cancelled" else JobState.FAILED
                    row.error_code = error.code
                    row.error_message = error.message
                    self._model.refresh_row(row.row_id)
                self._set_summary(f"{tr('voice.status.failed')}: {error.message}")
            elif kind == "weights":
                if not isinstance(payload, tuple) or len(payload) != 2:
                    continue
                ok, message = payload
                if not isinstance(ok, bool):
                    continue
                self.apply_weights_button.setEnabled(True)
                self._set_summary(
                    tr("voice.weights.applied") if ok else tr("voice.weights.failed", message=str(message))
                )
            elif kind == "done":
                self._worker = None
                self.generate_button.setEnabled(True)
                self.stop_button.setEnabled(False)
                self._update_summary()

    def _apply_result(self, result: TtsResult) -> None:
        row = self._model.table().row(result.row_id)
        if row is None:
            return
        row.job = JobState.IDLE
        row.artifact = ArtifactState.CURRENT
        row.spec_hash = row.compute_spec_hash(self._model.table().key_id)
        row.output_hash = result.output_hash
        row.audio_path = str(result.output_path)
        row.duration_ms = result.duration_ms
        row.error_code = ""
        row.error_message = ""
        self._model.refresh_row(row.row_id)

    def _on_params_toggled(self, checked: bool) -> None:
        self._update_params_toggle_text()
        self.params_scroll.setVisible(checked)

    def _update_params_toggle_text(self) -> None:
        arrow = "▾" if self.params_toggle.isChecked() else "▸"
        self.params_toggle.setText(f"{arrow} {tr('voice.params.toggle')}")

    # —— 模型权重（训练产物 → 推理热切换）——
    def _apply_weights_clicked(self) -> None:
        """应用权重：走工作线程。

        `set_weights` 是**两个阻塞 HTTP**（``/set_gpt_weights`` / ``/set_sovits_weights``），
        超时取自后端的 ``DEFAULT_TIMEOUT_S``（300s）。曾直接在 GUI 线程调用，点一下最坏冻结
        600s；本机因系统代理过滤 localhost，即使服务没起也要卡约 4s。
        """

        backend = getattr(self._runner, "backend", None)
        set_weights = getattr(backend, "set_weights", None)
        if not callable(set_weights):
            self._set_summary(tr("voice.weights.unsupported"))
            return
        if self._weights_worker is not None and self._weights_worker.is_alive():
            return
        gpt_path = self.gpt_weights_input.text().strip()
        sovits_path = self.sovits_weights_input.text().strip()
        self.apply_weights_button.setEnabled(False)
        self._set_summary(tr("voice.weights.applying"))
        self._weights_worker = threading.Thread(
            target=self._apply_weights_worker,
            args=(set_weights, gpt_path, sovits_path),
            name="tts-weights",
            daemon=True,
        )
        self._weights_worker.start()

    def _apply_weights_worker(self, set_weights: Callable[..., tuple[bool, str]], gpt_path: str, sovits_path: str) -> None:
        """工作线程：**不得在此触碰任何界面对象**，结果经事件队列回主线程。"""

        try:
            ok, message = set_weights(gpt_path, sovits_path)
        except Exception as error:  # noqa: BLE001  # 工作线程边界：统一转为失败结果
            ok, message = False, str(error)
        self._events.put(("weights", (ok, message)))

    def _on_weights_discovered(self, gpt_path: str, sovits_path: str) -> None:
        if gpt_path:
            self.gpt_weights_input.setText(gpt_path)
        if sovits_path:
            self.sovits_weights_input.setText(sovits_path)

    def set_backend_pending(self) -> None:
        """后端装配中：探活与拉起推理服务都可能阻塞（数秒到上百秒），由后台线程进行；
        本方法只负责禁用生成并给出提示，界面不阻塞。"""

        self._backend_pending = True
        self.generate_button.setEnabled(False)
        self.weights_holder.setVisible(False)
        self._set_summary(tr("voice.backend.connecting"))

    def set_backend(self, backend: TtsBackend) -> None:
        """切换推理后端（路由侧按模型选择装配；切换时重建串行执行器）。"""

        self._backend_pending = False
        self._runner = SerialTtsRunner(backend)
        name = getattr(backend, "name", type(backend).__name__)
        self.params_panel.set_backend_kind(name)
        self.set_model_kind(self.MODEL_COSY if self.params_panel.backend_kind == BACKEND_COSY else self.MODEL_GPT)
        self.weights_holder.setVisible(self.params_panel.backend_kind == BACKEND_GPT)
        if not self.is_busy:
            self.generate_button.setEnabled(True)
        self._set_summary(tr("voice.backend.demo") if name == "fake" else tr("voice.backend.ready", name=name))

    # —— 试听 ——
    def _preview(self, row_id: str) -> None:
        row = self._model.table().row(row_id)
        if row is None or not row.audio_path or not Path(row.audio_path).exists():
            self._set_summary(tr("voice.preview.missing"))
            return
        self._preview_path = Path(row.audio_path)
        self._player.setSource(QUrl.fromLocalFile(str(self._preview_path)))
        self._player.play()
        self._set_summary(tr("voice.preview.playing", name=row.name))

    # —— 展示 ——
    def _set_summary(self, text: str) -> None:
        self.summary_label.setText(text)

    def _update_summary(self) -> None:
        if self._backend_pending:
            # 装配尚未完成：不要用行数统计覆盖"正在连接…"提示
            self._set_summary(tr("voice.backend.connecting"))
            return
        rows = self._model.rows()
        done = sum(1 for row in rows if row.artifact is ArtifactState.CURRENT)
        stale = sum(1 for row in rows if row.needs_regeneration)
        pending = len(rows) - done - stale
        text = tr("voice.summary.counts", total=len(rows), done=done, stale=stale, pending=max(0, pending))
        if HASH_BACKEND != "vtcore":
            # 无扩展时 `.vt` 工程读写整体不可用：这条提示必须常驻，不能被统计文案覆盖
            text = f"{tr('voice.project.no_backend')}｜{text}"
        self._set_summary(text)

    def retranslate(self) -> None:
        super().retranslate()
        self.add_button.setText(tr("voice.action.add"))
        self.generate_button.setText(tr("voice.action.generate_selected"))
        self.regenerate_all_button.setText(tr("voice.action.generate_stale"))
        self.stop_button.setText(tr("voice.action.stop"))
        self.more_button.setText(tr("voice.action.more"))
        for action, key in self._more_actions:
            action.setText(tr(key))
        self.apply_weights_button.setText(tr("voice.weights.apply"))
        self.gpt_weights_input.setPlaceholderText(tr("voice.weights.gpt_hint"))
        self.sovits_weights_input.setPlaceholderText(tr("voice.weights.sovits_hint"))
        self.params_panel.retranslate()
        self.train_panel.retranslate()
        self.cosy_panel.retranslate()
        self._update_params_toggle_text()
        for key, label in self._pane_titles.items():
            label.setText(i18n_text(key))
        self._model.layoutChanged.emit()
        self._update_summary()

    # —— `.vt` 写出（M2）——
    def export_vt(self, target: Path, *, seed_hex: str = "") -> str:
        """把当前表写为 `.vt`（`seed_hex` 非空则签名）；返回状态文案。

        这里不做对话框交互，便于无界面测试；失败一律转成可读文案，不抛给 UI。
        """

        if HASH_BACKEND != "vtcore":
            return tr("voice.export.unavailable")
        table = self._model.table()
        try:
            signed = vt_project.save_table(target, table, seed_hex=seed_hex)
        except vt_project.VtProjectError as error:
            code = str(error).split(":", 1)[0]
            if code == vt_project.LOCK_ERROR:
                return tr("voice.export.locked")
            return tr("voice.export.failed", code=code)
        self.set_lock_state(target)
        return tr("voice.export.done_signed" if signed else "voice.export.done", name=target.name)

    # —— 工程文件（`.vt` 是唯一格式：未签名可编辑，已签名只读）——
    def open_project(self, path: Path) -> str:
        """打开 `.vt` 工程：未签名 → 可编辑（自动保存写回该文件）；已签名 → 只读。"""

        suffix = path.suffix.lower()
        if suffix == ".json":
            return tr("voice.open.json_retired")
        if suffix != ".vt":
            return tr("voice.open.not_supported")
        return self._open_vt_project(path)

    def _open_vt_project(self, path: Path) -> str:
        if HASH_BACKEND != "vtcore":
            return tr("voice.export.unavailable")
        try:
            table, info = vt_project.container_to_table(path)
        except (OSError, ValueError, vt_project.VtProjectError) as error:
            return tr("voice.open.failed", code=str(error).split(":", 1)[0])
        self._model.set_table(table)
        if info["applied"]:
            for row in self._model.rows():
                self._model.refresh_row(row.row_id)
        self._project_view = path
        self.set_lock_state(path)
        if info["locked"]:
            # 已签名 → 自动上锁 → 只读：不设自动保存目标；改动需"解锁以编辑"或"另存为新文件"
            self._project_file = None
            self.unlock_action.setEnabled(True)
            self._update_summary()
            return tr("voice.open.vt_readonly", name=path.name, count=len(table.rows))
        self._project_file = path
        self.unlock_action.setEnabled(False)
        self._update_summary()
        return tr("voice.open.vt_editable", name=path.name, count=len(table.rows))

    def _unlock_project_clicked(self) -> None:
        """解锁已签名的 `.vt` 以便原地编辑（解锁后保存会写出未签名容器）。"""

        path = self._project_view
        if path is None:
            return
        try:
            vt_project.unlock_file(path)
        except OSError as error:
            self._set_summary(tr("voice.unlock.failed", code=type(error).__name__))
            return
        opened = self.open_project(path)
        if self._project_file == path:
            self._set_summary(tr("voice.unlock.done", name=path.name))
        else:
            self._set_summary(opened)

    def _open_project_clicked(self) -> None:
        start = str((self._project_file or self._project_path()).parent)
        filters = f"{tr('voice.open.filter')} (*.vt)"
        target, _filter = QFileDialog.getOpenFileName(self, tr("voice.open.title"), start, filters)
        if not target:
            return
        self._set_summary(self.open_project(Path(target)))

    def set_lock_state(self, path: Path | None) -> None:
        """刷新锁状态徽章：文件处于只读锁时显示，否则清空。"""

        if path is not None and vt_project.is_locked(path):
            self.lock_label.setText(tr("voice.lock.badge", name=path.name))
        else:
            self.lock_label.setText("")

    def _export_vt_clicked(self) -> None:
        default = self._project_path().with_suffix(".vt")
        target, _filter = QFileDialog.getSaveFileName(self, tr("voice.export.title"), str(default), "VT (*.vt)")
        if not target:
            return
        self._set_summary(self.export_vt(Path(target)))

    def sign_and_export_vt(self, target: Path, *, create_if_missing: bool = True) -> str:
        """用项目密钥签名并导出 `.vt`；没有密钥且允许时自动生成一把。返回状态文案。"""

        if HASH_BACKEND != "vtcore":
            return tr("voice.export.unavailable")
        base = _key_store_dir()
        key_id = vt_key_store.latest_project_key(base)
        if not key_id:
            if not create_if_missing:
                return tr("voice.keys.none")
            key_id = vt_key_store.create_project_key(base).key_id
        try:
            seed = vt_key_store.load_project_seed(base, key_id)
        except vt_key_store.KeyStoreError as error:
            return tr("voice.keys.unreadable", code=str(error).split(":", 1)[0])
        return self.export_vt(target, seed_hex=seed.hex())

    def _sign_export_clicked(self) -> None:
        base = _key_store_dir()
        if not vt_key_store.latest_project_key(base):
            answer = QMessageBox.question(self, tr("voice.keys.title"), tr("voice.sign.confirm"))
            if answer != QMessageBox.StandardButton.Yes:
                return
        default = self._project_path().with_suffix(".vt")
        target, _filter = QFileDialog.getSaveFileName(self, tr("voice.export.title"), str(default), "VT (*.vt)")
        if not target:
            return
        self._set_summary(self.sign_and_export_vt(Path(target)))

    def _keys_clicked(self) -> None:
        VtKeyDialog(_key_store_dir(), self).exec()

    # —— 信任（TOFU）与整包校验（M2 接线增量 4）——
    def _trust_store_path(self) -> Path:
        return _key_store_dir() / "vt_trust.json"

    def verify_vt_file(self, path: Path, *, decide: Callable[[str, str], str] | None = None) -> str:
        """校验外部 `.vt`：结构 → 签名 → TOFU 信任判定；返回状态文案。

        `decide(key_id, public_key)` 返回 `"trust"` / `"once"` / `"reject"`，
        默认弹三选一对话框；测试可直接注入以避开界面交互。
        """

        if HASH_BACKEND != "vtcore":
            return tr("voice.export.unavailable")
        engine = vt_project.vtcore_api()
        try:
            data = path.read_bytes()
            document = engine.parse_container(data)
        except (OSError, ValueError) as error:
            return tr("voice.verify.failed", code=str(error).split(":", 1)[0])

        if not document["is_signed"]:
            return tr("voice.verify.unsigned")
        try:
            engine.verify_container_signature(data)
        except ValueError as error:
            return tr("voice.verify.failed", code=str(error).split(":", 1)[0])

        signature = document["signature"]
        key_id = signature["key_id"]
        store = TrustStore.load(self._trust_store_path())
        decision = store.observe(key_id, signature["public_key"], table_id=document["table_id"])
        store.save()
        if decision is TrustDecision.REVOKED:
            return tr("voice.verify.revoked", key_id=key_id)
        if decision is TrustDecision.ROTATED_UNKNOWN:
            return tr("voice.verify.rotated", key_id=key_id)
        if decision is TrustDecision.TRUSTED:
            return tr("voice.verify.ok_trusted", key_id=key_id)

        choice = (decide or self._ask_trust)(key_id, signature["public_key"])
        if choice == "trust":
            store.trust(key_id)
            store.save()
            return tr("voice.verify.ok_trusted", key_id=key_id)
        if choice == "once":
            return tr("voice.trust.once_done")
        return tr("voice.trust.rejected")

    def _ask_trust(self, key_id: str, _public_key: str) -> str:
        """首次见到未知签名者时的三选一（TOFU：不自动信任）。"""

        box = QMessageBox(self)
        box.setWindowTitle(tr("voice.verify.title"))
        box.setText(tr("voice.trust.prompt", key_id=key_id))
        remember = box.addButton(tr("voice.trust.remember"), QMessageBox.ButtonRole.AcceptRole)
        once = box.addButton(tr("voice.trust.once"), QMessageBox.ButtonRole.ActionRole)
        box.addButton(tr("voice.trust.reject"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is remember:
            return "trust"
        if clicked is once:
            return "once"
        return "reject"

    def _verify_vt_clicked(self) -> None:
        start = str((self._project_file or self._project_path()).parent)
        target, _filter = QFileDialog.getOpenFileName(self, tr("voice.verify.title"), start, "VT (*.vt)")
        if not target:
            return
        self._set_summary(self.verify_vt_file(Path(target)))

    def export_manifest(self, package_dir: Path, *, seed_hex: str = "") -> str:
        """为整包目录生成 `.vtmanifest`（`seed_hex` 非空则签名）；返回状态文案。"""

        if HASH_BACKEND != "vtcore":
            return tr("voice.export.unavailable")
        table = self._model.table()
        try:
            manifest = vt_manifest.build_manifest(
                package_dir, table_spec_hash=table.spec_hash(), seed_hex=seed_hex
            )
            path = vt_manifest.write_manifest(package_dir, manifest)
        except (OSError, ValueError, vt_manifest.ManifestError) as error:
            return tr("voice.manifest.failed", code=str(error).split(":", 1)[0])
        return tr("voice.manifest.exported", name=path.name, count=manifest["file_count"])

    def verify_manifest_package(self, package_dir: Path) -> str:
        """校验整包（清单签名 + 逐文件哈希 / 字节数）；返回状态文案。"""

        if HASH_BACKEND != "vtcore":
            return tr("voice.export.unavailable")
        try:
            report = vt_manifest.verify_package(package_dir)
        except (OSError, ValueError, vt_manifest.ManifestError) as error:
            return tr("voice.manifest.failed", code=str(error).split(":", 1)[0])
        return tr("voice.manifest.report", summary=report.summary())

    def _export_manifest_clicked(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, tr("voice.manifest.choose"), self._output_dir())
        if not directory:
            return
        base = _key_store_dir()
        seed_hex = ""
        if vt_key_store.latest_project_key(base):
            try:
                seed_hex = vt_key_store.load_project_seed(base, vt_key_store.latest_project_key(base)).hex()
            except vt_key_store.KeyStoreError:
                seed_hex = ""
        self._set_summary(self.export_manifest(Path(directory), seed_hex=seed_hex))

    def _verify_package_clicked(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, tr("voice.manifest.choose"), self._output_dir())
        if not directory:
            return
        self._set_summary(self.verify_manifest_package(Path(directory)))


    # —— 持久化 ——
    def _project_path(self) -> Path:
        """当前工程文件：打开过就写回该文件；否则用项目内默认工作文件 `voice_project.vt`。"""

        if self._project_file is not None:
            return self._project_file

        from app.paths import temp_dir

        return temp_dir() / "voice-output" / "voice_project.vt"

    def _load_existing_project(self) -> None:
        """启动时载入默认工作文件（`.vt`）。

        - **未构建 vtcore → 跳过**，只在状态栏说明（应用必须能在没有扩展时照常启动）；
        - 文件不存在或已损坏 → 静默跳过。
        """

        if HASH_BACKEND != "vtcore":
            # 无扩展：不尝试加载 `.vt`，由汇总文案常驻提示（见 _update_summary）
            self._update_summary()
            return
        path = self._project_path()
        if not path.exists():
            return
        try:
            table, info = vt_project.container_to_table(path)
        except (OSError, ValueError, vt_project.VtProjectError):
            return
        self._model.set_table(table)
        if info["applied"]:
            for row in self._model.rows():
                self._model.refresh_row(row.row_id)
        self._project_view = path
        self.set_lock_state(path)
        self._update_summary()

    def _on_save_failed(self, message: str) -> None:
        """自动保存失败（工程被锁定 / 缺扩展 / 磁盘错误）→ 状态栏显示可读文案。"""

        self._set_summary(tr("voice.project.save_failed", code=str(message).split(":", 1)[0]))
def choose_output_directory(page: VoiceBatchPage, parent: QWidget) -> str:
    """工具栏外的目录选择小工具（保留给后续接入；当前由偏好决定输出目录）。"""

    directory = QFileDialog.getExistingDirectory(parent, tr("voice.choose_output"), page._output_dir())
    return directory



