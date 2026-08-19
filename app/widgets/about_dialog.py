from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.branding import APP_NAME, AUTHOR_VERSION, ICON_RESOURCE
from .license_dialog import LicenseDialog


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("关于与许可")
        self.setWindowIcon(QIcon(ICON_RESOURCE))
        self.resize(700, 520)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        header = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(QIcon(ICON_RESOURCE).pixmap(64, 64))
        header.addWidget(icon)
        title = QLabel(f"{APP_NAME}\n{AUTHOR_VERSION}")
        title.setObjectName("disclaimerTitle")
        header.addWidget(title, 1)
        root.addLayout(header)
        text = QTextBrowser()
        text.setOpenExternalLinks(True)
        text.setHtml(
            """
            <h3>关于与许可</h3>
            <p>战争雷霆语音包文件名称补全、复制与语音处理工具。</p>
            <p>本工具为非官方第三方工具，不包含游戏官方资源，也不与
            Gaijin Entertainment 或 War Thunder 存在授权、赞助或合作关系。</p>
            <p><b>禁止对官方发布包进行二次售卖、倒卖、付费分发或捆绑收费。</b>
            此声明不替代第三方开源许可证已经授予的权利。</p>
            <p>项目原创部分采用 <b>WT-NameRelay Source-Available License 1.0</b>，
            允许个人非商业使用与同许可源码分享；本项目不是 OSI 定义的开源软件。</p>
            <h4>运行时第三方组件</h4>
            <ul>
              <li>CPython 3.11.5 — PSF License 2.0</li>
              <li>PySide6 6.7.3 / Qt for Python — LGPL-3.0 / GPL-3.0</li>
              <li>PyQtGraph 0.13.7 — MIT</li>
              <li>NumPy 1.26.4 — BSD-3-Clause</li>
              <li>OpenSSL 3.0.10 — Apache-2.0</li>
              <li>FFmpeg N-125829-gfe953596e9-20260728 — LGPL-3.0-or-later</li>
            </ul>
            <p>完整文本可在下方许可查看器与发布目录中查阅。</p>
            """
        )
        root.addWidget(text, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        view = buttons.addButton("查看完整许可证", QDialogButtonBox.ButtonRole.ActionRole)
        view.clicked.connect(lambda: LicenseDialog(self).exec())
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
