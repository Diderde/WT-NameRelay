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

from app.models import ConflictPolicy, CopyPlan, CopyResultStatus, CopyTask
from app.services import (
    AutoCompletionAnalyzer,
    AutoScanService,
    CrewNameParser,
    CrewNameRepository,
    DirectoryScanner,
)
from app.services.file_copy_worker import FileCopyWorker
from app.pages.crew_page import CrewPage


class AutoCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["wt-name-tool-auto-tests"])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.repository = CrewNameRepository()

    def _scan(self, root: Path, recursive: bool = False):
        parser = CrewNameParser(self.repository)
        return DirectoryScanner(parser).scan(root, recursive)

    def _analyze(self, root: Path, recursive: bool = False, seed: int = 3):
        return AutoCompletionAnalyzer(self.repository, random.Random(seed)).analyze(self._scan(root, recursive))

    def _wait_until(self, predicate: object, timeout_ms: int = 3000) -> None:
        deadline = time.monotonic() + timeout_ms / 1000
        while not predicate() and time.monotonic() < deadline:  # type: ignore[operator]
            QApplication.processEvents()
            time.sleep(0.005)
        self.assertTrue(predicate(), "Timed out waiting for scan")  # type: ignore[operator]

    def test_scanner_counts_supported_extensions_and_matches_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "voice_message_commander_shot_v1.WAV").write_bytes(b"a")
            (root / "unknown.ogg").write_bytes(b"b")
            (root / "ignored.txt").write_text("x", encoding="utf-8")
            scan = self._scan(root)
            self.assertEqual(scan.audio_count, 2)
            self.assertEqual(scan.recognized_count, 1)

    def test_single_group_missing_and_complete_or_absent_groups(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "voice_message_commander_shot_v1.wav").write_bytes(b"a")
            analysis = self._analyze(root)
            self.assertEqual(analysis.missing_group_count, 1)
            group = analysis.groups[0]
            self.assertEqual(group.current_logical_count, 1)
            self.assertEqual({item.target_name for item in group.plan.assignments}, {
                "voice_message_commander_shot_v2",
                "voice_message_commander_shot_v3",
            })
            self.assertEqual(analysis.complete_group_count, 0)

            (root / "voice_message_commander_shot_v2.wav").write_bytes(b"a")
            (root / "voice_message_commander_shot_v3.wav").write_bytes(b"a")
            complete = self._analyze(root)
            self.assertEqual(complete.missing_group_count, 0)
            self.assertGreaterEqual(complete.complete_group_count, 1)

    def test_double_and_mixed_groups_use_json_names(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "voice_message_chief_artillery_danger_v1_1.wav").write_bytes(b"a")
            (root / "voice_message_commander_ucav_launch_v1_1.wav").write_bytes(b"a")
            groups = {group.plan.group.base_name: group for group in self._analyze(root).groups}
            self.assertEqual(len(groups["voice_message_chief_artillery_danger"].plan.assignments), 7)
            mixed_targets = {item.target_name for item in groups["voice_message_commander_ucav_launch"].plan.assignments}
            self.assertIn("voice_message_commander_ucav_launch_v2", mixed_targets)
            self.assertIn("voice_message_commander_ucav_launch_v1_2", mixed_targets)

    def test_engine_stalled_special_groups_do_not_mix_sources_or_targets(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "voice_message_driver_engine_stalled_v1_1.wav").write_bytes(b"layered")
            (root / "voice_message_driver_engine_stalled_v2.wav").write_bytes(b"single")
            groups = [
                group
                for group in self._analyze(root).groups
                if group.plan.group.base_name == "voice_message_driver_engine_stalled"
            ]
            self.assertEqual(len(groups), 2)
            target_sets = [{assignment.target_name for assignment in group.plan.assignments} for group in groups]
            self.assertIn(
                {
                    "voice_message_driver_engine_stalled_v1_2",
                    "voice_message_driver_engine_stalled_v1_3",
                },
                target_sets,
            )
            self.assertIn({"voice_message_driver_engine_stalled_v3"}, target_sets)

    def test_multiple_formats_are_one_logical_member_and_balanced_sources(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "voice_message_chief_artillery_danger_v1_1.wav").write_bytes(b"a")
            (root / "voice_message_chief_artillery_danger_v1_1.flac").write_bytes(b"a")
            (root / "voice_message_chief_artillery_danger_v2_1.ogg").write_bytes(b"a")
            group = self._analyze(root).groups[0]
            self.assertEqual(group.current_logical_count, 2)
            self.assertIn("voice_message_chief_artillery_danger_v1_1", group.duplicate_stems)
            counts: dict[str, int] = {}
            for assignment in group.plan.assignments:
                counts[assignment.source.file_name] = counts.get(assignment.source.file_name, 0) + 1
            self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)

    def test_recursive_scanning_keeps_directories_independent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            child = root / "child"
            child.mkdir()
            (root / "voice_message_commander_shot_v1.wav").write_bytes(b"a")
            (child / "voice_message_commander_shot_v2.wav").write_bytes(b"b")
            self.assertEqual(self._analyze(root, False).missing_group_count, 1)
            recursive = self._analyze(root, True)
            self.assertEqual(recursive.missing_group_count, 2)
            self.assertEqual({group.directory for group in recursive.groups}, {root, child})
            keys = {
                assignment.selection_key
                for group in recursive.groups
                for assignment in group.plan.assignments
            }
            self.assertEqual(len(keys), sum(len(group.plan.assignments) for group in recursive.groups))

    def test_auto_preexisting_target_is_skipped_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source.wav"
            target = root / "target.wav"
            source.write_bytes(b"new")
            target.write_bytes(b"old")
            task = CopyTask("test", source, target, "target")
            worker = FileCopyWorker(CopyPlan((task,)), threading.Event(), ConflictPolicy.SKIP_EXISTING)
            batches = []
            worker.finished.connect(batches.append)
            worker.prepare()
            self.assertEqual(batches[0].results[0].status, CopyResultStatus.SKIPPED)
            self.assertIn("执行前", batches[0].results[0].reason)
            self.assertEqual(target.read_bytes(), b"old")

    def test_scan_service_keeps_qt_event_loop_alive(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "voice_message_commander_shot_v1.wav").write_bytes(b"a")
            service = AutoScanService(DirectoryScanner(CrewNameParser(self.repository)))
            finished = []
            heartbeat = []
            service.scan_finished.connect(finished.append)
            self.assertTrue(service.start_scan(root, False))
            QTimer.singleShot(0, lambda: heartbeat.append(True))
            self._wait_until(lambda: bool(finished) and not service.is_busy)
            self.assertTrue(heartbeat)
            self.assertEqual(finished[0].audio_count, 1)

    def test_crew_page_scans_updates_statistics_and_completes_in_background(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "voice_message_commander_shot_v1.wav"
            source.write_bytes(b"audio")
            page = CrewPage()
            page.directory_selector.path_edit.setText(str(root))
            page._start_auto_scan()
            self._wait_until(lambda: page._auto_analysis is not None and not page._scan_service.is_busy)
            self.assertEqual(page._auto_analysis.missing_group_count, 1)
            self.assertIn("计划新增：2", page.auto_result_panel.plan_stats.text())

            first_key = next(iter(page._auto_selected_targets))
            page._on_auto_selection_changed(first_key, False)
            self.assertIn("计划新增：1", page.auto_result_panel.plan_stats.text())
            page._on_auto_selection_changed(first_key, True)
            page._start_auto_completion()
            self._wait_until(
                lambda: not page._auto_copy_service.is_busy
                and not page._scan_service.is_busy
                and (root / "voice_message_commander_shot_v2.wav").exists()
                and (root / "voice_message_commander_shot_v3.wav").exists()
                and page._auto_analysis is not None
                and page._auto_analysis.missing_group_count == 0,
                timeout_ms=5000,
            )
            self.assertEqual(page._auto_analysis.missing_group_count, 0)
            self.assertIn("有效音频：3", page.directory_selector.audio_count_label.text())
            page.close()
            page.deleteLater()


if __name__ == "__main__":
    unittest.main(verbosity=2)
