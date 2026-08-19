from __future__ import annotations

import os
import sys
import time
import unittest
from types import TracebackType
from typing import Callable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedLayout, QWidget

from app.contracts import TaskState, TaskStatusSnapshot
from app.main_window import MainWindow
from app.pages.home_page import HomePage
from app.widgets.animated_stack import TransitionDirection
from app.widgets.task_status_panel import TaskStatusPanel


class UiSmokeTests(unittest.TestCase):
    app: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["wt-name-tool-tests"])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self._qt_exceptions: list[tuple[type[BaseException], BaseException, TracebackType | None]] = []
        self._old_excepthook = sys.excepthook

        def capture_exception(
            exception_type: type[BaseException],
            exception: BaseException,
            traceback: TracebackType | None,
        ) -> None:
            self._qt_exceptions.append((exception_type, exception, traceback))

        sys.excepthook = capture_exception

    def tearDown(self) -> None:
        sys.excepthook = self._old_excepthook
        QApplication.processEvents()
        if self._qt_exceptions:
            messages = "; ".join(f"{kind.__name__}: {error}" for kind, error, _ in self._qt_exceptions)
            self.fail(f"Qt signal handler raised: {messages}")

    def _wait_until(self, predicate: Callable[[], bool], timeout_ms: int = 1200) -> None:
        deadline = time.monotonic() + timeout_ms / 1000
        while not predicate() and time.monotonic() < deadline:
            QApplication.processEvents()
            QTest.qWait(10)
        self.assertTrue(predicate(), "Timed out waiting for UI state")

    def _create_window(self) -> MainWindow:
        window = MainWindow()
        window.show()
        QApplication.processEvents()
        QTest.qWait(30)
        return window

    def _assert_only_page_visible(self, window: MainWindow, expected_page: QWidget) -> None:
        QApplication.processEvents()
        stack_layout = window.stack.layout()
        self.assertIsInstance(stack_layout, QStackedLayout)
        if isinstance(stack_layout, QStackedLayout):
            self.assertEqual(stack_layout.stackingMode(), QStackedLayout.StackingMode.StackOne)
        self.assertIs(window.stack.currentWidget(), expected_page)
        visible_pages = [page for page in window.pages if page.isVisibleTo(window.stack)]
        self.assertEqual(visible_pages, [expected_page])
        for page in window.pages:
            with self.subTest(page=getattr(page, "page_key", "home")):
                self.assertEqual(page.isVisible(), page is expected_page)
                self.assertEqual(page.isHidden(), page is not expected_page)
        self.assertEqual(window.stack.findChildren(QWidget, "animatedStackSnapshot"), [])

    def test_status_panel_defaults_and_snapshot_updates(self) -> None:
        panel = TaskStatusPanel()
        panel.resize(760, 210)
        panel.show()
        QApplication.processEvents()

        self.assertEqual(panel.status_label.text(), "状态：等待任务")
        self.assertEqual(panel.progress_bar.value(), 0)
        self.assertEqual(panel.progress_bar.format(), "进度：%p%")
        self.assertEqual(panel.processed_label.text(), "已处理：0 / 0")
        self.assertEqual(panel.current_file_label.text(), "—")
        self.assertEqual(panel.success_label.text(), "成功：0")
        self.assertEqual(panel.skipped_label.text(), "跳过：0")
        self.assertEqual(panel.failure_label.text(), "失败：0")
        self.assertFalse(panel.start_button.isEnabled())
        self.assertFalse(panel.pause_button.isEnabled())
        self.assertFalse(panel.cancel_button.isEnabled())

        panel.set_snapshot(
            TaskStatusSnapshot(
                state=TaskState.RUNNING,
                progress=64,
                processed=16,
                total=25,
                current_file="voice_tank_commander_start_battle.wav",
                succeeded=15,
                skipped=2,
                failed=1,
            )
        )
        self._wait_until(lambda: panel.progress_bar.value() == 64)
        self.assertEqual(panel.status_label.text(), "状态：正在处理")
        self.assertEqual(panel.processed_label.text(), "已处理：16 / 25")
        self.assertEqual(panel.success_label.text(), "成功：15")
        self.assertEqual(panel.skipped_label.text(), "跳过：2")
        self.assertEqual(panel.failure_label.text(), "失败：1")
        self.assertEqual(panel.failure_label.property("hasFailures"), True)

        panel.set_snapshot(TaskStatusSnapshot(state=TaskState.COMPLETED, progress=90))
        self._wait_until(lambda: panel.progress_bar.value() == 100)
        self.assertEqual(panel.progress_bar.property("taskState"), "completed")
        panel.reset()
        self.assertEqual(panel.progress_bar.value(), 0)
        self.assertEqual(panel.status_label.text(), "状态：等待任务")
        panel.close()
        panel.deleteLater()

    def test_responsive_breakpoints_and_card_geometry(self) -> None:
        self.assertEqual(HomePage.column_count_for_width(559), 1)
        self.assertEqual(HomePage.column_count_for_width(560), 2)
        self.assertEqual(HomePage.column_count_for_width(839), 2)
        self.assertEqual(HomePage.column_count_for_width(840), 3)

        page = HomePage()
        page.show()
        for width, expected_columns in ((500, 1), (700, 2), (1000, 3)):
            with self.subTest(width=width):
                page.resize(width, 650)
                QApplication.processEvents()
                QTest.qWait(20)
                self.assertEqual(page.card_column_count, expected_columns)
                geometries = [card.geometry() for card in page.cards]
                self.assertTrue(all(rect.height() == geometries[0].height() for rect in geometries))
                for left_index, left_rect in enumerate(geometries):
                    for right_rect in geometries[left_index + 1 :]:
                        self.assertFalse(left_rect.intersects(right_rect))
        page.close()
        page.deleteLater()

    def test_window_structure_and_default_status_panels(self) -> None:
        window = self._create_window()
        self.assertEqual(window.windowTitle(), "WT-NameRelay by Beiku（beta 0.2.0）")
        self.assertEqual(window.size().width(), 1100)
        self.assertEqual(window.size().height(), 700)
        self.assertEqual(window.minimumWidth(), 820)
        self.assertEqual(window.minimumHeight(), 620)
        self.assertEqual(window.stack.count(), 5)
        self.assertIs(window.stack.currentWidget(), window.home_page)
        self.assertIsInstance(window.crew_page.status_panel, TaskStatusPanel)
        self.assertIsInstance(window.radio_page.status_panel, TaskStatusPanel)
        self.assertIsInstance(window.bank_page.status_panel, TaskStatusPanel)
        visible_windows = [
            widget
            for widget in QApplication.topLevelWidgets()
            if isinstance(widget, QMainWindow) and widget.isVisible()
        ]
        self.assertEqual(visible_windows, [window])
        window.close()
        window.deleteLater()

    def test_all_navigation_routes_return_to_home(self) -> None:
        window = self._create_window()
        routes = (
            (window.home_page.crew_card, window.crew_page),
            (window.home_page.radio_card, window.radio_page),
            (window.home_page.bank_card, window.bank_page),
        )
        for card, page in routes:
            with self.subTest(route=page.page_key):
                QTest.mouseClick(card, Qt.MouseButton.LeftButton)
                self._wait_until(lambda: not window.stack.is_animating)
                self.assertIs(window.stack.currentWidget(), page)
                self._assert_only_page_visible(window, page)
                self.assertTrue(page.back_button.isEnabled())
                QTest.mouseClick(page.back_button, Qt.MouseButton.LeftButton)
                self._wait_until(lambda: not window.stack.is_animating)
                self.assertIs(window.stack.currentWidget(), window.home_page)
                self._assert_only_page_visible(window, window.home_page)
        window.close()
        window.deleteLater()

    def test_transition_reentry_resize_cleanup_and_invalid_targets(self) -> None:
        window = self._create_window()
        stack = window.stack
        self.assertFalse(stack.transition_to(-1, TransitionDirection.FORWARD))
        self.assertFalse(stack.transition_to(stack.count(), TransitionDirection.FORWARD))
        self.assertFalse(stack.transition_to(stack.currentIndex(), TransitionDirection.FORWARD))

        self.assertTrue(stack.transition_to(window.CREW_INDEX, TransitionDirection.FORWARD))
        self.assertTrue(stack.is_animating)
        self.assertFalse(stack.transition_to(window.RADIO_INDEX, TransitionDirection.FORWARD))
        self._wait_until(lambda: not stack.is_animating)
        self.assertEqual(stack.currentIndex(), window.CREW_INDEX)
        self._assert_only_page_visible(window, window.crew_page)
        self.assertIsNone(window.crew_page.graphicsEffect())
        self.assertEqual(stack.findChildren(QWidget, "animatedStackSnapshot"), [])
        self.assertEqual(window.crew_page.geometry(), QRect(0, 0, stack.width(), stack.height()))

        self.assertTrue(stack.transition_to(window.RADIO_INDEX, TransitionDirection.FORWARD))
        window.resize(1200, 800)
        QApplication.processEvents()
        self.assertFalse(stack.is_animating)
        self.assertEqual(stack.currentIndex(), window.RADIO_INDEX)
        self._assert_only_page_visible(window, window.radio_page)
        self.assertIsNone(window.radio_page.graphicsEffect())
        self.assertEqual(stack.findChildren(QWidget, "animatedStackSnapshot"), [])

        self.assertTrue(stack.transition_to(window.HOME_INDEX, TransitionDirection.BACKWARD))
        self._wait_until(lambda: not stack.is_animating)
        self.assertEqual(stack.currentIndex(), window.HOME_INDEX)
        self._assert_only_page_visible(window, window.home_page)
        window.close()
        window.deleteLater()


if __name__ == "__main__":
    unittest.main(verbosity=2)
