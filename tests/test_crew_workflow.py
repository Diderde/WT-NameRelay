from __future__ import annotations

import os
import random
import tempfile
import threading
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.contracts import TaskState
from app.models import ConflictPolicy, CopyPlan, CopyResultStatus, CopyTask
from app.pages.crew_page import CrewPage
from app.services import CopyTaskBuilder, CrewFileService, CrewNameParser, CrewNameRepository
from app.services.file_copy_worker import FileCopyWorker


class CrewWorkflowTests(unittest.TestCase):
    app: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["wt-name-tool-crew-tests"])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.repository = CrewNameRepository()

    def _wait_until(self, predicate: object, timeout_ms: int = 3000) -> None:
        deadline = time.monotonic() + timeout_ms / 1000
        while not predicate() and time.monotonic() < deadline:  # type: ignore[operator]
            QApplication.processEvents()
            time.sleep(0.005)
        self.assertTrue(predicate(), "Timed out waiting for worker result")  # type: ignore[operator]

    def _create_source(self, directory: Path, stem: str, extension: str = ".wav", data: bytes = b"audio"):
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{stem}{extension}"
        path.write_bytes(data)
        return CrewNameParser(self.repository).parse(path)

    def _run_worker(self, plan: CopyPlan, policy: ConflictPolicy | None = None, cancel_after_first: bool = False):
        cancel_event = threading.Event()
        worker = FileCopyWorker(plan, cancel_event)
        batches = []
        conflicts = []
        successful_items = 0

        def on_item(result: object) -> None:
            nonlocal successful_items
            if getattr(result, "status", None) is CopyResultStatus.SUCCESS:
                successful_items += 1
                if cancel_after_first and successful_items == 1:
                    cancel_event.set()

        worker.finished.connect(batches.append)
        worker.conflicts_detected.connect(conflicts.append)
        worker.item_finished.connect(on_item)
        worker.prepare()
        if conflicts:
            self.assertIsNotNone(policy)
            worker.apply_conflict_policy((policy or ConflictPolicy.CANCEL_BATCH).value)
        self.assertEqual(len(batches), 1)
        return batches[0], conflicts

    def test_embedded_library_matches_locked_scope(self) -> None:
        groups = self.repository.groups()
        self.assertEqual(len(groups), 151)
        self.assertEqual(sum(len(group.names) for group in groups), 511)
        self.assertEqual(sum(group.group_type.value == "single" for group in groups), 130)
        self.assertEqual(sum(group.group_type.value == "double" for group in groups), 19)
        self.assertEqual(sum(group.group_type.value == "mixed" for group in groups), 2)
        self.assertIsNotNone(self.repository.lookup("voice_message_commander_shot_v1"))
        self.assertIsNone(self.repository.lookup("voice_message_artillery_1"))

    def test_engine_stalled_is_split_into_two_special_groups(self) -> None:
        layered = self.repository.lookup("voice_message_driver_engine_stalled_v1_1")
        single = self.repository.lookup("voice_message_driver_engine_stalled_v2")
        self.assertIsNotNone(layered)
        self.assertIsNotNone(single)
        assert layered is not None and single is not None
        self.assertNotEqual(layered.group_key, single.group_key)
        self.assertEqual(layered.names, (
            "voice_message_driver_engine_stalled_v1_1",
            "voice_message_driver_engine_stalled_v1_2",
            "voice_message_driver_engine_stalled_v1_3",
        ))
        self.assertEqual(single.names, (
            "voice_message_driver_engine_stalled_v2",
            "voice_message_driver_engine_stalled_v3",
        ))

    def test_parser_requires_extension_and_exact_case(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            no_extension = directory / "voice_message_commander_shot_v1"
            no_extension.write_bytes(b"x")
            unknown = directory / "VOICE_MESSAGE_COMMANDER_SHOT_V1.wav"
            unknown.write_bytes(b"x")
            parser = CrewNameParser(self.repository)
            self.assertEqual(parser.parse(no_extension).state.value, "no_extension")
            self.assertEqual(parser.parse(unknown).state.value, "unknown_name")

    def test_single_group_import_v1_completes_v2_and_v3(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            source = self._create_source(Path(raw_directory), "voice_message_commander_shot_v1")
            builder = CopyTaskBuilder(self.repository, random.Random(1))
            plans = builder.build_group_plans([source])
            self.assertEqual([item.target_name for item in plans[0].assignments], [
                "voice_message_commander_shot_v2",
                "voice_message_commander_shot_v3",
            ])

    def test_single_group_import_v2_completes_v1_and_v3(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            source = self._create_source(Path(raw_directory), "voice_message_commander_shot_v2")
            plans = CopyTaskBuilder(self.repository, random.Random(2)).build_group_plans([source])
            self.assertEqual({item.target_name for item in plans[0].assignments}, {
                "voice_message_commander_shot_v1",
                "voice_message_commander_shot_v3",
            })

    def test_double_group_uses_only_real_names(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            source = self._create_source(Path(raw_directory), "voice_message_chief_artillery_danger_v1_1")
            plans = CopyTaskBuilder(self.repository, random.Random(3)).build_group_plans([source])
            targets = [item.target_name for item in plans[0].assignments]
            self.assertEqual(len(targets), 7)
            self.assertIn("voice_message_chief_artillery_danger_v4_2", targets)
            self.assertNotIn("voice_message_chief_artillery_danger_v5_1", targets)

    def test_mixed_group_keeps_single_and_double_names(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            source = self._create_source(Path(raw_directory), "voice_message_commander_ucav_launch_v1_1")
            plans = CopyTaskBuilder(self.repository, random.Random(4)).build_group_plans([source])
            targets = {item.target_name for item in plans[0].assignments}
            self.assertIn("voice_message_commander_ucav_launch_v1_2", targets)
            self.assertIn("voice_message_commander_ucav_launch_v2", targets)

    def test_multiple_sources_are_balanced_and_imported_names_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            first = self._create_source(directory, "voice_message_chief_artillery_danger_v1_1")
            second = self._create_source(directory, "voice_message_chief_artillery_danger_v2_1")
            plans = CopyTaskBuilder(self.repository, random.Random(5)).build_group_plans([first, second, first])
            assignments = plans[0].assignments
            targets = {item.target_name for item in assignments}
            self.assertEqual(len(assignments), 6)
            self.assertNotIn(first.stem, targets)
            self.assertNotIn(second.stem, targets)
            counts = {first.normalized_path: 0, second.normalized_path: 0}
            for assignment in assignments:
                counts[assignment.source.normalized_path] += 1
            self.assertLessEqual(abs(counts[first.normalized_path] - counts[second.normalized_path]), 1)

    def test_different_directories_keep_independent_output_paths(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            source_a = self._create_source(root / "a", "voice_message_commander_shot_v1")
            source_b = self._create_source(root / "b", "voice_message_gunner_taking_command_v1")
            builder = CopyTaskBuilder(self.repository, random.Random(6))
            plans = builder.build_group_plans([source_a, source_b])
            selected = {assignment.selection_key: True for plan in plans for assignment in plan.assignments}
            plan = builder.build_copy_plan(plans, selected)
            self.assertTrue(any(task.target_path.parent == source_a.path.parent for task in plan.tasks))
            self.assertTrue(any(task.target_path.parent == source_b.path.parent for task in plan.tasks))

    def test_unchecked_targets_are_not_built(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            source = self._create_source(Path(raw_directory), "voice_message_commander_shot_v1")
            builder = CopyTaskBuilder(self.repository, random.Random(7))
            plans = builder.build_group_plans([source])
            selected = {assignment.selection_key: False for assignment in plans[0].assignments}
            self.assertEqual(builder.build_copy_plan(plans, selected).total, 0)

    def test_binary_copy_preserves_source_and_extension(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            payload = b"\x00\xff\x10binary-audio"
            source = directory / "voice_message_commander_shot_v1.ogg"
            source.write_bytes(payload)
            task = CopyTask("voice_message_commander_shot", source, directory / "voice_message_commander_shot_v2.ogg", "voice_message_commander_shot_v2")
            batch, conflicts = self._run_worker(CopyPlan((task,)))
            self.assertFalse(conflicts)
            self.assertEqual(batch.results[0].status, CopyResultStatus.SUCCESS)
            self.assertEqual(source.read_bytes(), payload)
            self.assertEqual(task.target_path.read_bytes(), payload)

    def test_existing_target_can_be_skipped_or_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            source = directory / "source.wav"
            target = directory / "target.wav"
            source.write_bytes(b"new")
            target.write_bytes(b"old")
            task = CopyTask("test", source, target, "target")
            skipped, conflicts = self._run_worker(CopyPlan((task,)), ConflictPolicy.SKIP_EXISTING)
            self.assertEqual(len(conflicts), 1)
            self.assertEqual(skipped.results[0].status, CopyResultStatus.SKIPPED)
            self.assertEqual(target.read_bytes(), b"old")

            overwritten, _ = self._run_worker(CopyPlan((task,)), ConflictPolicy.OVERWRITE_EXISTING)
            self.assertEqual(overwritten.results[0].status, CopyResultStatus.SUCCESS)
            self.assertEqual(target.read_bytes(), b"new")

    def test_cancel_stops_subsequent_tasks_safely(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            source = directory / "source.wav"
            source.write_bytes(b"audio")
            first = CopyTask("test", source, directory / "one.wav", "one")
            second = CopyTask("test", source, directory / "two.wav", "two")
            batch, _ = self._run_worker(CopyPlan((first, second)), cancel_after_first=True)
            self.assertEqual(batch.state, TaskState.CANCELLED)
            self.assertTrue(first.target_path.exists())
            self.assertFalse(second.target_path.exists())
            self.assertEqual(batch.results[-1].status, CopyResultStatus.CANCELLED)

    def test_missing_source_does_not_stop_other_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            source = directory / "source.wav"
            source.write_bytes(b"audio")
            missing = CopyTask("test", directory / "missing.wav", directory / "missing-target.wav", "missing")
            good = CopyTask("test", source, directory / "good.wav", "good")
            batch, _ = self._run_worker(CopyPlan((missing, good)))
            self.assertEqual(batch.state, TaskState.PARTIAL_FAILED)
            self.assertEqual(batch.results[0].status, CopyResultStatus.FAILED)
            self.assertEqual(batch.results[1].status, CopyResultStatus.SUCCESS)

    def test_crew_page_keeps_unknown_file_and_builds_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            known = directory / "voice_message_commander_shot_v1.wav"
            unknown = directory / "not_in_library.wav"
            known.write_bytes(b"a")
            unknown.write_bytes(b"b")
            page = CrewPage()
            page._add_paths([str(known), str(unknown)])
            self.assertEqual(len(page._imported_files), 2)
            self.assertEqual(len(page._group_plans), 1)
            self.assertEqual(len(page._group_plans[0].assignments), 2)
            page.close()
            page.deleteLater()

    def test_crew_page_uses_vertical_scroll_without_source_horizontal_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            source = directory / "voice_message_commander_shot_v1.wav"
            source.write_bytes(b"audio")
            page = CrewPage()
            page.resize(820, 620)
            page.show()
            QApplication.processEvents()
            page._add_paths([str(source)])
            QApplication.processEvents()
            self.assertGreaterEqual(page.drop_area.height(), 142)
            self.assertEqual(page.source_list.scroll.horizontalScrollBar().maximum(), 0)
            self.assertGreater(page._body_widget.verticalScrollBar().maximum(), 0)
            self.assertTrue(page.manual_status_panel.isVisible())
            self.assertTrue(page.auto_status_panel.isVisible())
            self.assertTrue(page.auto_action_bar.isVisible())
            self.assertFalse(page.auto_select_all_button.isEnabled())
            self.assertFalse(page.auto_start_copy_button.isEnabled())
            self.assertFalse(hasattr(page, "reassign_button"))
            self.assertTrue(hasattr(page, "auto_reassign_button"))
            self.assertFalse(page.auto_reassign_button.isEnabled())
            content = page._body_widget.widget()
            self.assertIsNotNone(content)
            if content is not None:
                widgets = [content.layout().itemAt(index).widget() for index in range(content.layout().count())]
                self.assertEqual(
                    widgets[2:7],
                    [
                        page.manual_status_panel,
                        page.action_bar,
                        page.auto_copy_panel,
                        page.auto_status_panel,
                        page.auto_action_bar,
                    ],
                )
            page.close()
            page.deleteLater()

    def test_manual_submission_retains_right_result_and_new_batch_resets_it(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            first = directory / "voice_message_commander_shot_v1.wav"
            second = directory / "voice_message_gunner_taking_command_v1.wav"
            first.write_bytes(b"audio")
            second.write_bytes(b"audio")
            page = CrewPage()
            page.resize(1100, 700)
            page.show()
            QApplication.processEvents()
            page._add_paths([str(first)])
            scroll = page._body_widget.verticalScrollBar()
            scroll.setValue(min(160, scroll.maximum()))
            expected_position = scroll.value()
            page._start_copy()
            self._wait_until(lambda: not page._service.is_busy and page.results_panel.isVisible())
            QApplication.processEvents()
            self.assertEqual(page._imported_files, [])
            self.assertEqual(page._manual_batch_state.value, "result_retained")
            self.assertTrue(page._submitted_group_plans)
            self.assertTrue(page._manual_result_messages)
            self.assertEqual(scroll.value(), min(expected_position, scroll.maximum()))

            page._add_paths([str(second)])
            self.assertEqual(page._manual_batch_state.value, "editing")
            self.assertEqual(len(page._imported_files), 1)
            self.assertFalse(page.results_panel.isVisible())
            self.assertNotEqual(page._group_plans, page._submitted_group_plans)
            page._clear_sources()
            self.assertEqual(page._manual_batch_state.value, "empty")
            self.assertEqual(page._imported_files, [])
            self.assertFalse(page.results_panel.isVisible())
            self.assertEqual(scroll.value(), min(expected_position, scroll.maximum()))
            page.close()
            page.deleteLater()

    def test_manual_validation_or_conflict_cancel_keeps_sources(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            source = directory / "voice_message_commander_shot_v1.wav"
            source.write_bytes(b"audio")
            page = CrewPage()
            page._add_paths([str(source)])
            page._choose_manual_conflict_policy = lambda _plan: None  # type: ignore[method-assign]
            page._start_copy()
            self.assertEqual(len(page._imported_files), 1)
            self.assertEqual(page._manual_batch_state.value, "editing")
            page.close()
            page.deleteLater()

    def test_service_runs_in_background_without_blocking_event_loop(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            source = directory / "source.wav"
            source.write_bytes(b"x" * (8 * 1024 * 1024))
            task = CopyTask("test", source, directory / "copy.wav", "copy")
            service = CrewFileService()
            finished = []
            heartbeat = []
            service.batch_finished.connect(finished.append)
            self.assertTrue(service.start_copy(CopyPlan((task,))))
            QTimer.singleShot(0, lambda: heartbeat.append(True))
            self._wait_until(lambda: bool(finished) and not service.is_busy)
            self.assertTrue(heartbeat)
            self.assertEqual(finished[0].results[0].status, CopyResultStatus.SUCCESS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
