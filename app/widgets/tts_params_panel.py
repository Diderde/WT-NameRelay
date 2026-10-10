# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""推理参数面板：把后端支持的合成参数暴露到界面。

契约要点 —— `TtsRequest.params` 会**原样透传**给后端：
GPT-SoVITS `api_v2.py` 的 `/tts`（`GptSovitsBackend.build_payload` 把 `params` 合并进请求体），
CosyVoice 3 shim 的 `/synthesize`（接受 `speed`）。字段按当前后端切换可见性。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.i18n import i18n_text, tr

BACKEND_GPT = "gpt-sovits"
BACKEND_COSY = "cosyvoice3-gguf"
BACKEND_FAKE = "fake"

#: GPT-SoVITS `text_split_method` 取值（api_v2 契约）
TEXT_SPLIT_METHODS = ("cut0", "cut1", "cut2", "cut3", "cut4", "cut5")
#: 参考文本语言：`auto` 表示不发送，交由后端按行语言处理
PROMPT_LANGS = ("auto", "zh", "en", "ja", "ko")

#: use_cuda_graph 三态的枚举位（对应下拉行索引）
CUDA_GRAPH_FOLLOW = 0
CUDA_GRAPH_ON = 1
CUDA_GRAPH_OFF = 2


class TtsParamsPanel(QWidget):
    """推理参数表单：产出可直接塞进 `TtsRequest.params` 的字典。"""

    #: 用户在服务下拉框里切换 GSV 推理服务（页面据此触发重装配）
    service_change_requested = Signal(str)
    #: 用户请求打开服务管理对话框
    service_manage_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._backend_kind = BACKEND_GPT
        self._capabilities = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self._hint = QLabel(i18n_text("voice.params.hint"))
        self._hint.setObjectName("mutedLabel")
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

        # 标题由 set_backend_kind 按后端给出（"voice.params.title" 键并不存在，别在这里引用）
        self._group = QGroupBox()
        form = QFormLayout(self._group)
        form.setLabelAlignment(form.labelAlignment())
        self._form = form

        self.speed_input = QDoubleSpinBox()
        self.speed_input.setRange(0.5, 2.0)
        self.speed_input.setSingleStep(0.05)
        self.speed_input.setDecimals(2)
        self.speed_input.setValue(1.0)

        self.seed_fixed = QCheckBox(i18n_text("voice.params.seed_fixed"))
        self.seed_fixed.setChecked(False)
        self.seed_input = QSpinBox()
        self.seed_input.setRange(0, 2_147_483_647)
        self.seed_input.setValue(0)
        self.seed_input.setEnabled(False)
        self.seed_fixed.toggled.connect(self.seed_input.setEnabled)

        self.top_k_input = QSpinBox()
        self.top_k_input.setRange(1, 100)
        self.top_k_input.setValue(15)
        self.top_p_input = QDoubleSpinBox()
        self.top_p_input.setRange(0.0, 1.0)
        self.top_p_input.setSingleStep(0.05)
        self.top_p_input.setDecimals(2)
        self.top_p_input.setValue(1.0)
        self.temperature_input = QDoubleSpinBox()
        self.temperature_input.setRange(0.0, 2.0)
        self.temperature_input.setSingleStep(0.05)
        self.temperature_input.setDecimals(2)
        self.temperature_input.setValue(1.0)

        self.split_input = QComboBox()
        self.split_input.addItems(TEXT_SPLIT_METHODS)

        self.prompt_text_input = QLineEdit()
        self.prompt_text_input.setPlaceholderText(i18n_text("voice.params.prompt_text_hint"))
        self.prompt_lang_input = QComboBox()
        self.prompt_lang_input.addItems(PROMPT_LANGS)

        # —— GSV 多分支兼容 P2：服务切换 + 分支高级参数（use_cuda_graph/cfg_rate）——
        self._service_combo = QComboBox()
        self._service_combo.setToolTip(i18n_text("voice.gsv.service_tooltip"))
        self._service_combo.activated.connect(self._on_service_activated)
        self._service_manage_button = QPushButton(i18n_text("voice.gsv.manage"))
        self._service_manage_button.setObjectName("clipGhost")
        self._service_manage_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._service_manage_button.clicked.connect(self.service_manage_requested.emit)
        service_holder = QWidget()
        service_layout = QHBoxLayout(service_holder)
        service_layout.setContentsMargins(0, 0, 0, 0)
        service_layout.setSpacing(6)
        service_layout.addWidget(self._service_combo, 1)
        service_layout.addWidget(self._service_manage_button, 0)

        self._cuda_graph_combo = QComboBox()
        self._cuda_graph_combo.addItem(i18n_text("voice.gsv.cuda_follow"))  # 跟随服务端 = 不发送
        self._cuda_graph_combo.addItem(i18n_text("voice.params.on"))
        self._cuda_graph_combo.addItem(i18n_text("voice.params.off"))
        self._cuda_graph_combo.setCurrentIndex(CUDA_GRAPH_FOLLOW)

        self._cfg_rate_input = QLineEdit()
        self._cfg_rate_input.setPlaceholderText(i18n_text("voice.gsv.cfg_rate_hint"))
        # 数字校验：非法输入（如 "0,7"）被拦在输入层，而不是 params() 里
        # 静默忽略——用户会以为发出去了一个值
        validator = QDoubleValidator(0.0, 10.0, 4, self._cfg_rate_input)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self._cfg_rate_input.setValidator(validator)
        self._cfg_rate_input.setPlaceholderText(i18n_text("voice.gsv.cfg_rate_hint"))

        self._dialect_label = QLabel()
        self._dialect_label.setObjectName("mutedLabel")
        self._dialect_label.setWordWrap(True)

        self._rows: dict[str, tuple[QWidget, QWidget]] = {}
        self._add_row("speed", self.speed_input, i18n_text("voice.params.speed"))
        self._add_row("seed", self._seed_row(), i18n_text("voice.params.seed"))
        self._add_row("top_k", self.top_k_input, i18n_text("voice.params.top_k"))
        self._add_row("top_p", self.top_p_input, i18n_text("voice.params.top_p"))
        self._add_row("temperature", self.temperature_input, i18n_text("voice.params.temperature"))
        self._add_row("split", self.split_input, i18n_text("voice.params.text_split"))
        self._add_row("prompt_text", self.prompt_text_input, i18n_text("voice.params.prompt_text"))
        self._add_row("prompt_lang", self.prompt_lang_input, i18n_text("voice.params.prompt_lang"))
        self._add_row("service", service_holder, i18n_text("voice.gsv.service"))
        self._add_row("cuda_graph", self._cuda_graph_combo, i18n_text("voice.gsv.advanced_cuda"))
        self._add_row("cfg_rate", self._cfg_rate_input, i18n_text("voice.gsv.cfg_rate"))
        self._add_row("dialect", self._dialect_label, i18n_text("voice.gsv.dialect"))
        root.addWidget(self._group)

        self.set_backend_kind(BACKEND_GPT)

    # —— 构建辅助 ——
    def _seed_row(self) -> QWidget:
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.seed_fixed)
        layout.addWidget(self.seed_input)
        return holder

    def _add_row(self, key: str, field: QWidget, label_text: str) -> None:
        label = QLabel(label_text)
        self._form.addRow(label, field)
        self._rows[key] = (label, field)

    # —— 契约 ——
    @property
    def backend_kind(self) -> str:
        return self._backend_kind

    def set_backend_kind(self, kind: str) -> None:
        """按后端切换可见字段：CosyVoice 只支持固定随机种子（不支持语速），其余为 GPT-SoVITS 专属。"""

        self._backend_kind = kind
        # 只有 CosyVoice 走另一套字段；演示后端沿用 GPT-SoVITS 字段（参数会被忽略）
        gpt_only = kind != BACKEND_COSY
        for key, (label, field) in self._rows.items():
            if key == "seed":
                visible = True  # 两种后端都支持固定随机种子
            elif key in ("service", "cuda_graph", "cfg_rate", "dialect"):
                visible = gpt_only  # GSV 服务与分支高级参数：GPT-SoVITS 专属
            else:
                # 含 speed：CosyVoice 3 运行时没有语速旋钮，展示假控件会误导
                visible = gpt_only
            label.setVisible(visible)
            field.setVisible(visible)
        self._group.setTitle(
            i18n_text("voice.params.title_gpt") if gpt_only else i18n_text("voice.params.title_cosy")
        )

    # —— GSV 服务与能力（P2）——
    def set_services(self, profiles, active_id: str) -> None:
        """刷新服务下拉框（程序化设置不发切换信号）。"""

        self._service_combo.blockSignals(True)
        self._service_combo.clear()
        for profile in profiles:
            self._service_combo.addItem(profile.name, profile.profile_id)
        index = self._service_combo.findData(active_id)
        if index >= 0:
            self._service_combo.setCurrentIndex(index)
        self._service_combo.blockSignals(False)

    def _on_service_activated(self, index: int) -> None:
        profile_id = self._service_combo.itemData(index)
        if profile_id:
            self.service_change_requested.emit(str(profile_id))

    def set_gsv_capabilities(self, capabilities) -> None:
        """按能力快照驱动高级区可用性与方言提示（None/未识别 = 基线模式）。

        capabilities 鸭子类型：docs_ok / dialect_hint / supports(field)。
        """

        self._capabilities = capabilities
        recognized = capabilities is not None and capabilities.docs_ok
        self._cuda_graph_combo.setEnabled(recognized and capabilities.supports("use_cuda_graph"))
        self._cfg_rate_input.setEnabled(recognized and capabilities.supports("cfg_rate"))
        if not recognized:
            self._cuda_graph_combo.setToolTip(i18n_text("voice.gsv.disabled_unknown"))
            self._cfg_rate_input.setToolTip(i18n_text("voice.gsv.disabled_unknown"))
            self._dialect_label.setText(i18n_text("voice.gsv.dialect_unknown"))
            return
        self._cuda_graph_combo.setToolTip(i18n_text("voice.gsv.needs_cuda"))
        # cfg_rate 是分支参数、与设备无关——曾复用 needs_cuda
        # （"需 CUDA 设备"）会在 CPU 机器上误导用户不敢填（复核自纠）
        self._cfg_rate_input.setToolTip(i18n_text("voice.gsv.cfg_rate_tip"))
        dialect = capabilities.dialect_hint
        self._dialect_label.setText(
            tr("voice.gsv.dialect_connected", dialect=tr(f"voice.gsv.dialect.{dialect}"))
        )

    def params(self) -> dict[str, object]:
        """产出透传给后端的参数字典（字段名与后端契约一致）。"""

        if self._backend_kind == BACKEND_COSY:
            payload: dict[str, object] = {}
            if self.seed_fixed.isChecked():
                payload["seed"] = self.seed_input.value()
            return payload

        payload: dict[str, object] = {
            "speed_factor": round(self.speed_input.value(), 2),
            "top_k": self.top_k_input.value(),
            "top_p": round(self.top_p_input.value(), 2),
            "temperature": round(self.temperature_input.value(), 2),
            "text_split_method": self.split_input.currentText(),
        }
        if self.seed_fixed.isChecked():
            payload["seed"] = self.seed_input.value()
        prompt_text = self.prompt_text_input.text().strip()
        if prompt_text:
            payload["prompt_text"] = prompt_text
        prompt_lang = self.prompt_lang_input.currentText()
        if prompt_lang != "auto":
            payload["prompt_lang"] = prompt_lang
        # GSV 分支高级参数：跟随服务端/留空 = 不发送；即使误发，后端也会按
        # 能力门控剥除（E3 双保险）
        cuda_index = self._cuda_graph_combo.currentIndex()
        if cuda_index == CUDA_GRAPH_ON:
            payload["use_cuda_graph"] = True
        elif cuda_index == CUDA_GRAPH_OFF:
            payload["use_cuda_graph"] = False
        cfg_text = self._cfg_rate_input.text().strip()
        if cfg_text:
            try:
                payload["cfg_rate"] = float(cfg_text)
            except ValueError:
                pass
        return payload

    def retranslate(self) -> None:
        self._hint.setText(i18n_text("voice.params.hint"))
        self.seed_fixed.setText(i18n_text("voice.params.seed_fixed"))
        self.prompt_text_input.setPlaceholderText(i18n_text("voice.params.prompt_text_hint"))
        self._service_combo.setToolTip(i18n_text("voice.gsv.service_tooltip"))
        self._cuda_graph_combo.setItemText(CUDA_GRAPH_FOLLOW, i18n_text("voice.gsv.cuda_follow"))
        self._cuda_graph_combo.setItemText(CUDA_GRAPH_ON, i18n_text("voice.params.on"))
        self._cuda_graph_combo.setItemText(CUDA_GRAPH_OFF, i18n_text("voice.params.off"))
        self._cfg_rate_input.setPlaceholderText(i18n_text("voice.gsv.cfg_rate_hint"))
        labels = {
            "speed": "voice.params.speed",
            "seed": "voice.params.seed",
            "top_k": "voice.params.top_k",
            "top_p": "voice.params.top_p",
            "temperature": "voice.params.temperature",
            "split": "voice.params.text_split",
            "prompt_text": "voice.params.prompt_text",
            "prompt_lang": "voice.params.prompt_lang",
            "service": "voice.gsv.service",
            "cuda_graph": "voice.gsv.advanced_cuda",
            "cfg_rate": "voice.gsv.cfg_rate",
            "dialect": "voice.gsv.dialect",
        }
        for key, i18n_key in labels.items():
            self._rows[key][0].setText(i18n_text(i18n_key))
        self.set_backend_kind(self._backend_kind)
