from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QVBoxLayout, QWidget

from app.branding import WINDOW_TITLE
from app.i18n import (
    current_language,
    off_language_changed,
    on_language_changed,
    set_language,
    tr,
)
from app.pages import (
    ApiChannelPage,
    AudioProcessingPage,
    BankPage,
    CrewPage,
    FileCopyPage,
    RadioPage,
    SeparationPage,
    VideoClipPage,
    VoiceBatchPage,
)
from app.pages.fmod_page import FmodConsolePage

# 副作用导入：注册内嵌名称库与许可文档等 Qt 资源，不直接引用其符号。
from app.resources import resources_rc as _resources_rc  # noqa: F401
from app.services import api_channels, gsv_services
from app.services.gsv_probe import probe_capabilities
from app.services.tts_hub_backend import TtsHubBackend
from app.services.tts_hub_inproc import hub_available
from app.services.tts_hub_inproc_backend import TtsHubInprocBackend
from app.services.tts_runner import (
    FakeTtsBackend,
    GptSovitsBackend,
    SubprocessTtsService,
    TtsBackend,
)
from app.services.voice_service_launcher import start_cosyvoice3_service
from app.styles import theme
from app.widgets.about_dialog import AboutDialog
from app.widgets.animated_stack import AnimatedStack, TransitionDirection
from app.widgets.nav_rail import NavRail

LOGGER = logging.getLogger("wt_name_relay")


