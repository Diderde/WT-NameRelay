from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.branding import (
    APP_NAME,
    BASE_AUTHOR,
    BASE_AUTHOR_HANDLE,
    BASE_LICENSE,
    BASE_PROJECT,
    BASE_REPO_URL,
    BASE_VERSION,
    FORK_AUTHOR,
    MODIFICATION_LICENSE,
    WINDOW_TITLE,
)
from app.i18n import tr

# 免责声明正文属于法律内容：固定使用中文原文，不参与界面语言切换；
# 窗口标题与倒计时按钮等界面控件仍随使用层语言切换。
_SUBTITLE = "使用声明"
_HINT = "请完整阅读并自行承担使用风险。"

# 首段即声明 fork 来源（原项目、仓库与作者），其余段落为免责与使用限制条款。
_FORK_NOTICE = (
    f"本项目（{APP_NAME}）为 {BASE_AUTHOR}（{BASE_AUTHOR_HANDLE}）原项目 {BASE_PROJECT}"
    f"（{BASE_REPO_URL}，{BASE_VERSION}）的 fork（非官方实验版），"
    f"由 {FORK_AUTHOR} 制作与维护，不代表原项目作者。"
    f"原始代码仍按 {BASE_LICENSE} 授权，修改与新增代码按 {MODIFICATION_LICENSE} 授权。"
)

# 段落样式按序与 _PARAGRAPHS 一一对应（两者必须等长），避免以下标硬编码。
_STYLES = (
    "disclaimerText",
    "disclaimerText",
    "disclaimerImportant",
    "disclaimerImportant",
    "disclaimerWarning",
    "disclaimerText",
    "disclaimerText",
)
_PARAGRAPHS = (
    _FORK_NOTICE,
    "本工具仅用于辅助制作War Thunder语音包，不提供任何未经许可的War Thunder官方的资产。",
    "使用本工具前，请用户自行备份重要文件，并认真确认来源文件、目标目录及待生成文件列表。因误操作、路径选择错误、文件覆盖、文件损坏、数据丢失、游戏更新、文件格式变化、第三方依赖变化或其他原因造成的直接或间接损失，开发者不承担责任。",
    "本工具为非官方第三方工具，与 Gaijin Entertainment、War Thunder及其关联主体不存在隶属、授权、赞助或合作关系。War Thunder及相关名称、商标、游戏资源的权利归其各自权利人所有。",
    "本工具仅供个人学习、非商业语音包制作及相关技术研究使用。严禁对本工具官方发布包进行二次售卖、倒卖、付费分发、捆绑收费，或未经作者许可用于其他商业用途。",
    "本工具使用的第三方开源组件分别遵循其原始许可证。第三方组件的授权权利与义务不因本声明而被替代。详细组件、版权声明和许可证文本请查看软件内“关于与许可”页面以及发布目录中的 THIRD_PARTY_LICENSES 文件。",
    "关闭本声明并继续使用，即表示用户已经阅读并理解以上内容，并愿意自行承担使用本工具产生的风险。",
)


class DisclaimerDialog(QDialog):
    """Mandatory, non-bypassable acknowledgement displayed before MainWindow exists."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._seconds_left = 3
        self.setWindowTitle(tr("dialog.disclaimer.window_title"))
        self.setModal(True)
        self.setMinimumSize(520, 430)
        self.resize(720, 560)
        root = QVBoxLayout(self); root.setContentsMargins(24, 20, 24, 20); root.setSpacing(12)
        header = QHBoxLayout()
        titles = QVBoxLayout(); title = QLabel(WINDOW_TITLE); title.setObjectName("disclaimerTitle"); subtitle = QLabel(_SUBTITLE); subtitle.setObjectName("sectionEyebrow"); titles.addWidget(title); titles.addWidget(subtitle); header.addLayout(titles, 1); root.addLayout(header)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget(); body = QVBoxLayout(content); body.setContentsMargins(8, 4, 8, 4); body.setSpacing(12)
        for index, paragraph in enumerate(_PARAGRAPHS):
            label = QLabel(paragraph); label.setWordWrap(True); label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setObjectName(_STYLES[index]); body.addWidget(label)
        body.addStretch(1); scroll.setWidget(content); root.addWidget(scroll, 1)
        self.continue_button = QPushButton(); self.continue_button.setObjectName("disclaimerContinueButton"); self.continue_button.setEnabled(False); self.continue_button.clicked.connect(self.accept)
        footer = QHBoxLayout(); hint = QLabel(_HINT); hint.setObjectName("mutedLabel"); footer.addWidget(hint, 1); footer.addWidget(self.continue_button); root.addLayout(footer)
        self._timer = QTimer(self); self._timer.setInterval(1000); self._timer.timeout.connect(self._tick); self._update_button(); self._timer.start()

    def _tick(self) -> None:
        self._seconds_left -= 1
        if self._seconds_left <= 0:
            self._seconds_left = 0; self._timer.stop(); self.continue_button.setEnabled(True)
        self._update_button()

    def _update_button(self) -> None:
        if self._seconds_left == 0:
            self.continue_button.setText(tr("dialog.disclaimer.continue"))
        else:
            self.continue_button.setText(tr("dialog.disclaimer.countdown", seconds=self._seconds_left))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space, Qt.Key.Key_Escape):
            if event.key() == Qt.Key.Key_Escape: self.reject()
            event.accept(); return
        super().keyPressEvent(event)
