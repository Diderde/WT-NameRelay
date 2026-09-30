# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""左侧图标导航栏：五个模块入口 + 语言/关于入口，图标随昼夜主题着色。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QButtonGroup, QToolButton, QVBoxLayout, QWidget

from app.i18n import tr
from app.styles import theme
from app.widgets.hover_card import attach_hover_card

#: 图标按钮尺寸与图标内径
_BUTTON_SIZE = 44
_ICON_SIZE = 26
_RAIL_WIDTH = 68


def _tinted_icon(svg_path: Path, color: str) -> QIcon:
    """读取 SVG（Bootstrap Icons 为 currentColor 填充）并以指定颜色着色为图标。"""

    renderer = QSvgRenderer(str(svg_path))
    source = QPixmap(_ICON_SIZE * 2, _ICON_SIZE * 2)
    source.fill(Qt.GlobalColor.transparent)
    painter = QPainter(source)
    renderer.render(painter)
    painter.end()

    tinted = QPixmap(source.size())
    tinted.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, source)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), QColor(color))
    painter.end()
    return QIcon(tinted)


class NavRail(QWidget):
    """窄幅图标导航栏：模块入口互斥选中，底部为语言切换与关于入口。"""

    navigate_requested = Signal(str)

    #: 路由键 → (图标文件名, 悬停卡标题键, 悬停卡正文键)
    ROUTES: tuple[tuple[str, str, str, str], ...] = (
        ("video", "nav-video.svg", "nav.rail.video", "nav.rail.video.tip"),
        ("tts", "nav-tts.svg", "nav.rail.tts", "nav.rail.tts.tip"),
        ("copy", "nav-copy.svg", "nav.rail.copy", "nav.rail.copy.tip"),
        ("audio", "nav-audio.svg", "nav.rail.audio", "nav.rail.audio.tip"),
        ("api", "nav-api.svg", "nav.rail.api", "nav.rail.api.tip"),
        ("settings", "nav-settings.svg", "nav.rail.settings", "nav.rail.settings.tip"),
    )

    def __init__(self, icons_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("navRail")
        self.setFixedWidth(_RAIL_WIDTH)
        self._icons_dir = icons_dir
        self._buttons: dict[str, QToolButton] = {}
        self._on_theme: Callable[[], None] = lambda: None
        self._on_language: Callable[[], None] = lambda: None
        self._on_about: Callable[[], None] = lambda: None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(8)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for route, _, _, _ in self.ROUTES:
            button = QToolButton()
            button.setObjectName("navRailButton")
            button.setCheckable(True)
            button.setFixedSize(_BUTTON_SIZE, _BUTTON_SIZE)
            button.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
            button.clicked.connect(lambda _checked=False, route=route: self.navigate_requested.emit(route))
            self._group.addButton(button)
            self._buttons[route] = button
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)

        self.theme_button = QToolButton()
        self.theme_button.setObjectName("navRailTextButton")
        self.theme_button.setAutoRaise(True)
        self.theme_button.clicked.connect(lambda: self._on_theme())
        layout.addWidget(self.theme_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.language_button = QToolButton()
        self.language_button.setObjectName("navRailTextButton")
        self.language_button.setAutoRaise(True)
        self.language_button.clicked.connect(lambda: self._on_language())
        layout.addWidget(self.language_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.about_button = QToolButton()
        self.about_button.setObjectName("navRailTextButton")
        self.about_button.setAutoRaise(True)
        self.about_button.clicked.connect(lambda: self._on_about())
        layout.addWidget(self.about_button, 0, Qt.AlignmentFlag.AlignHCenter)

        self.retranslate()
        self._apply_theme()
        # 监听须可退订：lambda 无法按等值移除，改用绑定方法 + destroyed 摘除
        theme.on_mode_changed(self._on_mode_changed)
        self.destroyed.connect(lambda: theme.off_mode_changed(self._on_mode_changed))

    def _on_mode_changed(self, _mode: str) -> None:
        self._apply_theme()

    # ── 公共接口 ──
    def set_callbacks(self, on_theme: Callable[[], None], on_language: Callable[[], None], on_about: Callable[[], None]) -> None:
        """注入底部三个入口的回调（避免本组件直接依赖对话框/主题/语言模块）。"""

        self._on_theme = on_theme
        self._on_language = on_language
        self._on_about = on_about

    def set_checked(self, route: str) -> None:
        button = self._buttons.get(route)
        if button is not None:
            button.setChecked(True)

    def retranslate(self) -> None:
        # 与语言按钮同语义：显示点击后将切换到的目标模式
        self.theme_button.setText(
            tr("home.toggle.theme.light") if theme.current_mode() == "dark" else tr("home.toggle.theme.dark")
        )
        self.language_button.setText(tr("home.toggle.language"))
        self.about_button.setText(tr("nav.rail.about"))
        for route, _, title_key, tip_key in self.ROUTES:
            button = self._buttons[route]
            button.setToolTip(tr(title_key))
            attach_hover_card(button, tr(title_key), tr(tip_key))

    # ── 内部 ──
    def _apply_theme(self) -> None:
        colors = theme.PALETTES[theme.current_mode()]
        svg_by_route = {route: svg_name for route, svg_name, _, _ in self.ROUTES}
        for route, button in self._buttons.items():  # 键为 route 字符串，图标名须经 ROUTES 查表
            button.setIcon(_tinted_icon(self._icons_dir / svg_by_route[route], colors["accent"]))
        self.setStyleSheet(f"""
            QWidget#navRail {{
                background-color: {colors['background_alt']};
                border-right: 1px solid {colors['border']};
            }}
            QToolButton#navRailButton {{
                border: 1px solid {colors['border']};
                border-radius: 10px;
                background-color: {colors['surface']};
            }}
            QToolButton#navRailButton:checked {{
                border: 2px solid {colors['border_hover']};
                background-color: {colors['drag_active_bg']};
            }}
            QToolButton#navRailTextButton {{
                border: none;
                color: {colors['text_muted']};
                font-size: 11px;
                padding: 2px;
            }}
            QToolButton#navRailTextButton:hover {{
                color: {colors['accent']};
            }}
        """)
        # 模式切换后按钮文案（目标模式）随新板刷新
        self.retranslate()
