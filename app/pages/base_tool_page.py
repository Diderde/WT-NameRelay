from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.widgets.task_status_panel import TaskStatusPanel


class BaseToolPage(QWidget):
    """Shared presentation-only framework for secondary pages."""

    back_requested = Signal()

    def __init__(self, page_key: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.page_key = page_key
        self.setObjectName("pageRoot")

        root = QVBoxLayout(self)
        root.setContentsMargins(34, 28, 34, 28)
        root.setSpacing(20)

        header = QHBoxLayout()
        header.setSpacing(16)
        self.back_button = QPushButton(QIcon(":/icons/back.svg"), "返回主界面")
        self.back_button.setObjectName("backButton")
        self.back_button.setAccessibleName("返回主界面")
        self.back_button.clicked.connect(self.back_requested.emit)
        header.addWidget(self.back_button)

        heading_group = QVBoxLayout()
        heading_group.setSpacing(3)
        eyebrow = QLabel("功能工作区")
        eyebrow.setObjectName("sectionEyebrow")
        page_title = QLabel(title)
        page_title.setObjectName("pageTitle")
        heading_group.addWidget(eyebrow)
        heading_group.addWidget(page_title)
        header.addLayout(heading_group)
        header.addStretch(1)
        root.addLayout(header)

        placeholder = QFrame()
        placeholder.setObjectName("placeholderPanel")
        placeholder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        placeholder_layout = QVBoxLayout(placeholder)
        placeholder_layout.setContentsMargins(32, 28, 32, 28)
        placeholder_layout.setSpacing(10)
        placeholder_layout.addStretch(1)
        placeholder_title = QLabel("功能区域")
        placeholder_title.setObjectName("placeholderTitle")
        placeholder_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_text = QLabel("功能框架已建立，具体处理逻辑将在后续阶段接入。")
        placeholder_text.setObjectName("placeholderText")
        placeholder_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_text.setWordWrap(True)
        placeholder_layout.addWidget(placeholder_title)
        placeholder_layout.addWidget(placeholder_text)
        placeholder_layout.addStretch(1)
        self._body_container = QWidget()
        self._body_layout = QVBoxLayout(self._body_container)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)
        self._body_widget: QWidget | None = None
        root.addWidget(self._body_container, 1)
        self.set_body_widget(placeholder)

        self.status_panel = TaskStatusPanel()
        root.addWidget(self.status_panel)

    def set_navigation_enabled(self, enabled: bool) -> None:
        self.back_button.setEnabled(enabled)

    def set_body_widget(self, widget: QWidget) -> None:
        """Replace only the page-specific content, keeping shared chrome intact."""
        if self._body_widget is widget:
            return
        if self._body_widget is not None:
            self._body_layout.removeWidget(self._body_widget)
            self._body_widget.deleteLater()
        self._body_widget = widget
        self._body_layout.addWidget(widget)
