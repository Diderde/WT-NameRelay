# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""推理参数面板：把后端支持的合成参数暴露到界面。

契约要点 —— `TtsRequest.params` 会**原样透传**给后端：
GPT-SoVITS `api_v2.py` 的 `/tts`（`GptSovitsBackend.build_payload` 把 `params` 合并进请求体），
CosyVoice 3 shim 的 `/synthesize`（接受 `speed`）。字段按当前后端切换可见性。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.i18n import i18n_text

BACKEND_GPT = "gpt-sovits"
BACKEND_COSY = "cosyvoice3-gguf"
BACKEND_FAKE = "fake"

#: GPT-SoVITS `text_split_method` 取值（api_v2 契约）
TEXT_SPLIT_METHODS = ("cut0", "cut1", "cut2", "cut3", "cut4", "cut5")
#: 参考文本语言：`auto` 表示不发送，交由后端按行语言处理
PROMPT_LANGS = ("auto", "zh", "en", "ja", "ko")


class TtsParamsPanel(QWidget):
    """推理参数表单：产出可直接塞进 `TtsRequest.params` 的字典。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._backend_kind = BACKEND_GPT

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self._hint = QLabel(i18n_text("voice.params.hint"))
        self._hint.setObjectName("mutedLabel")
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

        self._group = QGroupBox(i18n_text("voice.params.title"))
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

        self._rows: dict[str, tuple[QWidget, QWidget]] = {}
        self._add_row("speed", self.speed_input, i18n_text("voice.params.speed"))
        self._add_row("seed", self._seed_row(), i18n_text("voice.params.seed"))
        self._add_row("top_k", self.top_k_input, i18n_text("voice.params.top_k"))
        self._add_row("top_p", self.top_p_input, i18n_text("voice.params.top_p"))
        self._add_row("temperature", self.temperature_input, i18n_text("voice.params.temperature"))
        self._add_row("split", self.split_input, i18n_text("voice.params.text_split"))
        self._add_row("prompt_text", self.prompt_text_input, i18n_text("voice.params.prompt_text"))
        self._add_row("prompt_lang", self.prompt_lang_input, i18n_text("voice.params.prompt_lang"))
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
            elif key == "speed":
                # CosyVoice 3 运行时没有语速旋钮：展示假控件会误导使用者
                visible = gpt_only
            else:
                visible = gpt_only
            label.setVisible(visible)
            field.setVisible(visible)
        self._group.setTitle(
            i18n_text("voice.params.title_gpt") if gpt_only else i18n_text("voice.params.title_cosy")
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
        return payload

    def retranslate(self) -> None:
        self._hint.setText(i18n_text("voice.params.hint"))
        self.seed_fixed.setText(i18n_text("voice.params.seed_fixed"))
        self.prompt_text_input.setPlaceholderText(i18n_text("voice.params.prompt_text_hint"))
        labels = {
            "speed": "voice.params.speed",
            "seed": "voice.params.seed",
            "top_k": "voice.params.top_k",
            "top_p": "voice.params.top_p",
            "temperature": "voice.params.temperature",
            "split": "voice.params.text_split",
            "prompt_text": "voice.params.prompt_text",
            "prompt_lang": "voice.params.prompt_lang",
        }
        for key, i18n_key in labels.items():
            self._rows[key][0].setText(i18n_text(i18n_key))
        self.set_backend_kind(self._backend_kind)
