# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""三级页：API 渠道管理（W4）——TTS-Hub 管理台**进程内一比一集成**。

左区为内嵌 WebEngine，加载自定义协议 ``hub://console/``——该协议由
:mod:`app.services.hub_scheme` 拦截并分发到进程内 hub 的 FastAPI 应用（ASGI 调用）。
管理台的页面与全部功能即原项目本体（同一套 html/css/js，零改写），且**全程不创建
任何 socket、不监听任何端口**（无独立服务进程，安全软件无监听面可警告）。

右区为渠道连接编辑（地址/厂商/默认音色+拉取/模型/超时/fallback/启停）。密钥边界：
本应用只保存连接信息，厂商密钥全部在 TTS-Hub 侧（.env / 环境变量）。
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Any

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.i18n import i18n_text, tr
from app.services import api_channels, tts_hub_inproc
from app.services.api_channels import ApiChannel
from app.services.hub_scheme import (
    SCHEME_NAME,
    HubSchemeHandler,
    default_asgi_provider,
    register_hub_scheme,
)
from app.styles import theme

from .base_tool_page import BaseToolPage

_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# 进程加载即注册协议（幂等）：注册必须发生在首个 QApplication 创建之前——
# 本模块经由 app.pages 导入链，先于 main() 构建应用，时机天然满足
register_hub_scheme()


