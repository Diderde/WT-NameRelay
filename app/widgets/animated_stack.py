from __future__ import annotations

from enum import IntEnum

from PySide6.QtCore import QEasingCurve, QPoint, QParallelAnimationGroup, QPropertyAnimation, QRect, Signal, Qt
from PySide6.QtGui import QCloseEvent, QPixmap, QResizeEvent
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QStackedLayout, QStackedWidget, QWidget


class TransitionDirection(IntEnum):
    BACKWARD = -1
    FORWARD = 1


class AnimatedStack(QStackedWidget):
    """Animate disposable page snapshots so live widgets never leave paint trails."""

    transition_started = Signal(int)
    transition_finished = Signal(int)

    DURATION_MS = 260
    INCOMING_OFFSET = 36
    OUTGOING_OFFSET = 18

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("animatedStack")
        self._animating = False
        self._target_index: int | None = None
        self._snapshot_layers: list[QLabel] = []
        self._snapshot_effects: list[QGraphicsOpacityEffect] = []
        self._animation_group: QParallelAnimationGroup | None = None

    @property
    def is_animating(self) -> bool:
        return self._animating

    def transition_to(self, index: int, direction: TransitionDirection | int) -> bool:
        if self._animating or index < 0 or index >= self.count() or index == self.currentIndex():
            return False
        outgoing, incoming = self.currentWidget(), self.widget(index)
        if outgoing is None or incoming is None:
            return False

        self._animating = True
        self._target_index = index
        self.transition_started.emit(index)
        direction_value = 1 if int(direction) >= 0 else -1
        base_rect = QRect(0, 0, self.width(), self.height())
        outgoing.setGeometry(base_rect)
        incoming.setGeometry(base_rect)

        stack_layout = self.layout()
        if isinstance(stack_layout, QStackedLayout):
            stack_layout.setStackingMode(QStackedLayout.StackingMode.StackAll)
        incoming.show()
        outgoing.raise_()
        outgoing_snapshot = self._snapshot(outgoing, base_rect)
        incoming_snapshot = self._snapshot(incoming, base_rect)
        for page_index in range(self.count()):
            self.widget(page_index).hide()
        if isinstance(stack_layout, QStackedLayout):
            stack_layout.setStackingMode(QStackedLayout.StackingMode.StackOne)

        outgoing_layer, outgoing_effect = self._layer(outgoing_snapshot, base_rect)
        incoming_layer, incoming_effect = self._layer(incoming_snapshot, base_rect.translated(self.INCOMING_OFFSET * direction_value, 0))
        outgoing_effect.setOpacity(1.0)
        incoming_effect.setOpacity(0.0)
        self._snapshot_layers = [outgoing_layer, incoming_layer]
        self._snapshot_effects = [outgoing_effect, incoming_effect]
        outgoing_layer.show(); incoming_layer.show(); incoming_layer.raise_()

        group = QParallelAnimationGroup(self)
        self._animation_group = group
        easing = QEasingCurve.Type.OutCubic
        self._add_animation(group, outgoing_layer, b"pos", QPoint(0, 0), QPoint(-self.OUTGOING_OFFSET * direction_value, 0), easing)
        self._add_animation(group, incoming_layer, b"pos", QPoint(self.INCOMING_OFFSET * direction_value, 0), QPoint(0, 0), easing)
        self._add_animation(group, outgoing_effect, b"opacity", 1.0, 0.0, easing)
        self._add_animation(group, incoming_effect, b"opacity", 0.0, 1.0, easing)
        group.finished.connect(self._on_animation_finished)
        group.start()
        return True

    def finish_transition(self) -> None:
        if self._animating:
            self._cleanup_transition(commit=True)

    def _snapshot(self, page: QWidget, rect: QRect) -> QPixmap:
        pixmap = QPixmap(rect.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        page.render(pixmap)
        return pixmap

    def _layer(self, pixmap: QPixmap, geometry: QRect) -> tuple[QLabel, QGraphicsOpacityEffect]:
        layer = QLabel(self)
        layer.setObjectName("animatedStackSnapshot")
        layer.setPixmap(pixmap)
        layer.setGeometry(geometry)
        layer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        effect = QGraphicsOpacityEffect(layer)
        layer.setGraphicsEffect(effect)
        return layer, effect

    def _add_animation(self, group: QParallelAnimationGroup, target: object, property_name: bytes, start: object, end: object, easing: QEasingCurve.Type) -> None:
        animation = QPropertyAnimation(target, property_name, group)
        animation.setDuration(self.DURATION_MS)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(easing)

    def _on_animation_finished(self) -> None:
        self._cleanup_transition(commit=True)

    def _cleanup_transition(self, *, commit: bool) -> None:
        if not self._animating:
            return
        final_index = self._target_index if commit and self._target_index is not None else self.currentIndex()
        group, self._animation_group = self._animation_group, None
        if group is not None:
            group.stop()
        for layer in self._snapshot_layers:
            layer.setGraphicsEffect(None)
            layer.hide()
            layer.deleteLater()
        self._snapshot_layers.clear()
        self._snapshot_effects.clear()

        base_rect = QRect(0, 0, self.width(), self.height())
        stack_layout = self.layout()
        if isinstance(stack_layout, QStackedLayout):
            stack_layout.setStackingMode(QStackedLayout.StackingMode.StackOne)
        self.setCurrentIndex(final_index)
        for page_index in range(self.count()):
            page = self.widget(page_index)
            page.setGeometry(base_rect)
            page.setVisible(page_index == final_index)
        final_page = self.widget(final_index)
        final_page.raise_()
        final_page.repaint()
        self.repaint()
        self._target_index = None
        self._animating = False
        if group is not None:
            group.deleteLater()
        self.transition_finished.emit(final_index)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._animating:
            self._cleanup_transition(commit=True)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.finish_transition()
        super().closeEvent(event)
