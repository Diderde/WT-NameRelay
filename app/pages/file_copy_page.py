# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from app.i18n import tr
from app.widgets.feature_card import FeatureCard

from .base_tool_page import BaseToolPage


class FileCopyPage(BaseToolPage):
    """Second-level selector that groups the three name-copy tool pages."""

    navigate_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("copy", tr("page.copy.title"), parent)
        self.status_panel.setVisible(False)

        self.crew_card = FeatureCard(
            "crew",
            tr("home.card.crew.title"),
            tr("home.card.crew.desc"),
            card_height=140,
        )
        self.radio_card = FeatureCard(
            "radio",
            tr("home.card.radio.title"),
            tr("home.card.radio.desc"),
            card_height=140,
        )
        self.bank_card = FeatureCard(
            "bank",
            tr("home.card.bank.title"),
            tr("home.card.bank.desc"),
            card_height=140,
        )
        self.cards = (self.crew_card, self.radio_card, self.bank_card)
        for card in self.cards:
            card.activated.connect(self.navigate_requested.emit)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("copyGroupScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        container = QFrame()
        container.setObjectName("copyGroupContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 6, 4, 14)
        layout.setSpacing(18)
        for card in self.cards:
            layout.addWidget(card)
        layout.addStretch(1)
        self._scroll.setWidget(container)
        self.set_body_widget(self._scroll)

    def can_navigate_away(self) -> bool:
        return True

    def set_navigation_enabled(self, enabled: bool) -> None:
        super().set_navigation_enabled(enabled)
        for card in self.cards:
            if enabled:
                card.setEnabled(True)
                card.set_transition_active(False)
            else:
                card.set_transition_active(True)
                card.setEnabled(False)

    def retranslate(self) -> None:
        super().retranslate()
        for card in self.cards:
            card.retranslate()
