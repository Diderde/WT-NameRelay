# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""TTS-Hub 管理台的自定义协议：``hub://console/...`` → 进程内 ASGI 分发。

**零监听端口**：WebEngine 里管理台页面与其 ``fetch`` 的所有 ``/api/*`` 请求都被
:class:`HubSchemeHandler` 拦截，直接在进程内喂给 TTS-Hub 的 FastAPI 应用（ASGI 调用），
再以 ``job.reply`` 回填响应——不创建 socket、不开端口、无独立服务进程（安全软件无监听
面可警告）。管理台本体（index.html + console.js/css）也从 hub 项目的 ``server/web/``
目录**直接读文件**，不经过任何传输层。

Qt 约束：``QWebEngineUrlScheme.registerScheme`` 必须在首个 ``QApplication`` 创建之前
调用——本模块在导入期（即 ``app.main_window``/``app.pages`` 导入链上，先于 ``main()``
创建应用）完成注册，且幂等。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWebEngineCore import (
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)

from app.services import tts_hub_inproc

SCHEME_NAME = b"hub"
CONSOLE_HOST = b"console"

_REGISTERED = False


def register_hub_scheme() -> None:
    """注册 ``hub://`` 协议（幂等；必须在首个 QApplication 之前调用）。"""

    global _REGISTERED
    if _REGISTERED:
        return
    scheme = QWebEngineUrlScheme(SCHEME_NAME)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.LocalScheme
        | QWebEngineUrlScheme.Flag.LocalAccessAllowed
        | QWebEngineUrlScheme.Flag.FetchApiAllowed
        | QWebEngineUrlScheme.Flag.CorsEnabled
    )
    QWebEngineUrlScheme.registerScheme(scheme)
    _REGISTERED = True


class HubSchemeHandler(QWebEngineUrlSchemeHandler):
    """把 ``hub://console/<path>`` 请求分发到进程内 hub 的 ASGI 应用。

    ``asgi_provider`` 返回 ASGI 可调用对象（默认：进程内 hub 的 FastAPI 应用）；
    测试可注入假应用。分发在 WebEngine 的 IO 线程内以独立事件循环同步执行——
    全部为本机进程内调用，无网络。
    """

    def __init__(self, asgi_provider: Callable[[], Any], parent: Any | None = None) -> None:

        super().__init__(parent)
        self._asgi_provider = asgi_provider

    # —— ASGI 分发 ——
    def requestStarted(self, job: Any) -> None:
        method = bytes(job.requestMethod()).decode("ascii", "replace").upper()
        url = job.requestUrl()
        path = url.path()
        query = url.query().encode("utf-8")
        body = self._read_body(job)
        headers = self._read_headers(job)
        try:
            _status, response_headers, payload = self._dispatch_asgi(method, path, query, headers, body)
        except Exception as error:  # noqa: BLE001  分发失败 → 500 JSON（管理台 banner 可读）
            payload = json.dumps(
                {"error": {"kind": "scheme", "vendor": None, "code": "inproc", "status": 500, "message": str(error)}}
            ).encode("utf-8")
            response_headers = [(b"content-type", b"application/json")]
        content_type = "application/octet-stream"
        for key, value in response_headers:
            if key.decode("latin-1").lower() == "content-type":
                content_type = value.decode("latin-1")
        # reply 的第二参是 QIODevice 而非 bytes；QBuffer 挂在 job 上保证读到时仍存活
        device = QBuffer(parent=job)
        device.setData(payload)
        device.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(content_type.encode("ascii"), device)

    def _read_body(self, job: Any) -> bytes:
        try:
            device: QIODevice = job.requestBody()
            if device is None:
                return b""
            if not device.isOpen():
                device.open(QIODevice.OpenModeFlag.ReadOnly)
            return bytes(device.readAll())
        except Exception:  # noqa: BLE001  读不出请求体时按空体处理（GET 不受影响）
            return b""

    def _read_headers(self, job: Any) -> list[tuple[bytes, bytes]]:
        pairs: list[tuple[bytes, bytes]] = []
        try:
            raw_headers = job.requestHeaders()
            items = raw_headers.items() if hasattr(raw_headers, "items") else list(raw_headers)
            for key, value in items:
                pairs.append((str(key).encode("latin-1"), str(value).encode("latin-1")))
        except Exception:  # noqa: BLE001  头部缺失不致命（Content-Type 由我们补默认）
            pairs = []
        if not any(key == b"content-type" for key, _ in pairs):
            pairs.append((b"content-type", b"application/json"))
        # hub 服务端有防 DNS rebinding 校验（Host 必须是本机回环）——
        # 分发发生在同一进程内，显式注入回环 Host 即如实表述请求来源
        pairs = [(key, value) for key, value in pairs if key != b"host"]
        pairs.append((b"host", b"127.0.0.1"))
        return pairs

    def _dispatch_asgi(
        self,
        method: str,
        path: str,
        query: bytes,
        headers: list[tuple[bytes, bytes]],
        body: bytes,
    ) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
        asgi_app = self._asgi_provider()
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "hub",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": query,
            "root": "",
            "server": ("127.0.0.1", 0),
            "client": ("127.0.0.1", 0),
            "headers": headers,
        }
        status = 500
        response_headers: list[tuple[bytes, bytes]] = []
        chunks: list[bytes] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(event: dict[str, Any]) -> None:
            nonlocal status, response_headers
            if event["type"] == "http.response.start":
                status = event["status"]
                response_headers = [(k, v) for k, v in event["headers"]]
            elif event["type"] == "http.response.body":
                chunks.append(event.get("body", b""))

        async def runner() -> None:
            await asgi_app(scope, receive, send)

        asyncio.run(runner())
        payload = self._postprocess(path, status, response_headers, chunks)
        return status, response_headers, payload

    def _postprocess(
        self,
        path: str,
        status: int,
        response_headers: list[tuple[bytes, bytes]],
        chunks: list[bytes],
    ) -> bytes:
        """health 端点如实化：hub 配置里写的是 providers.yaml 默认端口（如 8000），
        而进程内集成不监听任何端口——顶栏展示按实况覆盖，避免误导为仍有服务在 8000。"""

        payload = b"".join(chunks)
        if path != "/api/health" or status != 200:
            return payload
        try:
            data = json.loads(payload.decode("utf-8"))
            data["host"] = "进程内集成"
            data["port"] = "无监听端口"
            return json.dumps(data, ensure_ascii=False).encode("utf-8")
        except (ValueError, AttributeError):
            return payload


def default_asgi_provider() -> Any:
    """默认 ASGI 应用提供者：进程内 hub 的 FastAPI 应用（含管理台路由与 /api/*）。"""

    from tts_hub.server.app import create_app

    return create_app(hub=tts_hub_inproc.ensure_hub())
