from __future__ import annotations

from enum import IntEnum

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QStackedWidget


class TransitionDirection(IntEnum):
    BACKWARD = -1
    FORWARD = 1


class AnimatedStack(QStackedWidget):
    """Page switching is instant — 转场动画已移除（平实观感）。

    started/finished 信号仍成对发出：导航按钮启停与关窗协调依赖这对协议。
    """

    transition_started = Signal(int)
    transition_finished = Signal(int)

    def transition_to(self, index: int, direction: TransitionDirection | int) -> bool:
        """切页；`direction` 仅为兼容既有调用保留。非法目标返回 False。"""

        if index < 0 or index >= self.count() or index == self.currentIndex():
            return False
        self.transition_started.emit(index)
        self.setCurrentIndex(index)
        self.transition_finished.emit(index)
        return True

    @property
    def is_animating(self) -> bool:
        """恒为 False：无动画态，属性保留以兼容既有调用。"""

        return False

    def finish_transition(self) -> None:
        """兼容保留：无动画即无在途转场。"""
