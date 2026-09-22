from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
)
from PySide6.QtWidgets import QAbstractButton, QWidget

from app.styles import theme


class CopyModeSwitch(QAbstractButton):
    """Compact animated two-state switch for radio manual copy mode."""

    mode_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip("切换无线电手动复制的来源分配方式")
        self._position = 0.0
        self._animation = QPropertyAnimation(self, b"position", self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_to_state)
        self.toggled.connect(self.mode_changed)

    def sizeHint(self) -> QSize:
        return QSize(196, 40)

    def minimumSizeHint(self) -> QSize:
        return QSize(174, 36)

    def set_average_checked(self, checked: bool, *, emit: bool = False) -> None:
        previous = self.blockSignals(not emit)
        self.setChecked(checked)
        self.blockSignals(previous)
        self._animation.stop()
        self._position = 1.0 if checked else 0.0
        self.update()

    def _get_position(self) -> float:
        return self._position

    def _set_position(self, value: float) -> None:
        self._position = max(0.0, min(1.0, value))
        self.update()

    position = Property(float, _get_position, _set_position)

    def _animate_to_state(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() is Qt.MouseButton.LeftButton:
            desired = event.position().x() >= self.width() / 2
            if desired != self.isChecked():
                self.setChecked(desired)
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Home):
            self.setChecked(False)
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_End):
            self.setChecked(True)
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outer = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setPen(QColor(theme.color("border")))
        painter.setBrush(QColor(theme.color("triple_bg")))
        painter.drawRoundedRect(outer, 10, 10)

        half = outer.width() / 2
        thumb = QRectF(outer.left() + self._position * half, outer.top(), half, outer.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.color("accent")))
        painter.drawRoundedRect(thumb.adjusted(2, 2, -2, -2), 8, 8)

        metrics = QFontMetrics(self.font())
        labels = (("顺序复制", QRectF(outer.left(), outer.top(), half, outer.height()), self._position < 0.5),
                  ("平均分配", QRectF(outer.left() + half, outer.top(), half, outer.height()), self._position >= 0.5))
        for text, rect, selected in labels:
            # 选中侧文字画在琥珀色 thumb 上用深色，未选中侧用主题次级文字色。
            painter.setPen(QColor(theme.color("on_accent")) if selected else QColor(theme.color("text_muted")))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(rect.width() - 10)))