class MainWindow(QMainWindow):
    """Application shell responsible only for page routing."""

    #: 后端装配完成（工作线程 → GUI 线程）：(token, (backend, service))
    backend_ready = Signal(int, object)
    #: 后端装配异常（工作线程 → GUI 线程）：(token, message)
    backend_failed = Signal(int, str)

    VOICE_INDEX = 0
    COPY_INDEX = 1
    AUDIO_INDEX = 2
    SEPARATE_INDEX = 3
    API_INDEX = 4
    SETTINGS_INDEX = 5
    FMOD_INDEX = 6
    EXPERIMENTAL_INDEX = 7
    VIDEO_INDEX = 8

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(820, 620)
        self.resize(1100, 700)

        root = QWidget()
        root.setObjectName("appRoot")
        self._root_layout = QHBoxLayout(root)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)
        self.setCentralWidget(root)

        # 左侧图标导航栏（水纹背板与首页卡片入口已随平实化改版移除，恢复时参考 git 历史）。
        # 图标本体与 `bootstrap-icons-LICENSE.txt` 都在 Qt 资源 `/icons` 段里，NavRail 优先读
        # `:/icons/<name>`；这里传入的磁盘目录只是回退。spec 与 build_release.py 同样收
        # `app/resources/icons/`，以同时满足 Bootstrap Icons（MIT）「随副本保留版权与许可
        # 声明」的义务 —— 详见 `THIRD_PARTY_LICENSES.md` 的图标一节。
        self.rail = NavRail(Path(__file__).resolve().parents[1] / "app" / "resources" / "icons")
        self.rail.set_callbacks(self._toggle_theme, self._toggle_language, self._open_about)
        self.rail.navigate_requested.connect(self._open_route)
        self._root_layout.addWidget(self.rail)

        self.stack = AnimatedStack()
        self._root_layout.addWidget(self.stack, 1)
        #: 占位页标题（label, i18n key）：语言切换时统一刷新
        self._placeholder_labels: list[tuple[QLabel, str]] = []

        self.voice_page = VoiceBatchPage(FakeTtsBackend())
        # 车组/无线电/Bank 三个功能页嵌入文件复制宿主页（同页模块切换），不再入主栈
        self.crew_page = CrewPage()
        self.radio_page = RadioPage()
        self.bank_page = BankPage()
        self.copy_page = FileCopyPage(self.crew_page, self.radio_page, self.bank_page)
        self.audio_page = AudioProcessingPage()
        self.separate_page = SeparationPage()
        self.api_page = ApiChannelPage()
        self.settings_page = self._build_placeholder("nav.page.settings")
        self.fmod_page = FmodConsolePage()
        self.experimental_page = self._build_placeholder("nav.page.experimental")
        self.video_clip_page = VideoClipPage()
        self.pages = (
            self.voice_page,
            self.copy_page,
            self.audio_page,
            self.separate_page,
            self.api_page,
            self.settings_page,
            self.fmod_page,
            self.experimental_page,
            self.video_clip_page,
        )
        for page in self.pages:
            self.stack.addWidget(page)
        # 启动落地页 = 视频裁剪（2026-10-05 用户指定）；TTS 工作台改为
        # 首次进入时装配后端（与工作台内切换模型同一链路，懒装配）
        self.stack.setCurrentIndex(self.VIDEO_INDEX)

        self._route_indexes = {
            "video": self.VIDEO_INDEX,
            "copy": self.COPY_INDEX,
            "audio": self.AUDIO_INDEX,
            "separate": self.SEPARATE_INDEX,
            "api": self.API_INDEX,
            "settings": self.SETTINGS_INDEX,
            "fmod": self.FMOD_INDEX,
            "experimental": self.EXPERIMENTAL_INDEX,
        }
        # 工作台内切换推理模型：复用进入工作台的异步装配链路
        self.voice_page.model_switch_requested.connect(self._open_voice_batch)
        # 顶级模块（文件复制/语音/语音处理/人声分离/API 渠道/视频裁剪）：导航
        # 由左侧图标栏承担，返回按钮不再展示；嵌入的 crew/radio/bank 已在
        # FileCopyPage 构造时隐藏
        self.copy_page.back_button.setVisible(False)
        self.voice_page.back_button.setVisible(False)
        self.audio_page.back_button.setVisible(False)
        self.separate_page.back_button.setVisible(False)
        self.api_page.back_button.setVisible(False)
        # 视频裁剪页漏在隐藏清单外：返回钮可见但 back_requested
        # 从未接线，点了毫无反应的死按钮（2026-10-05 用户反馈，图2 风格对齐）
        self.video_clip_page.back_button.setVisible(False)
        self.fmod_page.back_button.setVisible(False)  # FMOD 控制台同为导航页
        self.stack.transition_started.connect(lambda _index: self._set_navigation_enabled(False))
        self.stack.transition_finished.connect(lambda _index: self._set_navigation_enabled(True))
        self.crew_page.close_ready.connect(self._close_after_active_task)
        self.radio_page.close_ready.connect(self._close_after_active_task)
        self.bank_page.close_ready.connect(self._close_after_active_task)
        self.audio_page.close_ready.connect(self._close_after_active_task)
        self.separate_page.close_ready.connect(self._close_after_active_task)
        self.voice_page.close_ready.connect(self._close_after_active_task)
        # R2 候选流：分离页切点候选 → 裁剪页同名素材挂载，应用仍由用户确认
        self.separate_page.candidates_ready.connect(
            self._apply_separation_candidates)
        self._allow_close = False
        self._voice_service: object | None = None
        #: 装配令牌：每次选择模型自增，用于丢弃过期的工作线程结果
        self._backend_token = 0
        #: 上次所选推理模型：左侧栏再次进入工作台时保持用户的选择
        self._preferred_model_key = VoiceBatchPage.MODEL_GPT
        #: 在途装配的中止信号：closeEvent 置位，让探活等待立即退出并收掉子进程（深查 P2-1）
        self._backend_abort = threading.Event()
        self.backend_ready.connect(self._on_backend_ready)
        self.backend_failed.connect(self._on_backend_failed)
        on_language_changed(self._retranslate)
        # 启动即进入默认模块（视频裁剪）；TTS 后端不再启动即装配——
        # 首次点左侧"TTS 生成"时经 _open_route("tts") 走同一装配链路
        self._open_route("video")
        # 后台预热 TTS-Hub（首次导入+打开库可达数十秒；预热后用户点 API 渠道即时可用）
        if os.environ.get("WT_HUB_WARMUP", "1") != "0" and hub_available():
            from app.services import tts_hub_inproc

            tts_hub_inproc.warm_up_async()

    def _retranslate(self, _language: str | None = None) -> None:
        self.rail.retranslate()
        for label, key in self._placeholder_labels:
            label.setText(tr(key))
        for page in self.pages:
            retranslate = getattr(page, "retranslate", None)
            if callable(retranslate):
                retranslate()

    def _toggle_theme(self) -> None:
        """昼/夜热切换：set_mode 立即重建全局 QSS 与调色板，无需重启。"""

        theme.set_mode("light" if theme.current_mode() == "dark" else "dark")

    def _toggle_language(self) -> None:
        set_language("en" if current_language() == "zh" else "zh")

    def _open_about(self) -> None:
        AboutDialog(self).exec()

    def _build_placeholder(self, label_key: str) -> QWidget:
        """占位页（界面规划中）；标题随语言切换经 _placeholder_labels 刷新。"""

        page = QWidget()
        page.setObjectName("pageRoot")
        layout = QVBoxLayout(page)
        layout.addStretch(1)
        label = QLabel(tr(label_key))
        label.setObjectName("placeholderTitle")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        layout.addStretch(2)
        self._placeholder_labels.append((label, label_key))
        return page

    def _open_route(self, route_key: str) -> None:
        """左侧图标栏路由：tts 进入工作台（异步装配），其余直接切页。"""

        if route_key == "tts":
            self.rail.set_checked("tts")
            self._open_voice_batch(self._preferred_model_key)
            return
        index = self._route_indexes.get(route_key)
        if index is not None:
            self.rail.set_checked(route_key)
            self.stack.transition_to(index, TransitionDirection.FORWARD)

    def _apply_separation_candidates(self, source_stem: str,
                                     ranges: list) -> None:
        """分离页切点候选 → 裁剪页：同名素材在位则跳转挂载，否则回报。"""

        applied = self.video_clip_page.apply_external_proposals(
            source_stem, ranges)
        self.separate_page.notify_candidates_applied(source_stem, applied)
        if applied:
            self._open_route("video")

    def _backend_for(self, model_key: str, abort_event: threading.Event | None = None) -> tuple[TtsBackend, object | None]:
        """按模型键装配推理后端；服务未就绪时回落到演示后端（界面会提示演示模式）。

        内部会做**阻塞式探活**，CosyVoice 3 会拉起子进程并轮询到就绪（上限约
        180s），GSV 服务同理（上限 300s，CPU 冷启动实测 ~168s），
        因此只允许在工作线程调用。返回值第二项是需要托管的服务句柄（无则 None）。
        `abort_event` 置位会中止在途启动并停掉子进程（应用退出收尾）。
        """

        if model_key in (VoiceBatchPage.MODEL_GPT, VoiceBatchPage.MODEL_GPT_CPUFAST):
            # GSV 兼容 P2+：地址来自服务注册表——官方包入口用 active 档，
            # CPUFast 入口固定 cpufast 档（原生 CPU torch 独立克隆仓）。
            # 档可携带启动命令——探活失败且有命令 → 应用内自动拉起
            # （SubprocessTtsService 托管，过期令牌/退出统一回收）；
            # 无命令 → 外部服务语义（只探活）。
            if model_key == VoiceBatchPage.MODEL_GPT_CPUFAST:
                profile = gsv_services.profile_by_id(gsv_services.CPUFAST_PROFILE_ID)
            else:
                profile = gsv_services.active_profile()
            base_url = profile.base_url
            backend = GptSovitsBackend(base_url)
            if backend.is_available():
                # GSV 兼容 P1：服务活着才探能力（openapi.json，失败降级基线）；
                # 本工作线程内执行，GUI 不阻塞
                backend.capabilities = probe_capabilities(base_url)
                return backend, None
            command_text = profile.command.strip()
            if command_text:
                service = SubprocessTtsService(
                    gsv_services.split_command(command_text),
                    cwd=Path(profile.cwd) if profile.cwd.strip() else None,
                    probe=lambda url=base_url: GptSovitsBackend(url).is_available(),
                    # GSV CPU 真机 E2E（2026-10-09）：v5 整合包冷启动
                    # 实测 167.7s，180s 余量只剩 ~7%，机器稍有负载即超时回落演示模式；
                    # 上调到 300s（CosyVoice 3 的 180s 不动）。
                    startup_timeout_s=300.0,  # GSV 冷启动加载模型较慢（CPU 实测 ~168s）
                )
                if service.start(abort_event=abort_event):
                    backend.capabilities = probe_capabilities(base_url)
                    return backend, service
        elif model_key == "tts_cosyvoice":
            handle = start_cosyvoice3_service(Path(__file__).resolve().parents[1], abort_event=abort_event)
            if handle is not None:
                return handle.backend, handle.service
        elif model_key.startswith("api:"):
            # API 渠道（TTS-Hub）：优先进程内库（无端口）；hub 项目根缺失时退回
            # 渠道配置的外部 serve 地址（HTTP），再退演示模式
            channel = api_channels.get_channel(model_key.split(":", 1)[1])
            if channel is not None and channel.enabled and channel.kind == api_channels.KIND_TTS_HUB:
                if hub_available():
                    backend = TtsHubInprocBackend(
                        vendor=channel.vendor,
                        voice=channel.voice,
                        model=channel.model,
                        fallback=channel.fallback,
                    )
                    if backend.is_available():
                        return backend, None
                backend = TtsHubBackend(
                    channel.base_url,
                    vendor=channel.vendor,
                    voice=channel.voice,
                    model=channel.model,
                    timeout_s=channel.timeout_s,
                )
                if backend.is_available():
                    return backend, None
        return FakeTtsBackend(), None

    def _open_voice_batch(self, model_key: str) -> None:
        """立即切页；后端装配交给工作线程（探活/拉起服务会阻塞，不能在 GUI 线程做）。"""

        self._preferred_model_key = model_key
        self._backend_token += 1
        token = self._backend_token
        abort = threading.Event()
        self._backend_abort = abort
        self.voice_page.set_model_kind(model_key)
        self.voice_page.set_backend_pending()
        self.stack.transition_to(self.VOICE_INDEX, TransitionDirection.FORWARD)
        threading.Thread(
            target=self._prepare_backend,
            args=(token, model_key, abort),
            name="tts-backend",
            daemon=True,
        ).start()

    def _prepare_backend(self, token: int, model_key: str, abort_event: threading.Event) -> None:
        """工作线程：装配后端并回报。**不得在此触碰任何界面对象。**"""

        try:
            backend, service = self._backend_for(model_key, abort_event)
        except Exception as error:  # 工作线程边界：统一转为失败信号
            LOGGER.exception("TTS backend preparation failed: %s", model_key)
            self.backend_failed.emit(token, str(error))
            return
        if token != self._backend_token:
            # 已过期（用户改选模型或窗口已关闭）：此结果不会被接管，就地收掉刚拉起的服务，
            # 否则关窗后事件循环不再排空信号，子进程就漏在外面了。
            self._stop_service(service)
            return
        self.backend_ready.emit(token, (backend, service))

    def _on_backend_ready(self, token: int, payload: object) -> None:
        backend, service = cast("tuple[TtsBackend, object | None]", payload)
        if token != self._backend_token:
            self._stop_service(service)
            return
        self._voice_service = service
        self.voice_page.set_backend(backend)

    def _on_backend_failed(self, token: int, _message: str) -> None:
        if token != self._backend_token:
            return
        self.voice_page.set_backend(FakeTtsBackend())

    def _stop_service(self, service: object) -> None:
        if service is not None and hasattr(service, "stop"):
            service.stop()

    def _set_navigation_enabled(self, enabled: bool) -> None:
        for page in self.pages:
            # 占位页是普通 QWidget，无该能力——用能力探测而非假设
            setter = getattr(page, "set_navigation_enabled", None)
            if callable(setter):
                setter(enabled)

    def closeEvent(self, event: QCloseEvent) -> None:
        # 作废装配令牌并中止在途装配；已拉起/在拉起的服务统一 terminate
        # （深查 P2-1：装配窗口期内句柄尚未交回，仅靠 _voice_service 会漏掉它们）
        self._backend_token += 1
        self._backend_abort.set()
        self._stop_service(self._voice_service)
        self._voice_service = None
        SubprocessTtsService.stop_all_registered()
        # 进程内 TTS-Hub（库实例；管理台走 hub:// 协议无监听）随应用退出收尾
        from app.services import tts_hub_inproc

        tts_hub_inproc.close_hub()
        if not self._allow_close:
            active_copy_page = next(
                (
                    page
                    for page in (self.crew_page, self.radio_page, self.bank_page, self.audio_page, self.voice_page)
                    if page.is_busy
                ),
                None,
            )
            if active_copy_page is not None and not active_copy_page.request_safe_close():
                event.ignore()
                return
        self.stack.finish_transition()
        # 窗口关闭即退订语言广播：残留回调会在窗口销毁后打到已删除的控件上（§4.4）
        off_language_changed(self._retranslate)
        super().closeEvent(event)

    def _close_after_active_task(self) -> None:
        self._allow_close = True
        self.close()
