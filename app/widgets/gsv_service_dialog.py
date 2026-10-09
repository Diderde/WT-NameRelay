# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""GSV 推理服务管理对话框（命名规范/多分支兼容的建档入口）。

服务档语义：一个档 = 一个 GSV 服务实例（地址+显示名）。V1~V4 权重版本
可由同一服务经「应用权重」热切；不同分支（cuda_graph_v5 / 仅CPU 的
CPUFast）是不同可执行文件，必须各起一个服务、各占一个端口——所以
"选版本"在客户端的落点就是**多档服务 + 下拉切换**。

模板下拉预置三种形态的名称与默认端口建议（上游:9880 / cuda_v5:9881 /
CPUFast:9882），保存即建档；活跃档切换经信号交还页面触发重装配。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.i18n import i18n_text
from app.services.gsv_services import (
    GsvServiceProfile,
)

#: 模板：(显示名键, 默认地址, 启动命令, 工作目录)。地址/命令按官方
#: 整合包布局预填，均可改；命令留空 = 外部服务（只探活不拉起）。
_TEMPLATES: tuple[tuple[str, str, str, str], ...] = (
    (
        "voice.gsv.tpl.upstream",
        "http://127.0.0.1:9880",
        '"TTS model/GPT-SoVITS/runtime/python.exe" api_v2.py -a 127.0.0.1 -p 9880',
        "TTS model/GPT-SoVITS",
    ),
    (
        "voice.gsv.tpl.cuda_v5",
        "http://127.0.0.1:9881",
        '"TTS model/GPT-SoVITS/runtime/python.exe" api_v2.py -a 127.0.0.1 -p 9881',
        "TTS model/GPT-SoVITS",
    ),
    (
        "voice.gsv.tpl.cpufast",
        "http://127.0.0.1:9882",
        '"TTS model/GPT-SoVITS-CPUFast/runtime/python.exe" api_v2.py -a 127.0.0.1 -p 9882',
        "TTS model/GPT-SoVITS-CPUFast",
    ),
)


