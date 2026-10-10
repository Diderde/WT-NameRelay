# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""左侧图标导航栏：五个模块入口 + 语言/关于入口，图标随昼夜主题着色。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QByteArray, QFile, QIODevice, QSize, Qt, Signal
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


def _read_icon(name: str, icons_dir: Path | None = None) -> bytes | None:
    """读取一个导航图标 SVG 的字节：**优先 Qt 资源** `:/icons/<name>`，磁盘目录仅作回退。

    资源优先的理由：打包版（PyInstaller onefile 解包目录 / onedir）里必然存在的是
    `resources_rc.py` 内嵌的那一份，磁盘 `app/resources/icons/` 的落点随构建方式变化；
    源码树里两条路等价（qrc 由 `app.resources` 的副作用导入注册）。
    保留磁盘回退，是为了「改了 qrc 还没用 rcc 重编译」或 `NavRail` 被单独构造
    （未经 `app.resources` 注册资源）时导航栏不至于整栏空白。

    统一返回 `bytes` 而不是路径：`QSvgRenderer` 吃 `QByteArray`，资源与磁盘两种来源
    因此共用同一条着色路径，调用方不必再区分自己拿到的是哪一种。
    """

    resource = QFile(f":/icons/{name}")
    if resource.open(QIODevice.OpenModeFlag.ReadOnly):
        try:
            embedded = bytes(resource.readAll())
        finally:
            resource.close()
        if embedded:
            return embedded
    if icons_dir is None:
        return None
    try:
        return (icons_dir / name).read_bytes() or None
    except OSError:
        return None


def _tinted_pixmap(svg_data: bytes, color: str) -> QPixmap:
    """把 SVG 字节（Bootstrap Icons 为 currentColor 填充）以指定颜色着色为位图。"""

    renderer = QSvgRenderer(QByteArray(svg_data))
    source = QPixmap(_ICON_SIZE * 2, _ICON_SIZE * 2)
    source.fill(Qt.GlobalColor.transparent)
    if not renderer.isValid():
        return source
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
    return tinted


def _stateful_icon(svg_data: bytes, idle_color: str, active_color: str,
                   disabled_color: str) -> QIcon:
    """双态图标：未选中用柔和色、选中用 accent（QIcon 的 On/Off 态自动切换），
    禁用态给更暗的颜色。当前页由此获得比"边框加粗"强得多的辨识度。"""

    icon = QIcon()
    icon.addPixmap(_tinted_pixmap(svg_data, idle_color), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(_tinted_pixmap(svg_data, active_color), QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(_tinted_pixmap(svg_data, disabled_color), QIcon.Mode.Disabled, QIcon.State.Off)
    icon.addPixmap(_tinted_pixmap(svg_data, disabled_color), QIcon.Mode.Disabled, QIcon.State.On)
    return icon


class NavRail(QWidget):
    """窄幅图标导航栏：模块入口互斥选中，底部为语言切换与关于入口。"""

    navigate_requested = Signal(str)

    #: 路由键 → (图标文件名, 悬停卡标题键, 悬停卡正文键)。
    # 可见顺序（用户指定）：视频裁剪 → 人声分离 → 语音批量生成
    # → API 渠道 → 文件复制；audio 隐藏、fmod/experimental/settings 依次垫后
    ROUTES: tuple[tuple[str, str, str, str], ...] = (
        ("video", "nav-video.svg", "nav.rail.video", "nav.rail.video.tip"),
        ("separate", "nav-separate.svg", "nav.rail.separate", "nav.rail.separate.tip"),
        ("tts", "nav-tts.svg", "nav.rail.tts", "nav.rail.tts.tip"),
        ("api", "nav-api.svg", "nav.rail.api", "nav.rail.api.tip"),
        ("copy", "nav-copy.svg", "nav.rail.copy", "nav.rail.copy.tip"),
        ("audio", "nav-audio.svg", "nav.rail.audio", "nav.rail.audio.tip"),
        ("fmod", "nav-fmod.svg", "nav.rail.fmod", "nav.rail.fmod.tip"),
        ("experimental", "nav-experimental.svg", "nav.rail.experimental", "nav.rail.experimental.tip"),
        ("settings", "nav-settings.svg", "nav.rail.settings", "nav.rail.settings.tip"),
    )

    #: 图标栏暂不展示的路由（页面保留在栈内，程序内跳转仍可达）：
    # "audio" 的处理入口改由语音工作台"进入处理"按钮承担（验收决定）
    HIDDEN_ROUTES = frozenset({"audio"})

    def __init__(self, icons_dir: Path | None, parent: QWidget | None = None) -> None:
        """`icons_dir` 是**回退**图标目录：图标优先取 Qt 资源 `:/icons/<name>`。
        传 None 表示只用资源（`_read_icon` 见模块级说明）。"""
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
            button.setVisible(route not in self.HIDDEN_ROUTES)
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
            svg_data = _read_icon(svg_by_route[route], self._icons_dir)
            if svg_data is None:  # 图标缺失时留空按钮，不让整栏构造失败
                continue
            button.setIcon(_stateful_icon(
                svg_data,
                idle_color=colors["text_muted"],
                active_color=colors["accent"],
                disabled_color=colors["text_disabled"],
            ))
        self.setStyleSheet(f"""
            QWidget#navRail {{
                background-color: {colors['background_alt']};
                border-right: 1px solid {colors['border']};
            }}
            QToolButton#navRailButton {{
                border: 1px solid transparent;
                border-radius: 10px;
                background-color: transparent;
            }}
            QToolButton#navRailButton:hover {{
                background-color: {colors['surface_hover']};
                border-color: {colors['border']};
            }}
            QToolButton#navRailButton:checked {{
                border: 1px solid {colors['border_hover']};
                background-color: {colors['drag_active_bg']};
            }}
            /* 底部文字入口：与上方图标入口同一视觉语言（等宽圆角块 + 悬停浮底），
               保留文字是刻意的——主题/语言按钮的文案即"点击后的目标"，
               图标化反而要再猜一次，且回归测试按 text() 断言。 */
            QToolButton#navRailTextButton {{
                border: 1px solid transparent;
                border-radius: 8px;
                color: {colors['text_muted']};
                background-color: transparent;
                font-size: 11px;
                min-width: 46px;
                min-height: 26px;
                padding: 2px 4px;
            }}
            QToolButton#navRailTextButton:hover {{
                color: {colors['accent']};
                background-color: {colors['surface_hover']};
                border-color: {colors['border']};
            }}
            QToolButton#navRailTextButton:pressed {{
                background-color: {colors['surface_pressed']};
            }}
        """)
        # 模式切换后按钮文案（目标模式）随新板刷新
        self.retranslate()
