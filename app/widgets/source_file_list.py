from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.i18n import i18n_live, i18n_text
from app.i18n import mark as _i18n_mark
from app.i18n import refresh as _i18n_refresh
from app.models import RecognitionState, SourceFile

_STATE_LABELS = {RecognitionState.RECOGNIZED: i18n_text('w.098'), RecognitionState.NO_EXTENSION: i18n_text('w.099'), RecognitionState.UNKNOWN_NAME: i18n_text('w.100')}

class SourceFileList(QFrame):
    """Scrollable imported-file list with per-item removal controls."""
    remove_requested = Signal(str)
    clear_requested = Signal()

    def __init__(self, parent: QWidget | None=None) -> None:
        super().__init__(parent)
        self.setObjectName('sourceFileList')
        self.setMinimumHeight(230)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        heading = QHBoxLayout()
        self.count_label = _i18n_mark(QLabel(i18n_text('w.101')), 'text', 'w.101')
        self.count_label.setObjectName('listHeading')
        self.clear_button = _i18n_mark(QPushButton(i18n_text('w.102')), 'text', 'w.102')
        self.clear_button.setObjectName('clearFilesButton')
        self.clear_button.clicked.connect(self.clear_requested.emit)
        heading.addWidget(self.count_label)
        heading.addStretch(1)
        heading.addWidget(self.clear_button)
        root.addLayout(heading)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName('sourceFileScroll')
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.container.setObjectName('sourceFileContainer')
        self.items_layout = QVBoxLayout(self.container)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(7)
        self.items_layout.addStretch(1)
        self.scroll_area.setWidget(self.container)
        root.addWidget(self.scroll_area, 1)

    def retranslate(self) -> None:
        _i18n_refresh(self)

    def set_files(self, files: Iterable[SourceFile]) -> None:
        source_files = tuple(files)
        self.count_label.setText(i18n_live('ui.068').format(len(source_files)))
        self.clear_button.setEnabled(bool(source_files))
        while self.items_layout.count() > 1:
            item = self.items_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for source in source_files:
            self.items_layout.insertWidget(self.items_layout.count() - 1, self._create_item(source))

    def _create_item(self, source: SourceFile) -> QWidget:
        item = QFrame()
        item.setObjectName('sourceFileItem')
        item.setProperty('recognized', source.is_recognized)
        layout = QHBoxLayout(item)
        layout.setContentsMargins(11, 9, 9, 9)
        layout.setSpacing(10)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)
        name = QLabel(source.file_name)
        name.setObjectName('sourceFileName')
        name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        name.setWordWrap(True)
        name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path = QLabel(str(source.path))
        path.setObjectName('sourceFilePath')
        path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        path.setWordWrap(True)
        path.setToolTip(str(source.path))
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        state_text = _STATE_LABELS[source.state]
        if source.reason:
            state_text = f'{state_text}：{source.reason}'
        state = QLabel(state_text)
        state.setObjectName('sourceFileState')
        state.setProperty('recognized', source.is_recognized)
        text_layout.addWidget(name)
        text_layout.addWidget(path)
        text_layout.addWidget(state)
        layout.addLayout(text_layout, 1)
        remove_button = _i18n_mark(QPushButton(i18n_text('w.103')), 'text', 'w.103')
        remove_button.setObjectName('removeSourceButton')
        remove_button.clicked.connect(lambda _checked=False, key=source.normalized_path: self.remove_requested.emit(key))
        layout.addWidget(remove_button)
        return item