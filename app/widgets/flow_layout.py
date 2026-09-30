# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""自动换行的水平流式布局（Qt 官方 FlowLayout 示例的 PySide6 实现）。

用于按钮条等"数量不定、宽度不定"的行：子项依次排列，一行放不下自动换行，
避免固定行布局在窄分栏里把按钮压扁或裁字。
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QWidget


class FlowLayout(QLayout):
    """内容按行流式排列；高度随宽度变化（hasHeightForWidth）。"""

    def __init__(self, parent: QWidget | None = None, spacing: int = 8) -> None:
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self._spacing = spacing
        self._items: list[QLayoutItem] = []

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _arrange(self, rect: QRect, *, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        x, y = effective.x(), effective.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > effective.right() + 1 and line_height > 0:
                x = effective.x()
                y = y + line_height + self._spacing
                next_x = x + hint.width() + self._spacing
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()
