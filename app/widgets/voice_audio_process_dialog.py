# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""语音工作台"进行处理"小窗：行内音频编辑 + 保存回写 + 成功后自动关闭。

2026-10-02：三新列的"进入处理"原为切到（已隐藏的）音频处理页，实机
路径不通；现改为弹出本小窗——嵌入从音频处理页提取的编辑核心
（EveWakamiya），"保存"把处理结果渲染回该行产物路径（原子替换），
成功后由页面按产物口径重登记，约两秒后自动关闭。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app.i18n import mark as _i18n_mark
from app.i18n import refresh as _i18n_refresh
from app.i18n import tr
from app.widgets.audio_editor_core import EveWakamiya

#: 保存成功到自动关闭的停留时间（用户可见"已保存"提示）
AUTO_CLOSE_MS = 2000


class KokoroTsurumaki(QDialog):
    """单行音频的处理小窗（模态）。

    保存目标在构造期定死（该行产物路径），不做另存为；
    ``saved`` 在导出成功后发出，携带产物路径供页面回登记。
    """

    saved = Signal(str)

    def __init__(self, source_path: str, save_path: Path, parent=None) -> None:
        super().__init__(parent)
        self._save_path = Path(save_path)
        self._close_pending = False
        self.setWindowTitle(tr('voice.process.dialog_title'))
        root = QVBoxLayout(self)
        source_label = QLabel(Path(source_path).name)
        source_label.setToolTip(source_path)
        self._source_label = source_label
        root.addWidget(source_label)
        self._core = EveWakamiya(self)
        root.addWidget(self._core, 1)
        self._format_note = QLabel(tr(
            'voice.process.format_note',
            fmt=self._save_path.suffix.lstrip('.').upper() or 'WAV'))
        self._format_note.setObjectName('mutedLabel')
        root.addWidget(self._format_note)
        footer = QHBoxLayout()
        self._status = QLabel('—')
        self._status.setObjectName('mutedLabel')
        self._status.setWordWrap(True)
        footer.addWidget(self._status, 1)
        self._save_button = _i18n_mark(QPushButton(tr('voice.process.save')), 'text', 'voice.process.save')
        self._save_button.clicked.connect(self._on_save_clicked)
        footer.addWidget(self._save_button)
        root.addLayout(footer)
        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.setInterval(AUTO_CLOSE_MS)
        self._close_timer.timeout.connect(self.accept)
        self._core.state_changed.connect(self._on_core_state)
        self._core.save_finished.connect(self._on_save_finished)
        self._core.load_paths([source_path])
        self.resize(880, 640)

    def retranslate(self) -> None:
        _i18n_refresh(self)
        self._core.retranslate()
        self._format_note.setText(tr(
            'voice.process.format_note',
            fmt=self._save_path.suffix.lstrip('.').upper() or 'WAV'))

    def _on_core_state(self) -> None:
        self._save_button.setEnabled(self._core.has_clips and not self._core.is_busy)
        if self._close_pending and not self._core.is_busy:
            self._close_pending = False
            if self._core.request_safe_close():
                self.accept()

    def _on_save_clicked(self) -> None:
        if self._core.is_busy or not self._core.has_clips:
            return
        self._status.setText(tr('voice.process.saving'))
        self._core.request_save(self._save_path)

    def _on_save_finished(self, ok: bool, message: str) -> None:
        if ok:
            self._status.setText(tr('voice.process.saved'))
            self.saved.emit(str(self._save_path))
            self._close_timer.start()
        else:
            self._status.setText(tr('voice.process.save_failed', detail=message))

    def _try_close(self) -> bool:
        """关窗守卫：导出中拒绝；忙则取消任务等收尾；闲则收尾放行。"""
        if self._core.exporting:
            self._status.setText(tr('voice.process.close_blocked'))
            return False
        if self._core.is_busy:
            self._core.request_safe_close()
            self._close_pending = True
            return False
        return self._core.request_safe_close()

    def closeEvent(self, event) -> None:  # Qt 命名
        if self._try_close():
            event.accept()
        else:
            event.ignore()

    def reject(self) -> None:
        if self._try_close():
            super().reject()
