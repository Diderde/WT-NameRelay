from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.branding import (
    APP_NAME,
    BASE_AUTHOR,
    BASE_PROJECT,
    BASE_REPO_URL,
    BASE_VERSION,
    FORK_AUTHOR,
    FORK_VERSION,
    MODIFICATION_LICENSE,
)
from app.i18n import about_html, tr
from app.models.voice_table import HASH_BACKEND

from .license_dialog import LicenseDialog


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("dialog.about.window_title"))
        self.resize(700, 520)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        header = QHBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("disclaimerTitle")
        header.addWidget(title, 1)
        root.addLayout(header)
        text = QTextBrowser()
        text.setOpenExternalLinks(True)
        text.setHtml(about_html())
        root.addWidget(text, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        view = buttons.addButton(tr("dialog.about.view_license"), QDialogButtonBox.ButtonRole.ActionRole)
        view.clicked.connect(lambda: LicenseDialog(self).exec())
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        # 署名与许可信息属于法律内容，固定中文原文，不随界面语言切换。
        footer = QLabel(
            f"本工具 fork 自 {BASE_AUTHOR} 的 {BASE_PROJECT} {BASE_VERSION}"
            f"（{BASE_REPO_URL}） · 本版 {FORK_VERSION}，维护者：{FORK_AUTHOR}"
            f"（新增代码：{MODIFICATION_LICENSE}）"
        )
        footer.setObjectName("aboutFooter")
        footer.setWordWrap(True)
        root.addWidget(footer)
        # 规范字节后端（技术信息，固定中文原文）：未构建 Rust 扩展时会显式提示降级后果，
        # 避免"以为在用 vtcore、实际走 Python 参考实现"。
        backend_text = (
            f"规范字节后端：{HASH_BACKEND}"
            if HASH_BACKEND == "vtcore"
            else f"规范字节后端：{HASH_BACKEND}（未构建 Rust 扩展 vtcore：签名、.vt 容器与整包校验不可用）"
        )
        backend = QLabel(backend_text)
        backend.setObjectName("aboutFooter")
        backend.setWordWrap(True)
        root.addWidget(backend)
