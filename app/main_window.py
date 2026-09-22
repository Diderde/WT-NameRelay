from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import cast

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QStackedLayout, QWidget

from app.branding import WINDOW_TITLE
from app.i18n import on_language_changed
from app.pages import (
    AudioProcessingPage,
    BankPage,
    CrewPage,
    FileCopyPage,
    HomePage,
    RadioPage,
    TtsModelPage,
    VoiceBatchPage,
)

# 副作用导入：注册内嵌名称库与许可文档等 Qt 资源，不直接引用其符号。
from app.resources import resources_rc as _resources_rc  # noqa: F401
from app.services.tts_runner import (
    FakeTtsBackend,
    GptSovitsBackend,
    TtsBackend,
)
from app.services.voice_service_launcher import start_cosyvoice3_service
from app.widgets.animated_stack import AnimatedStack, TransitionDirection
from app.widgets.water_backdrop import WaterBackdrop

LOGGER = logging.getLogger("wt_name_relay")


class MainWindow(QMainWindow):
    """Application shell responsible only for page routing."""

    #: 后端装配完成（工作线程 → GUI 线程）：(token, (backend, service))
    backend_ready = Signal(int, object)
    #: 后端装配异常（工作线程 → GUI 线程）：(token, message)
    backend_failed = Signal(int, str)

    HOME_INDEX = 0
    COPY_INDEX = 1
    CREW_INDEX = 2
    RADIO_INDEX = 3
    BANK_INDEX = 4
    AUDIO_INDEX = 5
    TTS_INDEX = 6
    VOICE_INDEX = 7

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(820, 620)
        self.resize(1100, 700)

        root = QWidget()
        root.setObjectName("appRoot")
        # StackAll：底层水纹背板常驻可见，上层页面以透明容器叠放其上
        self._root_layout = QStackedLayout(root)
        self._root_layout.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(root)

        self.water_backdrop = WaterBackdrop()
        self._root_layout.addWidget(self.water_backdrop)

        self.stack = AnimatedStack()
        self._root_layout.addWidget(self.stack)
        self.stack.raise_()

        self.home_page = HomePage()
        self.copy_page = FileCopyPage()
        self.crew_page = CrewPage()
        self.radio_page = RadioPage()
        self.bank_page = BankPage()
        self.audio_page = AudioProcessingPage()
        self.tts_page = TtsModelPage()
        self.voice_page = VoiceBatchPage(FakeTtsBackend())
        self.pages = (
            self.home_page,
            self.copy_page,
            self.crew_page,
            self.radio_page,
            self.bank_page,
            self.audio_page,
            self.tts_page,
            self.voice_page,
        )
        for page in self.pages:
            self.stack.addWidget(page)
        self.stack.setCurrentIndex(self.HOME_INDEX)

        self._route_indexes = {
            "copy": self.COPY_INDEX,
            "audio": self.AUDIO_INDEX,
            "tts": self.TTS_INDEX,
        }
        self._copy_routes = {
            "crew": self.CREW_INDEX,
            "radio": self.RADIO_INDEX,
            "bank": self.BANK_INDEX,
        }
        self.home_page.navigate_requested.connect(self._open_tool_page)
        self.copy_page.navigate_requested.connect(self._open_copy_page)
        self.copy_page.back_requested.connect(self._return_home)
        for page in (self.crew_page, self.radio_page, self.bank_page):
            page.back_requested.connect(self._return_to_copy)
        self.audio_page.back_requested.connect(self._return_home)
        self.tts_page.back_requested.connect(self._return_home)
        self.tts_page.navigate_requested.connect(self._open_voice_batch)
        self.voice_page.back_requested.connect(self._return_home)
        self.stack.transition_started.connect(lambda _index: self._set_navigation_enabled(False))
        self.stack.transition_finished.connect(lambda _index: self._set_navigation_enabled(True))
        self.crew_page.close_ready.connect(self._close_after_active_task)
        self.radio_page.close_ready.connect(self._close_after_active_task)
        self.bank_page.close_ready.connect(self._close_after_active_task)
        self.audio_page.close_ready.connect(self._close_after_active_task)
        self.voice_page.close_ready.connect(self._close_after_active_task)
        self._allow_close = False
        self._voice_service: object | None = None
        #: 装配令牌：每次选择模型自增，用于丢弃过期的工作线程结果
        self._backend_token = 0
        self.backend_ready.connect(self._on_backend_ready)
        self.backend_failed.connect(self._on_backend_failed)
        on_language_changed(self._retranslate)

    def _retranslate(self, _language: str | None = None) -> None:
        for page in self.pages:
            retranslate = getattr(page, "retranslate", None)
            if callable(retranslate):
                retranslate()

    def _open_tool_page(self, route_key: str) -> None:
        target_index = self._route_indexes.get(route_key)
        if target_index is not None:
            self.stack.transition_to(target_index, TransitionDirection.FORWARD)

    def _backend_for(self, model_key: str) -> tuple[TtsBackend, object | None]:
        """按模型键装配推理后端；服务未就绪时回落到演示后端（界面会提示演示模式）。

        内部会做**阻塞式探活**，CosyVoice 3 还会拉起子进程并轮询到就绪（上限约 180s），
        因此只允许在工作线程调用。返回值第二项是需要托管的服务句柄（无则 None）。
        """

        if model_key == "tts_gpt_sovits":
            backend = GptSovitsBackend(os.environ.get("WT_GPT_SOVITS_URL", "http://127.0.0.1:9880"))
            if backend.is_available():
                return backend, None
        elif model_key == "tts_cosyvoice":
            handle = start_cosyvoice3_service(Path(__file__).resolve().parents[1])
            if handle is not None:
                return handle.backend, handle.service
        return FakeTtsBackend(), None

    def _open_voice_batch(self, model_key: str) -> None:
        """立即切页；后端装配交给工作线程（探活/拉起服务会阻塞，不能在 GUI 线程做）。"""

        self._backend_token += 1
        token = self._backend_token
        self.voice_page.set_model_kind(model_key)
        self.voice_page.set_backend_pending()
        self.stack.transition_to(self.VOICE_INDEX, TransitionDirection.FORWARD)
        threading.Thread(
            target=self._prepare_backend,
            args=(token, model_key),
            name="tts-backend",
            daemon=True,
        ).start()

    def _prepare_backend(self, token: int, model_key: str) -> None:
        """工作线程：装配后端并回报。**不得在此触碰任何界面对象。**"""

        try:
            backend, service = self._backend_for(model_key)
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

    def _open_copy_page(self, route_key: str) -> None:
        target_index = self._copy_routes.get(route_key)
        if target_index is not None:
            self.stack.transition_to(target_index, TransitionDirection.FORWARD)

    def _return_home(self) -> None:
        current_page = self.stack.currentWidget()
        if current_page in (self.copy_page, self.audio_page, self.tts_page, self.voice_page) and not current_page.can_navigate_away():
            return
        self.stack.transition_to(self.HOME_INDEX, TransitionDirection.BACKWARD)

    def _return_to_copy(self) -> None:
        current_page = self.stack.currentWidget()
        if current_page in (self.crew_page, self.radio_page, self.bank_page) and not current_page.can_navigate_away():
            return
        self.stack.transition_to(self.COPY_INDEX, TransitionDirection.BACKWARD)

    def _set_navigation_enabled(self, enabled: bool) -> None:
        for page in self.pages:
            page.set_navigation_enabled(enabled)

    def closeEvent(self, event: QCloseEvent) -> None:
        # 作废装配令牌：在途的工作线程结果不再被应用（它拉起的服务由该线程自行收掉）
        self._backend_token += 1
        self._stop_service(self._voice_service)
        self._voice_service = None
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
        super().closeEvent(event)

    def _close_after_active_task(self) -> None:
        self._allow_close = True
        self.close()
