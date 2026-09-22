# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""签名密钥对话框（M2 界面接线）：展示项目密钥的**公开部分**，并可生成新密钥。

只展示 `key_id` 与公钥；私钥始终留在 `config/`（受系统凭据库保护），界面不读取、不显示。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr
from app.services import vt_key_store


class VtKeyDialog(QDialog):
    """密钥一览（可生成新密钥）。`base_dir` 为密钥目录（通常是项目内 `config/`）。"""

    def __init__(self, base_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base = base_dir
        self.setWindowTitle(tr("voice.keys.title"))
        self.resize(600, 260)
        root = QVBoxLayout(self)

        hint = QLabel(tr("voice.keys.hint"))
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.selector = QComboBox()
        self.selector.currentIndexChanged.connect(lambda _index: self.show_current())
        root.addWidget(self.selector)

        form = QFormLayout()
        self.key_id_label = QLabel("—")
        self.key_id_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.public_key_label = QLabel("—")
        self.public_key_label.setWordWrap(True)
        self.public_key_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("key_id", self.key_id_label)
        form.addRow(tr("voice.keys.public"), self.public_key_label)
        root.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.generate_button = buttons.addButton(tr("voice.keys.generate"), QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button = buttons.addButton(tr("voice.keys.copy_public"), QDialogButtonBox.ButtonRole.ActionRole)
        self.generate_button.clicked.connect(self.generate)
        self.copy_button.clicked.connect(self.copy_public)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.refresh()

    # —— 数据 ——
    def refresh(self) -> None:
        """重新载入密钥列表（当前密钥排在首位）。"""

        current = vt_key_store.latest_project_key(self._base)
        keys = vt_key_store.list_project_keys(self._base)
        if current and current in keys:
            keys = [current] + [item for item in keys if item != current]
        self.selector.blockSignals(True)
        self.selector.clear()
        self.selector.addItems(keys)
        self.selector.blockSignals(False)
        self.show_current()

    def current_key_id(self) -> str:
        return self.selector.currentText()

    def show_current(self) -> None:
        key_id = self.current_key_id()
        if not key_id:
            self.key_id_label.setText(tr("voice.keys.none"))
            self.public_key_label.setText("—")
            self.copy_button.setEnabled(False)
            return
        try:
            reference = vt_key_store.describe_project_key(self._base, key_id)
        except vt_key_store.KeyStoreError as error:
            code = str(error).split(":", 1)[0]
            self.key_id_label.setText(key_id)
            self.public_key_label.setText(tr("voice.keys.unreadable", code=code))
            self.copy_button.setEnabled(False)
            return
        self.key_id_label.setText(reference.key_id)
        self.public_key_label.setText(reference.public_key)
        self.copy_button.setEnabled(True)

    def public_key(self) -> str:
        """当前显示的完整公钥（十六进制）；无密钥或不可读时为空串。"""

        text = self.public_key_label.text()
        return text if len(text) == 64 else ""

    # —— 动作 ——
    def generate(self) -> str:
        """生成新密钥并刷新列表；返回新 `key_id`。"""

        reference = vt_key_store.create_project_key(self._base)
        self.refresh()
        return reference.key_id

    def copy_public(self) -> bool:
        key = self.public_key()
        if not key:
            return False
        QGuiApplication.clipboard().setText(key)
        return True
