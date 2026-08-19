from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon, QKeyEvent
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from app.branding import AUTHOR_VERSION, ICON_RESOURCE, WINDOW_TITLE


_PARAGRAPHS = (
    "本工具仅用于战争雷霆语音包相关文件名称的识别、复制与补全，不包含、不提供也不分发任何游戏官方资源或官方音频。",
    "使用本工具前，请用户自行备份重要文件，并认真确认来源文件、目标目录及待生成文件列表。因误操作、路径选择错误、文件覆盖、文件损坏、数据丢失、游戏更新、文件格式变化、第三方依赖变化或其他原因造成的直接或间接损失，开发者 Beiku 不承担责任。",
    "本工具为非官方第三方工具，与 Gaijin Entertainment、War Thunder 及其关联主体不存在隶属、授权、赞助或合作关系。War Thunder 及相关名称、商标、游戏资源的权利归其各自权利人所有。",
    "本工具仅供个人学习、非商业语音包制作及相关技术研究使用。严禁对本工具官方发布包进行二次售卖、倒卖、付费分发、捆绑收费，或未经作者许可用于其他商业用途。",
    "本工具使用的第三方开源组件分别遵循其原始许可证。第三方组件的授权权利与义务不因本声明而被替代。详细组件、版权声明和许可证文本请查看软件内“关于与许可”页面以及发布目录中的 THIRD_PARTY_LICENSES 文件。",
    "关闭本声明并继续使用，即表示用户已经阅读并理解以上内容，并愿意自行承担使用本工具产生的风险。",
)


class DisclaimerDialog(QDialog):
    """Mandatory, non-bypassable acknowledgement displayed before MainWindow exists."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._seconds_left = 3
        self.setWindowTitle("WT-NameRelay 使用声明")
        self.setWindowIcon(QIcon(ICON_RESOURCE))
        self.setModal(True)
        self.setMinimumSize(520, 430)
        self.resize(720, 560)
        root = QVBoxLayout(self); root.setContentsMargins(24, 20, 24, 20); root.setSpacing(12)
        header = QHBoxLayout(); icon = QLabel(); icon.setPixmap(QIcon(ICON_RESOURCE).pixmap(56, 56)); header.addWidget(icon)
        titles = QVBoxLayout(); title = QLabel(WINDOW_TITLE); title.setObjectName("disclaimerTitle"); subtitle = QLabel("使用声明"); subtitle.setObjectName("sectionEyebrow"); titles.addWidget(title); titles.addWidget(subtitle); header.addLayout(titles, 1); root.addLayout(header)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget(); body = QVBoxLayout(content); body.setContentsMargins(8, 4, 8, 4); body.setSpacing(12)
        for index, paragraph in enumerate(_PARAGRAPHS):
            label = QLabel(paragraph); label.setWordWrap(True); label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setObjectName("disclaimerWarning" if index == 3 else ("disclaimerImportant" if index in (1, 2) else "disclaimerText")); body.addWidget(label)
        body.addStretch(1); scroll.setWidget(content); root.addWidget(scroll, 1)
        self.continue_button = QPushButton(); self.continue_button.setObjectName("disclaimerContinueButton"); self.continue_button.setEnabled(False); self.continue_button.clicked.connect(self.accept)
        footer = QHBoxLayout(); hint = QLabel("请完整阅读并自行承担使用风险。"); hint.setObjectName("mutedLabel"); footer.addWidget(hint, 1); footer.addWidget(self.continue_button); root.addLayout(footer)
        self._timer = QTimer(self); self._timer.setInterval(1000); self._timer.timeout.connect(self._tick); self._update_button(); self._timer.start()

    def _tick(self) -> None:
        self._seconds_left -= 1
        if self._seconds_left <= 0:
            self._seconds_left = 0; self._timer.stop(); self.continue_button.setEnabled(True)
        self._update_button()

    def _update_button(self) -> None:
        self.continue_button.setText("我已阅读并继续" if self._seconds_left == 0 else f"我已阅读（{self._seconds_left}秒）")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space, Qt.Key.Key_Escape):
            if event.key() == Qt.Key.Key_Escape: self.reject()
            event.accept(); return
        super().keyPressEvent(event)
