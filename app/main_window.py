from __future__ import annotations

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget

from app.pages import AudioProcessingPage, BankPage, CrewPage, HomePage, RadioPage
from app.resources import resources_rc as _resources_rc
from app.widgets.animated_stack import AnimatedStack, TransitionDirection
from app.branding import ICON_RESOURCE, WINDOW_TITLE
from PySide6.QtGui import QIcon


class MainWindow(QMainWindow):
    """Application shell responsible only for page routing."""

    HOME_INDEX = 0
    CREW_INDEX = 1
    RADIO_INDEX = 2
    BANK_INDEX = 3
    AUDIO_INDEX = 4

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowIcon(QIcon(ICON_RESOURCE))
        self.setMinimumSize(820, 620)
        self.resize(1100, 700)

        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        self.stack = AnimatedStack()
        root_layout.addWidget(self.stack)

        self.home_page = HomePage()
        self.crew_page = CrewPage()
        self.radio_page = RadioPage()
        self.bank_page = BankPage()
        self.audio_page = AudioProcessingPage()
        self.pages = (
            self.home_page,
            self.crew_page,
            self.radio_page,
            self.bank_page,
            self.audio_page,
        )
        for page in self.pages:
            self.stack.addWidget(page)
        self.stack.setCurrentIndex(self.HOME_INDEX)

        self._route_indexes = {
            "crew": self.CREW_INDEX,
            "radio": self.RADIO_INDEX,
            "bank": self.BANK_INDEX,
            "audio": self.AUDIO_INDEX,
        }
        self.home_page.navigate_requested.connect(self._open_tool_page)
        self.crew_page.back_requested.connect(self._return_home)
        self.radio_page.back_requested.connect(self._return_home)
        self.bank_page.back_requested.connect(self._return_home)
        self.audio_page.back_requested.connect(self._return_home)
        self.stack.transition_started.connect(lambda _index: self._set_navigation_enabled(False))
        self.stack.transition_finished.connect(lambda _index: self._set_navigation_enabled(True))
        self.crew_page.close_ready.connect(self._close_after_active_task)
        self.radio_page.close_ready.connect(self._close_after_active_task)
        self.bank_page.close_ready.connect(self._close_after_active_task)
        self.audio_page.close_ready.connect(self._close_after_active_task)
        self._allow_close = False

    def _open_tool_page(self, route_key: str) -> None:
        target_index = self._route_indexes.get(route_key)
        if target_index is not None:
            self.stack.transition_to(target_index, TransitionDirection.FORWARD)

    def _return_home(self) -> None:
        current_page = self.stack.currentWidget()
        if current_page in (self.crew_page, self.radio_page, self.bank_page, self.audio_page) and not current_page.can_navigate_away():
            return
        self.stack.transition_to(self.HOME_INDEX, TransitionDirection.BACKWARD)

    def _set_navigation_enabled(self, enabled: bool) -> None:
        self.home_page.set_navigation_enabled(enabled)
        self.crew_page.set_navigation_enabled(enabled)
        self.radio_page.set_navigation_enabled(enabled)
        self.bank_page.set_navigation_enabled(enabled)
        self.audio_page.set_navigation_enabled(enabled)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._allow_close:
            active_copy_page = next(
                (page for page in (self.crew_page, self.radio_page, self.bank_page, self.audio_page) if page.is_busy),
                None,
            )
            if active_copy_page is not None and not active_copy_page.request_safe_close():
                event.ignore()
                return
        self.stack.finish_transition()
        super().closeEvent(event)

    def _close_after_active_task(self) -> None:
        self._allow_close = True
        self.close()
