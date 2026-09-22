# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""CosyVoice 3（GGUF）信息面板：模型位置、就绪状态与用途说明。

CosyVoice 3 为推理专用模型，本工具不提供其微调——三级工作台在选用该模型时
以本面板替换左栏的 GPT-SoVITS 微调面板；微调能力在模型选择页的另一张卡。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from app.i18n import i18n_text, tr

MODEL_ROOT = Path(__file__).resolve().parents[2] / "TTS model"
COSY_MIN_FILES = 6


class CosyVoiceInfoPanel(QFrame):
    """模型信息只读面板：不承载操作，供三级工作台在 CosyVoice 3 下显示。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("cosyVoiceInfoPanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.note_label = QLabel(i18n_text("voice.cosy.note"))
        self.note_label.setObjectName("mutedLabel")
        self.note_label.setWordWrap(True)
        root.addWidget(self.note_label)

        self.dir_label = QLabel()
        self.dir_label.setObjectName("mutedLabel")
        self.dir_label.setWordWrap(True)
        root.addWidget(self.dir_label)

        self.ready_label = QLabel()
        self.ready_label.setObjectName("mutedLabel")
        self.ready_label.setWordWrap(True)
        root.addWidget(self.ready_label)

        self.service_label = QLabel(i18n_text("voice.cosy.service"))
        self.service_label.setObjectName("mutedLabel")
        self.service_label.setWordWrap(True)
        root.addWidget(self.service_label)

        root.addStretch(1)
        self.refresh_status()

    def refresh_status(self) -> None:
        """重算模型就绪状态（进入页面 / 语言切换时调用）。"""

        model_dir = MODEL_ROOT / "CosyVoice3"
        count = len(list(model_dir.glob("*.gguf"))) if model_dir.is_dir() else 0
        self.dir_label.setText(tr("voice.cosy.model_dir", path=str(model_dir)))
        if count >= COSY_MIN_FILES:
            self.ready_label.setText(tr("voice.cosy.ready", count=count))
        else:
            self.ready_label.setText(tr("voice.cosy.missing", count=count, need=COSY_MIN_FILES))

    def retranslate(self) -> None:
        self.note_label.setText(i18n_text("voice.cosy.note"))
        self.service_label.setText(i18n_text("voice.cosy.service"))
        self.refresh_status()
