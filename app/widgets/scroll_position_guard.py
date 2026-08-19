from __future__ import annotations

import weakref

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QScrollArea


class ScrollPositionGuard:
    """Keep a page scroll position stable across deferred Qt layout updates."""

    def __init__(self, scroll_area: QScrollArea) -> None:
        self._scroll_ref = weakref.ref(scroll_area)
        self._generation = 0
        self._held_value: int | None = None

    def begin_hold(self) -> None:
        """Hold one manual-task position until its terminal UI update is rendered."""
        scroll_area = self._scroll_ref()
        if scroll_area is not None and self._held_value is None:
            self._held_value = scroll_area.verticalScrollBar().value()

    def end_hold(self) -> None:
        self.preserve()
        self._held_value = None

    def preserve(self) -> None:
        scroll_area = self._scroll_ref()
        if scroll_area is None:
            return
        bar = scroll_area.verticalScrollBar()
        value = self._held_value if self._held_value is not None else bar.value()
        self._generation += 1
        generation = self._generation

        def restore() -> None:
            area = self._scroll_ref()
            if area is None or generation != self._generation:
                return
            current_bar = area.verticalScrollBar()
            current_bar.setValue(min(value, current_bar.maximum()))

        # The second pass runs after QWidget geometry and focus changes settle.
        QTimer.singleShot(0, restore)
