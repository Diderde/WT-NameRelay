from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QAbstractAnimation,
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QColor,
    QHideEvent,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.contracts import TaskState, TaskStatusSnapshot
from app.i18n import i18n_live, i18n_text
from app.i18n import mark as _i18n_mark
from app.i18n import refresh as _i18n_refresh

_STATE_TEXT: dict[TaskState, str] = {TaskState.WAITING: i18n_text('w.026'), TaskState.PREPARING: i18n_text('w.027'), TaskState.RUNNING: i18n_text('w.028'), TaskState.PAUSED: i18n_text('w.029'), TaskState.COMPLETED: i18n_text('w.030'), TaskState.PARTIAL_FAILED: i18n_text('w.031'), TaskState.FAILED: i18n_text('w.032'), TaskState.CANCELLED: i18n_text('w.033')}

def _refresh_style(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()

class SmoothProgressBar(QProgressBar):
    """Progress bar with smooth value changes and a restrained running sheen."""

    def __init__(self, parent: QWidget | None=None) -> None:
        super().__init__(parent)
        self._shimmer_phase = 0.0
        self._task_state = TaskState.WAITING
        self.setObjectName('progressBar')
        self.setRange(0, 100)
        self.setValue(0)
        self.setFormat(i18n_text('w.034'))
        self.setTextVisible(True)
        self._value_animation = QPropertyAnimation(self, b'value', self)
        self._value_animation.setDuration(180)
        self._value_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._shimmer_animation = QPropertyAnimation(self, b'shimmerPhase', self)
        self._shimmer_animation.setStartValue(0.0)
        self._shimmer_animation.setEndValue(1.0)
        self._shimmer_animation.setDuration(1500)
        self._shimmer_animation.setLoopCount(-1)
        self._shimmer_animation.setEasingCurve(QEasingCurve.Type.Linear)

    def retranslate(self) -> None:
        _i18n_refresh(self)

    def _get_shimmer_phase(self) -> float:
        return self._shimmer_phase

    def _set_shimmer_phase(self, value: float) -> None:
        self._shimmer_phase = value
        self.update()
    shimmerPhase = Property(float, _get_shimmer_phase, _set_shimmer_phase)

    def set_smooth_value(self, value: int) -> None:
        target = max(0, min(100, int(value)))
        self._value_animation.stop()
        if target == self.value():
            self.setValue(target)
            return
        self._value_animation.setStartValue(self.value())
        self._value_animation.setEndValue(target)
        self._value_animation.start()

    def set_task_state(self, state: TaskState) -> None:
        self._task_state = state
        self.setProperty('taskState', state.value)
        _refresh_style(self)
        if state == TaskState.RUNNING and self.isVisible():
            self._start_shimmer()
        else:
            self._stop_shimmer()

    def stop_animations(self) -> None:
        self._value_animation.stop()
        self._stop_shimmer()

    def _start_shimmer(self) -> None:
        if self._shimmer_animation.state() != QAbstractAnimation.State.Running:
            self._shimmer_animation.start()

    def _stop_shimmer(self) -> None:
        self._shimmer_animation.stop()
        self._shimmer_phase = 0.0
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self._task_state != TaskState.RUNNING or self.value() <= 0:
            return
        inner = self.rect().adjusted(2, 2, -2, -2)
        filled_width = round(inner.width() * self.value() / 100)
        if filled_width <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip_path = QPainterPath()
        clip_path.addRoundedRect(inner, 5.0, 5.0)
        painter.setClipPath(clip_path)
        painter.setClipRect(inner.x(), inner.y(), filled_width, inner.height(), Qt.ClipOperation.IntersectClip)
        center_x = inner.x() - 45 + (filled_width + 90) * self._shimmer_phase
        gradient = QLinearGradient(center_x - 40, 0, center_x + 40, 0)
        gradient.setColorAt(0.0, QColor(255, 244, 224, 0))
        gradient.setColorAt(0.5, QColor(255, 244, 224, 46))
        gradient.setColorAt(1.0, QColor(255, 244, 224, 0))
        painter.fillRect(inner, gradient)
        painter.end()

    def hideEvent(self, event: QHideEvent) -> None:
        self._stop_shimmer()
        super().hideEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._task_state == TaskState.RUNNING:
            self._start_shimmer()

class TaskStatusPanel(QFrame):
    """Reusable task-status surface shared by every tool page."""
    start_requested = Signal()
    pause_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None=None) -> None:
        super().__init__(parent)
        self._current_file_raw = '—'
        self.setObjectName('taskStatusPanel')
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 15, 18, 16)
        root.setSpacing(12)
        heading_row = QHBoxLayout()
        self.title_label = _i18n_mark(QLabel(i18n_text('w.035')), 'text', 'w.035')
        self.title_label.setObjectName('statusPanelTitle')
        self.status_label = _i18n_mark(QLabel(i18n_text('w.036')), 'text', 'w.036')
        self.status_label.setObjectName('statusLabel')
        self.status_label.setProperty('taskState', TaskState.WAITING.value)
        heading_row.addWidget(self.title_label)
        heading_row.addStretch(1)
        heading_row.addWidget(self.status_label)
        root.addLayout(heading_row)
        self.progress_bar = SmoothProgressBar()
        root.addWidget(self.progress_bar)
        details = QGridLayout()
        details.setHorizontalSpacing(24)
        details.setVerticalSpacing(8)
        self.processed_label = _i18n_mark(QLabel(i18n_text('w.037')), 'text', 'w.037')
        self.processed_label.setObjectName('processedLabel')
        self.success_label = _i18n_mark(QLabel(i18n_text('w.038')), 'text', 'w.038')
        self.success_label.setObjectName('successLabel')
        self.skipped_label = _i18n_mark(QLabel(i18n_text('w.039')), 'text', 'w.039')
        self.skipped_label.setObjectName('skippedLabel')
        self.failure_label = _i18n_mark(QLabel(i18n_text('w.040')), 'text', 'w.040')
        self.failure_label.setObjectName('failureLabel')
        self.failure_label.setProperty('hasFailures', False)
        current_file_caption = _i18n_mark(QLabel(i18n_text('w.041')), 'text', 'w.041')
        current_file_caption.setObjectName('mutedLabel')
        self.current_file_label = QLabel('—')
        self.current_file_label.setObjectName('currentFileLabel')
        details.addWidget(self.processed_label, 0, 0)
        details.addWidget(self.success_label, 0, 1)
        details.addWidget(self.skipped_label, 0, 2)
        details.addWidget(self.failure_label, 0, 3)
        details.addWidget(current_file_caption, 1, 0)
        details.addWidget(self.current_file_label, 1, 1, 1, 3)
        details.setColumnStretch(0, 0)
        details.setColumnStretch(1, 0)
        details.setColumnStretch(3, 1)
        root.addLayout(details)
        self.controls_widget = QWidget()
        controls = QHBoxLayout(self.controls_widget)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addStretch(1)
        self.start_button = _i18n_mark(QPushButton(i18n_text('w.042')), 'text', 'w.042')
        self.start_button.setObjectName('startButton')
        self.pause_button = _i18n_mark(QPushButton(i18n_text('w.043')), 'text', 'w.043')
        self.pause_button.setObjectName('pauseButton')
        self.cancel_button = _i18n_mark(QPushButton(i18n_text('ui.047')), 'text', 'ui.047')
        self.cancel_button.setObjectName('cancelButton')
        controls.addWidget(self.start_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.cancel_button)
        root.addWidget(self.controls_widget)
        self.start_button.clicked.connect(self.start_requested.emit)
        self.pause_button.clicked.connect(self.pause_requested.emit)
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        self.set_controls_enabled(False, False, False)

    @Slot(object)
    def set_snapshot(self, snapshot: TaskStatusSnapshot) -> None:
        if not isinstance(snapshot, TaskStatusSnapshot):
            raise TypeError('snapshot must be a TaskStatusSnapshot')
        state_text = snapshot.message.strip() or _STATE_TEXT[snapshot.state]
        self.status_label.setText(i18n_live('w.004').format(state_text))
        self.status_label.setProperty('taskState', snapshot.state.value)
        _refresh_style(self.status_label)
        progress = max(0, min(100, snapshot.progress))
        if snapshot.state == TaskState.COMPLETED:
            progress = 100
        self.progress_bar.set_task_state(snapshot.state)
        self.progress_bar.set_smooth_value(progress)
        processed = max(0, snapshot.processed)
        total = max(0, snapshot.total)
        succeeded = max(0, snapshot.succeeded)
        skipped = max(0, snapshot.skipped)
        failed = max(0, snapshot.failed)
        self.processed_label.setText(i18n_live('w.022').format(processed, total))
        self.success_label.setText(i18n_live('w.023').format(succeeded))
        self.skipped_label.setText(i18n_live('w.024').format(skipped))
        self.failure_label.setText(i18n_live('w.025').format(failed))
        self.failure_label.setProperty('hasFailures', failed > 0)
        _refresh_style(self.failure_label)
        self._current_file_raw = snapshot.current_file.strip() or '—'
        self.current_file_label.setToolTip('' if self._current_file_raw == '—' else self._current_file_raw)
        self._update_current_file_text()

    @Slot()
    def reset(self) -> None:
        self.progress_bar.stop_animations()
        self.progress_bar.setValue(0)
        self.set_snapshot(TaskStatusSnapshot())
        self.progress_bar.stop_animations()
        self.progress_bar.setValue(0)
        self.set_controls_enabled(False, False, False)

    def set_controls_enabled(self, start: bool, pause: bool, cancel: bool) -> None:
        self.start_button.setEnabled(start)
        self.pause_button.setEnabled(pause)
        self.cancel_button.setEnabled(cancel)

    def set_controls_visible(self, visible: bool) -> None:
        """Allow specialised pages to provide their own fixed action bar."""
        self.controls_widget.setVisible(visible)

    def set_title(self, title: str) -> None:
        """Set a contextual heading when several task panels share one page."""
        self.title_label.setText(title)

    def _update_current_file_text(self) -> None:
        available_width = max(80, self.current_file_label.width())
        elided = self.current_file_label.fontMetrics().elidedText(self._current_file_raw, Qt.TextElideMode.ElideMiddle, available_width)
        self.current_file_label.setText(elided)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_current_file_text()