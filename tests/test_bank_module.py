from __future__ import annotations

import os
import random
import tempfile
import threading
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.models import BankFileRole, ConflictPolicy
from app.pages.bank_page import BankPage
from app.services import BankCopyTaskBuilder, BankFilenameParser, BankNameRepository, BankPairMatcher
from app.services.file_copy_worker import FileCopyWorker


class BankModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["wt-name-tool-bank-tests"])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.repository = BankNameRepository(); cls.parser = BankFilenameParser(); cls.matcher = BankPairMatcher()

    def _wait_until(self, predicate: object, timeout_ms: int = 6000) -> None:
        deadline = time.monotonic() + timeout_ms / 1000
        while not predicate() and time.monotonic() < deadline:  # type: ignore[operator]
            QApplication.processEvents(); time.sleep(0.005)
        self.assertTrue(predicate(), "Timed out waiting for Bank task")  # type: ignore[operator]

    @staticmethod
    def _create(directory: Path, category: str, country: str, role: BankFileRole, data: bytes = b"bank") -> Path:
        suffix = ".assets.bank" if role is BankFileRole.ASSETS else ".bank"
        path = directory / f"_crew_dialogs_{category}_{country}{suffix}"; path.write_bytes(data); return path

    def test_embedded_library_and_parser_keep_roles_distinct(self) -> None:
        self.assertEqual(len(self.repository.countries("common")), 17); self.assertEqual(len(self.repository.countries("ground")), 35)
        assets = self.parser.parse("_crew_dialogs_ground_zh.assets.bank"); main = self.parser.parse("_crew_dialogs_ground_zh.bank")
        self.assertEqual((assets.category, assets.country, assets.role), ("ground", "zh", BankFileRole.ASSETS))
        self.assertEqual((main.category, main.country, main.role), ("ground", "zh", BankFileRole.MAIN))
        self.assertFalse(self.parser.parse("_crew_dialogs_air_zh.bank").valid)

    def test_pairing_requires_same_directory_category_and_country(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            first, second = Path(raw) / "a", Path(raw) / "b"; first.mkdir(); second.mkdir()
            files = [self.parser.parse(self._create(first, "ground", "zh", BankFileRole.ASSETS)), self.parser.parse(self._create(second, "ground", "zh", BankFileRole.MAIN)), self.parser.parse(self._create(first, "common", "zh", BankFileRole.MAIN))]
            groups = self.matcher.group(files)
            self.assertEqual(len(groups), 3); self.assertFalse(any(group.complete for group in groups))

    def test_country_assignment_keeps_two_roles_from_the_same_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            files = [self.parser.parse(self._create(directory, "ground", "zh", role)) for role in BankFileRole] + [self.parser.parse(self._create(directory, "ground", "de", role)) for role in BankFileRole]
            builder = BankCopyTaskBuilder(self.repository, random.Random(3)); ground = [item for item in builder.build_assignments(self.matcher.group(files)) if item.category == "ground"]
            self.assertTrue(ground); self.assertTrue(all(item.source.country in {"zh", "de"} and len(item.target_roles) == 2 for item in ground))
            counts = {country: sum(item.source.country == country for item in ground) for country in {"zh", "de"}}; self.assertLessEqual(abs(counts["zh"] - counts["de"]), 1)
            plan = builder.build_copy_plan(ground[:1], {ground[0].selection_key: True})
            self.assertEqual(len(plan.tasks), 2); self.assertTrue(plan.tasks[0].source_path.name.endswith(".assets.bank")); self.assertTrue(plan.tasks[0].target_path.name.endswith(".assets.bank")); self.assertTrue(plan.tasks[1].source_path.name.endswith(".bank") and not plan.tasks[1].source_path.name.endswith(".assets.bank"))

    def test_partial_target_only_copies_the_missing_role(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw); files = [self.parser.parse(self._create(directory, "common", "zh", role)) for role in BankFileRole]; files.append(self.parser.parse(self._create(directory, "common", "de", BankFileRole.ASSETS)))
            assignments = BankCopyTaskBuilder(self.repository).build_assignments(self.matcher.group(files)); de = next(item for item in assignments if item.category == "common" and item.country == "de")
            self.assertEqual(de.target_roles, (BankFileRole.MAIN,))

    def test_page_manual_and_auto_use_background_copy(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw); source_paths = [self._create(directory, "common", "zh", role) for role in BankFileRole]
            page = BankPage(); page._add_paths([str(path) for path in source_paths]); self.assertTrue(page._manual_assignments); page._start_manual()
            self._wait_until(lambda: not page._manual_service.is_busy and (directory / "_crew_dialogs_common_de.assets.bank").exists() and (directory / "_crew_dialogs_common_de.bank").exists())
            page.close(); page.deleteLater()
            auto = Path(raw) / "auto"; auto.mkdir()
            for role in BankFileRole: self._create(auto, "common", "zh", role)
            auto_page = BankPage(); auto_page.directory_selector.path_edit.setText(str(auto)); auto_page._start_scan(); self._wait_until(lambda: auto_page._auto_result is not None and not auto_page._scan_service.is_busy); self.assertTrue(auto_page._auto_assignments); auto_page._start_auto()
            self._wait_until(lambda: not auto_page._auto_service.is_busy and not auto_page._scan_service.is_busy and (auto / "_crew_dialogs_common_de.assets.bank").exists())
            auto_page.close(); auto_page.deleteLater()

    def test_bank_manual_submission_clears_left_and_keeps_frozen_pair_result(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            sources = [self._create(directory, "common", "zh", role) for role in BankFileRole]
            page = BankPage(); page.resize(1100, 700); page.show(); QApplication.processEvents()
            page._add_paths([str(path) for path in sources])
            scroll = page._body_widget.verticalScrollBar(); scroll.setValue(min(150, scroll.maximum())); expected_position = scroll.value()
            page._start_manual()
            self._wait_until(lambda: not page._manual_service.is_busy and page.results.isVisible())
            QApplication.processEvents()
            self.assertEqual(page._imported, [])
            self.assertEqual(page._manual_batch_state.value, "result_retained")
            self.assertTrue(page._submitted_manual_assignments)
            self.assertTrue(page._manual_result_messages)
            self.assertEqual(scroll.value(), min(expected_position, scroll.maximum()))
            page._clear_sources()
            self.assertEqual(page._manual_batch_state.value, "empty")
            self.assertFalse(page.results.isVisible())
            page.close(); page.deleteLater()

    def test_auto_conflict_skips_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw); source = self._create(directory, "common", "zh", BankFileRole.ASSETS, b"new"); target = self._create(directory, "common", "de", BankFileRole.ASSETS, b"old")
            from app.models import CopyPlan, CopyTask
            worker = FileCopyWorker(CopyPlan((CopyTask("common/de", source, target, target.name),)), threading.Event(), ConflictPolicy.SKIP_EXISTING); results = []; worker.finished.connect(results.append); worker.prepare()
            self.assertEqual(results[0].results[0].status.value, "skipped"); self.assertEqual(target.read_bytes(), b"old")


if __name__ == "__main__":
    unittest.main(verbosity=2)
