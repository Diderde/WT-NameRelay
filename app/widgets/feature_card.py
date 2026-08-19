from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, Property, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QEnterEvent, QFocusEvent, QIcon, QKeyEvent, QMouseEvent, QPaintEvent, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class FeatureCard(QAbstractButton):
    """Keyboard-accessible feature card with restrained hover feedback."""

    activated = Signal(str)

    def __init__(
        self,
        feature_key: str,
        title: str,
        description: str,
        icon_path: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.feature_key = feature_key
        self._lift_offset = 0.0

        self.setObjectName(f"{feature_key}Card")
        self.setAccessibleName(title)
        self.setToolTip(f"进入{title}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(220)
        self.setFixedHeight(240)

        self._surface = QFrame(self)
        self._surface.setObjectName("featureCardSurface")
        self._surface.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._surface.setProperty("hovered", False)
        self._surface.setProperty("pressed", False)
        self._surface.setProperty("focused", False)

        self._shadow = QGraphicsDropShadowEffect(self._surface)
        self._shadow.setBlurRadius(18.0)
        self._shadow.setOffset(0.0, 4.0)
        self._shadow.setColor(Qt.GlobalColor.black)
        self._surface.setGraphicsEffect(self._shadow)

        content = QVBoxLayout(self._surface)
        content.setContentsMargins(24, 22, 24, 20)
        content.setSpacing(0)

        icon_label = QLabel()
        icon_label.setObjectName("cardIcon")
        icon_label.setFixedSize(56, 56)
        icon_label.setPixmap(QIcon(icon_path).pixmap(52, 52))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignLeft)
        content.addSpacing(20)

        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        content.addWidget(title_label)
        content.addSpacing(8)

        description_label = QLabel(description)
        description_label.setObjectName("cardDescription")
        description_label.setWordWrap(True)
        content.addWidget(description_label)
        content.addStretch(1)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_label = QLabel("进入功能")
        action_label.setObjectName("cardAction")
        arrow_label = QLabel("→")
        arrow_label.setObjectName("cardAction")
        action_row.addWidget(action_label)
        action_row.addStretch(1)
        action_row.addWidget(arrow_label)
        content.addLayout(action_row)

        self._lift_animation = QPropertyAnimation(self, b"liftOffset", self)
        self._lift_animation.setDuration(150)
        self._lift_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.clicked.connect(self._emit_activated)

    def _emit_activated(self, _checked: bool = False) -> None:
        self.activated.emit(self.feature_key)

    def set_transition_active(self, active: bool) -> None:
        """Suspend the card shadow while a parent page opacity effect is active."""
        self._lift_animation.stop()
        if active:
            self._set_visual_property("hovered", False)
            self._set_visual_property("pressed", False)
            self._set_lift_offset(0.0)
            self._shadow.setEnabled(False)
            return

        self._shadow.setEnabled(True)
        hovered = self.underMouse() and self.isEnabled()
        self._set_visual_property("hovered", hovered)
        self._shadow.setBlurRadius(26.0 if hovered else 18.0)
        self._shadow.setOffset(0.0, 7.0 if hovered else 4.0)
        self._set_lift_offset(3.0 if hovered else 0.0)

    def _get_lift_offset(self) -> float:
        return self._lift_offset

    def _set_lift_offset(self, value: float) -> None:
        self._lift_offset = value
        self._position_surface()

    liftOffset = Property(float, _get_lift_offset, _set_lift_offset)

    def _animate_lift(self, target: float) -> None:
        self._lift_animation.stop()
        self._lift_animation.setStartValue(self._lift_offset)
        self._lift_animation.setEndValue(target)
        self._lift_animation.start()

    def _position_surface(self) -> None:
        base_rect = self.rect().adjusted(8, 8, -8, -8)
        base_rect.translate(0, -round(self._lift_offset))
        self._surface.setGeometry(base_rect)

    def _set_visual_property(self, name: str, value: bool) -> None:
        if self._surface.property(name) == value:
            return
        self._surface.setProperty(name, value)
        style = self._surface.style()
        style.unpolish(self._surface)
        style.polish(self._surface)
        self._surface.update()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._position_surface()

    def paintEvent(self, event: QPaintEvent) -> None:
        # The child surface owns all visual painting; the button shell stays transparent.
        event.accept()

    def enterEvent(self, event: QEnterEvent) -> None:
        if not self.isEnabled():
            super().enterEvent(event)
            return
        self._set_visual_property("hovered", True)
        self._shadow.setBlurRadius(26.0)
        self._shadow.setOffset(0.0, 7.0)
        self._animate_lift(3.0)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._set_visual_property("hovered", False)
        self._set_visual_property("pressed", False)
        self._shadow.setBlurRadius(18.0)
        self._shadow.setOffset(0.0, 4.0)
        self._animate_lift(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._set_visual_property("pressed", True)
            self._shadow.setBlurRadius(12.0)
            self._shadow.setOffset(0.0, 2.0)
            self._animate_lift(1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        self._set_visual_property("pressed", False)
        if self.underMouse() and self.isEnabled():
            self._shadow.setBlurRadius(26.0)
            self._shadow.setOffset(0.0, 7.0)
            self._animate_lift(3.0)
        else:
            self._shadow.setBlurRadius(18.0)
            self._shadow.setOffset(0.0, 4.0)
            self._animate_lift(0.0)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.isAutoRepeat():
            self.setDown(True)
            self._set_visual_property("pressed", True)
            self._animate_lift(1.0)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.isAutoRepeat():
            self.setDown(False)
            self._set_visual_property("pressed", False)
            self._animate_lift(3.0 if self.underMouse() else 0.0)
            self.click()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def focusInEvent(self, event: QFocusEvent) -> None:
        self._set_visual_property("focused", True)
        super().focusInEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self._set_visual_property("focused", False)
        super().focusOutEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.EnabledChange and not self.isEnabled():
            self._set_visual_property("pressed", False)
            self._animate_lift(0.0)
        super().changeEvent(event)