class ApiChannelPage(BaseToolPage):
    """API 渠道页：内嵌 TTS-Hub 管理台（进程内、零端口）+ 渠道连接管理。"""

    #: 工作线程 → GUI 线程
    voices_fetched = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("api", tr("page.api.title"), parent)
        self.status_panel.setVisible(False)
        self._channels: list[ApiChannel] = []
        self._labels: dict[str, QLabel] = {}

        self.voices_fetched.connect(self._deliver_voices)

        self.set_body_widget(self._build_body())
        self._install_hub_scheme_handler()
        # 内嵌管理台主题随应用昼夜热切换（监听器须随销毁摘除）
        theme.on_mode_changed(self._on_app_mode_changed)
        self.destroyed.connect(lambda: theme.off_mode_changed(self._on_app_mode_changed))
        self._reload_from_disk()
        self.retranslate()

    def _on_app_mode_changed(self, _mode: str) -> None:
        # 主题通知在全局重打磨中途派发，此时同步 runJavaScript 的内存分配
        # 会触发回收周期并原生崩溃（GC 中崩在枚举包装析构）；
        # 延后到下一轮事件循环再注入
        QTimer.singleShot(0, self._apply_console_theme)

    # —— 构建 ——
    def _build_body(self) -> QWidget:
        host = QWidget()
        root = QHBoxLayout(host)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        root.addWidget(self._build_hub_area(), 3)
        root.addWidget(self._build_channel_editor(), 2)
        return host

    def _build_hub_area(self) -> QWidget:
        """左区：内嵌 TTS-Hub 管理台（一比一）+ 工具条。"""

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        toolbar = QHBoxLayout()
        self.status_label = QLabel(i18n_text("hub.hint.offline"))
        self.status_label.setObjectName("mutedLabel")
        toolbar.addWidget(self.status_label, 1)
        self.refresh_button = QPushButton(i18n_text("hub.action.refresh"))
        self.refresh_button.setObjectName("smallActionButton")
        self.refresh_button.clicked.connect(self._refresh_hub)
        toolbar.addWidget(self.refresh_button)
        self.open_browser_button = QPushButton(i18n_text("hub.action.open_browser"))
        self.open_browser_button.setObjectName("smallActionButton")
        self.open_browser_button.clicked.connect(self._open_in_browser)
        toolbar.addWidget(self.open_browser_button)
        layout.addLayout(toolbar)

        from PySide6.QtWebEngineWidgets import QWebEngineView

        self.hub_view = QWebEngineView(self)
        self.hub_view.setObjectName("hubView")
        self.hub_view.loadFinished.connect(self._on_hub_load_finished)
        self.hub_view.setMinimumHeight(320)
        layout.addWidget(self.hub_view, 1)
        return panel

    def _install_hub_scheme_handler(self) -> None:
        """在默认 profile 上安装 ``hub://`` 处理器（幂等，全局一次）。"""

        from PySide6.QtWebEngineCore import QWebEngineProfile

        cls = HubSchemeHandler
        handler = getattr(cls, "_installed", None)
        if handler is None:
            # 
            # 处理器不能挂在页面父子树上：首建页面销毁会把子对象一并带走，之后再建的
            # 实例便拿不到可用处理器；改为无父对象、由类属性强引用全程持有，且每个
            # 实例都要拿到引用（旧逻辑只给首建实例赋值，第二个实例 AttributeError）
            handler = cls(default_asgi_provider)
            QWebEngineProfile.defaultProfile().installUrlSchemeHandler(SCHEME_NAME, handler)
            cls._installed = handler
        self._hub_handler = handler

    def _build_channel_editor(self) -> QWidget:
        """右区：渠道连接编辑（列表压缩为下拉）。"""

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        channel_label = QLabel(i18n_text("api.field.channel"))
        channel_label.setObjectName("mutedLabel")
        self._labels["api.field.channel"] = channel_label
        layout.addWidget(channel_label)
        self.channel_select_combo = QComboBox()
        self.channel_select_combo.currentIndexChanged.connect(self._on_channel_selected)
        layout.addWidget(self.channel_select_combo)

        form = QFormLayout()
        form.setSpacing(8)

        def add_labeled(key: str, widget: QWidget) -> None:
            label = QLabel(i18n_text(key))
            label.setObjectName("mutedLabel")
            self._labels[key] = label
            form.addRow(label, widget)

        self.label_input = QLineEdit()
        add_labeled("api.field.label", self.label_input)

        self.kind_label = QLabel(i18n_text("api.kind.tts_hub"))
        self.kind_label.setObjectName("mutedLabel")
        add_labeled("api.field.kind", self.kind_label)

        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText(i18n_text("api.field.base_url_hint"))
        self.base_url_input.setToolTip(i18n_text("api.field.base_url_tooltip"))
        add_labeled("api.field.base_url", self.base_url_input)

        self.vendor_input = QLineEdit()
        self.vendor_input.setPlaceholderText(i18n_text("api.field.vendor_hint"))
        add_labeled("api.field.vendor", self.vendor_input)

        self.voice_input = QComboBox()
        self.voice_input.setEditable(True)
        voice_row = QHBoxLayout()
        voice_row.setContentsMargins(0, 0, 0, 0)
        voice_row.addWidget(self.voice_input, 1)
        self.fetch_voices_button = QPushButton(i18n_text("api.action.fetch_voices"))
        self.fetch_voices_button.setObjectName("smallActionButton")
        self.fetch_voices_button.clicked.connect(self._fetch_voices)
        voice_row.addWidget(self.fetch_voices_button)
        voice_host = QWidget()
        voice_host.setLayout(voice_row)
        add_labeled("api.field.voice", voice_host)

        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText(i18n_text("api.field.model_hint"))
        add_labeled("api.field.model", self.model_input)

        self.timeout_input = QSpinBox()
        self.timeout_input.setRange(10, 600)
        self.timeout_input.setSuffix(" s")
        add_labeled("api.field.timeout", self.timeout_input)

        self.fallback_checkbox = QCheckBox(i18n_text("api.field.fallback"))
        self._labels["api.field.fallback"] = self.fallback_checkbox
        form.addRow(self.fallback_checkbox)
        self.enabled_checkbox = QCheckBox(i18n_text("api.field.enabled"))
        self._labels["api.field.enabled"] = self.enabled_checkbox
        form.addRow(self.enabled_checkbox)

        layout.addLayout(form)

        actions = QHBoxLayout()
        self.save_button = QPushButton(i18n_text("api.action.save"))
        self.save_button.clicked.connect(self._save_current)
        self.probe_button = QPushButton(i18n_text("api.action.probe"))
        self.probe_button.setObjectName("smallActionButton")
        self.probe_button.clicked.connect(self._refresh_hub)
        actions.addWidget(self.save_button)
        actions.addWidget(self.probe_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("mutedLabel")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        note = QLabel(i18n_text("api.note.keys"))
        note.setObjectName("mutedLabel")
        note.setWordWrap(True)
        self._labels["api.note.keys"] = note
        layout.addWidget(note)

        layout.addStretch(1)
        return panel

    # —— 数据装载 ——
    def _reload_from_disk(self) -> None:
        selected_id = self._current_channel_id()
        self._channels = api_channels.load_channels()
        self.channel_select_combo.blockSignals(True)
        self.channel_select_combo.clear()
        for channel in self._channels:
            state = "● " if channel.enabled else "○ "
            self.channel_select_combo.addItem(f"{state}{channel.label}", channel.channel_id)
        restore_index = next(
            (index for index, channel in enumerate(self._channels) if channel.channel_id == selected_id),
            0 if self._channels else -1,
        )
        self.channel_select_combo.setCurrentIndex(restore_index)
        self.channel_select_combo.blockSignals(False)
        if 0 <= restore_index < len(self._channels):
            self._fill_form(self._channels[restore_index])

    def _current_channel_id(self) -> str | None:
        index = self.channel_select_combo.currentIndex()
        if index < 0:
            return None
        return self.channel_select_combo.itemData(index)

    def _current_channel(self) -> ApiChannel | None:
        channel_id = self._current_channel_id()
        return next((c for c in self._channels if c.channel_id == channel_id), None)

    def _fill_form(self, channel: ApiChannel) -> None:
        self.label_input.setText(channel.label)
        self.base_url_input.setText(channel.base_url)
        self.vendor_input.setText(channel.vendor)
        self.voice_input.setCurrentText(channel.voice)
        self.model_input.setText(channel.model)
        self.timeout_input.setValue(int(channel.timeout_s))
        self.fallback_checkbox.setChecked(channel.fallback)
        self.enabled_checkbox.setChecked(channel.enabled)

    def _on_channel_selected(self, index: int) -> None:
        if 0 <= index < len(self._channels):
            self._fill_form(self._channels[index])
        self._set_summary("")

    # —— 动作 ——
    def _save_current(self) -> None:
        channel = self._current_channel()
        if channel is None:
            return
        channel.label = self.label_input.text().strip() or channel.channel_id
        channel.base_url = self.base_url_input.text().strip()
        channel.vendor = self.vendor_input.text().strip()
        channel.voice = self.voice_input.currentText().strip()
        channel.model = self.model_input.text().strip()
        channel.timeout_s = float(self.timeout_input.value())
        channel.fallback = self.fallback_checkbox.isChecked()
        channel.enabled = self.enabled_checkbox.isChecked()
        api_channels.upsert_channel(channel)
        self._reload_from_disk()
        self._set_summary(i18n_text("api.saved"))

    def _refresh_hub(self) -> None:
        """刷新 = 加载 ``hub://console/``（进程内协议，零端口）。

        hub 的打开（含首次导入）由启动预热线程在后台完成；分发时惰性 ensure——
        即便未预热，也只是管理台页面等待，不阻塞界面。
        """

        self._set_status(i18n_text("hub.fetching"))
        self.hub_view.load(QUrl("hub://console/"))

    def _on_hub_load_finished(self, ok: bool) -> None:
        if ok:
            self._set_status(i18n_text("hub.status.inproc"))
            self._apply_console_theme()
        else:
            self._set_status(tr("api.probe.fail", error="load failed"))

    def _apply_console_theme(self) -> None:
        """把当前昼夜主题的覆盖 CSS 热注入内嵌管理台（无需重载页面）。"""

        css = _HUB_THEME_CSS[theme.current_mode()]
        js = (
            "(function(){let el=document.getElementById('wt-theme-ov');"
            "if(!el){el=document.createElement('style');el.id='wt-theme-ov';"
            "document.head.appendChild(el);}el.textContent=" + json.dumps(css) + ";})()"
        )
        self.hub_view.page().runJavaScript(js)

    def _open_in_browser(self) -> None:
        """外接 serve 形态下跳系统浏览器；进程内形态无外部地址，仅提示。"""

        base_url = self.base_url_input.text().strip() or (self._current_channel().base_url if self._current_channel() else "")
        if base_url:
            QDesktopServices.openUrl(QUrl(base_url.rstrip("/") + "/"))
        else:
            self._set_status(tr("api.probe.fail", error="no base_url"))

    def _fetch_voices(self) -> None:
        channel = self._current_channel()
        if channel is None or not self.fetch_voices_button.isEnabled():
            return
        self._set_summary(i18n_text("api.fetching"))
        self.fetch_voices_button.setEnabled(False)
        threading.Thread(target=self._fetch_voices_work, name="api-voice-fetch", daemon=True).start()

    def _fetch_voices_work(self) -> None:
        # 进程内直调 hub 门面：音色表即时可得（无 HTTP、无端口）
        try:
            hub = tts_hub_inproc.ensure_hub()
            names = [str(row.get("name") or row.get("id") or "") for row in hub.local_voices()]
            self.voices_fetched.emit({"ok": True, "names": [n for n in names if n]})
            return
        except Exception as inproc_error:  # noqa: BLE001  进程内不可用 → 外部 serve HTTP 兜底
            inproc_detail = str(inproc_error)
        channel = self._current_channel()
        base_url = channel.base_url if channel else ""
        if not base_url:
            self.voices_fetched.emit({"ok": False, "error": inproc_detail})
            return
        try:
            request = urllib.request.Request(base_url.rstrip("/") + "/api/voices")
            with _NO_PROXY_OPENER.open(request, timeout=5.0) as response:
                data = json.loads(response.read(1 << 20).decode("utf-8", "replace"))
            voices = data.get("voices", data) if isinstance(data, dict) else data
            names = [
                str(entry.get("name") or entry.get("voice_id") or "") if isinstance(entry, dict) else str(entry)
                for entry in (voices if isinstance(voices, list) else [])
            ]
            self.voices_fetched.emit({"ok": True, "names": [n for n in names if n]})
        except (urllib.error.URLError, OSError, ValueError) as error:
            self.voices_fetched.emit({"ok": False, "error": f"{inproc_detail} | http: {error}"})

    def _deliver_voices(self, result: dict[str, Any]) -> None:
        self.fetch_voices_button.setEnabled(True)
        if result["ok"]:
            names = list(result["names"])
            current = self.voice_input.currentText().strip()
            self.voice_input.clear()
            self.voice_input.addItems(names)
            if current:
                self.voice_input.setCurrentText(current)
            self._set_summary(i18n_text("api.voices.fetched", count=len(names)))
        else:
            self._set_summary(tr("api.probe.fail", error=str(result["error"])))

    # —— 展示 ——
    def _set_summary(self, text: str) -> None:
        self.summary_label.setText(text)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def retranslate(self) -> None:
        super().retranslate()
        for key, label in self._labels.items():
            label.setText(i18n_text(key))
        self.refresh_button.setText(i18n_text("hub.action.refresh"))
        self.open_browser_button.setText(i18n_text("hub.action.open_browser"))
        self.fetch_voices_button.setText(i18n_text("api.action.fetch_voices"))
        self.save_button.setText(i18n_text("api.action.save"))
        self.probe_button.setText(i18n_text("api.action.probe"))
        selected_id = self._current_channel_id()
        self.channel_select_combo.blockSignals(True)
        for index, channel in enumerate(self._channels):
            state = "● " if channel.enabled else "○ "
            self.channel_select_combo.setItemText(index, f"{state}{channel.label}")
        self.channel_select_combo.blockSignals(False)
        if selected_id is not None:
            row = next((i for i, c in enumerate(self._channels) if c.channel_id == selected_id), -1)
            self.channel_select_combo.setCurrentIndex(row)


#: 管理台主题覆盖 CSS：hub 的 console.css 写死深色且 input/button 等含硬编码色，
#: 按 app 昼夜主题注入同源配色变量 + 对应选择器覆盖，实现内嵌区与本体风格一致
_HUB_THEME_CSS: dict[str, str] = {
    "light": """
:root { --bg:#f8f9fc; --panel:#ffffff; --line:#dfe3ec; --fg:#1a1a2e; --muted:#4a4a5a;
        --accent:#3b82f6; --ok:#10b981; --bad:#ef4444; --warn:#d29922; }
input, textarea, select { background:#ffffff; }
button { background:#eef2f7; color:#1a1a2e; }
table.grid tr:hover td { background:#f1f5f9; }
.banner, #banner { background:#f1f5f9; }
.card { background:#ffffff; }
.chip.on { background:#e7effd; color:#1a1a2e; }
body { color:#1a1a2e; }
""",
    "dark": """
:root { --bg:#0b1020; --panel:#111827; --line:#263149; --fg:#edf3ff; --muted:#8f9bb0;
        --accent:#60a5fa; --ok:#10b981; --bad:#ef4444; --warn:#d29922; }
input, textarea, select { background:#111827; }
button { background:#243247; color:#edf3ff; }
table.grid tr:hover td { background:#182235; }
.banner, #banner { background:#141d31; }
.card { background:#0f1626; }
.chip.on { background:#1d2a44; color:#edf3ff; }
body { color:#edf3ff; }
""",
}

#: hub 项目根不可用时内嵌的占位页（原生 HTML：指引先准备好 TTS-Hub 项目根）
_OFFLINE_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>
body { background:#14161a; color:#e6e9ef; font:14px/1.8 "Segoe UI","Microsoft YaHei",sans-serif;
       display:flex; align-items:center; justify-content:center; height:96vh; margin:0; }
.box { max-width: 560px; }
h2 { font-size:16px; margin:0 0 10px; }
p { color:#9aa3b2; font-size:13px; margin:6px 0; }
code { background:#101216; border:1px solid #2c313b; border-radius:4px; padding:1px 6px; }
</style></head><body><div class="box">
<h2>TTS-Hub 未就绪</h2>
<p>管理台与云端合成由 TTS-Hub 提供。请确认项目根（含 <code>tts_hub/</code>、<code>.env</code>）存在后点击上方「刷新」。</p>
<p>密钥全部保存在 TTS-Hub 侧，本应用不读取、不保存。</p>
</div></body></html>"""
