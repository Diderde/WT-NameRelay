from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QScrollArea,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.widgets.feature_card import FeatureCard
from app.widgets.about_dialog import AboutDialog
from app.branding import APP_NAME, AUTHOR_VERSION


class HomePage(QWidget):
    """Landing page containing the three available tool modules."""

    navigate_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._card_column_count = 3

        root = QVBoxLayout(self)
        root.setContentsMargins(48, 34, 48, 34)
        root.setSpacing(0)

        header = QHBoxLayout()
        eyebrow = QLabel("战争雷霆语音工具")
        eyebrow.setObjectName("sectionEyebrow")
        header.addWidget(eyebrow); header.addStretch(1)
        about_button = QPushButton("关于与许可")
        about_button.setObjectName("aboutButton"); about_button.clicked.connect(lambda: AboutDialog(self).exec()); header.addWidget(about_button)
        root.addLayout(header)
        root.addSpacing(8)

        title = QLabel(APP_NAME)
        title.setObjectName("appTitle")
        root.addWidget(title)
        root.addSpacing(6)

        subtitle = QLabel(f"{AUTHOR_VERSION}　战争雷霆语音包文件名称补全与复制工具")
        subtitle.setObjectName("appSubtitle")
        root.addWidget(subtitle)
        root.addSpacing(28)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("homeScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._card_container = QWidget()
        self._card_container.setObjectName("cardContainer")
        self._card_grid = QGridLayout(self._card_container)
        self._card_grid.setContentsMargins(4, 6, 4, 14)
        self._card_grid.setHorizontalSpacing(18)
        self._card_grid.setVerticalSpacing(18)
        self._card_grid.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.crew_card = FeatureCard(
            "crew",
            "车组文件复制",
            "用于处理车组语音相关文件名称",
            ":/icons/crew.svg",
        )
        self.radio_card = FeatureCard(
            "radio",
            "无线电文件复制",
            "用于处理无线电语音相关文件名称",
            ":/icons/radio.svg",
        )
        self.bank_card = FeatureCard(
            "bank",
            "Bank 文件复制",
            "用于处理 Bank 相关文件名称",
            ":/icons/bank.svg",
        )
        self.audio_card = FeatureCard(
            "audio",
            "\u8bed\u97f3\u5904\u7406",
            "\u7528\u4e8e\u7f16\u8f91\u3001\u5bfc\u51fa\u4e0e\u8865\u9f50\u8bed\u97f3\u9879\u76ee\u6587\u4ef6",
            ":/icons/audio_processing.svg",
        )
        self.cards = (self.crew_card, self.radio_card, self.bank_card, self.audio_card)
        for card in self.cards:
            card.activated.connect(self.navigate_requested.emit)

        self._scroll.setWidget(self._card_container)
        self._scroll.viewport().installEventFilter(self)
        root.addWidget(self._scroll, 1)
        self._rebuild_grid(3)

    @staticmethod
    def column_count_for_width(width: int) -> int:
        if width >= 1120:
            return 4
        if width >= 840:
            return 3
        if width >= 560:
            return 2
        return 1

    @property
    def card_column_count(self) -> int:
        return self._card_column_count

    def set_navigation_enabled(self, enabled: bool) -> None:
        for card in self.cards:
            if enabled:
                card.setEnabled(True)
                card.set_transition_active(False)
            else:
                card.set_transition_active(True)
                card.setEnabled(False)

    def _update_columns(self, width: int) -> None:
        columns = self.column_count_for_width(width)
        if columns != self._card_column_count:
            self._rebuild_grid(columns)

    def _rebuild_grid(self, columns: int) -> None:
        for card in self.cards:
            self._card_grid.removeWidget(card)
        for column in range(len(self.cards)):
            self._card_grid.setColumnStretch(column, 0)
        for index, card in enumerate(self.cards):
            row, column = divmod(index, columns)
            self._card_grid.addWidget(card, row, column)
        for column in range(columns):
            self._card_grid.setColumnStretch(column, 1)
        self._card_column_count = columns
        self._card_container.updateGeometry()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._update_columns(self._scroll.viewport().width())
        return super().eventFilter(watched, event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._update_columns(self._scroll.viewport().width())
