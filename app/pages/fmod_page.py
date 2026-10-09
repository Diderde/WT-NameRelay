# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""FMOD 控制台页：当前提供「启动工作区 FMOD Studio」入口。

探测口径与 start.bat 一致：工作区 ``FMOD Studio */fmodstudio.exe`` 优先，
回退 Program Files 的 ``FMOD Sound Systems`` 安装。经 ``os.startfile`` 以
独立进程拉起（等价双击启动，应用退出不影响 FMOD 运行）；流水线其余能力
（构建触发、bank 拷贝等）按 ``docs/fmod-pipeline-plan.md`` 后续轮次扩展。
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from app.i18n import tr
from app.pages.base_tool_page import BaseToolPage


def find_fmod_studio(workspace: Path) -> Path | None:
    """探测 FMOD Studio 可执行文件：工作区优先，回退 Program Files 安装。"""

    candidates: list[Path] = sorted(workspace.glob("FMOD Studio */fmodstudio.exe"))
    for env_key in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env_key)
        if base:
            candidates.extend(sorted(Path(base).glob("FMOD Sound Systems/*/fmodstudio.exe")))
    return candidates[0] if candidates else None


class FmodConsolePage(BaseToolPage):
    """FMOD 控制台：启动工作区 FMOD Studio；其余流水线能力后续扩展。"""

    def __init__(self, workspace: Path | None = None, parent: QWidget | None = None) -> None:
        self._workspace = (
            workspace if workspace is not None else Path(__file__).resolve().parents[2]
        )
        super().__init__("fmod", tr("fmod.page.title"), parent)
        self.status_panel.setVisible(False)
        self.set_body_widget(self._build_body())
        self.retranslate()

    def _build_body(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("crewManualPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 14, 15, 14)
        layout.setSpacing(10)

        self.hint_label = QLabel(tr("fmod.page.hint"))
        self.hint_label.setObjectName("mutedLabel")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        self.launch_button = QPushButton(tr("fmod.launch.button"))
        self.launch_button.clicked.connect(self._launch_clicked)
        layout.addWidget(self.launch_button)

        self.status_label = QLabel()
        self.status_label.setObjectName("mutedLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        return frame

    def retranslate(self) -> None:
        self.launch_button.setText(tr("fmod.launch.button"))
        self.hint_label.setText(tr("fmod.page.hint"))
        self._refresh_status()

    def _refresh_status(self) -> None:
        exe = find_fmod_studio(self._workspace)
        if exe is None:
            self.launch_button.setEnabled(False)
            self.status_label.setText(tr("fmod.launch.not_found"))
        else:
            self.launch_button.setEnabled(True)
            self.status_label.setText(str(exe))

    def _launch_clicked(self) -> None:
        exe = find_fmod_studio(self._workspace)
        if exe is None:
            self.status_label.setText(tr("fmod.launch.not_found"))
            return
        try:
            # FMOD Studio 以"当前目录"解析工程/诊断文件——直接继承应用的仓库根
            # 会翻错位置（2026-10-08 实测：启动横幅出现 -diagnostic foobar.fspro）。
            # 官方启动脚本都是先 cd 到自身目录再启动，这里同样瞬时切换后还原。
            previous = os.getcwd()
            os.chdir(exe.parent)
            try:
                os.startfile(exe.name)  # 相对名 + 正确 cwd：独立进程、不经 shell
            finally:
                os.chdir(previous)
            self.status_label.setText(tr("fmod.launch.started", path=str(exe)))
        except OSError as error:
            self.status_label.setText(tr("fmod.launch.failed", error=str(error)))
