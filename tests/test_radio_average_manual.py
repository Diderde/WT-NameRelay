from __future__ import annotations

import os
import hashlib
import random
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from app.models import (
    ConflictPolicy,
    CopyResult,
    CopyResultStatus,
    CrewGroupType,
    CrewNameGroup,
    ManualBatchState,
    ManualCopyMode,
    RecognitionState,
    RadioTargetConflictKind,
    RadioTargetOperation,
    SourceFile,
)
from app.module_config import RADIO_MODULE
from app.pages.radio_page import RadioPage
from app.services import CopyTaskBuilder, CrewNameParser, CrewNameRepository, RadioAveragePlanBuilder
from app.services.radio_staged_worker import RadioStagedFileCopyWorker


class _RepositoryStub:
    def __init__(self, groups: tuple[CrewNameGroup, ...]) -> None:
        self.by_key = {group.group_key: group for group in groups}
        self.by_name = {name: group for group in groups for name in group.names}

    def get_by_key(self, key: str) -> CrewNameGroup | None:
        return self.by_key.get(key)

    def lookup(self, name: str) -> CrewNameGroup | None:
        return self.by_name.get(name)


class RadioAverageManualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["radio-average-tests"])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.repository = CrewNameRepository(RADIO_MODULE.data_path)
        cls.parser = CrewNameParser(cls.repository)
        cls.builder = RadioAveragePlanBuilder(
            cls.repository,
            CopyTaskBuilder(cls.repository, random.Random(19)),
        )

    def _sources(
        self,
        directory: Path,
        stems: tuple[str, ...],
        payloads: tuple[bytes, ...] | None = None,
        suffixes: tuple[str, ...] | None = None,
    ) -> tuple[SourceFile, ...]:
        result = []
        for index, stem in enumerate(stems):
            suffix = suffixes[index] if suffixes else ".wav"
            path = directory / f"{stem}{suffix}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payloads[index] if payloads else bytes([65 + index]))
            result.append(self.parser.parse(path))
        return tuple(result)

    @staticmethod
    def _source_stems(plan: object) -> list[str]:
        return [triple.source.stem for triple in plan.triples]

    def _wait_until(self, predicate: object, timeout_ms: int = 5000) -> None:
        deadline = time.monotonic() + timeout_ms / 1000
        while not predicate() and time.monotonic() < deadline:  # type: ignore[operator]
            QApplication.processEvents()
            time.sleep(0.005)
        self.assertTrue(predicate())  # type: ignore[operator]

    def test_current_library_has_39_eligible_matrix_groups(self) -> None:
        eligible = [
            group for group in self.repository.groups()
            if self.builder.is_average_eligible(group.group_key)
        ]
        self.assertEqual(len(eligible), 39)
        self.assertEqual(sum(len(group.names) == 9 for group in eligible), 13)
        self.assertEqual(sum(len(group.names) == 12 for group in eligible), 26)

    def test_nine_members_same_original_triple_maps_aaa_bbb_ccc(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            stems = tuple(f"pilot_tickets_lead_start_ally_1_v{i}" for i in range(1, 4))
            sources = self._sources(directory, stems)
            plan = self.builder.build_group_plans(sources, [item.normalized_path for item in sources])[0]
            self.assertEqual(self._source_stems(plan), list(stems))
            self.assertTrue(all(len({a.source.stem for a in plan.assignments if a.target_group_index == i}) == 1 for i in range(3)))

    def test_nine_members_different_triples_keep_original_positions(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            stems = tuple(f"pilot_tickets_lead_start_ally_{i}_v1" for i in range(1, 4))
            sources = self._sources(directory, stems)
            plan = self.builder.build_group_plans(sources, [item.normalized_path for item in sources])[0]
            self.assertEqual(self._source_stems(plan), list(stems))

    def test_nine_members_two_sources_cycle_aaa_bbb_aaa(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            stems = ("pilot_tickets_lead_start_ally_1_v1", "pilot_tickets_lead_start_ally_1_v2")
            sources = self._sources(directory, stems)
            plan = self.builder.build_group_plans(sources, [item.normalized_path for item in sources])[0]
            self.assertEqual(self._source_stems(plan), [stems[0], stems[1], stems[0]])

    def test_twelve_members_four_three_and_two_source_cycles(self) -> None:
        group = self.repository.get_by_key("voice_message_attack_A")
        assert group is not None
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for indexes, expected in (
                ((0, 3, 6, 9), [0, 1, 2, 3]),
                ((0, 1, 2), [0, 1, 2, 0]),
                ((0, 1), [0, 1, 0, 1]),
            ):
                directory = root / str(len(indexes))
                stems = tuple(group.names[index] for index in indexes)
                sources = self._sources(directory, stems)
                plan = self.builder.build_group_plans(
                    sources, [item.normalized_path for item in sources]
                )[0]
                self.assertEqual(
                    self._source_stems(plan),
                    [stems[index] for index in expected],
                )

    def test_units_from_two_directories_never_cross_assign(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            stem = "pilot_tickets_lead_start_ally_1_v1"
            sources_a = self._sources(root / "中文 A", (stem,))
            sources_b = self._sources(root / "folder B", (stem,), suffixes=(".ogg",))
            sources = sources_a + sources_b
            plans = self.builder.build_group_plans(sources, [item.normalized_path for item in sources])
            self.assertEqual(len(plans), 2)
            for plan in plans:
                self.assertTrue(all(item.output_path.parent == plan.directory for item in plan.assignments))
                self.assertTrue(all(item.source.path.parent == plan.directory for item in plan.assignments))

    def test_six_and_ten_member_structures_fall_back_safely(self) -> None:
        for count in (6, 10):
            names = tuple(f"synthetic_{count}_{index}" for index in range(count))
            group = CrewNameGroup(f"g{count}", f"synthetic_{count}", CrewGroupType.MATRIX_SUFFIX, names)
            repository = _RepositoryStub((group,))
            builder = RadioAveragePlanBuilder(repository, CopyTaskBuilder(repository, random.Random(2)))  # type: ignore[arg-type]
            with tempfile.TemporaryDirectory() as raw:
                path = Path(raw) / f"{names[0]}.wav"
                path.write_bytes(b"x")
                source = SourceFile(
                    path,
                    os.path.normcase(os.path.abspath(path)),
                    path.name,
                    names[0],
                    ".wav",
                    RecognitionState.RECOGNIZED,
                    group_base=group.base_name,
                    group_key=group.group_key,
                )
                plan = builder.build_group_plans((source,), (source.normalized_path,))[0]
                self.assertEqual(plan.copy_mode, ManualCopyMode.SEQUENTIAL)
                self.assertTrue(plan.fallback_reason)

    def test_snapshot_prevents_source_overwrite_from_destroying_b_and_c(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            stems = tuple(f"pilot_tickets_lead_start_ally_1_v{i}" for i in range(1, 4))
            sources = self._sources(directory, stems, (b"A", b"B", b"C"))
            group_plan = self.builder.build_group_plans(
                sources, [item.normalized_path for item in sources]
            )[0]
            selected = {item.selection_key: True for item in group_plan.assignments}
            plan = self.builder.build_staged_copy_plan((group_plan,), selected)
            batches = []
            worker = RadioStagedFileCopyWorker(plan, threading.Event(), ConflictPolicy.OVERWRITE_EXISTING)
            worker.finished.connect(batches.append)
            worker.prepare()
            self.assertEqual(len(batches), 1)
            group = self.repository.get_by_key("pilot_tickets_lead_start_ally")
            assert group is not None
            expected = (b"A",) * 3 + (b"B",) * 3 + (b"C",) * 3
            self.assertEqual(
                tuple((directory / f"{name}.wav").read_bytes() for name in group.names), expected
            )
            self.assertEqual(batches[0].overwritten, 3)
            self.assertEqual(batches[0].created, 6)
            assert worker.last_temporary_directory is not None
            self.assertFalse(worker.last_temporary_directory.exists())

    def test_source_targets_bypass_external_conflicts_and_skip_still_produces_aaa_bbb_ccc(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            stems = tuple(f"pilot_tickets_lead_continue_enemy_1_v{i}" for i in range(1, 4))
            sources = self._sources(directory, stems, (b"audio-A", b"audio-B", b"audio-C"))
            original_hashes = [hashlib.sha256(source.path.read_bytes()).hexdigest() for source in sources]
            group_plan = self.builder.build_group_plans(
                sources, [source.normalized_path for source in sources]
            )[0]
            staged_plan = self.builder.build_staged_copy_plan(
                (group_plan,),
                {assignment.selection_key: True for assignment in group_plan.assignments},
            )

            self.assertEqual(
                [operation.conflict_kind for operation in staged_plan.operations[:3]],
                [RadioTargetConflictKind.SOURCE_TARGET] * 3,
            )
            self.assertEqual(
                [operation.conflict_kind for operation in staged_plan.operations[3:]],
                [RadioTargetConflictKind.GENERATED_TARGET] * 6,
            )
            self.assertEqual(staged_plan.current_external_conflicts(), ())
            page = RadioPage()
            with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Ok) as execute:
                self.assertIs(
                    page._choose_average_conflict_policy(staged_plan),
                    ConflictPolicy.SKIP_EXISTING,
                )
                self.assertEqual(execute.call_count, 0)
            page.close()
            page.deleteLater()

            events: list[str] = []
            batches = []
            worker = RadioStagedFileCopyWorker(
                staged_plan,
                threading.Event(),
                ConflictPolicy.SKIP_EXISTING,
            )
            original_snapshot = worker._copy_snapshot
            original_copy_one = worker._copy_one

            def record_snapshot(source: Path, target: Path) -> None:
                original_snapshot(source, target)
                events.append(f"snapshot:{source.name}")

            def record_copy(
                operation: RadioTargetOperation,
                staged_source: Path,
                policy: ConflictPolicy,
            ) -> CopyResult:
                events.append(f"write:{operation.target_path.name}")
                return original_copy_one(operation, staged_source, policy)

            worker._copy_snapshot = record_snapshot  # type: ignore[method-assign]
            worker._copy_one = record_copy  # type: ignore[method-assign]
            worker.finished.connect(batches.append)
            worker.prepare()

            self.assertEqual(len([event for event in events if event.startswith("snapshot:")]), 3)
            first_write = next(index for index, event in enumerate(events) if event.startswith("write:"))
            self.assertTrue(all(event.startswith("snapshot:") for event in events[:first_write]))
            group = self.repository.get_by_key("pilot_tickets_lead_continue_enemy")
            assert group is not None
            final_names = sorted(path.name for path in directory.iterdir())
            self.assertEqual(final_names, sorted(f"{name}.wav" for name in group.names))
            final_hashes = [
                hashlib.sha256((directory / f"{name}.wav").read_bytes()).hexdigest()
                for name in group.names
            ]
            self.assertEqual(
                final_hashes,
                [original_hashes[0]] * 3
                + [original_hashes[1]] * 3
                + [original_hashes[2]] * 3,
            )
            self.assertEqual(batches[0].created, 6)
            self.assertEqual(batches[0].overwritten, 3)
            self.assertEqual(batches[0].skipped, 0)
            assert worker.last_temporary_directory is not None
            self.assertFalse(worker.last_temporary_directory.exists())

    def test_true_external_conflict_still_obeys_skip_policy(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            source = self._sources(
                directory,
                ("pilot_tickets_lead_continue_enemy_1_v1",),
                (b"source-A",),
            )[0]
            group_plan = self.builder.build_group_plans((source,), (source.normalized_path,))[0]
            external_target = directory / "pilot_tickets_lead_continue_enemy_2_v1.wav"
            external_target.write_bytes(b"external")
            staged_plan = self.builder.build_staged_copy_plan(
                (group_plan,),
                {assignment.selection_key: True for assignment in group_plan.assignments},
            )
            self.assertEqual(staged_plan.current_external_conflicts(), (external_target,))
            operation = next(
                item for item in staged_plan.operations if item.target_path == external_target
            )
            self.assertIs(operation.conflict_kind, RadioTargetConflictKind.EXTERNAL_CONFLICT)

            batches = []
            worker = RadioStagedFileCopyWorker(
                staged_plan,
                threading.Event(),
                ConflictPolicy.SKIP_EXISTING,
            )
            worker.finished.connect(batches.append)
            worker.prepare()
            self.assertEqual(external_target.read_bytes(), b"external")
            self.assertEqual(batches[0].skipped, 1)
            self.assertGreaterEqual(batches[0].overwritten, 1)

    def test_staging_failure_writes_no_targets(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            stems = ("pilot_tickets_lead_start_ally_1_v1", "pilot_tickets_lead_start_ally_1_v2")
            sources = self._sources(directory, stems, (b"A", b"B"))
            group_plan = self.builder.build_group_plans(sources, [item.normalized_path for item in sources])[0]
            plan = self.builder.build_staged_copy_plan(
                (group_plan,), {item.selection_key: True for item in group_plan.assignments}
            )
            sources[1].path.unlink()
            batches = []
            worker = RadioStagedFileCopyWorker(plan, threading.Event(), ConflictPolicy.OVERWRITE_EXISTING)
            worker.finished.connect(batches.append)
            worker.prepare()
            self.assertEqual(len(batches), 1)
            self.assertTrue(any(item.status is CopyResultStatus.FAILED for item in batches[0].results))
            self.assertEqual(sources[0].path.read_bytes(), b"A")
            self.assertFalse((directory / "pilot_tickets_lead_start_ally_2_v1.wav").exists())
            assert worker.last_temporary_directory is not None
            self.assertFalse(worker.last_temporary_directory.exists())

    def test_cancel_during_staging_cleans_temporary_directory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            sources = self._sources(
                directory,
                ("pilot_tickets_lead_start_ally_1_v1",),
                (b"x" * (2 * 1024 * 1024),),
            )
            group_plan = self.builder.build_group_plans(sources, [sources[0].normalized_path])[0]
            plan = self.builder.build_staged_copy_plan(
                (group_plan,), {item.selection_key: True for item in group_plan.assignments}
            )
            cancel = threading.Event()
            batches = []
            worker = RadioStagedFileCopyWorker(plan, cancel, ConflictPolicy.OVERWRITE_EXISTING)
            worker.snapshot_changed.connect(
                lambda snapshot: cancel.set() if snapshot.message == "正在暂存来源" else None
            )
            worker.finished.connect(batches.append)
            worker.prepare()
            self.assertEqual(batches[0].cancelled, plan.total)
            assert worker.last_temporary_directory is not None
            self.assertFalse(worker.last_temporary_directory.exists())

    def test_page_defaults_to_sequence_and_average_submission_keeps_right_side(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            sources = self._sources(
                directory,
                ("pilot_tickets_lead_start_ally_1_v1", "pilot_tickets_lead_start_ally_1_v2"),
                (b"A", b"B"),
            )
            page = RadioPage()
            page.resize(1100, 700)
            page.show()
            QApplication.processEvents()
            self.assertEqual(page._manual_copy_mode, ManualCopyMode.SEQUENTIAL)
            self.assertFalse(page.copy_mode_switch.isChecked())
            page.copy_mode_switch.set_average_checked(True, emit=True)
            page._add_paths([str(item.path) for item in sources])
            self.assertTrue(all(plan.copy_mode is ManualCopyMode.AVERAGE for plan in page._group_plans))
            scroll = page._body_widget.verticalScrollBar()
            scroll.setValue(min(120, scroll.maximum()))
            expected_scroll = scroll.value()
            page._choose_manual_conflict_policy = lambda _plan: ConflictPolicy.OVERWRITE_EXISTING  # type: ignore[method-assign]
            page._start_copy()
            self._wait_until(lambda: not page._average_service.is_busy and page.results_panel.isVisible())
            self.assertEqual(page._imported_files, [])
            self.assertEqual(page._manual_batch_state, ManualBatchState.RESULT_RETAINED)
            self.assertTrue(page._submitted_group_plans)
            self.assertEqual(scroll.value(), min(expected_scroll, scroll.maximum()))
            page.close()
            page.deleteLater()

    def test_mode_switch_preserves_existing_target_selection(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            source = self._sources(
                directory, ("pilot_tickets_lead_start_ally_1_v1",)
            )[0]
            page = RadioPage()
            page._add_paths([str(source.path)])
            target_name = "pilot_tickets_lead_start_ally_1_v2"
            sequential_assignment = next(
                assignment
                for plan in page._group_plans
                for assignment in plan.assignments
                if assignment.target_name == target_name
            )
            page._selected_targets[sequential_assignment.selection_key] = False
            page.copy_mode_switch.set_average_checked(True, emit=True)
            average_assignment = next(
                assignment
                for plan in page._group_plans
                for assignment in plan.assignments
                if assignment.target_name == target_name
            )
            self.assertFalse(page._selected_targets[average_assignment.selection_key])
            page.close()
            page.deleteLater()

    def test_average_import_limit_rejects_only_extra_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            group = self.repository.get_by_key("pilot_tickets_lead_start_ally")
            assert group is not None
            sources = self._sources(directory, tuple(group.names[:4]))
            page = RadioPage()
            page.copy_mode_switch.set_average_checked(True, emit=True)
            notices = []
            page._show_rejected_imports = notices.append  # type: ignore[method-assign]
            page._add_paths([str(item.path) for item in sources[:3]])
            page._add_paths([str(sources[3].path)])
            self.assertEqual(len(page._imported_files), 3)
            self.assertEqual(len(notices), 1)
            page.close()
            page.deleteLater()

    def test_switch_to_average_is_rejected_when_sequence_batch_is_over_limit(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            group = self.repository.get_by_key("pilot_tickets_lead_start_ally")
            assert group is not None
            sources = self._sources(directory, tuple(group.names[:4]))
            page = RadioPage()
            page._add_paths([str(item.path) for item in sources])
            notices = []
            page._show_limit_violations = lambda value, switching: notices.append((value, switching))  # type: ignore[method-assign]
            page.copy_mode_switch.set_average_checked(True, emit=True)
            self.assertEqual(page._manual_copy_mode, ManualCopyMode.SEQUENTIAL)
            self.assertFalse(page.copy_mode_switch.isChecked())
            self.assertEqual(len(page._imported_files), 4)
            self.assertEqual(len(notices), 1)
            page.close()
            page.deleteLater()

    def test_fallback_groups_are_aggregated_into_one_warning_signature(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            fallback_groups = [
                group for group in self.repository.groups()
                if len(group.names) == 3 and not self.builder.is_average_eligible(group.group_key)
            ]
            self.assertGreaterEqual(len(fallback_groups), 2)
            sources = self._sources(
                directory,
                (fallback_groups[0].names[0], fallback_groups[1].names[0]),
            )
            page = RadioPage()
            with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Ok) as execute:
                page.copy_mode_switch.set_average_checked(True, emit=True)
                page._add_paths([str(item.path) for item in sources])
                self.assertEqual(execute.call_count, 1)
                page._refresh_sources_and_groups()
                self.assertEqual(execute.call_count, 1)
            self.assertEqual(len(page._fallback_warning_signature), 2)
            self.assertTrue(all(plan.fallback_reason for plan in page._group_plans))
            page.close()
            page.deleteLater()


if __name__ == "__main__":
    unittest.main(verbosity=2)