class MisumiUika(QDialog):
    """GSV 服务档管理：新建（模板预填）/ 编辑 / 删除 / 设为当前。"""

    def __init__(self, profiles: list[GsvServiceProfile], active_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n_text("voice.gsv.manage_title"))
        self.setMinimumWidth(460)
        self._working = list(profiles)
        self._active_id = active_id

        layout = QVBoxLayout(self)

        self._list = QListWidget(self)
        for profile in self._working:
            self._list.addItem(self._item_text(profile))
        layout.addWidget(self._list)

        form = QFormLayout()
        self._template_combo = QComboBox(self)
        for key, _url, _command, _cwd in _TEMPLATES:
            self._template_combo.addItem(i18n_text(key))
        form.addRow(i18n_text("voice.gsv.manage_template"), self._template_combo)
        self._name_input = QLineEdit(self)
        form.addRow(i18n_text("voice.gsv.manage_name"), self._name_input)
        self._url_input = QLineEdit(self)
        self._url_input.setPlaceholderText("http://127.0.0.1:9880")
        form.addRow(i18n_text("voice.gsv.manage_url"), self._url_input)
        self._command_input = QLineEdit(self)
        self._command_input.setPlaceholderText(i18n_text("voice.gsv.manage_command_hint"))
        form.addRow(i18n_text("voice.gsv.manage_command"), self._command_input)
        self._cwd_input = QLineEdit(self)
        self._cwd_input.setPlaceholderText(i18n_text("voice.gsv.manage_cwd_hint"))
        form.addRow(i18n_text("voice.gsv.manage_cwd"), self._cwd_input)
        layout.addLayout(form)

        button_row = QHBoxLayout()
        self._add_button = QPushButton(i18n_text("voice.gsv.manage_add"))
        self._add_button.clicked.connect(self._add_clicked)
        button_row.addWidget(self._add_button)
        self._delete_button = QPushButton(i18n_text("voice.gsv.manage_delete"))
        self._delete_button.clicked.connect(self._delete_clicked)
        button_row.addWidget(self._delete_button)
        self._use_button = QPushButton(i18n_text("voice.gsv.manage_use"))
        self._use_button.clicked.connect(self._use_clicked)
        button_row.addWidget(self._use_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._template_combo.currentIndexChanged.connect(self._template_changed)
        self._template_changed(0)
        self._list.currentRowChanged.connect(self._on_row_selected)
        self._sync_buttons()

    # —— 展示 ——
    def _item_text(self, profile: GsvServiceProfile) -> str:
        mark = i18n_text("voice.gsv.manage_active_mark") if profile.profile_id == self._active_id else ""
        return f"{profile.name} — {profile.base_url}{mark}"

    def _selected_profile(self) -> GsvServiceProfile | None:
        row = self._list.currentRow()
        return self._working[row] if 0 <= row < len(self._working) else None

    def _reload(self, select_id: str | None = None) -> None:
        self._list.clear()
        for profile in self._working:
            self._list.addItem(self._item_text(profile))
        if select_id is not None:
            for index, profile in enumerate(self._working):
                if profile.profile_id == select_id:
                    self._list.setCurrentRow(index)
                    return
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        selected = self._selected_profile()
        deletable = selected is not None and len(self._working) > 1
        self._delete_button.setEnabled(deletable)
        self._use_button.setEnabled(selected is not None and selected.profile_id != self._active_id)

    def _on_row_selected(self, _row: int) -> None:
        selected = self._selected_profile()
        if selected is not None:
            self._name_input.setText(selected.name)
            self._url_input.setText(selected.base_url)
            self._command_input.setText(selected.command)
            self._cwd_input.setText(selected.cwd)
        self._sync_buttons()

    # —— 动作 ——
    def _template_changed(self, index: int) -> None:
        if 0 <= index < len(_TEMPLATES):
            key, url, command, cwd = _TEMPLATES[index]
            if not self._name_input.text().strip():
                self._name_input.setText(i18n_text(key))
            self._url_input.setText(url)
            self._command_input.setText(command)
            self._cwd_input.setText(cwd)

    def _add_clicked(self) -> None:
        name = self._name_input.text().strip()
        url = self._url_input.text().strip()
        if not name or not url:
            return
        command = self._command_input.text().strip()
        cwd = self._cwd_input.text().strip()
        existing = next((p for p in self._working if p.name == name), None)
        if existing is not None:
            # 同名即更新（含地址/命令/工作目录），身份与 active 语义保持
            existing.base_url = url
            existing.command = command
            existing.cwd = cwd
            self._reload(existing.profile_id)
            return
        # profile_id 曾用 abs(hash(name)) % 10000——
        # 字符串 hash 跨进程随机（PYTHONHASHSEED）且 500 档内实测撞击
        # 16 次（生日悖论），撞击会让「设为当前/删除」指向歧义档；
        # 改 uuid 短码（与 VoiceRow 同源语义）
        import uuid as _uuid

        profile_id = _uuid.uuid4().hex[:12]
        profile = GsvServiceProfile(
            profile_id=profile_id, name=name, base_url=url, command=command, cwd=cwd)
        self._working.append(profile)
        self._reload(profile.profile_id)
        self._active_id = profile.profile_id
        self._reload(self._active_id)

    def _delete_clicked(self) -> None:
        selected = self._selected_profile()
        if selected is None or len(self._working) <= 1:
            return
        self._working = [p for p in self._working if p.profile_id != selected.profile_id]
        if self._active_id == selected.profile_id:
            self._active_id = self._working[0].profile_id
        self._reload(self._active_id)

    def _use_clicked(self) -> None:
        selected = self._selected_profile()
        if selected is not None:
            self._active_id = selected.profile_id
            self._reload(self._active_id)

    # —— 结果 ——
    def result_profiles(self) -> tuple[list[GsvServiceProfile], str]:
        """对话框确认后的 (全量档, active id)。"""

        return self._working, self._active_id
