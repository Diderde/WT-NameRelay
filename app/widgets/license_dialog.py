from __future__ import annotations

from PySide6.QtCore import QFile, QIODevice
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr

# (标题, 资源路径, 是否按 Markdown 渲染)
# 许可页标题属于法律内容，一律使用固定文字，不参与界面语言切换。
# 原始法律文本正文 setPlainText 逐字呈现；仅修改版自行撰写的声明（Markdown）使用渲染。
_PAGES = (
    ("修改版声明（GPL-3.0）", ":/licenses/ModificationNotice.md", True),
    ("WT-NameRelay Source-Available License 1.0", ":/licenses/WT-NameRelay-Source-Available.txt", False),
    ("GNU General Public License v2.0", ":/licenses/GPL-2.0.txt", False),
    ("GNU General Public License v3.0", ":/licenses/GPL-3.0.txt", False),
    ("CPython 3.11.5 — PSF License 2.0", ":/licenses/Python-PSF-2.0.txt", False),
    ("PySide6 / Qt 6.7.3 — LGPL-3.0", ":/licenses/LGPL-3.0.txt", False),
    ("FFmpeg N-125829 — LGPL-3.0-or-later", ":/licenses/FFmpeg-LGPL-3.0-or-later.txt", False),
    ("PyQtGraph 0.13.7 — MIT", ":/licenses/PyQtGraph-MIT.txt", False),
    ("NumPy 1.26.4 — BSD-3-Clause", ":/licenses/NumPy-BSD-3-Clause.txt", False),
    ("OpenSSL 3.0.10 — Apache-2.0", ":/licenses/OpenSSL-Apache-2.0.txt", False),
    ("PyInstaller 6.11.1 — GPL-2.0 with exception", ":/licenses/PyInstaller-GPL-2.0-with-exception.txt", False),
    ("openpyxl 3.1.5 — MIT", ":/licenses/openpyxl-MIT.txt", False),
)


def _read_resource(path: str) -> str:
    file = QFile(path)
    if not file.open(QIODevice.OpenModeFlag.ReadOnly):
        return "许可证资源不可用。"
    try:
        return bytes(file.readAll()).decode("utf-8", errors="replace")
    finally:
        file.close()


class LicenseDialog(QDialog):
    """License documents presented as one sub-page per document.

    Original legal texts are shown verbatim (plain text, untranslated); only the
    modification notice written for this fork is rendered from Markdown.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("dialog.license.window_title"))
        self.resize(880, 580)
        root = QVBoxLayout(self)
        body = QHBoxLayout()
        self.page_list = QListWidget()
        self.page_list.setObjectName("licenseList")
        self.page_list.setFixedWidth(250)
        body.addWidget(self.page_list)
        self.stack = QStackedWidget()
        self.browsers: list[QTextBrowser] = []
        for title, resource, is_markdown in _PAGES:
            title_text = title
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(4, 0, 0, 0)
            heading = QLabel(title_text)
            heading.setObjectName("licensePageTitle")
            heading.setWordWrap(True)
            layout.addWidget(heading)
            browser = QTextBrowser()
            browser.setObjectName("licenseBrowser")
            browser.setOpenExternalLinks(True)
            if is_markdown:
                browser.setMarkdown(_read_resource(resource))
            else:
                browser.setPlainText(_read_resource(resource))
            layout.addWidget(browser, 1)
            self.browsers.append(browser)
            self.stack.addWidget(page)
            self.page_list.addItem(title_text)
        self.page_list.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.page_list.setCurrentRow(0)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
