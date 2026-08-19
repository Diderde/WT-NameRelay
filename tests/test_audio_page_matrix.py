from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QTimer, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QScrollArea

from app.audio import AudioMatrixExportService, ExportSettings, FfmpegLocator, TimelineModel
from app.models import ManualCopyMode
from app.pages.audio_processing_page import AudioProcessingPage
from app.services import MatrixGroupPlanner
from app.widgets.pyqtgraph_timeline import PyQtGraphTimeline, TimelineViewBox


class _WheelStub:
    def __init__(self, delta: int, modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier) -> None:
        self._delta = delta
        self._modifiers = modifiers
        self.accepted = False

    def modifiers(self):
        return self._modifiers

    def delta(self):
        return self._delta

    def accept(self):
        self.accepted = True


class AudioPageMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["audio-page-matrix-tests"])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.app.processEvents()
        self.temporary.cleanup()

    def _eligible_group(self, page: AudioProcessingPage):
        unique = {group.group_key: group for group in page._groups._by_name.values()}
        planner = MatrixGroupPlanner()
        for group in unique.values():
            layout = planner.analyze(
                group.group_key,
                group.names,
                lambda name: (
                    owner.group_key if (owner := page._groups.lookup(name)) is not None else None
                ),
            )
            if layout is not None and group.category:
                return group, layout
        self.fail("No categorized eligible matrix group found")

    def _prepare_page(self):
        page = AudioProcessingPage()
        page.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        page.path_edit.setText(str(self.root))
        page._set_root()
        group, layout = self._eligible_group(page)
        page.target_edit.setText(group.names[0])
        page._target_timer.stop()
        page._resolve_target()
        return page, group, layout

    def _prepare_radio_nine_page(self):
        page = AudioProcessingPage()
        page.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        page.path_edit.setText(str(self.root))
        page._set_root()
        name = "pilot_tickets_lead_continue_enemy_1_v1"
        group = page._groups.lookup(name)
        self.assertIsNotNone(group)
        assert group is not None
        layout = page._matrix_planner.analyze(
            group.group_key,
            group.names,
            lambda member: (
                owner.group_key if (owner := page._groups.lookup(member)) is not None else None
            ),
        )
        self.assertIsNotNone(layout)
        assert layout is not None
        self.assertEqual(len(layout.subgroups), 3)
        page.target_edit.setText(name)
        page._target_timer.stop()
        page._resolve_target()
        return page, group, layout

    def _wait_for_matrix_copy(self, page: AudioProcessingPage, timeout_ms: int = 3000) -> None:
        elapsed = 0
        while page._matrix_copy_service.is_busy and elapsed < timeout_ms:
            self.app.processEvents()
            time.sleep(0.01)
            elapsed += 10
        self.app.processEvents()
        self.assertFalse(page._matrix_copy_service.is_busy, "matrix copy did not finish")

    def test_timeline_has_bounded_vertical_size_without_changing_data(self) -> None:
        timeline = PyQtGraphTimeline()
        model = TimelineModel()
        model.add_blank(duration=2.0)
        timeline.set_timeline(model)
        self.assertEqual(timeline.minimumHeight(), 220)
        self.assertEqual(timeline.maximumHeight(), 340)
        self.assertEqual(timeline.sizeHint().height(), 300)
        self.assertEqual(model.duration_ms, 2000)
        timeline.close()

    def test_plain_timeline_wheel_requests_zoom_and_shift_requests_pan(self) -> None:
        box = TimelineViewBox()
        zooms: list[float] = []
        pans: list[float] = []
        box.zoom_requested.connect(zooms.append)
        box.horizontal_pan_requested.connect(pans.append)
        plain = _WheelStub(120)
        shifted = _WheelStub(120, Qt.KeyboardModifier.ShiftModifier)
        box.wheelEvent(plain)
        box.wheelEvent(shifted)
        self.assertTrue(plain.accepted)
        self.assertEqual(len(zooms), 1)
        self.assertEqual(len(pans), 1)

    def test_right_hot_zone_routes_to_outer_page_scroll(self) -> None:
        page = AudioProcessingPage()
        page.resize(760, 480)
        page.show()
        self.app.processEvents()
        scroll = page._body_widget
        self.assertIsInstance(scroll, QScrollArea)
        assert isinstance(scroll, QScrollArea)
        bar = scroll.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        bar.setValue(0)
        viewport = scroll.viewport()
        local = QPoint(max(0, viewport.width() - 5), min(100, viewport.height() - 1))
        global_position = viewport.mapToGlobal(local)
        event = QWheelEvent(
            QPointF(local),
            QPointF(global_position),
            QPoint(),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        before = bar.value()
        consumed = page._scroll_router.eventFilter(page.timeline_view.graph.viewport(), event)
        QTest.qWait(25)
        self.assertTrue(consumed)
        self.assertGreater(bar.value(), before)
        page.close()

    def test_target_recognition_syncs_navigation_and_same_group_keeps_timeline_and_mode(self) -> None:
        page, group, layout = self._prepare_page()
        page._timeline.add_blank(duration=2.0)
        page._render_timeline()
        page._set_audio_copy_mode(ManualCopyMode.AVERAGE)
        second_name = layout.subgroups[0].names[1]
        page.target_edit.setText(second_name)
        page._target_timer.stop()
        page._resolve_target()
        self.assertEqual(page._audio_copy_mode, ManualCopyMode.AVERAGE)
        self.assertEqual(page._timeline.duration_ms, 2000)
        self.assertTrue(page._module_button_by_id[group.module].isChecked())
        self.assertTrue(page._category_button_by_id[group.category].isChecked())
        page.close()

    def test_matrix_export_renders_once_and_writes_three_identical_targets(self) -> None:
        model = TimelineModel()
        model.add_blank(duration=0.1)
        snapshot = model.snapshot()
        targets = tuple(self.root / f"target_{index}.wav" for index in range(3))
        worker = AudioMatrixExportService(
            snapshot,
            ExportSettings(),
            targets,  # type: ignore[arg-type]
            threading.Event(),
        )
        renders: list[Path] = []

        def fake_render(path: Path) -> None:
            renders.append(path)
            path.write_bytes(b"one-render")

        finished: list[tuple] = []
        worker.finished.connect(lambda *args: finished.append(args))
        with patch.object(worker, "_run_ffmpeg", side_effect=fake_render), patch.object(
            FfmpegLocator, "probe_duration_ms", return_value=100
        ):
            worker.run()
        self.assertEqual(len(renders), 1)
        self.assertTrue(finished[-1][0], finished)
        self.assertEqual([path.read_bytes() for path in targets], [b"one-render"] * 3)
        self.assertFalse(list(self.root.glob("*.part")))

    def test_average_fill_uses_one_source_for_every_member_of_target_subgroup(self) -> None:
        page, group, layout = self._prepare_page()
        directory = page._directory()
        assert directory is not None
        source_group = layout.subgroups[0]
        for name in source_group.names:
            (directory / f"{name}.wav").write_bytes(b"source-A")
        page._set_audio_copy_mode(ManualCopyMode.AVERAGE)
        page._refresh_group()
        captured = []
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), patch.object(
            page._matrix_copy_service,
            "start_copy",
            side_effect=lambda plan, policy: captured.append((plan, policy)) or True,
        ):
            page._fill()
        self.assertEqual(len(captured), 1)
        plan = captured[0][0]
        self.assertEqual(len(plan.operations), len(group.names))
        for subgroup in layout.subgroups[1:]:
            operations = [op for op in plan.operations if op.target_member_name in subgroup.names]
            self.assertEqual(len(operations), 3)
            self.assertEqual(len({op.source_original_path for op in operations}), 1)
        page.close()

    def test_real_qmessagebox_integer_yes_starts_and_completes_full_nine_operations(self) -> None:
        page, _group, layout = self._prepare_radio_nine_page()
        directory = page._directory()
        assert directory is not None
        for member in layout.subgroups[0].names:
            (directory / f"{member}.wav").write_bytes(b"source-A")
        page._set_audio_copy_mode(ManualCopyMode.AVERAGE)
        page._refresh_group()
        processed: list[int] = []
        page._matrix_copy_service.snapshot_changed.connect(
            lambda snapshot: processed.append(snapshot.processed)
        )

        def click_yes() -> None:
            dialog = self.app.activeModalWidget()
            self.assertIsInstance(dialog, QMessageBox)
            assert isinstance(dialog, QMessageBox)
            dialog.button(QMessageBox.StandardButton.Yes).click()

        QTimer.singleShot(20, click_yes)
        page._fill()
        self.assertTrue(page._matrix_copy_service.is_busy)
        self._wait_for_matrix_copy(page)
        generated = [
            directory / f"{member}.wav"
            for subgroup in layout.subgroups[1:]
            for member in subgroup.names
        ]
        self.assertTrue(all(path.is_file() for path in generated))
        self.assertEqual(len(generated), 6)
        self.assertIn(0, processed)
        self.assertEqual(processed[-1], 9)
        QTest.qWait(550)
        self.assertIn("9 / 9", page.group_detail.text())
        page.close()

    def test_average_fill_integer_no_does_not_start(self) -> None:
        page, _group, layout = self._prepare_radio_nine_page()
        directory = page._directory()
        assert directory is not None
        for member in layout.subgroups[0].names:
            (directory / f"{member}.wav").write_bytes(b"source-A")
        page._set_audio_copy_mode(ManualCopyMode.AVERAGE)
        page._refresh_group()
        with patch.object(QMessageBox, "question", return_value=int(QMessageBox.StandardButton.No)), patch.object(
            page._matrix_copy_service, "start_copy"
        ) as start_copy:
            page._fill()
        start_copy.assert_not_called()
        page.close()

    def test_average_fill_freezes_plan_and_rejects_new_conflict_after_confirmation(self) -> None:
        page, _group, layout = self._prepare_radio_nine_page()
        directory = page._directory()
        assert directory is not None
        for member in layout.subgroups[0].names:
            (directory / f"{member}.wav").write_bytes(b"source-A")
        page._set_audio_copy_mode(ManualCopyMode.AVERAGE)
        page._refresh_group()
        new_target = directory / f"{layout.subgroups[1].names[0]}.wav"

        def confirm_with_race(*_args, **_kwargs):
            new_target.write_bytes(b"external")
            return int(QMessageBox.StandardButton.Yes)

        with patch.object(QMessageBox, "question", side_effect=confirm_with_race), patch.object(
            QMessageBox, "warning"
        ) as warning, patch.object(page._matrix_copy_service, "start_copy") as start_copy:
            page._fill()
        start_copy.assert_not_called()
        warning.assert_called_once()
        self.assertEqual(new_target.read_bytes(), b"external")
        page.close()

    def test_average_fill_start_rejection_is_reported(self) -> None:
        page, _group, layout = self._prepare_radio_nine_page()
        directory = page._directory()
        assert directory is not None
        for member in layout.subgroups[0].names:
            (directory / f"{member}.wav").write_bytes(b"source-A")
        page._set_audio_copy_mode(ManualCopyMode.AVERAGE)
        page._refresh_group()
        with patch.object(QMessageBox, "question", return_value=int(QMessageBox.StandardButton.Yes)), patch.object(
            page._matrix_copy_service, "start_copy", return_value=False
        ), patch.object(QMessageBox, "warning") as warning:
            page._fill()
        warning.assert_called_once()
        self.assertIn("未启动", page.target_info.text())
        self.assertFalse(page._matrix_copy_service.is_busy)
        page.close()

    def test_average_fill_start_exception_is_reported_and_controls_recover(self) -> None:
        page, _group, layout = self._prepare_radio_nine_page()
        directory = page._directory()
        assert directory is not None
        for member in layout.subgroups[0].names:
            (directory / f"{member}.wav").write_bytes(b"source-A")
        page._set_audio_copy_mode(ManualCopyMode.AVERAGE)
        page._refresh_group()
        with patch.object(QMessageBox, "question", return_value=int(QMessageBox.StandardButton.Yes)), patch.object(
            page._matrix_copy_service, "start_copy", side_effect=RuntimeError("thread unavailable")
        ), patch.object(QMessageBox, "critical") as critical:
            page._fill()
        critical.assert_called_once()
        self.assertIn("thread unavailable", page.target_info.text())
        self.assertTrue(page.fill_button.isEnabled())
        page.close()

    def test_average_export_accepts_real_integer_yes_result(self) -> None:
        page, group, layout = self._prepare_radio_nine_page()
        directory = page._directory()
        assert directory is not None
        page._timeline.add_blank(duration=0.1)
        page._render_timeline()
        page._set_audio_copy_mode(ManualCopyMode.AVERAGE)
        (directory / f"{layout.subgroups[0].names[0]}.wav").write_bytes(b"partial")
        page._refresh_group()
        started: list[tuple] = []
        with patch.object(QMessageBox, "question", return_value=int(QMessageBox.StandardButton.Yes)), patch.object(
            page, "_start_export_worker", side_effect=lambda thread, worker: started.append((thread, worker))
        ):
            page._export()
        self.assertEqual(len(started), 1)
        worker = started[0][1]
        self.assertEqual(tuple(path.stem for path in worker.targets), layout.subgroups[0].names)
        page.close()

    def test_sequential_fill_keeps_outer_scroll_position_through_completion(self) -> None:
        page, group, _layout = self._prepare_radio_nine_page()
        directory = page._directory()
        assert directory is not None
        (directory / f"{group.names[0]}.wav").write_bytes(b"source-A")
        page._set_audio_copy_mode(ManualCopyMode.SEQUENTIAL)
        page._refresh_group()
        page.resize(760, 480)
        page.show()
        self.app.processEvents()
        scroll = page._body_widget
        self.assertIsInstance(scroll, QScrollArea)
        assert isinstance(scroll, QScrollArea)
        bar = scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.app.processEvents()
        expected = bar.value()
        observed: list[int] = []
        page._copy_service.snapshot_changed.connect(lambda _snapshot: observed.append(bar.value()))
        page._copy_service.batch_finished.connect(lambda _result: observed.append(bar.value()))
        page.fill_button.setFocus(Qt.FocusReason.MouseFocusReason)
        QTest.mouseClick(page.fill_button, Qt.MouseButton.LeftButton)
        elapsed = 0
        while page._copy_service.is_busy and elapsed < 3000:
            self.app.processEvents()
            time.sleep(0.01)
            elapsed += 10
        QTest.qWait(20)
        self.assertFalse(page._copy_service.is_busy)
        self.assertLessEqual(abs(bar.value() - expected), 2)
        self.assertTrue(observed)
        self.assertTrue(all(abs(value - expected) <= 2 for value in observed), observed)
        page.close()

    def test_task_scroll_guard_does_not_restore_again_after_user_scrolls(self) -> None:
        page, _group, _layout = self._prepare_radio_nine_page()
        page.resize(760, 480)
        page.show()
        self.app.processEvents()
        scroll = page._body_widget
        assert isinstance(scroll, QScrollArea)
        bar = scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        page._begin_task_ui_transition("test")
        page._end_task_ui_transition("test")
        QTest.qWait(20)
        user_position = max(0, bar.value() // 2)
        bar.setValue(user_position)
        page._task_progress_observed(object())
        page._refresh_group()
        QTest.qWait(20)
        self.assertEqual(bar.value(), user_position)
        page.close()

    def test_sequential_export_disabling_focused_button_keeps_scroll_position(self) -> None:
        page, _group, _layout = self._prepare_radio_nine_page()
        page._timeline.add_blank(duration=0.1)
        page._render_timeline()
        page.resize(760, 480)
        page.show()
        self.app.processEvents()
        scroll = page._body_widget
        assert isinstance(scroll, QScrollArea)
        bar = scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.app.processEvents()
        expected = bar.value()

        def simulate_started(thread, worker) -> None:
            page._export_thread = thread
            page._export_worker = worker
            page._sync()

        page.export_button.setFocus(Qt.FocusReason.MouseFocusReason)
        with patch.object(page, "_start_export_worker", side_effect=simulate_started):
            QTest.mouseClick(page.export_button, Qt.MouseButton.LeftButton)
        QTest.qWait(20)
        self.assertLessEqual(abs(bar.value() - expected), 2)
        page._export_thread = None
        page._export_worker = None
        page._sync()
        page.close()


if __name__ == "__main__":
    unittest.main()
