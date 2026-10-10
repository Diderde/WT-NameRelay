# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr

from .base_tool_page import BaseToolPage

#: 模块页 key → 顶部切换按钮标题键（与原卡片文案同源）
_MODULE_TITLE_KEYS = {
    "crew": "home.card.crew.title",
    "radio": "home.card.radio.title",
    "bank": "home.card.bank.title",
}


class FileCopyPage(BaseToolPage):
    """模块宿主页：顶部切换按钮 + 内嵌的车组/无线电/Bank 功能页（同页切换）。

    由「卡片落地页 + 主栈跳转」重构为「同页模块切换」
    （对齐语音批量生成的模块按钮形态）：页面即宿主，返回按钮随嵌入
    隐藏，导航由左侧图标栏与模块按钮承担。
    """

    def __init__(self, crew_page: BaseToolPage, radio_page: BaseToolPage,
                 bank_page: BaseToolPage, parent: QWidget | None = None) -> None:
        super().__init__("copy", tr("page.copy.title"), parent)
        self.status_panel.setVisible(False)
        self.crew_page = crew_page
        self.radio_page = radio_page
        self.bank_page = bank_page
        self._modules = (crew_page, radio_page, bank_page)
        for module in self._modules:
            # 嵌入后导航由模块按钮与左侧图标栏承担，返回按钮不再展示
            module.back_button.setVisible(False)

        host = QWidget()
        root = QVBoxLayout(host)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self._module_buttons: dict[str, QPushButton] = {}
        self._module_button_titles: list[tuple[QPushButton, str]] = []
        self._module_group = QButtonGroup(self)
        self._module_group.setExclusive(True)
        module_bar = QHBoxLayout()
        module_bar.setContentsMargins(0, 0, 0, 0)
        module_bar.setSpacing(8)
        for module in self._modules:
            button = QPushButton()
            button.setObjectName("moduleSwitchButton")
            button.setProperty("audioNavigation", True)  # 复用选中态高亮样式
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._module_group.addButton(button)
            self._module_buttons[module.page_key] = button
            title_key = _MODULE_TITLE_KEYS[module.page_key]
            self._module_button_titles.append((button, title_key))
            module_bar.addWidget(button)
        module_bar.addStretch(1)
        root.addLayout(module_bar)

        self._module_panes = QStackedWidget()
        self._module_panes.setObjectName("modulePanes")
        for module in self._modules:
            self._module_panes.addWidget(module)
        root.addWidget(self._module_panes, 1)
        self.set_body_widget(host)

        for key, button in self._module_buttons.items():
            button.clicked.connect(lambda _checked=False, key=key: self.show_module(key))
        self.show_module(self._modules[0].page_key)
        # 按钮文字只在 retranslate 里设置——构造器不调一次，
        # 首次进页面三枚模块按钮全是空白
        self.retranslate()

    # ── 公共接口 ──
    def show_module(self, page_key: str) -> None:
        """切换顶部按钮对应的模块界面。"""

        self._module_panes.setCurrentWidget(self._module_of(page_key))
        for key, button in self._module_buttons.items():
            button.setChecked(key == page_key)

    def _module_of(self, page_key: str) -> BaseToolPage:
        return {
            "crew": self.crew_page,
            "radio": self.radio_page,
            "bank": self.bank_page,
        }[page_key]

    def can_navigate_away(self) -> bool:
        return all(module.can_navigate_away() for module in self._modules)

    def set_navigation_enabled(self, enabled: bool) -> None:
        super().set_navigation_enabled(enabled)
        for module in self._modules:
            module.set_navigation_enabled(enabled)

    def retranslate(self) -> None:
        super().retranslate()
        for button, key in self._module_button_titles:
            button.setText(tr(key))
        for module in self._modules:
            module.retranslate()
