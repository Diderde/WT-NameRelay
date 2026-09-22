from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.branding import APP_NAME
from app.i18n import current_language, on_language_changed, set_language, tr
from app.styles import theme
from app.widgets.about_dialog import AboutDialog
from app.widgets.feature_card import FeatureCard
from app.widgets.water_backdrop import is_reduced_motion, set_reduced_motion


class HomePage(QWidget):
    """Landing page with one entry per tool group."""

    navigate_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._card_column_count = 2

        root = QVBoxLayout(self)
        root.setContentsMargins(48, 34, 48, 34)
        root.setSpacing(0)

        header = QHBoxLayout()
        eyebrow = QLabel(tr("home.eyebrow"))
        self._eyebrow = eyebrow
        eyebrow.setObjectName("sectionEyebrow")
        header.addWidget(eyebrow); header.addStretch(1)
        self.language_button = QPushButton()
        self.language_button.setObjectName("headerToggleButton")
        self.language_button.clicked.connect(self._toggle_language)
        header.addWidget(self.language_button)
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("headerToggleButton")
        self.theme_button.clicked.connect(self._toggle_theme)
        header.addWidget(self.theme_button)
        self.motion_button = QPushButton()
        self.motion_button.setObjectName("headerToggleButton")
        self.motion_button.clicked.connect(self._toggle_motion)
        header.addWidget(self.motion_button)
        about_button = QPushButton(tr("home.about"))
        self._about_button = about_button
        about_button.setObjectName("aboutButton"); about_button.clicked.connect(lambda: AboutDialog(self).exec()); header.addWidget(about_button)
        root.addLayout(header)
        root.addSpacing(8)

        title = QLabel(APP_NAME)
        self._title_label = title
        title.setObjectName("appTitle")
        root.addWidget(title)
        root.addSpacing(6)

        subtitle = QLabel(tr("home.subtitle"))
        self._subtitle_label = subtitle
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

        self.copy_card = FeatureCard(
            "copy",
            tr("home.card.copy.title"),
            tr("home.card.copy.desc"),
        )
        self.audio_card = FeatureCard(
            "audio",
            tr("home.card.audio.title"),
            tr("home.card.audio.desc"),
        )
        self.tts_card = FeatureCard(
            "tts",
            tr("home.card.tts.title"),
            tr("home.card.tts.desc"),
        )
        self.cards = (self.copy_card, self.audio_card, self.tts_card)
        for card in self.cards:
            card.activated.connect(self.navigate_requested.emit)

        self._scroll.setWidget(self._card_container)
        self._scroll.viewport().installEventFilter(self)
        root.addWidget(self._scroll, 1)
        self._rebuild_grid(2)
        on_language_changed(self._on_language_changed)
        self.retranslate()

    def _toggle_language(self) -> None:
        set_language("en" if current_language() == "zh" else "zh")

    def _toggle_theme(self) -> None:
        theme.set_mode("light" if theme.current_mode() == "dark" else "dark")
        self.retranslate()

    def _toggle_motion(self) -> None:
        set_reduced_motion(not is_reduced_motion())
        self.retranslate()

    def _on_language_changed(self, _language: str) -> None:
        self.retranslate()

    def retranslate(self) -> None:
        self._eyebrow.setText(tr("home.eyebrow"))
        self._subtitle_label.setText(tr("home.subtitle"))
        self._about_button.setText(tr("home.about"))
        self.language_button.setText(tr("home.toggle.language"))
        self.theme_button.setText(
            tr("home.toggle.theme.light") if theme.current_mode() == "dark" else tr("home.toggle.theme.dark")
        )
        self.motion_button.setText(
            tr("home.toggle.motion.off") if is_reduced_motion() else tr("home.toggle.motion.on")
        )
        for card in self.cards:
            card.retranslate()

    @staticmethod
    def column_count_for_width(width: int) -> int:
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
