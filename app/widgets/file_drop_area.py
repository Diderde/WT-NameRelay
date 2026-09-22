from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.i18n import i18n_text
from app.i18n import mark as _i18n_mark
from app.i18n import refresh as _i18n_refresh


class FileDropArea(QFrame):
    """Small drag-and-drop surface that forwards local filesystem paths."""
    choose_requested = Signal()
    files_dropped = Signal(list)

    def __init__(self, parent: QWidget | None=None) -> None:
        super().__init__(parent)
        self.setObjectName('fileDropArea')
        self.setAcceptDrops(True)
        self.setProperty('dragActive', False)
        self.setMinimumHeight(142)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 13, 18, 13)
        layout.setSpacing(7)
        title = _i18n_mark(QLabel(i18n_text('w.001')), 'text', 'w.001')
        title.setObjectName('dropAreaTitle')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        hint = _i18n_mark(QLabel(i18n_text('w.002')), 'text', 'w.002')
        hint.setObjectName('mutedLabel')
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        self.choose_button = _i18n_mark(QPushButton(i18n_text('w.003')), 'text', 'w.003')
        self.choose_button.setObjectName('chooseFilesButton')
        self.choose_button.setMinimumHeight(38)
        self.choose_button.clicked.connect(self.choose_requested.emit)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.choose_button, 0, Qt.AlignmentFlag.AlignHCenter)

    def retranslate(self) -> None:
        _i18n_refresh(self)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty('dragActive', True)
            self._refresh_style()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.setProperty('dragActive', False)
        self._refresh_style()
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty('dragActive', False)
        self._refresh_style()
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _refresh_style(self) -> None:
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()