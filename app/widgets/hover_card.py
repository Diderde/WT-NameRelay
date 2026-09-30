# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""悬停信息卡（hover card）：鼠标停在目标控件上延时弹出的正式卡片浮层。

- 卡片无边框、不抢鼠标（WA_TransparentForMouseEvents），移开目标即收回；
- 配色在每次显示时从当前主题现取，昼夜切换无需额外处理；
- 弹出位置跟随光标并钳制在屏幕可用区内；目标控件销毁时自动清理。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget

#: 弹出前悬停延时（防误触）
DEFAULT_DELAY_MS = 500
#: 卡片固定宽度（长文本自动换行）
CARD_WIDTH = 380


class HoverCard(QFrame):
    """卡片浮层本体：标题 + 正文，样式随当前主题现取。"""

    def __init__(self, title: str, body: str, width: int = CARD_WIDTH) -> None:
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("hoverCard")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setWordWrap(True)
        body_label = QLabel(body)
        body_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(body_label, 1)
        self._title_label = title_label
        self._body_label = body_label
        self._width = width
        self.setStyleSheet(self._build_qss())

    def _build_qss(self) -> str:
        from app.styles import theme

        colors = theme.PALETTES[theme.current_mode()]
        return f"""
        QFrame#hoverCard {{
            background-color: {colors['drag_active_bg']};
            border: 2px solid {colors['border_hover']};
            border-radius: 10px;
        }}
        QLabel {{ background: transparent; border: none; }}
        """

    def set_content(self, title: str, body: str) -> None:
        self._title_label.setText(title)
        self._body_label.setText(body)

    def popup_near_cursor(self) -> None:
        """按当前主题刷新样式，在光标右下方弹出并钳制到屏幕可用区。"""

        self.setStyleSheet(self._build_qss())
        self.adjustSize()
        self.setFixedWidth(self._width)
        self.adjustSize()
        cursor = QCursor.pos()
        x, y = cursor.x() + 16, cursor.y() + 20
        screen = QGuiApplication.screenAt(cursor)
        bounds = screen.availableGeometry() if screen is not None else QGuiApplication.primaryScreen().availableGeometry()
        if x + self.width() > bounds.right():
            x = cursor.x() - self.width() - 12
        if y + self.height() > bounds.bottom():
            y = bounds.bottom() - self.height() - 8
        self.move(max(bounds.left() + 4, x), max(bounds.top() + 4, y))
        self.show()
        self.raise_()


class _HoverController(QObject):
    """挂在目标控件上的事件过滤器：Enter 延时弹出，Leave/按下即收回。"""

    def __init__(self, target: QWidget, title: str, body: str, delay_ms: int, width: int) -> None:
        super().__init__(target)
        self._target = target
        self._title = title
        self._body = body
        self._width = width
        self._card: HoverCard | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self._show)
        target.installEventFilter(self)
        target.destroyed.connect(self.hide)

    def set_text(self, title: str, body: str) -> None:
        """运行时更新卡片文案（界面语言切换时由调用方转发）。"""

        self._title = title
        self._body = body
        if self._card is not None:
            self._card.set_content(title, body)

    def hide(self) -> None:
        self._timer.stop()
        if self._card is not None:
            self._card.hide()

    def _show(self) -> None:
        if self._card is None:
            self._card = HoverCard(self._title, self._body, self._width)
        self._card.set_content(self._title, self._body)
        self._card.popup_near_cursor()

    def eventFilter(self, watched: QObject, event) -> bool:
        kind = event.type()
        if kind == event.Type.Enter:
            if QApplication.activeWindow() is not None:
                self._timer.start()
        elif kind in (event.Type.Leave, event.Type.MouseButtonPress):
            self.hide()
        return False


def attach_hover_card(
    target: QWidget,
    title: str,
    body: str,
    *,
    delay_ms: int = DEFAULT_DELAY_MS,
    width: int = CARD_WIDTH,
) -> _HoverController:
    """给任意控件挂一张悬停信息卡。

    幂等：目标已挂卡时只更新文案并返回原控制器
    （retranslate 等路径会反复调用，叠卡会无限堆积事件过滤器与计时器）。
    """

    existing = target.findChildren(_HoverController)
    if existing:
        existing[0].set_text(title, body)
        return existing[0]
    return _HoverController(target, title, body, delay_ms, width)
