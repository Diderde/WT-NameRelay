# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""TTS-Hub 进程内合成后端：直接调用 hub 库的 ``speak``（无 HTTP、无端口）。

与 :class:`app.services.tts_hub_backend.TtsHubBackend`（HTTP 客户端形态）对应：
本后端跑在应用进程内（见 :mod:`app.services.tts_hub_inproc`），合成走
``hub.speak(text, voice=..., vendor=..., model=...)``，产物默认 mp3，经自带
ffmpeg 转码为 WAV。hub 的四类归一错误（AuthError=无密钥 / QuotaError=无余额 /
ReviewRejectedError=审核 / ProviderError=厂商）转成带可读文案的 :class:`TtsError`。
"""

from __future__ import annotations

import threading

from app.services import tts_hub_inproc
from app.services.tts_hub_backend import transcode_bytes_to_wav
from app.services.tts_runner import (
    DEFAULT_TIMEOUT_S,
    TtsError,
    TtsRequest,
    TtsResult,
    sha256_file,
    wav_duration_ms,
)

#: hub 归一错误 → 用户可读前缀（错误码保持 kind，落进 .vt.state 可检索）
_ERROR_PREFIX = {
    "auth": "无密钥或密钥无效",
    "quota": "余额不足或配额耗尽",
    "review": "内容未过审核",
    "provider": "厂商返回错误",
}


class TtsHubInprocBackend:
    """以进程内 TTS-Hub 库为一个 API 渠道的合成后端。"""

    name = "tts-hub-inproc"

    def __init__(
        self,
        *,
        vendor: str = "",
        voice: str = "",
        model: str = "",
        fallback: bool = False,
        name: str | None = None,
        transcoder=None,
    ) -> None:
        self.vendor = vendor.strip()
        self.default_voice = voice.strip()
        self.model = model.strip()
        self.fallback = fallback
        self._transcoder = transcoder or transcode_bytes_to_wav
        if name:
            self.name = name

    def is_available(self) -> bool:
        try:
            tts_hub_inproc.ensure_hub()
            return True
        except RuntimeError:
            return False

    def synthesize(
        self,
        request: TtsRequest,
        *,
        cancel_event: threading.Event | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> TtsResult:
        if cancel_event is not None and cancel_event.is_set():
            raise TtsError("cancelled", "已取消")
        try:
            hub = tts_hub_inproc.ensure_hub()
        except RuntimeError as error:
            raise TtsError("hub_unavailable", str(error)) from error
        voice = request.voice.strip()
        if voice.lower().endswith((".wav", ".mp3", ".flac", ".ogg")):
            # 行内「音色」列是参考音频路径（本地渠道语义）：云端渠道回退渠道默认音色
            voice = ""
        try:
            if self.fallback:
                result = hub.speak_with_fallback(
                    request.text,
                    voice=voice or self.default_voice,
                    vendor=self.vendor or None,
                    model=self.model or None,
                )
            else:
                result = hub.speak(
                    request.text,
                    voice=voice or self.default_voice,
                    vendor=self.vendor or None,
                    model=self.model or None,
                )
        except Exception as error:
            raise self._to_tts_error(error) from error
        audio = result.audio or b""
        if not audio:
            raise TtsError("hub_empty_audio", "TTS-Hub 返回了空音频")
        audio = audio if audio.startswith(b"RIFF") else self._transcoder(audio)
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_path.write_bytes(audio)
        return TtsResult(
            row_id=request.row_id,
            output_path=request.output_path,
            output_hash=sha256_file(request.output_path),
            duration_ms=wav_duration_ms(request.output_path),
            backend=self.name,
        )

    def _to_tts_error(self, error: Exception) -> TtsError:
        kind = getattr(error, "kind", "") or type(error).__name__
        prefix = _ERROR_PREFIX.get(str(kind), "TTS-Hub 错误")
        message = str(error) or type(error).__name__
        return TtsError(f"hub_{kind}", f"{prefix}：{message}")
