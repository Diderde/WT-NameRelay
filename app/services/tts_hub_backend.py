# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""TTS-Hub 渠道后端：对接维护者自研 TTS-Hub 的 HTTP 服务（``tts-hub serve``）。

契约（TTS-Hub P2）：``POST /api/tts`` JSON ``{"text", "voice", "vendor"?, "model"?}``
→ 音频字节（格式随厂商，通常 mp3）；``GET /api/health`` 探活；错误统一
``{"error": {"kind", "vendor", "code", "status", "message"}}``（message 已被
``HttpWavBackend`` 的错误详情提取器读取）。

本应用产出必须是 WAV：非 WAV 响应经**自带 ffmpeg** 转码（ffmpeg 缺失时给出可读
降级错误，不静默失败）。密钥全部在 TTS-Hub 服务侧，本后端只携带连接信息。
"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from app.audio.ffmpeg_service import FfmpegLocator
from app.services.tts_runner import (
    DEFAULT_TIMEOUT_S,
    WAV_MAGIC,
    HttpWavBackend,
    TtsError,
    TtsRequest,
)

#: TTS-Hub 的探活与合成端点
HEALTH_ENDPOINT = "/api/health"
TTS_ENDPOINT = "/api/tts"


def _sniff_audio_suffix(audio: bytes) -> str:
    """按字节签名猜容器后缀（只为 ffmpeg 提示输入格式，猜错由 ffmpeg 兜底重试）。"""

    if audio.startswith(b"ID3") or audio[:2] == b"\xff\xfb" or audio[:2] == b"\xff\xf3":
        return ".mp3"
    if audio.startswith(b"OggS"):
        return ".ogg"
    if audio.startswith(b"fLaC"):
        return ".flac"
    if audio[4:8] == b"ftyp":
        return ".m4a"
    return ".bin"


def transcode_bytes_to_wav(audio: bytes) -> bytes:
    """任意音频字节 → WAV（pcm_s16le，经自带 ffmpeg）；缺失/失败抛 :class:`TtsError`。"""

    try:
        ffmpeg = FfmpegLocator.executable("ffmpeg")
    except FileNotFoundError as error:
        raise TtsError(
            "hub_no_ffmpeg",
            "TTS-Hub 返回的是非 WAV 音频，本机未找到自带 ffmpeg，无法转码（"
            "可在 TTS-Hub 侧配置 WAV 输出，或补齐 app/resources/ffmpeg）。",
        ) from error
    with tempfile.TemporaryDirectory(prefix="hub-transcode-") as tmp:
        source = Path(tmp) / f"input{_sniff_audio_suffix(audio)}"
        output = Path(tmp) / "output.wav"
        source.write_bytes(audio)
        result = subprocess.run(
            [
                str(ffmpeg),
                "-v", "error",
                "-y",
                "-i", str(source),
                "-vn",
                "-acodec", "pcm_s16le",
                str(output),
            ],
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
            timeout=120.0,
        )
        if result.returncode != 0 or not output.is_file():
            detail = (result.stderr or "").strip().splitlines()[-1] if (result.stderr or "").strip() else "未知原因"
            raise TtsError("hub_transcode_failed", f"TTS-Hub 音频转码失败：{detail}")
        return output.read_bytes()


class TtsHubBackend(HttpWavBackend):
    """以 TTS-Hub 服务为一个 API 渠道的合成后端。"""

    name = "tts-hub"

    def __init__(
        self,
        base_url: str,
        *,
        vendor: str = "",
        voice: str = "",
        model: str = "",
        timeout_s: float = DEFAULT_TIMEOUT_S,
        name: str | None = None,
        transcoder: Callable[[bytes, Path], bytes] | None = None,
    ) -> None:
        super().__init__(
            base_url,
            endpoint=TTS_ENDPOINT,
            probe_endpoint=HEALTH_ENDPOINT,
            timeout_s=timeout_s,
            name=name,
        )
        self.vendor = vendor.strip()
        self.default_voice = voice.strip()
        self.model = model.strip()
        self._transcoder = transcoder or transcode_bytes_to_wav

    def build_payload(self, request: TtsRequest) -> dict[str, object]:
        """hub 契约：text + voice 必填；行内「音色」列填逻辑音色名，留空或填参考音频
        路径（.wav/.mp3/.flac，本地渠道语义）时用渠道默认音色。"""

        voice = request.voice.strip()
        if voice.lower().endswith((".wav", ".mp3", ".flac", ".ogg")):
            voice = ""
        payload: dict[str, object] = {
            "text": request.text,
            "voice": voice or self.default_voice,
        }
        if self.vendor:
            payload["vendor"] = self.vendor
        if self.model:
            payload["model"] = self.model
        return payload

    def _normalize_audio(self, audio: bytes) -> bytes:
        if audio.startswith(WAV_MAGIC):
            return audio
        return self._transcoder(audio)
