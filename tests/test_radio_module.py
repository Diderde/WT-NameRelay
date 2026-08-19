from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.module_config import RADIO_MODULE
from app.pages.radio_page import RadioPage
from app.services import AutoCompletionAnalyzer, CopyTaskBuilder, CrewNameParser, CrewNameRepository, DirectoryScanner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = PROJECT_ROOT / "tools" / "build_radio_name_groups.py"


class RadioModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["wt-name-tool-radio-tests"])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.repository = CrewNameRepository(RADIO_MODULE.data_path)

    def _wait_until(self, predicate: object, timeout_ms: int = 4000) -> None:
        deadline = time.monotonic() + timeout_ms / 1000
        while not predicate() and time.monotonic() < deadline:  # type: ignore[operator]
            QApplication.processEvents()
            time.sleep(0.005)
        self.assertTrue(predicate(), "Timed out waiting for radio workflow")  # type: ignore[operator]

    def test_embedded_radio_library_is_isolated_and_complete(self) -> None:
        groups = self.repository.groups()
        self.assertEqual(len(groups), 56)
        self.assertEqual(sum(len(group.names) for group in groups), 480)
        self.assertEqual(sum(group.group_type.value == "v_suffix" for group in groups), 17)
        self.assertEqual(sum(group.group_type.value == "matrix_suffix" for group in groups), 26)
        self.assertEqual(sum(group.group_type.value == "v_matrix_suffix" for group in groups), 13)
        self.assertIsNotNone(self.repository.lookup("voice_message_air_v1"))
        matrix_group = self.repository.lookup("voice_message_attack_A_0_1")
        self.assertIsNotNone(matrix_group)
        assert matrix_group is not None
        self.assertEqual(matrix_group.base_name, "voice_message_attack_A")
        self.assertEqual(len(matrix_group.names), 12)
        self.assertIn("voice_message_attack_A_3_3", matrix_group.names)
        pilot_group = self.repository.lookup("pilot_base_underattack_1_v1")
        self.assertIsNotNone(pilot_group)
        assert pilot_group is not None
        self.assertEqual(pilot_group.base_name, "pilot_base_underattack")
        self.assertEqual(len(pilot_group.names), 9)
        self.assertIn("pilot_base_underattack_3_v3", pilot_group.names)
        self.assertIsNone(self.repository.lookup("voice_message_commander_shot_v1"))
        self.assertIsNone(self.repository.lookup("voice_message_bearing_10"))

    def test_radio_manual_and_automatic_completion_use_radio_groups(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            source = directory / "voice_message_air_v1.wav"
            source.write_bytes(b"radio")
            parser = CrewNameParser(self.repository)
            parsed = parser.parse(source)
            plan = CopyTaskBuilder(self.repository).build_group_plans((parsed,))
            self.assertEqual({item.target_name for item in plan[0].assignments}, {"voice_message_air_v2", "voice_message_air_v3"})
            manual_page = RadioPage()
            manual_page._add_paths((str(source),))
            manual_page._start_copy()
            self._wait_until(
                lambda: not manual_page._service.is_busy
                and (directory / "voice_message_air_v2.wav").exists()
                and (directory / "voice_message_air_v3.wav").exists(),
            )
            manual_page.close()
            manual_page.deleteLater()

            auto_directory = directory / "automatic"
            auto_directory.mkdir()
            auto_source = auto_directory / "voice_message_air_v1.wav"
            auto_source.write_bytes(b"radio")
            analysis = AutoCompletionAnalyzer(self.repository).analyze(DirectoryScanner(parser).scan(auto_directory, False))
            self.assertEqual(analysis.missing_group_count, 1)
            page = RadioPage()
            page.directory_selector.path_edit.setText(str(auto_directory))
            page._start_auto_scan()
            self._wait_until(lambda: page._auto_analysis is not None and not page._scan_service.is_busy)
            self.assertEqual(page.page_key, "radio")
            self.assertEqual(page._auto_analysis.missing_group_count, 1)
            page._start_auto_completion()
            self._wait_until(
                lambda: not page._auto_copy_service.is_busy
                and not page._scan_service.is_busy
                and (auto_directory / "voice_message_air_v2.wav").exists()
                and (auto_directory / "voice_message_air_v3.wav").exists()
                and page._auto_analysis is not None
                and page._auto_analysis.missing_group_count == 0,
                timeout_ms=5000,
            )
            page.close()
            page.deleteLater()

    def test_builder_is_non_recursive_and_rejects_semantic_numeric_suffixes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            voice1, additional, english = root / "voice1", root / "additional_01", root / "english"
            for folder in (voice1, additional, english):
                folder.mkdir()
            (voice1 / "radio_alpha_v1.wav").write_bytes(b"a")
            (voice1 / "child").mkdir()
            (voice1 / "child" / "radio_hidden_v2.wav").write_bytes(b"a")
            (additional / "radio_alpha_v2.OGG").write_bytes(b"a")
            (english / "radio_numeric_0_1.wav").write_bytes(b"a")
            (english / "radio_numeric_0_2.wav").write_bytes(b"a")
            (english / "radio_numeric_0_3.wav").write_bytes(b"a")
            (additional / "voice_message_bearing_10.wav").write_bytes(b"a")
            (additional / "voice_message_bearing_20.wav").write_bytes(b"a")
            output, report = root / "radio.json", root / "report.json"
            subprocess.run(
                [
                    sys.executable, str(BUILD_SCRIPT), "--voice1", str(voice1), "--additional-01", str(additional),
                    "--english", str(english), "--output", str(output), "--report", str(report),
                ],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(set(payload["groups"]), {"radio_alpha", "radio_numeric"})
            self.assertEqual(payload["groups"]["radio_alpha"]["sources"], {
                "radio_alpha_v1": ["voice1"], "radio_alpha_v2": ["additional_01"],
            })
            audit = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(audit["total_audio_files"], 7)
            self.assertEqual(audit["directory_audio_counts"], {"voice1": 1, "additional_01": 3, "english": 3})
            self.assertNotIn("radio_hidden_v2", json.dumps(payload, ensure_ascii=False))
            self.assertEqual(audit["excluded_name_count"], 2)

    def test_v_matrix_group_completes_all_nine_real_members(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            source = directory / "pilot_base_underattack_1_v1.wav"
            source.write_bytes(b"radio")
            parser = CrewNameParser(self.repository)
            group_plan = CopyTaskBuilder(self.repository).build_group_plans((parser.parse(source),))[0]
            self.assertEqual(len(group_plan.assignments), 8)
            self.assertIn("pilot_base_underattack_3_v3", {item.target_name for item in group_plan.assignments})


if __name__ == "__main__":
    unittest.main(verbosity=2)
