from __future__ import annotations

from PySide6.QtCore import QFile, QIODevice
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout, QWidget

from app.branding import ICON_RESOURCE


_LICENSES = {
    "WT-NameRelay — Source-Available License 1.0": ":/licenses/WT-NameRelay-Source-Available.txt",
    "CPython 3.11.5 — PSF License 2.0": ":/licenses/Python-PSF-2.0.txt",
    "PySide6 / Qt 6.7.3 — LGPL-3.0": ":/licenses/LGPL-3.0.txt",
    "GNU GPL 3.0（LGPL 3.0 引用）": ":/licenses/GPL-3.0.txt",
    "FFmpeg N-125829-gfe953596e9-20260728 — LGPL-3.0-or-later": (
        ":/licenses/FFmpeg-LGPL-3.0-or-later.txt"
    ),
    "PyQtGraph 0.13.7 — MIT": ":/licenses/PyQtGraph-MIT.txt",
    "NumPy 1.26.4 — BSD-3-Clause": ":/licenses/NumPy-BSD-3-Clause.txt",
    "OpenSSL 3.0.10 — Apache-2.0": ":/licenses/OpenSSL-Apache-2.0.txt",
    "PyInstaller 6.11.1 — GPL-2.0 with exception": (
        ":/licenses/PyInstaller-GPL-2.0-with-exception.txt"
    ),
    "Pillow 10.4.0 — HPND": ":/licenses/Pillow-HPND.txt",
    "openpyxl 3.1.5 — MIT": ":/licenses/openpyxl-MIT.txt",
}


class LicenseDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("完整许可证文本")
        self.setWindowIcon(QIcon(ICON_RESOURCE))
        self.resize(760, 580)
        layout = QVBoxLayout(self)
        self.selector = QComboBox()
        self.selector.addItems(_LICENSES)
        self.selector.currentTextChanged.connect(self._load)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(self.selector)
        layout.addWidget(self.browser, 1)
        layout.addWidget(buttons)
        self._load(self.selector.currentText())

    def _load(self, label: str) -> None:
        file = QFile(_LICENSES[label])
        if not file.open(QIODevice.OpenModeFlag.ReadOnly):
            self.browser.setPlainText("许可证资源不可用。")
            return
        try:
            self.browser.setPlainText(bytes(file.readAll()).decode("utf-8", errors="replace"))
        finally:
            file.close()
