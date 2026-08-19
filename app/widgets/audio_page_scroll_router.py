from __future__ import annotations

import weakref

from PySide6.QtCore import QEvent, QObject, QPoint, QTimer
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QScrollArea,
    QScrollBar,
    QWidget,
)


class AudioPageScrollRouter(QObject):
    """Route wheel input between the timeline and the page scroll area."""

    def __init__(
        self,
        page: QWidget,
        scroll_area: QScrollArea,
        timeline: QWidget,
        *,
        hot_zone_width: int = 40,
    ) -> None:
        super().__init__(page)
        self._page_ref = weakref.ref(page)
        self._scroll_ref = weakref.ref(scroll_area)
        self._timeline_ref = weakref.ref(timeline)
        self._hot_zone_width = hot_zone_width
        self._pending_delta = 0.0
        self._flush_timer = QTimer(self)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.setInterval(16)
        self._flush_timer.timeout.connect(self._flush)
        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)

    @staticmethod
    def _belongs_to(widget: QWidget, ancestor: QWidget) -> bool:
        current: QWidget | None = widget
        while current is not None:
            if current is ancestor:
                return True
            current = current.parentWidget()
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if event.type() is not QEvent.Type.Wheel or not isinstance(event, QWheelEvent):
            return False
        if not isinstance(watched, QWidget):
            return False
        page = self._page_ref()
        scroll = self._scroll_ref()
        timeline = self._timeline_ref()
        if page is None or scroll is None or timeline is None or not page.isVisible():
            return False
        if not self._belongs_to(watched, page):
            return False
        if isinstance(watched, (QScrollBar, QAbstractItemView)):
            return False
        if isinstance(watched, (QAbstractSpinBox, QComboBox)) and watched.hasFocus():
            return False

        viewport = scroll.viewport()
        global_position = event.globalPosition().toPoint()
        viewport_position = viewport.mapFromGlobal(global_position)
        in_viewport = viewport.rect().contains(viewport_position)
        in_hot_zone = in_viewport and viewport_position.x() >= viewport.width() - self._hot_zone_width

        timeline_position = timeline.mapFromGlobal(global_position)
        in_timeline = timeline.rect().contains(timeline_position)
        if in_timeline and not in_hot_zone:
            return False

        pixel_delta = event.pixelDelta().y()
        angle_delta = event.angleDelta().y()
        if pixel_delta:
            self._pending_delta -= pixel_delta
        elif angle_delta:
            step = max(24, scroll.verticalScrollBar().singleStep() * 3)
            self._pending_delta -= angle_delta / 120 * step
        else:
            return False
        if not self._flush_timer.isActive():
            self._flush_timer.start()
        event.accept()
        return True

    def _flush(self) -> None:
        scroll = self._scroll_ref()
        if scroll is None:
            self._pending_delta = 0.0
            return
        bar = scroll.verticalScrollBar()
        delta = round(self._pending_delta)
        self._pending_delta -= delta
        bar.setValue(max(bar.minimum(), min(bar.maximum(), bar.value() + delta)))
