from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QFile, QIODevice
from PySide6.QtWidgets import QApplication, QTextBrowser

from app.branding import APP_NAME, WINDOW_TITLE
from app.main_window import MainWindow
from app.widgets import AboutDialog, DisclaimerDialog, LicenseDialog


class ReleaseFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["wt-name-relay-release-tests"])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_branding_and_icons_are_available(self) -> None:
        window = MainWindow()
        self.assertEqual(window.windowTitle(), WINDOW_TITLE)
        self.assertFalse(window.windowIcon().isNull())
        self.assertEqual(APP_NAME, "WT-NameRelay")
        window.close()

    def test_disclaimer_requires_three_ticks_before_acceptance(self) -> None:
        dialog = DisclaimerDialog()
        self.assertFalse(dialog.continue_button.isEnabled())
        dialog._tick(); self.assertEqual(dialog.continue_button.text(), "我已阅读（2秒）")
        dialog._tick(); self.assertEqual(dialog.continue_button.text(), "我已阅读（1秒）")
        dialog._tick(); self.assertTrue(dialog.continue_button.isEnabled())
        dialog.continue_button.click()
        self.assertEqual(dialog.result(), DisclaimerDialog.DialogCode.Accepted)

    def test_about_and_embedded_license_text_are_available(self) -> None:
        about = AboutDialog()
        license_dialog = LicenseDialog(about)
        self.assertGreater(len(license_dialog.browser.toPlainText()), 100)
        about_text = next(
            child.toPlainText()
            for child in about.findChildren(QTextBrowser)
            if "运行时第三方组件" in child.toPlainText()
        )
        self.assertIn("FFmpeg N-125829-gfe953596e9-20260728", about_text)
        self.assertIn("LGPL-3.0-or-later", about_text)
        self.assertNotIn("LGPL-2.1-or-later", about_text)
        labels = [
            license_dialog.selector.itemText(index)
            for index in range(license_dialog.selector.count())
        ]
        self.assertTrue(any("Source-Available License 1.0" in label for label in labels))
        self.assertTrue(any("CPython 3.11.5" in label for label in labels))
        self.assertTrue(any("OpenSSL 3.0.10" in label for label in labels))
        self.assertIn("Source-Available", about_text)
        license_dialog.close(); about.close()

    def test_public_metadata_does_not_embed_development_machine_paths(self) -> None:
        root = Path(__file__).resolve().parents[1]
        public_files = (
            root / "README.md",
            root / "JSON_GROUPING_REPORT.md",
            root / "reports" / "radio_name_analysis.json",
            root / "reports" / "bank_name_analysis.json",
            root / "app" / "resources" / "data" / "radio_name_groups.json",
            root / "app" / "resources" / "data" / "bank_name_groups.json",
        )
        for path in public_files:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"(?i)\b[A-Z]:[\\/]{1,2}")
        for resource_path in (
            ":/data/radio_name_groups.json",
            ":/data/bank_name_groups.json",
        ):
            resource = QFile(resource_path)
            self.assertTrue(resource.open(QIODevice.OpenModeFlag.ReadOnly))
            try:
                text = bytes(resource.readAll()).decode("utf-8")
            finally:
                resource.close()
            self.assertNotRegex(text, r"(?i)\b[A-Z]:[\\/]{1,2}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
