# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""二级页：TTS 模型选择（GPT-SoVITS / CosyVoice 3 GGUF）。

文案按用户原文一字不改；专名一律官方称呼 GPT-SoVITS（禁用缩写）。
安装状态角标复用 start.bat / download_tts_verify.bat 的既有判断口径（权重代表文件/集合）。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from app.i18n import i18n_text
from app.widgets.feature_card import FeatureCard

from .base_tool_page import BaseToolPage

MODEL_ROOT = Path(__file__).resolve().parents[2] / "TTS model"
GPT_SOVITS_WEIGHTS = ("s2Gv3.pth", "s2Gv2ProPlus.pth")
COSY_MIN_FILES = 6


def gpt_sovits_ready(root: Path = MODEL_ROOT) -> bool:
    """GPT-SoVITS 就绪判断：pretrained_models 下存在 v3/v2ProPlus 代表权重。"""

    models = root / "GPT-SoVITS" / "GPT_SoVITS" / "pretrained_models"
    if not models.is_dir():
        return False
    return any((models / name).exists() or any(models.rglob(name)) for name in GPT_SOVITS_WEIGHTS)


def cosyvoice_ready(root: Path = MODEL_ROOT) -> bool:
    """CosyVoice 3 GGUF 就绪判断：q4 集合 6 件齐备。"""

    model_dir = root / "CosyVoice3"
    if not model_dir.is_dir():
        return False
    return len(list(model_dir.glob("*.gguf"))) >= COSY_MIN_FILES


class TtsModelPage(BaseToolPage):
    """两张模型卡：点击进入三级工作台（后端由路由侧装配）。"""

    navigate_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("tts_model", i18n_text("page.tts_model.title"), parent)
        self.status_panel.setVisible(False)

        self.gpt_card = FeatureCard(
            "tts_gpt_sovits",
            i18n_text("tts.card.gpt.title"),
            i18n_text("tts.card.gpt.desc"),
            card_height=150,
        )
        self.cosy_card = FeatureCard(
            "tts_cosyvoice",
            i18n_text("tts.card.cosy.title"),
            i18n_text("tts.card.cosy.desc"),
            card_height=150,
        )
        self.cards = (self.gpt_card, self.cosy_card)
        for card in self.cards:
            card.activated.connect(self.navigate_requested.emit)

        scroll = QScrollArea()
        scroll.setObjectName("copyGroupScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        container = QFrame()
        container.setObjectName("copyGroupContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 6, 4, 14)
        layout.setSpacing(12)
        self.gpt_badge = QLabel(i18n_text("tts.badge.ready" if gpt_sovits_ready() else "tts.badge.missing"))
        self.gpt_badge.setObjectName("mutedLabel")
        self.cosy_badge = QLabel(i18n_text("tts.badge.ready" if cosyvoice_ready() else "tts.badge.missing"))
        self.cosy_badge.setObjectName("mutedLabel")
        layout.addWidget(self.gpt_card)
        layout.addWidget(self.gpt_badge)
        layout.addSpacing(6)
        layout.addWidget(self.cosy_card)
        layout.addWidget(self.cosy_badge)
        layout.addStretch(1)
        scroll.setWidget(container)
        self.set_body_widget(scroll)

    def can_navigate_away(self) -> bool:
        return True

    def set_navigation_enabled(self, enabled: bool) -> None:
        super().set_navigation_enabled(enabled)
        for card in self.cards:
            card.setEnabled(enabled)

    def retranslate(self) -> None:
        super().retranslate()
        for card in self.cards:
            card.retranslate()
        self.gpt_badge.setText(i18n_text("tts.badge.ready" if gpt_sovits_ready() else "tts.badge.missing"))
        self.cosy_badge.setText(i18n_text("tts.badge.ready" if cosyvoice_ready() else "tts.badge.missing"))