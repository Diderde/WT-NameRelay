from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr
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
        self.back_button = QPushButton(tr("common.back"))
        self.back_button.setObjectName("backButton")
        self.back_button.setAccessibleName(tr("common.back"))
        self.back_button.clicked.connect(self.back_requested.emit)
        header.addWidget(self.back_button)

        heading_group = QVBoxLayout()
        heading_group.setSpacing(3)
        self._title = title
        eyebrow = QLabel(tr("page.eyebrow"))
        self._eyebrow = eyebrow
        eyebrow.setObjectName("sectionEyebrow")
        page_title = QLabel(tr(f"page.{page_key}.title", fallback=title))
        self._page_title = page_title
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
        placeholder_title = QLabel(tr("page.placeholder.title"))
        self._placeholder_title = placeholder_title
        placeholder_title.setObjectName("placeholderTitle")
        placeholder_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_text = QLabel(tr("page.placeholder.text"))
        self._placeholder_text = placeholder_text
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

    def retranslate(self) -> None:
        self.back_button.setText(tr("common.back"))
        self.back_button.setAccessibleName(tr("common.back"))
        self._eyebrow.setText(tr("page.eyebrow"))
        self._page_title.setText(tr(f"page.{self.page_key}.title", fallback=self._title))
        self._placeholder_title.setText(tr("page.placeholder.title"))
        self._placeholder_text.setText(tr("page.placeholder.text"))

    def set_body_widget(self, widget: QWidget) -> None:
        """Replace only the page-specific content, keeping shared chrome intact."""
        if self._body_widget is widget:
            return
        if self._body_widget is not None:
            self._body_layout.removeWidget(self._body_widget)
            # hide() 立即生效：deleteLater 的延迟删除依赖事件循环，
            # 窗口期内旧占位面板（默认 640x480）会作为子件残留可见。
            self._body_widget.hide()
            self._body_widget.deleteLater()
        self._body_widget = widget
        self._body_layout.addWidget(widget)
