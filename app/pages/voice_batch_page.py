# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""三级页：TTS 批量生成工作台（W3）。

- 行身份与状态语义（row_id 永久；JobState × ArtifactState 双轴）；
- 生成走 ``SerialTtsRunner``（串行、子进程/HTTP 后端），在工作线程执行，
  结果经线程安全队列回主线程刷新（避免跨线程直接改 UI）；
- 试听复用 QMediaPlayer（同音频处理页用法）。
"""

from __future__ import annotations

import hashlib
import queue
import shutil
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QKeySequence,
    QPalette,
    QShortcut,
    QShowEvent,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
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
    QStackedWidget,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.audio.ffmpeg_service import FfmpegLocator
from app.i18n import i18n_text, tr
from app.models.voice_table import (
    HASH_BACKEND,
    ArtifactState,
    JobState,
    VoiceRow,
    VoiceTable,
)
from app.preferences import get_preference, set_preference
from app.services import gsv_services, tts_spec, vt_key_store, vt_manifest, vt_project
from app.services import tts_training as training
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
from app.styles import theme
from app.widgets.cosyvoice_info_panel import CosyVoiceInfoPanel
from app.widgets.flow_layout import FlowLayout
from app.widgets.hover_card import attach_hover_card
from app.widgets.tts_params_panel import BACKEND_COSY, BACKEND_GPT, TtsParamsPanel
from app.widgets.tts_train_panel import TtsTrainPanel, gsv_root
from app.widgets.voice_audio_process_dialog import KokoroTsurumaki
from app.widgets.voice_table_model import (
    VoiceColumn,
    VoiceRowDelegate,
    VoiceTableModel,
    default_audio_picker,
)
from app.widgets.vt_key_dialog import VtKeyDialog

from .base_tool_page import BaseToolPage

#: 输出目录的偏好键（config/settings.ini；未设置时回退项目内 temp/voice-output）
OUTPUT_DIR_SETTING = "voice/output_dir"
#: 命名规范名单文件的偏好键（表格规范化：行集合由该名单决定）
SPEC_PATH_KEY = "voice/spec_path"
#: 命名规范当前激活路径的偏好键（值 = "/" 连接的路径段，如 tank/UK/high/gunner）
SPEC_SELECTION_KEY = "voice/spec_selection"
#: 情绪音频共用的偏好键（"1" = 共用一份音频服务全部情绪；"0" = 每情绪各自生成）
EMOTION_SHARED_KEY = "voice/emotion_shared"
#: GSV 模型版本偏好键（先选版本再工作的前置选择；装配成功后自动应用）


def _key_store_dir() -> Path:
    """签名密钥的存放目录（项目内 `config/`，已 gitignore；测试可整体替换）。"""

    from app.paths import config_dir

    return config_dir()


class VoiceBatchPage(BaseToolPage):
    """语音批量生成工作台：表格编辑 + 串行生成 + 试听 + 状态徽章。"""

    close_ready = Signal()
    #: 用户请求切换推理模型（GPT-SoVITS / CosyVoice 3）；装配由路由侧（MainWindow）异步完成
    model_switch_requested = Signal(str)

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
        #: 整包清单导出/校验的在途标志（整包哈希在后台线程做，期间禁用两个清单动作）
        self._manifest_busy = False
        self._preview_path: Path | None = None
        #: 当前工程文件（`None` = 尚未打开，使用项目内默认路径；打开后自动保存写回该文件）
        self._project_file: Path | None = None
        #: 最近打开的工程文件（可能是已签名的只读文件；解锁动作以它为目标）
        self._project_view: Path | None = None
        #: 后端装配中（由路由侧的工作线程完成；期间禁用生成并提示"正在连接"）
        self._backend_pending = False
        #: 参考音频的文件选择对话框（可注入替换，测试用）
        self._reference_picker = default_audio_picker
        #: 命名规范名单文件（路径分节：行集合由它决定；None = 未加载）
        self._spec_path: Path | None = None
        #: 已加载规范的路径分节文档（`tts_spec.SpecDocument`；None = 未加载）
        self._spec_sections: tts_spec.SpecDocument | None = None
        #: 会话级路径暂存：切路径时把当前表格对象整体存进来（切回时按名继承）
        self._path_tables: dict[tuple[str, ...], VoiceTable] = {}
        #: 当前激活路径（如 ("tank","UK","high","gunner")；() = 尚未选择类别）
        self._active_path: tuple[str, ...] = ()
        #: 情绪音频共用（勾选 = 一份音频服务该类别全部情绪；偏好持久化）
        self._emotion_shared = get_preference(EMOTION_SHARED_KEY, "1") != "0"
        #: 两栏标题（按 i18n key 索引，供 retranslate 更新）
        self._pane_titles: dict[str, QLabel] = {}
        #: 当前模型键（MODEL_GPT / MODEL_COSY），供切换按钮去重与选中态同步
        self._model_kind = self.MODEL_GPT

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
        self._apply_selection_palette()
        # 监听须可退订：lambda 无法按等值移除，改用绑定方法 + destroyed 摘除（同 nav_rail）
        theme.on_mode_changed(self._on_theme_mode_changed)
        self.destroyed.connect(lambda: theme.off_mode_changed(self._on_theme_mode_changed))

    def showEvent(self, event: QShowEvent) -> None:
        # 首次进入本页发生在全部 reparent/polish 之后：构造期应用的视图级
        # 选中色覆盖可能被 polish 吞回全局亮蓝，显示时补打一次（幂等）
        super().showEvent(event)
        self._apply_selection_palette()

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
        """顶部模块切换按钮 + 下方单界面（语音工作台改版）：训练/生成各占整宽，避免双栏拥挤。

        「模型训练模块」内容随模型选择切换（GPT-SoVITS=微调面板 / CosyVoice 3=模型信息面板）；
        「语音生成列表」为原有推理工作台能力。两个模块常驻（切换不丢状态）。
        """

        host = QWidget()
        root = QVBoxLayout(host)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.train_module_button = QPushButton()
        self.train_module_button.setObjectName("moduleSwitchButton")
        self.train_module_button.setProperty("audioNavigation", True)  # 复用选中态高亮样式
        self.train_module_button.setCheckable(True)
        self.generation_module_button = QPushButton()
        self.generation_module_button.setObjectName("moduleSwitchButton")
        self.generation_module_button.setProperty("audioNavigation", True)
        self.generation_module_button.setCheckable(True)
        self._module_group = QButtonGroup(self)
        self._module_group.setExclusive(True)
        self._module_group.addButton(self.train_module_button)
        self._module_group.addButton(self.generation_module_button)
        module_bar = QHBoxLayout()
        module_bar.setContentsMargins(0, 0, 0, 0)
        module_bar.setSpacing(8)
        module_bar.addWidget(self.train_module_button)
        module_bar.addWidget(self.generation_module_button)
        module_bar.addStretch(1)
        # 模型选择（模块选择页移除后的常驻入口）：切换请求交路由侧异步装配后端
        self.model_kind_label = QLabel()
        self.model_kind_label.setObjectName("mutedLabel")
        module_bar.addWidget(self.model_kind_label)
        self.gpt_model_button = QPushButton("GPT-SoVITS")
        self.gpt_model_button.setObjectName("moduleSwitchButton")
        self.gpt_model_button.setProperty("audioNavigation", True)
        self.gpt_model_button.setCheckable(True)
        self.cosy_model_button = QPushButton("CosyVoice 3")
        self.cosy_model_button.setObjectName("moduleSwitchButton")
        self.cosy_model_button.setProperty("audioNavigation", True)
        self.cosy_model_button.setCheckable(True)
        self.cpufast_model_button = QPushButton("GPT-SoVITS CPUFast")
        self.cpufast_model_button.setObjectName("moduleSwitchButton")
        self.cpufast_model_button.setProperty("audioNavigation", True)
        self.cpufast_model_button.setCheckable(True)
        self._model_group = QButtonGroup(self)
        # 组不可独占：独占组会忽略对当前选中按钮的程序化取消选中，
        # 选 API 渠道时两个本地按钮将无法置为未选；选中态由 set_model_kind 全权管理
        self._model_group.setExclusive(False)
        self._model_group.addButton(self.gpt_model_button)
        self._model_group.addButton(self.cpufast_model_button)
        self._model_group.addButton(self.cosy_model_button)
        self.gpt_model_button.setChecked(True)
        module_bar.addWidget(self.gpt_model_button)
        module_bar.addWidget(self.cpufast_model_button)
        module_bar.addWidget(self.cosy_model_button)
        # API 渠道（index 0 为占位）：选中即发出 api:<渠道id> 切换请求，经路由侧装配 TTS-Hub 后端
        self.channel_combo = QComboBox()
        self.channel_combo.addItem(i18n_text("voice.channel.combo_hint"))
        self.channel_combo.currentIndexChanged.connect(self._on_channel_combo)
        module_bar.addWidget(self.channel_combo)
        root.addLayout(module_bar)

        left_pane = self._build_train_pane()
        left_pane.setMinimumWidth(380)
        cosy_pane = self._build_cosy_pane()
        cosy_pane.setMinimumWidth(380)
        api_pane = self._build_api_pane()
        api_pane.setMinimumWidth(380)
        right_pane = self._build_inference_pane()
        # 训练模块页随所选模型切换：GPT-SoVITS=微调面板 / CosyVoice 3、API 渠道=信息面板
        self._model_panes = QStackedWidget()
        self._model_panes.addWidget(left_pane)
        self._model_panes.addWidget(cosy_pane)
        self._model_panes.addWidget(api_pane)
        self._module_panes = QStackedWidget()
        self._module_panes.setObjectName("modulePanes")
        self._module_panes.addWidget(self._model_panes)
        self._module_panes.addWidget(right_pane)
        root.addWidget(self._module_panes, 1)

        self.train_module_button.clicked.connect(lambda: self._show_module(0))
        self.generation_module_button.clicked.connect(lambda: self._show_module(1))
        self.gpt_model_button.clicked.connect(lambda: self._request_model(self.MODEL_GPT))
        self.cpufast_model_button.clicked.connect(lambda: self._request_model(self.MODEL_GPT_CPUFAST))
        self.cosy_model_button.clicked.connect(lambda: self._request_model(self.MODEL_COSY))
        # 悬停信息卡：说明两种 TTS（GPT-SoVITS / CosyVoice 3）的功能与接口差异
        self._train_module_card = attach_hover_card(
            self.train_module_button,
            i18n_text("voice.module.train"),
            i18n_text("voice.module.train.tip"),
        )
        self._generation_module_card = attach_hover_card(
            self.generation_module_button,
            i18n_text("voice.module.generation"),
            i18n_text("voice.module.generation.tip"),
        )
        self._update_module_cards_language()
        # 默认展示生成列表（日常主工作流）
        self.generation_module_button.setChecked(True)
        self._module_panes.setCurrentIndex(1)
        return host

    def _show_module(self, index: int) -> None:
        """切换顶部按钮对应的模块界面。"""

        self._module_panes.setCurrentIndex(index)
        self.train_module_button.setChecked(index == 0)
        self.generation_module_button.setChecked(index == 1)

    def _request_model(self, model_key: str) -> None:
        """点击模型切换按钮：与当前模型不同才发出请求，避免重复点击反复重装配后端。"""

        if model_key == self._model_kind:
            # 非独占组下点击已选中按钮会先取消勾选：必须恢复选中态，
            # 否则界面进入"全按钮不选"的死态（面板仍是该模型但看不出选的谁）
            self.gpt_model_button.setChecked(model_key == self.MODEL_GPT)
            self.cpufast_model_button.setChecked(model_key == self.MODEL_GPT_CPUFAST)
            self.cosy_model_button.setChecked(model_key == self.MODEL_COSY)
            return
        self.model_switch_requested.emit(model_key)

    def _update_module_cards_language(self) -> None:
        """悬停信息卡文案随界面语言刷新。"""

        self._train_module_card.set_text(
            i18n_text("voice.module.train"), i18n_text("voice.module.train.tip")
        )
        self._generation_module_card.set_text(
            i18n_text("voice.module.generation"), i18n_text("voice.module.generation.tip")
        )

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

    def _build_api_pane(self) -> QFrame:
        """API 渠道信息面板：展示当前启用渠道的连接要点（云端渠道无训练能力）。"""

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)
        title = QLabel(i18n_text("voice.channel.pane.title"))
        title.setObjectName("crewPanelTitle")
        layout.addWidget(title)
        self._api_channel_labels: dict[str, QLabel] = {}
        for key in ("voice.channel.pane.channel", "voice.channel.pane.address", "voice.channel.pane.vendor", "voice.channel.pane.voice"):
            label = QLabel("")
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            self._api_channel_labels[key] = label
            layout.addWidget(label)
        note = QLabel(i18n_text("voice.channel.pane.note"))
        note.setObjectName("mutedLabel")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return self._pane("voice.pane.inference", body)

    def _update_api_pane(self, channel_id: str) -> None:
        from app.services import api_channels

        channel = api_channels.get_channel(channel_id)
        values = {
            "voice.channel.pane.channel": channel.label if channel else i18n_text("voice.channel.combo_hint"),
            "voice.channel.pane.address": channel.base_url if channel else "—",
            "voice.channel.pane.vendor": channel.vendor or i18n_text("api.field.vendor_hint") if channel else "—",
            "voice.channel.pane.voice": channel.voice or "—" if channel else "—",
        }
        for key, value in values.items():
            self._api_channel_labels[key].setText(f"{i18n_text(key)}：{value}")

    # —— 模型感知 ——
    MODEL_GPT = "tts_gpt_sovits"
    #: CPUFast 分支（CPU 提速版 GPT-SoVITS，独立克隆 + 原生 CPU torch 环境）：
    #: 与官方整合包同级的独立入口，面板同 GPT（微调面板），服务档案固定 id=cpufast
    MODEL_GPT_CPUFAST = "tts_gpt_sovits_cpufast"
    MODEL_COSY = "tts_cosyvoice"

    def set_model_kind(self, model_key: str) -> None:
        """按所选模型切换「模型训练模块」内的面板（进入工作台/装配后端/切换模型时调用）。

        GPT-SoVITS = 微调面板（数据集工具 + 微调训练）；CosyVoice 3 与 API 渠道 = 信息面板。
        同时同步右上角模型切换按钮 / API 渠道下拉的选中态。
        """

        self._model_kind = model_key
        if model_key.startswith("api:"):
            self._model_panes.setCurrentIndex(2)
            self.gpt_model_button.setChecked(False)
            self.cpufast_model_button.setChecked(False)
            self.cosy_model_button.setChecked(False)
            self._update_api_pane(model_key.split(":", 1)[1])
            self._sync_channel_combo(model_key.split(":", 1)[1])
            self.cosy_panel.refresh_status()
            return
        self._model_panes.setCurrentIndex(1 if model_key == self.MODEL_COSY else 0)
        self.gpt_model_button.setChecked(model_key == self.MODEL_GPT)
        self.cpufast_model_button.setChecked(model_key == self.MODEL_GPT_CPUFAST)
        self.cosy_model_button.setChecked(model_key == self.MODEL_COSY)
        self._sync_channel_combo(None)
        self.cosy_panel.refresh_status()

    def _sync_channel_combo(self, channel_id: str | None) -> None:
        """按当前模型键同步渠道下拉选中态（程序化设置不发切换请求）。"""

        target = 0
        if channel_id is not None:
            for index in range(1, self.channel_combo.count()):
                if self.channel_combo.itemData(index) == channel_id:
                    target = index
                    break
        if self.channel_combo.currentIndex() != target:
            self.channel_combo.blockSignals(True)
            self.channel_combo.setCurrentIndex(target)
            self.channel_combo.blockSignals(False)

    def _on_channel_combo(self, index: int) -> None:
        channel_id = self.channel_combo.itemData(index)
        if not channel_id:
            return
        model_key = f"api:{channel_id}"
        if model_key != self._model_kind:
            self.model_switch_requested.emit(model_key)

    def refresh_api_channels(self) -> None:
        """重建渠道下拉（API 渠道页保存/语言切换后调用）；保持当前选中渠道。"""

        selected = self.channel_combo.currentData() if self.channel_combo.currentIndex() > 0 else None
        self.channel_combo.blockSignals(True)
        self.channel_combo.clear()
        self.channel_combo.addItem(i18n_text("voice.channel.combo_hint"))
        from app.services import api_channels

        for channel in api_channels.enabled_channels():
            self.channel_combo.addItem(channel.label, channel.channel_id)
        if selected is not None:
            index = next(
                (i for i in range(1, self.channel_combo.count()) if self.channel_combo.itemData(i) == selected),
                0,
            )
            self.channel_combo.setCurrentIndex(index)
        self.channel_combo.blockSignals(False)

    def _build_inference_pane(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("crewManualPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 14, 15, 14)
        layout.setSpacing(10)

        title = QLabel(i18n_text("voice.table.title"))
        title.setObjectName("crewPanelTitle")
        # 构建期只设一次的标签必须登记进 _pane_titles，否则语言切换后滞留旧语言
        self._pane_titles["voice.table.title"] = title
        layout.addWidget(title)

        hint = QLabel(i18n_text("voice.table.hint"))
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        self._pane_titles["voice.table.hint"] = hint
        layout.addWidget(hint)

        # 主要操作：单行流式布局；低频操作收进「更多」下拉，避免按钮行堆叠挤压布局
        # 表格规范化：行集合由命名规范名单决定（无自由增删行），「加载规范」是入口
        edit_bar = FlowLayout(spacing=10)
        self.spec_button = QPushButton(i18n_text("voice.spec.load"))
        self.spec_button.clicked.connect(self._load_spec_clicked)
        self.generate_button = QPushButton(i18n_text("voice.action.generate_selected"))
        self.regenerate_all_button = QPushButton(i18n_text("voice.action.generate_stale"))
        self.stop_button = QPushButton(i18n_text("voice.action.stop"))
        self.stop_button.setEnabled(False)
        self.spec_label = QLabel()
        self.spec_label.setObjectName("mutedLabel")
        for widget in (self.spec_button, self.generate_button, self.regenerate_all_button, self.stop_button, self.spec_label):
            edit_bar.addWidget(widget)
        layout.addLayout(edit_bar)

        # 参考音频（常驻显眼入口）：上传即写入选中行；「应用到所有行」批量铺开。
        # （此前只藏在「音色」列的双击编辑态里，使用者完全发现不了——血泪教训。）
        self.reference_bar = QWidget()
        reference_row = FlowLayout(self.reference_bar, spacing=8)
        self.reference_label = QLabel(i18n_text("voice.reference.label"))
        self.reference_display = QLineEdit()
        self.reference_display.setReadOnly(True)
        self.reference_display.setPlaceholderText(i18n_text("voice.reference.empty"))
        self.reference_display.setToolTip(i18n_text("voice.reference.empty_tip"))
        self.reference_pick_button = QPushButton(i18n_text("voice.reference.pick"))
        self.reference_pick_button.clicked.connect(self._pick_reference_clicked)
        self.reference_apply_all_button = QPushButton(i18n_text("voice.reference.apply_all"))
        self.reference_apply_all_button.clicked.connect(self._apply_reference_to_all)
        self.reference_clear_button = QPushButton(i18n_text("voice.reference.clear"))
        self.reference_clear_button.clicked.connect(self._clear_reference_clicked)
        for widget in (
            self.reference_label,
            self.reference_display,
            self.reference_pick_button,
            self.reference_apply_all_button,
            self.reference_clear_button,
        ):
            reference_row.addWidget(widget)
        layout.addWidget(self.reference_bar)

        # 输出目录（可配置并持久化）：生成的音频写到这里；「更多」菜单亦可选择。
        self.output_bar = QWidget()
        output_row = FlowLayout(self.output_bar, spacing=8)
        self.output_label = QLabel(i18n_text("voice.output.label"))
        self.output_display = QLineEdit()
        self.output_display.setReadOnly(True)
        self.output_display.setToolTip(i18n_text("voice.output.tooltip"))
        self.output_change_button = QPushButton(i18n_text("voice.output.change"))
        self.output_change_button.clicked.connect(self._change_output_dir_clicked)
        self.output_open_button = QPushButton(i18n_text("voice.output.open"))
        self.output_open_button.clicked.connect(self._open_output_dir_clicked)
        for widget in (
            self.output_label,
            self.output_display,
            self.output_change_button,
            self.output_open_button,
        ):
            output_row.addWidget(widget)
        layout.addWidget(self.output_bar)
        self._refresh_output_display()

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

        # 模型权重：微调产物下拉选择 + 手动路径回填；运行时热切换（api_v2 权重端点，仅 GPT-SoVITS）
        self.weights_holder = QWidget()
        weights_row = FlowLayout(self.weights_holder, spacing=8)
        self.finetuned_label = QLabel(i18n_text("voice.weights.finetuned"))
        self.finetuned_combo = QComboBox()
        self.finetuned_combo.setMinimumContentsLength(18)
        self.finetuned_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.finetuned_combo.currentIndexChanged.connect(self._on_finetuned_selected)
        self.scan_weights_button = QPushButton(i18n_text("voice.weights.scan"))
        self.scan_weights_button.clicked.connect(self._scan_finetuned_clicked)
        self.gpt_weights_input = QLineEdit()
        self.gpt_weights_input.setPlaceholderText(i18n_text("voice.weights.gpt_hint"))
        self.sovits_weights_input = QLineEdit()
        self.sovits_weights_input.setPlaceholderText(i18n_text("voice.weights.sovits_hint"))
        self.apply_weights_button = QPushButton(i18n_text("voice.weights.apply"))
        self.apply_weights_button.clicked.connect(self._apply_weights_clicked)
        weights_row.addWidget(self.finetuned_label)
        weights_row.addWidget(self.finetuned_combo)
        weights_row.addWidget(self.scan_weights_button)
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
        # GSV 多分支兼容 P2：服务下拉（注册表驱动）+ 用户切换 → 重装配
        self.params_panel.service_change_requested.connect(self._on_gsv_service_changed)
        self.params_panel.service_manage_requested.connect(self._manage_gsv_services)
        self.refresh_gsv_services()
        self.params_scroll = QScrollArea()
        self.params_scroll.setObjectName("voiceParamsScroll")
        self.params_scroll.setWidgetResizable(True)
        self.params_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.params_scroll.setWidget(self.params_panel)
        self.params_scroll.setMaximumHeight(230)
        self.params_scroll.setVisible(False)
        layout.addWidget(self.params_scroll)

        # 五类分节（v2）：类别按钮行在「推理参数」之下、表格之上；
        # 互斥选项键（QPushButton checkable + QButtonGroup），点选即换表
        self.category_bar = QWidget()
        category_row = FlowLayout(self.category_bar, spacing=8)
        self.category_buttons: dict[str, QPushButton] = {}
        self._category_group = QButtonGroup(self)
        self._category_group.setExclusive(True)
        for index, category in enumerate(tts_spec.SPEC_CATEGORIES):
            button = QPushButton(i18n_text(f"voice.spec.category.{category}"))
            button.setProperty("audioNavigation", True)  # 复用选中态高亮样式
            button.setCheckable(True)
            self._category_group.addButton(button, index)
            self.category_buttons[category] = button
            category_row.addWidget(button)
        self._category_group.idClicked.connect(self._on_category_clicked)
        layout.addWidget(self.category_bar)

        # 国家/语音组、情绪/成员级联行（v3）：类别之下最多三行动态
        # 按钮（深度随官方结构自适应：vws/wopl 一行、radio 两行、tank/ship 三行），
        # 选项来自已加载 txt 的路径段（未加载时国家行用内置常量预览，更深各行
        # 隐藏并提示先加载）；情绪所在行的尾部挂「多情绪共用一份音频」勾选框。
        self.level_rows: list[QWidget] = []
        self.level_groups: list[QButtonGroup] = []
        self.level_buttons: list[dict[str, QPushButton]] = []
        self._level_options_cache: list[list[str]] = [[], [], []]
        self.emotion_shared_checkbox = QCheckBox(i18n_text("voice.spec.emotion_shared"))
        self.emotion_shared_checkbox.setChecked(self._emotion_shared)
        self.emotion_shared_checkbox.setToolTip(i18n_text("voice.spec.emotion_shared_tip"))
        self.emotion_shared_checkbox.toggled.connect(self._on_emotion_shared_toggled)
        for row_index in range(3):
            bar = QWidget()
            bar.setVisible(False)
            FlowLayout(bar, spacing=8)  # 布局随即创建；按钮由 _sync_level_rows 动态填充
            group = QButtonGroup(self)
            group.setExclusive(True)
            group.idClicked.connect(
                lambda button_id, row=row_index: self._on_level_clicked(row, button_id)
            )
            self.level_rows.append(bar)
            self.level_groups.append(group)
            self.level_buttons.append({})
            layout.addWidget(bar)

        self.table = QTableView()
        self.table.setObjectName("voiceTable")
        self.table.setModel(self._model)
        self.delegate = VoiceRowDelegate(self.table)
        self.table.setItemDelegate(self.delegate)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        # 行高要罩得住状态徽章：徽章上下各缩 6px，再留 4px 余量，
        # 默认行高对 CJK 字形偏紧，会出现徽章内文字被裁的观感
        self.table.verticalHeader().setDefaultSectionSize(
            self.table.fontMetrics().height() + 16)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(int(VoiceColumn.STATUS), QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(int(VoiceColumn.NAME), QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(int(VoiceColumn.TEXT), QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(int(VoiceColumn.PROCESS), QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(int(VoiceColumn.SKIP), QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(int(VoiceColumn.IMPORT), QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(int(VoiceColumn.VOICE), QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(int(VoiceColumn.DURATION), QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(int(VoiceColumn.ACTIONS), QHeaderView.ResizeMode.Fixed)
        # 官方音频名普遍 30~50 字符（如 voice_message_gunner_armor_breached_v1），
        # 160px 会截断成省略号；给足初始宽度，仍可拖动微调
        self.table.setColumnWidth(int(VoiceColumn.NAME), 400)
        self.table.setColumnWidth(int(VoiceColumn.PROCESS), 96)
        self.table.setColumnWidth(int(VoiceColumn.SKIP), 84)
        self.table.setColumnWidth(int(VoiceColumn.IMPORT), 150)
        self.table.setColumnWidth(int(VoiceColumn.VOICE), 150)
        self.table.setColumnWidth(int(VoiceColumn.ACTIONS), 150)
        self.table.setMinimumHeight(180)
        layout.addWidget(self.table, 1)
        self.table.selectionModel().currentRowChanged.connect(self._on_selection_changed)

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

        self.generate_button.clicked.connect(lambda: self._start_generation(self._selected_row_ids()))
        self.regenerate_all_button.clicked.connect(self._start_regeneration_for_stale)
        self.stop_button.clicked.connect(self._stop_generation)
        self.delegate.preview_requested.connect(self._preview)
        self.delegate.regenerate_requested.connect(lambda row_id: self._start_generation([row_id]))
        # 委托按钮在鼠标事件栈内抛信号：模态对话框/页面跳转必须出栈后再做
        self.delegate.import_requested.connect(
            lambda row_id: QTimer.singleShot(0, lambda: self._import_audio_row(row_id)))
        self.delegate.process_requested.connect(
            lambda row_id: QTimer.singleShot(0, lambda: self._process_row(row_id)))
        self._model.rows_changed.connect(self._update_summary)
        self._model.row_edited.connect(lambda _row_id: self._update_summary())
        return panel

    # —— 参考音频（常驻入口）——
    def _on_selection_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        row = self._model.row_at(current.row()) if current.isValid() else None
        self.reference_display.setText(row.voice if row is not None else "")

    def _on_theme_mode_changed(self, _mode: str) -> None:
        self._apply_selection_palette()
        # 行内按钮与状态徽章按主题取色（委托自绘）：换肤后主动重绘，
        # 否则要等下一次交互才刷新，看着像"半截没换肤"
        self.table.viewport().update()

    def _apply_selection_palette(self) -> None:
        """行选中底色收窄为本表调色板（只动 Highlight/HighlightedText 两角色）。

        委托已对可绘制单元格自铺 selection_bg（voice_table_model.paint）；
        这里收窄 Highlight 是补编辑器格的底：格内有打开的编辑器时视图跳过
        委托绘制，行原语（PE_PanelItemViewRow）用 Highlight 铺的整行底会
        从编辑器四周露出。全局 Highlight 是品牌亮蓝，不适用本表（自绘按钮
        按深底取色，亮蓝铺底对比度掉到 ~1.1:1，用户反馈）。
        应用时机：构造末期 + showEvent + 主题切换监听——应用级 QSS 存在时
        构造期 polish 会吞掉视图调色板覆盖（实测），多时机幂等补打。
        """
        palette = self.table.palette()
        palette.setColor(QPalette.ColorRole.Highlight, QColor(theme.color("selection_bg")))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(theme.color("selection_text")))
        self.table.setPalette(palette)

    def _apply_reference(self, path: str, row_ids: Sequence[str]) -> int:
        applied = 0
        for row_id in row_ids:
            row = self._model.table().row(row_id)
            if row is None:
                continue
            row.voice = path
            self._model.refresh_row(row_id)
            self._coordinator.mark_dirty()
            applied += 1
        return applied

    def _pick_reference_clicked(self) -> None:
        path = self._reference_picker(self)
        if not path:
            return
        self.reference_display.setText(path)
        selected = self._selected_row_id()
        if selected:
            self._apply_reference(path, [selected])
            self._set_summary(tr("voice.reference.applied_one", name=Path(path).name))
        else:
            applied = self._apply_reference(path, [row.row_id for row in self._model.rows()])
            self._set_summary(tr("voice.reference.applied_all", name=Path(path).name, count=applied))

    def _apply_reference_to_all(self) -> None:
        path = self.reference_display.text().strip()
        if not path:
            self._set_summary(tr("voice.reference.empty_hint"))
            return
        applied = self._apply_reference(path, [row.row_id for row in self._model.rows()])
        self._set_summary(tr("voice.reference.applied_all", name=Path(path).name, count=applied))

    def _clear_reference_clicked(self) -> None:
        selected = self._selected_row_id()
        if not selected:
            self._set_summary(tr("voice.reference.no_selection"))
            return
        self._apply_reference("", [selected])
        self._set_summary(tr("voice.reference.cleared"))

    # —— 输出目录 ——
    def _refresh_output_display(self) -> None:
        self.output_display.setText(self._output_dir())

    def _change_output_dir_clicked(self) -> None:
        directory = choose_output_directory(self, self)
        if not directory:
            return
        set_preference(OUTPUT_DIR_SETTING, directory)
        self._refresh_output_display()
        self._set_summary(tr("voice.output.set", path=directory))

    def _open_output_dir_clicked(self) -> None:
        path = Path(self._output_dir())
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # —— 命名规范模式 ——
    def _selected_row_id(self) -> str:
        index = self.table.currentIndex()
        return self._model.row_id_at(index.row()) if index.isValid() else ""

    def _selected_row_ids(self) -> list[str]:
        row_id = self._selected_row_id()
        if row_id:
            return [row_id]
        return [row.row_id for row in self._model.rows()]

    def _load_spec_clicked(self) -> None:
        """选择规范名单文件（txt）→ 解析校验路径分节 → 应用默认路径并锁定表格。"""

        path, _filter = QFileDialog.getOpenFileName(
            self, tr("voice.spec.load"), "", tr("voice.spec.dialog_filter"),
            options=QFileDialog.Option.DontUseNativeDialog)
        if not path:
            return
        try:
            document = tts_spec.parse_spec_file(Path(path))
            errors = tts_spec.validate_spec_entries(document, self._validator)
        except tts_spec.SpecError as error:
            QMessageBox.critical(self, tr("voice.spec.load"), tr("voice.spec.load_failed", error=str(error)))
            return
        if errors:
            shown = "\n".join(errors[:10])
            if len(errors) > 10:
                shown += tr("voice.spec.more_errors", count=len(errors) - 10)
            QMessageBox.critical(self, tr("voice.spec.load"), tr("voice.spec.invalid", errors=shown))
            return
        self._spec_path = Path(path)
        self._spec_sections = document
        # 换了文件：旧暂存整体作废（各类内容不许跨规范串味）
        self._path_tables.clear()
        stored = str(get_preference(SPEC_SELECTION_KEY, ""))
        preferred = tuple(segment for segment in stored.split("/") if segment)
        new_path = self._resolve_loaded_path(preferred)
        names = list(document.names("/".join(new_path)))
        kept = 0
        if names:
            kept = self._model.apply_spec(names, carry=self._model.table())
        else:  # 防御：校验已保证叶子路径有名单，这里理论上不可达
            self._model.clear_spec()
        set_preference(SPEC_PATH_KEY, path)
        set_preference(SPEC_SELECTION_KEY, "/".join(new_path))
        self._active_path = new_path
        self._sync_spec_ui()
        self._update_summary()
        self._set_summary(tr(
            "voice.spec.applied",
            category=tr(f"voice.spec.category.{new_path[0]}"),
            count=len(list(self._model.rows())),
            kept=kept,
        ))

    def _on_category_clicked(self, index: int) -> None:
        """类别按钮点击（互斥选项键）：路径切到该类，更深选择作废重选。"""

        categories = tts_spec.SPEC_CATEGORIES
        if 0 <= index < len(categories):
            self._select_level(0, categories[index])

    def _on_level_clicked(self, row_index: int, button_id: int) -> None:
        """子层按钮点击：把路径的第 row_index+1 段切到该选项。"""

        options = (
            self._level_options_cache[row_index]
            if row_index < len(self._level_options_cache)
            else []
        )
        if 0 <= button_id < len(options):
            self._select_level(row_index + 1, options[button_id])

    def _select_level(self, depth: int, segment: str) -> None:
        """层级选中（depth 0 = 类别，1~3 = 子层）：路径切到对应段并换表。"""

        if not 0 <= depth <= 3:
            return
        new_path = self._active_path[:depth] + (segment,)
        self._switch_spec_path(new_path)

    def _resolve_loaded_path(self, preferred: tuple[str, ...]) -> tuple[str, ...]:
        """把偏好的路径段对齐到已加载文档：逐段校验存在性，失效层改取第一
        选项；无偏好时从第一类别自动下探到叶子。"""

        document = self._spec_sections
        path: tuple[str, ...] = ()
        while len(path) < tts_spec.MAX_PATH_DEPTH:
            options = document.sub_options(path)
            if not options:
                break
            take = options[0]
            if len(preferred) > len(path) and preferred[len(path)] in options:
                take = preferred[len(path)]
            path = path + (take,)
        if not path:
            path = (tts_spec.SPEC_CATEGORIES[0],)
        return path

    def _switch_spec_path(self, new_path: tuple[str, ...]) -> None:
        """切换激活路径：已加载规范 → 按该路径名单换表；未加载 → 只展开已知层级。

        - 已加载：当前表存入会话路径暂存 → 取目标路径名单对账重建表格
          （暂存命中按名继承内容/会话字段/生成状态/row_id，未命中全新空表）；
        - 未加载规范：表格保持为空，名单仍需加载路径分节 txt；
        - 目标路径在 txt 里没有名单（中间层）→ 表格清空，待选到叶子。
        生成忙碌期间整组按钮已禁用，这里再做一道显式闸（防程序化调用绕过）。
        """

        if self.is_busy or not new_path:
            self._sync_level_rows()
            self._sync_category_buttons()
            return
        if new_path == self._active_path:
            return
        if self._model.spec_names is not None and self._active_path:
            # 模型 apply_spec 会用全新 VoiceTable 重建 self._table：旧对象引用安全
            self._path_tables[self._active_path] = self._model.table()
        document = self._spec_sections
        self._active_path = new_path
        set_preference(SPEC_SELECTION_KEY, "/".join(new_path))
        names = list(document.names("/".join(new_path))) if document else []
        if names:
            kept = self._model.apply_spec(names, carry=self._path_tables.get(new_path))
            self._sync_spec_ui()
            self._set_summary(tr(
                "voice.spec.switched",
                path=" / ".join(self._display_segments(new_path)),
                count=len(names),
                kept=kept,
            ))
            return
        # 未加载规范 / 中间层暂无名单：表格清空解锁，待选到叶子
        self._model.clear_spec()
        self._sync_spec_ui()
        summary_key = (
            "voice.spec.category_preview" if document is None else "voice.spec.path_preview"
        )
        self._set_summary(tr(summary_key, path=" / ".join(self._display_segments(new_path))))

    def _sync_category_buttons(self) -> None:
        """类别按钮可用性与选中态：生成中 → 整组禁用；其余时候可点。

        换表只动模型与偏好、**不碰后端**，故后端装配中（`_backend_pending`）照样可切
        ——否则"进页面后想先挑类别"会白等一次装配。按钮上的提示文案随状态更新：
        禁用时写明原因，可用时说明点选即换表（避免"看着能点、点了没反应"的误解）。
        """

        loaded = self._spec_sections is not None or self._model.spec_names is not None
        enabled = not self.is_busy
        if self.is_busy:
            hint = tr("voice.spec.category.tip_busy")
        elif loaded:
            hint = tr("voice.spec.category.tip")
        else:
            hint = tr("voice.spec.category.tip_need_spec")
        active_category = self._active_path[0] if self._active_path else None
        for category, button in self.category_buttons.items():
            button.setEnabled(enabled)
            button.setChecked(enabled and category == active_category)
            button.setToolTip(hint)

    def _sync_level_rows(self) -> None:
        """逐层重建子层按钮行：选项来自已加载 txt 的路径段；未加载 txt 时
        按 `SUBLEVEL_SCHEMA` 用内置常量预览（国家行 → 情绪/成员行，深度
        随官方结构自适应）；情绪所在行尾挂「多情绪共用一份音频」勾选框。"""

        document = self._spec_sections
        category = self._active_path[0] if self._active_path else None
        schema = tts_spec.SUBLEVEL_SCHEMA.get(category or "", ())
        emotion_row = next(
            # 情绪行号 = 情绪在 schema 里的下标（row r 展示
            # path[r+1] 段的选项）——曾误写 index+1：tank 勾选框挂到成员行、
            # ship 勾选框随导航顺序时有时无（复核实验实测）。
            (index for index, kind in enumerate(schema) if kind == "emotions"), -1
        )
        for row_index in range(3):
            bar = self.level_rows[row_index]
            group = self.level_groups[row_index]
            for button in self.level_buttons[row_index].values():
                group.removeButton(button)
                bar.layout().removeWidget(button)
                button.deleteLater()
            self.level_buttons[row_index] = {}
            if len(self._active_path) <= row_index:
                options: tuple[str, ...] = ()
                visible = False
            elif document is not None:
                options = document.sub_options(self._active_path[: row_index + 1])
                visible = bool(options)
            else:
                # 未加载 txt：按官方结构用内置常量逐层预览（更深各行随选择展开）
                kind = schema[row_index] if row_index < len(schema) else ""
                if kind == "countries":
                    options = tts_spec.CATEGORY_COUNTRIES.get(category or "", ())
                elif kind == "emotions":
                    options = tts_spec.EMOTION_VALUES.get(category or "", ())
                elif kind == "members":
                    options = tts_spec.CATEGORY_MEMBERS.get(category or "", ())
                else:  # vws 的 groups 在常量里归入 countries 预览
                    options = tts_spec.CATEGORY_COUNTRIES.get(category or "", ())
                visible = bool(options)
            self._level_options_cache[row_index] = list(options)
            flow = bar.layout()
            if row_index == emotion_row:
                flow.addWidget(self.emotion_shared_checkbox)
            checked = (
                self._active_path[row_index + 1] if len(self._active_path) > row_index + 1 else None
            )
            for option_index, option in enumerate(options):
                button = QPushButton(option)
                button.setProperty("audioNavigation", True)  # 复用选中态高亮样式
                button.setCheckable(True)
                button.setChecked(option == checked)
                group.addButton(button, option_index)
                self.level_buttons[row_index][option] = button
                flow.addWidget(button)
            bar.setVisible(visible)
        if emotion_row < 0 or not self._active_path:
            # 无情绪层的类别（或尚未选类别）：勾选框随行隐藏
            self.emotion_shared_checkbox.setParent(None)

    def _on_emotion_shared_toggled(self, checked: bool) -> None:
        """情绪共用勾选：勾选 = 一份音频服务该类别全部情绪（生成一份，后续
        推送时覆盖全部情绪目录）；不勾 = 每个情绪各自生成一份。只记录语义
        与偏好，不改变当前表格。"""

        self._emotion_shared = checked
        set_preference(EMOTION_SHARED_KEY, "1" if checked else "0")

    def _display_segments(self, path: tuple[str, ...]) -> list[str]:
        """路径的展示段：类别段用中文名，其余段按 txt 原文。"""

        if not path:
            return []
        return [tr(f"voice.spec.category.{path[0]}"), *path[1:]]

    def _spec_label_text(self) -> str:
        """规范状态文案：类别中文名 · 行数 · 文件名（未加载规范时给提示）。"""

        spec_names = self._model.spec_names
        if spec_names is None or not self._active_path:
            return tr("voice.spec.none")
        name = self._spec_path.name if self._spec_path else "—"
        return tr(
            "voice.spec.active",
            category=tr(f"voice.spec.category.{self._active_path[0]}"),
            count=len(spec_names),
            name=name,
        )

    def _sync_spec_ui(self) -> None:
        """按规范状态刷新常驻标签、生成按钮、类别与子层按钮可用性。"""

        spec_names = self._model.spec_names
        self.spec_label.setText(self._spec_label_text())
        self.generate_button.setEnabled(spec_names is not None and not self.is_busy)
        self._sync_category_buttons()
        self._sync_level_rows()

    def _spec_mismatch(self) -> bool:
        """生成前置对账（防绕过双保险）：行数与名字序列必须与规范一致。"""

        spec_names = self._model.spec_names
        if spec_names is None:
            return True
        current = [row.name for row in self._model.rows()]
        return current != list(spec_names)

    # —— 生成 ——
    def _start_regeneration_for_stale(self) -> None:
        stale = [
            row.row_id
            for row in self._model.rows()
            if (row.needs_regeneration or row.artifact is ArtifactState.MISSING)
            and not row.skip_generation
        ]
        if stale:
            self._start_generation(stale)

    def _start_generation(self, row_ids: Sequence[str]) -> None:
        if self.is_busy or not row_ids:
            return
        if self._model.spec_names is None:
            self._set_summary(tr("voice.spec.required"))
            return
        if self._spec_mismatch():
            # 防绕过双保险：模型层锁 + 生成前置对账（行数与名字序列必须一致）
            self._set_summary(tr("voice.spec.mismatch"))
            return
        requires_reference = bool(
            getattr(getattr(self._runner, "backend", None), "requires_reference_audio", False)
        )
        requests: list[TtsRequest] = []
        rejected = 0
        skipped = 0
        adopted = 0
        for row_id in row_ids:
            row = self._model.table().row(row_id)
            if row is None:
                continue
            if row.skip_generation:
                # "不用生成"：批量流程整行跳过，不发 TTS、不改状态
                skipped += 1
                continue
            if row.imported_audio:
                # 自备音频：拷贝进输出目录并按产物登记，占位即"生成完成"
                if self._adopt_imported_audio(row):
                    adopted += 1
                continue
            result = self._validator.validate(row.name, existing=())
            if not result.ok:
                self._set_summary(tr(result.i18n_key))
                continue
            row.name = result.normalized[: -len(self._validator.profile.extension)]
            if requires_reference and not row.voice.strip():
                # api_v2 对 ref_audio_path 是硬要求：发送前拦截，给出可读失败（省一次必败的 HTTP）
                row.job = JobState.FAILED
                row.error_code = "reference_missing"
                row.error_message = tr("voice.preflight.reference_missing")
                self._model.refresh_row(row_id)
                rejected += 1
                continue
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
            if rejected:
                self._set_summary(tr("voice.preflight.rejected", count=rejected))
            elif adopted or skipped:
                self._set_summary(
                    tr("voice.gen.partitioned", adopted=adopted, skipped=skipped))
            return
        if rejected:
            self._set_summary(tr("voice.preflight.rejected", count=rejected))
        self._cancel.clear()
        self._worker = threading.Thread(
            target=self._run_requests, args=(requests,), name="voice-batch", daemon=True
        )
        self._worker.start()
        self.generate_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        # 生成忙碌期间整组类别按钮禁用：切换会换表，不能发生在生成中
        self._sync_category_buttons()

    def _output_path(self, row: VoiceRow) -> Path:
        root = Path(self._output_dir())
        name = row.name or row.row_id
        return root / f"{name}{self._validator.profile.extension}"

    def _output_dir(self) -> str:
        """输出目录：偏好可配置并持久化；未设置时回退项目内 temp/voice-output（M1 默认）。"""

        configured = get_preference(OUTPUT_DIR_SETTING, "")
        if configured:
            return str(configured)
        from app.paths import temp_dir

        return str(temp_dir() / "voice-output")

    # —— 自备音频 / 不用生成 / 进入处理 ——

    def _import_audio_row(self, row_id: str) -> None:
        """导入列：为该行挑选自备音频；生成时直接采用，不经 TTS。"""
        row = self._model.table().row(row_id)
        if row is None or self.is_busy:
            return
        start_dir = str(Path(row.imported_audio).parent) if row.imported_audio else ""
        path, _ = QFileDialog.getOpenFileName(
            self, tr("voice.import.dialog"), start_dir,
            "Audio (*.wav *.flac *.mp3 *.ogg *.m4a *.aac *.opus)",
            options=QFileDialog.Option.DontUseNativeDialog)  # 原生框堆损坏坑，见 default_audio_picker 登记
        if not path:
            return
        row.imported_audio = path
        try:
            row.duration_ms = FfmpegLocator.probe_duration_ms(Path(path))
        except (OSError, RuntimeError, ValueError):
            pass  # 时长探测失败不拦导入；采用时再探一次
        self._model.refresh_row(row_id)
        self._update_summary()

    def _adopt_imported_audio(self, row: VoiceRow) -> bool:
        """导入音频的"生成"：拷进输出目录并按产物口径登记（与 _apply_result 对齐）。

        音频文件 MB 量级，GUI 线程同步拷贝可接受（与一次试听解码同量级）。"""
        source = Path(row.imported_audio)
        if not source.is_file():
            row.job = JobState.FAILED
            row.error_code = "import_missing"
            row.error_message = tr("voice.import.missing")
            self._model.refresh_row(row.row_id)
            return False
        target = self._output_path(row)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        digest = hashlib.sha256()
        with target.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        try:
            duration_ms = FfmpegLocator.probe_duration_ms(target)
        except (OSError, RuntimeError, ValueError):
            duration_ms = row.duration_ms
        row.job = JobState.IDLE
        row.artifact = ArtifactState.CURRENT
        row.spec_hash = row.compute_spec_hash(self._model.table().key_id)
        row.output_hash = digest.hexdigest()
        row.audio_path = str(target)
        row.duration_ms = duration_ms
        row.error_code = ""
        row.error_message = ""
        self._model.refresh_row(row.row_id)
        return True

    def _process_row(self, row_id: str) -> None:
        """进行处理：弹出该行音频的编辑小窗，保存后按产物口径回登记。

        音频解析顺序：生成产物优先（audio_path），导入源兜底；保存目标
        始终是该行产物路径（_output_path），用户的导入源文件不被覆盖。"""
        row = self._model.table().row(row_id)
        if row is None:
            return
        path = next(
            (item for item in (row.audio_path, row.imported_audio)
             if item and Path(item).is_file()), "")
        if not path:
            self._set_summary(tr("voice.process.no_audio"))
            return
        dialog = KokoroTsurumaki(path, self._output_path(row), self)
        dialog.saved.connect(
            lambda target, row_id=row_id: self._register_processed_audio(row_id, Path(target)))
        dialog.exec()
        # 小窗以页面为父，exec 返回后 C++ 对象随父存活——不删则
        # 每次打开累积一份 QMediaPlayer/时间轴等重对象
        dialog.deleteLater()

    def _register_processed_audio(self, row_id: str, target: Path) -> None:
        """处理保存的回登记：与 _apply_result / _adopt_imported_audio 同口径。"""
        row = self._model.table().row(row_id)
        if row is None or not target.is_file():
            return
        digest = hashlib.sha256()
        with target.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        try:
            duration_ms = FfmpegLocator.probe_duration_ms(target)
        except (OSError, RuntimeError, ValueError):
            duration_ms = row.duration_ms
        row.job = JobState.IDLE
        row.artifact = ArtifactState.CURRENT
        row.spec_hash = row.compute_spec_hash(self._model.table().key_id)
        row.output_hash = digest.hexdigest()
        row.audio_path = str(target)
        row.duration_ms = duration_ms
        row.error_code = ""
        row.error_message = ""
        self._model.refresh_row(row_id)
        self._set_summary(tr("voice.process.saved_summary"))

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
                if not ok and "weight failed" in message:
                    # 上游 400 只说 "change sovits weight failed"：
                    # 版本错配（CPUFast 不吃 v3/v4）是最常见根因，就地给本地化
                    # 建议；服务层保持零 Qt 依赖，提示组装放 UI 层（GSV 兼容 P1）
                    message = f"{message}。{tr('voice.gsv.weight_version_hint')}"
                self._set_summary(
                    tr("voice.weights.applied") if ok else tr("voice.weights.failed", message=str(message))
                )
            elif kind == "manifest_progress":
                if not isinstance(payload, tuple) or len(payload) != 3:
                    continue
                done, total, current = payload
                if not isinstance(done, int) or not isinstance(total, int) or not isinstance(current, str):
                    continue
                self._set_summary(tr("voice.manifest.progress", done=done, total=total, name=current))
            elif kind == "manifest_done":
                self._manifest_busy = False
                self.export_manifest_action.setEnabled(True)
                self.verify_package_action.setEnabled(True)
                self._set_summary(str(payload))
            elif kind == "done":
                self._worker = None
                self._sync_spec_ui()
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
        # 禁用时摘掉 ▾/▸ 箭头：无箭头 + 灰字，一眼看出"现在展不开"，
        # 而不是"看着能点却没反应"（用户反馈同源问题的顺带收口）
        arrow = ""
        if self.params_toggle.isEnabled():
            arrow = "▾ " if self.params_toggle.isChecked() else "▸ "
        self.params_toggle.setText(f"{arrow}{tr('voice.params.toggle')}")

    # —— 微调模型选择（训练产物 → 推理热切换）——
    def refresh_finetuned_models(self) -> int:
        """扫描 GPT-SoVITS 训练产物并重建下拉；返回发现的实验数。

        只遍历本地的小目录（logs/ 与权重目录），GUI 线程执行可接受；重建期间屏蔽
        选中信号，保持与输入框当前值匹配的项不被打断。
        """

        combo = self.finetuned_combo
        current = (self.gpt_weights_input.text().strip(), self.sovits_weights_input.text().strip())
        models = training.discover_finetuned_weights(gsv_root())
        combo.blockSignals(True)
        combo.clear()
        for model in models:
            combo.addItem(self._finetuned_label(model), (model.gpt_path, model.sovits_path))
            combo.setItemData(
                combo.count() - 1,
                tr("voice.weights.tooltip", gpt=model.gpt_path or "—", sovits=model.sovits_path or "—"),
                Qt.ItemDataRole.ToolTipRole,
            )
        if not models:
            combo.addItem(tr("voice.weights.none"), None)
        matched = -1
        for position in range(combo.count()):
            if combo.itemData(position) == current:
                matched = position
                break
        combo.setCurrentIndex(max(matched, 0))
        combo.blockSignals(False)
        return len(models)

    def _finetuned_label(self, model: training.FinetunedWeights) -> str:
        if model.complete:
            return model.name
        missing = "SoVITS" if model.gpt_path else "GPT"
        return f"{model.name}{tr('voice.weights.partial', part=missing)}"

    def _scan_finetuned_clicked(self) -> None:
        count = self.refresh_finetuned_models()
        if count:
            self._set_summary(tr("voice.weights.found", count=count))
        else:
            self._set_summary(tr("voice.weights.none_found"))

    def _on_finetuned_selected(self, index: int) -> None:
        """选中一个微调模型：把两条权重路径回填输入框（仍需点「应用权重」才热切换）。"""

        data = self.finetuned_combo.itemData(index)
        if not isinstance(data, tuple):
            return
        gpt_path, sovits_path = data
        if gpt_path:
            self.gpt_weights_input.setText(gpt_path)
        if sovits_path:
            self.sovits_weights_input.setText(sovits_path)
        self._set_summary(tr("voice.weights.picked", name=self.finetuned_combo.itemText(index)))

    # —— GSV 服务切换（多分支兼容 P2）——
    def refresh_gsv_services(self) -> None:
        """把注册表快照刷进参数面板的服务下拉框。"""

        profiles, active_id = gsv_services.registry_snapshot()
        self.params_panel.set_services(profiles, active_id)

    def _on_gsv_service_changed(self, profile_id: str) -> None:
        """用户切换 GSV 服务：持久化 active 档并复用模型装配链路重连。"""

        try:
            gsv_services.set_active(profile_id)
        except KeyError:
            self.refresh_gsv_services()  # 幽灵档（注册表已变）：回拉真实状态
            return
        self.model_switch_requested.emit(self.MODEL_GPT)

    def _manage_gsv_services(self) -> None:
        """打开服务管理对话框：确认后落盘注册表并按需重连。"""

        from app.widgets.gsv_service_dialog import MisumiUika

        profiles, active_id = gsv_services.registry_snapshot()
        dialog = MisumiUika(profiles, active_id, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_profiles, new_active = dialog.result_profiles()
        gsv_services.replace_all(new_profiles, new_active)
        self.refresh_gsv_services()
        if new_active != active_id:
            self.model_switch_requested.emit(self.MODEL_GPT)

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
        # GSV 兼容 P3/E5：CPUFast 服务 + v3/v4 权重（版本目录段判定，路径
        # 手输与下拉同权）→ 确认框软拦截，可强行尝试（方言推断可能失准）
        capabilities = getattr(backend, "capabilities", None)
        if (
            capabilities is not None
            and capabilities.docs_ok
            and capabilities.dialect_hint == "cpufast"
            and (
                training.weight_version_is_v3v4(training.weight_version_root(gpt_path))
                or training.weight_version_is_v3v4(training.weight_version_root(sovits_path))
            )
        ):
            answer = QMessageBox.question(
                self,
                tr("voice.gsv.weight_version_confirm_title"),
                tr("voice.gsv.weight_version_confirm_body"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
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
        self.refresh_finetuned_models()

    def set_backend_pending(self) -> None:
        """后端装配中：探活与拉起推理服务都可能阻塞（数秒到上百秒），由后台线程进行；
        本方法只负责禁用生成并给出提示，界面不阻塞。"""

        self._backend_pending = True
        self.generate_button.setEnabled(False)
        self._sync_category_buttons()  # 只刷新按钮提示文案（类别切换不依赖后端）
        self.params_toggle.setEnabled(False)
        self._update_params_toggle_text()  # 摘掉箭头：禁用态一眼可辨
        self.weights_holder.setVisible(False)
        self._set_summary(tr("voice.backend.connecting"))
    def set_backend(self, backend: TtsBackend) -> None:
        """切换推理后端（路由侧按模型选择装配；切换时重建串行执行器）。

        演示回退（fake）时只保持用户选择的模型/渠道面板（服务离线不悄悄翻回
        本地面板，摘要行给出演示模式提示），其余行为与真后端一致。
        """

        self._backend_pending = False
        self.params_toggle.setEnabled(True)  # 装配结束恢复「推理参数」折叠头（并带回箭头）
        self._update_params_toggle_text()
        self._runner = SerialTtsRunner(backend)
        name = getattr(backend, "name", type(backend).__name__)
        self.params_panel.set_backend_kind(name)
        # GSV 兼容 P2：能力快照推送面板（高级区可用性 + 方言提示）；
        # 非 GSV 后端 / 探测失败 → None → 面板回到基线提示
        capabilities = getattr(backend, "capabilities", None)
        self.params_panel.set_gsv_capabilities(
            capabilities if capabilities is not None and capabilities.docs_ok else None
        )
        if name == "fake":
            if self._model_kind.startswith("api:"):
                self._model_panes.setCurrentIndex(2)
            elif self._model_kind == self.MODEL_COSY:
                self._model_panes.setCurrentIndex(1)
            else:
                self._model_panes.setCurrentIndex(0)
            is_gpt_kind = self._model_kind in (self.MODEL_GPT, self.MODEL_GPT_CPUFAST)
            self.weights_holder.setVisible(is_gpt_kind)
            if is_gpt_kind:
                self.refresh_finetuned_models()
            self._sync_spec_ui()
            self._set_summary(tr("voice.backend.demo"))
            return
        # 面板往返曾无条件回落 MODEL_GPT：CPUFast 入口装配真实
        # GSV 后端后按钮会被翻回官方包入口（第三入口轮修复）
        gsv_kind = (
            self._model_kind
            if self._model_kind in (self.MODEL_GPT, self.MODEL_GPT_CPUFAST)
            else self.MODEL_GPT
        )
        self.set_model_kind(self.MODEL_COSY if self.params_panel.backend_kind == BACKEND_COSY else gsv_kind)
        self.weights_holder.setVisible(self.params_panel.backend_kind == BACKEND_GPT)
        if self.params_panel.backend_kind != BACKEND_COSY:
            self.refresh_finetuned_models()
        self._sync_spec_ui()
        summary = tr("voice.backend.ready", name=name)
        if capabilities is not None and capabilities.docs_ok:
            # 方言提示随连接结果落摘要行（设计 §5.5）
            summary += " · " + tr(f"voice.gsv.dialect.{capabilities.dialect_hint}")
        self._set_summary(summary)

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
        # 禁行行必须从生成统计三桶（完成/待重生成/未完成）整桶
        # 退出、单独计入"禁止生成"——曾只追加后缀，pending/stale 的数学仍把
        # 禁行算进去，勾选后"未完成"纹丝不动，与登记意图相悖
        done = sum(
            1 for row in rows
            if row.artifact is ArtifactState.CURRENT and not row.skip_generation
        )
        stale = sum(
            1 for row in rows
            if row.needs_regeneration and not row.skip_generation
        )
        skipped = sum(1 for row in rows if row.skip_generation)
        pending = len(rows) - done - stale - skipped
        text = tr("voice.summary.counts", total=len(rows), done=done, stale=stale, pending=max(0, pending))
        if skipped:
            # 禁止生成的行不再混进"未完成"计数：汇总必须反映勾选状态
            text += tr("voice.summary.skipped", skipped=skipped)
        if HASH_BACKEND != "vtcore":
            # 无扩展时 `.vt` 工程读写整体不可用：这条提示必须常驻，不能被统计文案覆盖
            text = f"{tr('voice.project.no_backend')}｜{text}"
        self._set_summary(text)

    def retranslate(self) -> None:
        super().retranslate()
        self.train_module_button.setText(i18n_text("voice.module.train"))
        self.generation_module_button.setText(i18n_text("voice.module.generation"))
        self.gpt_model_button.setText(i18n_text("voice.model.gpt"))
        self.cpufast_model_button.setText(i18n_text("voice.model.cpufast"))
        self.cosy_model_button.setText(i18n_text("voice.model.cosy"))
        self.model_kind_label.setText(tr("voice.model.kind"))
        self.refresh_api_channels()
        if self._model_kind.startswith("api:"):
            # API 信息面板的动态行前缀也要随语言刷新（值是数据保留）
            self._update_api_pane(self._model_kind.split(":", 1)[1])
        self._update_module_cards_language()
        self.spec_button.setText(tr("voice.spec.load"))
        for category, button in self.category_buttons.items():
            button.setText(tr(f"voice.spec.category.{category}"))
        self.emotion_shared_checkbox.setText(i18n_text("voice.spec.emotion_shared"))
        self.emotion_shared_checkbox.setToolTip(i18n_text("voice.spec.emotion_shared_tip"))
        self._sync_spec_ui()
        self.generate_button.setText(tr("voice.action.generate_selected"))
        self.regenerate_all_button.setText(tr("voice.action.generate_stale"))
        self.stop_button.setText(tr("voice.action.stop"))
        self.more_button.setText(tr("voice.action.more"))
        for action, key in self._more_actions:
            action.setText(tr(key))
        self.reference_label.setText(tr("voice.reference.label"))
        self.reference_display.setPlaceholderText(tr("voice.reference.empty"))
        self.reference_display.setToolTip(tr("voice.reference.empty_tip"))
        self.reference_pick_button.setText(tr("voice.reference.pick"))
        self.reference_apply_all_button.setText(tr("voice.reference.apply_all"))
        self.reference_clear_button.setText(tr("voice.reference.clear"))
        self.output_label.setText(tr("voice.output.label"))
        self.output_display.setToolTip(tr("voice.output.tooltip"))
        self.output_change_button.setText(tr("voice.output.change"))
        self.output_open_button.setText(tr("voice.output.open"))
        self.apply_weights_button.setText(tr("voice.weights.apply"))
        self.gpt_weights_input.setPlaceholderText(tr("voice.weights.gpt_hint"))
        self.sovits_weights_input.setPlaceholderText(tr("voice.weights.sovits_hint"))
        self.finetuned_label.setText(tr("voice.weights.finetuned"))
        self.scan_weights_button.setText(tr("voice.weights.scan"))
        if self.finetuned_combo.count() == 1 and self.finetuned_combo.itemData(0) is None:
            self.finetuned_combo.setItemText(0, tr("voice.weights.none"))
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
        if self._model.spec_names is None:
            # 表格规范化：.vt 的行集合必须服从规范名单，未加载规范一律拒绝
            # （顺序在容器解析之后：损坏文件无论规范如何都打不开）
            return tr("voice.spec.vt_requires_spec")
        kept = self._model.apply_spec(self._model.spec_names or (), carry=table)
        dropped = len(table.rows) - kept
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
            detail = tr("voice.spec.vt_open_summary", kept=kept, dropped=dropped) if dropped else ""
            return (tr("voice.open.vt_readonly", name=path.name, count=len(table.rows)) + (" " + detail if detail else ""))
        self._project_file = path
        self.unlock_action.setEnabled(False)
        self._update_summary()
        detail = tr("voice.spec.vt_open_summary", kept=kept, dropped=dropped) if dropped else ""
        return (tr("voice.open.vt_editable", name=path.name, count=len(table.rows)) + (" " + detail if detail else ""))

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

    def export_manifest(
        self, package_dir: Path, *, seed_hex: str = "", progress=None, table_spec_hash: str | None = None
    ) -> str:
        """为整包目录生成 `.vtmanifest`（`seed_hex` 非空则签名）；返回状态文案。

        本方法只做纯计算，可在工作线程调用；界面动线走 `_start_manifest_work`。
        `table_spec_hash` 缺省时在调用线程现算（工作线程动线请由主线程先算好传入，
        避免工作线程触碰 GUI 侧模型）。
        """

        if HASH_BACKEND != "vtcore":
            return tr("voice.export.unavailable")
        if table_spec_hash is None:
            table_spec_hash = self._model.table().spec_hash()
        try:
            manifest = vt_manifest.build_manifest(
                package_dir, table_spec_hash=table_spec_hash, seed_hex=seed_hex, progress=progress
            )
            path = vt_manifest.write_manifest(package_dir, manifest)
        except (OSError, ValueError, vt_manifest.ManifestError) as error:
            return tr("voice.manifest.failed", code=str(error).split(":", 1)[0])
        return tr("voice.manifest.exported", name=path.name, count=manifest["file_count"])

    def verify_manifest_package(self, package_dir: Path, *, progress=None) -> str:
        """校验整包（清单签名 + 逐文件哈希 / 字节数）；返回状态文案。"""

        if HASH_BACKEND != "vtcore":
            return tr("voice.export.unavailable")
        try:
            report = vt_manifest.verify_package(package_dir, progress=progress)
        except (OSError, ValueError, vt_manifest.ManifestError) as error:
            return tr("voice.manifest.failed", code=str(error).split(":", 1)[0])
        return tr("voice.manifest.report", summary=report.summary())

    def _start_manifest_work(self, kind: str, package_dir: Path, seed_hex: str = "") -> None:
        """把清单导出/校验放到工作线程（深查 P1-1：整包读盘+哈希可冻结主线程数十秒）。"""

        if self._manifest_busy:
            return
        self._manifest_busy = True
        self.export_manifest_action.setEnabled(False)
        self.verify_package_action.setEnabled(False)
        self._set_summary(tr("voice.manifest.working"))
        # spec_hash 在主线程先算好：工作线程只做纯 IO，不触碰 GUI 侧模型
        spec = self._model.table().spec_hash() if kind == "export" else ""
        worker = threading.Thread(
            target=self._run_manifest_work, args=(kind, package_dir, seed_hex, spec), name="manifest-work", daemon=True
        )
        worker.start()

    def _run_manifest_work(self, kind: str, package_dir: Path, seed_hex: str, spec_hash: str) -> None:
        def progress(done: int, total: int, current: str) -> None:
            self._events.put(("manifest_progress", (done, total, current)))

        message = ""
        try:
            if kind == "export":
                message = self.export_manifest(
                    package_dir, seed_hex=seed_hex, progress=progress, table_spec_hash=spec_hash
                )
            else:
                message = self.verify_manifest_package(package_dir, progress=progress)
        finally:
            # 两个入口已把已知失败集转成状态文案；空文案 = 意外异常（threading.excepthook
            # 已留痕），这里仍必须把 done 事件发回去恢复界面状态（§4.4：失败转成信号）
            self._events.put(("manifest_done", message or tr("voice.manifest.failed", code="internal")))

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
        self._start_manifest_work("export", Path(directory), seed_hex=seed_hex)

    def _verify_package_clicked(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, tr("voice.manifest.choose"), self._output_dir())
        if not directory:
            return
        self._start_manifest_work("verify", Path(directory))


    # —— 持久化 ——
    def _project_path(self) -> Path:
        """当前工程文件：打开过就写回该文件；否则用项目内默认工作文件 `voice_project.vt`。"""

        if self._project_file is not None:
            return self._project_file

        from app.paths import temp_dir

        return temp_dir() / "voice-output" / "voice_project.vt"

    def _load_existing_project(self) -> None:
        """启动装配：先恢复上次命名规范（含激活类别），再把默认 `.vt` 对账进规范。

        - 未加载规范（无偏好/文件丢失/校验失败）→ **空表启动**（表格规范化后
          不再无条件载旧工程），摘要行说明原因；
        - 规范在 → 读默认 `.vt` 为旧表（可缺失），按**激活节**名单对账继承内容
          （`.vt` 仍只承载当前激活类；会话暂存启动时为空）。
        """

        restored = self._restore_spec_from_preference()
        old_table: VoiceTable | None = None
        old_state_applied = False
        if HASH_BACKEND == "vtcore":
            path = self._project_path()
            if path.exists():
                try:
                    old_table, info = vt_project.container_to_table(path)
                except (OSError, ValueError, vt_project.VtProjectError):
                    old_table = None
                else:
                    old_state_applied = bool(info["applied"])
                    self._project_view = path
                    self.set_lock_state(path)
                    if info["locked"]:
                        self._project_file = None
                        self.unlock_action.setEnabled(True)
                    else:
                        self._project_file = path
        if restored is None or not restored:
            self._sync_spec_ui()
            self._update_summary()
            return
        self._active_path = restored
        names = list(self._spec_sections.names("/".join(restored)))
        if names:
            self._model.apply_spec(names, carry=old_table)
        else:  # 防御：校验保证叶子路径有名单，这里理论上不可达
            self._model.clear_spec()
        if old_table is not None and old_state_applied:
            for row in self._model.rows():
                self._model.refresh_row(row.row_id)
        self._sync_spec_ui()
        self._update_summary()

    def _restore_spec_from_preference(self) -> tuple[str, ...]:
        """从偏好恢复上次规范与路径选择；不可用（缺失/损坏）时摘要说明并返回空路径。"""

        stored = get_preference(SPEC_PATH_KEY, "")
        if not stored:
            return ()
        path = Path(str(stored))
        if not path.is_file():
            self._set_summary(tr("voice.spec.autoload_missing", name=path.name))
            return ()
        try:
            document = tts_spec.parse_spec_file(path)
            errors = tts_spec.validate_spec_entries(document, self._validator)
        except tts_spec.SpecError as error:
            self._set_summary(tr("voice.spec.autoload_failed", error=str(error)))
            return ()
        if errors:
            self._set_summary(tr("voice.spec.autoload_failed", error=errors[0]))
            return ()
        self._spec_path = path
        self._spec_sections = document
        stored_selection = str(get_preference(SPEC_SELECTION_KEY, ""))
        preferred = tuple(segment for segment in stored_selection.split("/") if segment)
        return self._resolve_loaded_path(preferred)

    def _on_save_failed(self, message: str) -> None:
        """自动保存失败（工程被锁定 / 缺扩展 / 磁盘错误）→ 状态栏显示可读文案。"""

        self._set_summary(tr("voice.project.save_failed", code=str(message).split(":", 1)[0]))


def choose_output_directory(page: VoiceBatchPage, parent: QWidget) -> str:
    """工具栏外的目录选择小工具（保留给后续接入；当前由偏好决定输出目录）。"""

    directory = QFileDialog.getExistingDirectory(parent, tr("voice.choose_output"), page._output_dir())
    return directory



