# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""TTS 运行时（M1）：串行队列 + 后端抽象 + 产物校验。

设计要点（依据后端契约的实测结论）：

- 真实推理在**外部服务进程**内完成（GPT-SoVITS ``api_v2.py`` / CosyVoice GGUF runner），
  本模块只做 HTTP 客户端与落盘，保证推理崩溃/超时不带走 UI 进程；
- **串行执行**（一次一条），避免并发挤爆 GPU；
- 每项独立失败隔离 + 超时 + 可取消；
- 产出 WAV → ``SHA-256(文件字节)`` 作为 ``output_hash``，用标准库 ``wave`` 读时长（零新增依赖）。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

DEFAULT_TIMEOUT_S = 300.0
WAV_MAGIC = b"RIFF"


# 本地推理服务必须直连：显式禁用代理链路（系统代理会拦截 127.0.0.1 并返回 404）。
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class TtsError(RuntimeError):
    """带错误码的合成失败（``code`` 会写入 ``.vt.state`` 的 ``error.code``）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(slots=True)
class TtsRequest:
    """一条合成请求（内容字段来自 VoiceRow，非内容状态由调用方维护）。"""

    row_id: str
    text: str
    output_path: Path
    language: str = "zh"
    voice: str = ""
    params: Mapping[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class TtsResult:
    """一条合成结果（可直接转换为 ArtifactState=current 所需的记录）。"""

    row_id: str
    output_path: Path
    output_hash: str
    duration_ms: int
    backend: str


@dataclass(slots=True)
class BatchOutcome:
    """一批（串行）执行的结果与错误。"""

    results: list[TtsResult] = field(default_factory=list)
    errors: list[tuple[str, TtsError]] = field(default_factory=list)

    @property
    def cancelled(self) -> bool:
        return any(error.code == "cancelled" for _, error in self.errors)


def sha256_file(path: Path) -> str:
    """文件字节的 SHA-256（64 位小写 hex）。"""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wav_duration_ms(path: Path) -> int:
    """WAV 时长（毫秒）；文件异常时返回 0（不抛错，保证状态可落盘）。"""

    try:
        with wave.open(str(path), "rb") as handle:
            frames, rate = handle.getnframes(), handle.getframerate()
    except (wave.Error, OSError):
        return 0
    if rate <= 0:
        return 0
    return round(frames * 1000 / rate)


@runtime_checkable
class TtsBackend(Protocol):
    """后端协议：实现方负责产出 WAV 文件并返回结果。"""

    name: str

    def is_available(self) -> bool:
        """后端是否可用（服务在跑 / 命令已配置）。"""

    def synthesize(
        self,
        request: TtsRequest,
        *,
        cancel_event: threading.Event | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> TtsResult:
        """合成一条；失败抛 :class:`TtsError`。"""


class FakeTtsBackend:
    """确定性假后端：写 WAV、可注入失败/延迟，驱动队列/取消/超时/失败隔离测试。"""

    name = "fake"

    def __init__(
        self,
        *,
        sample_rate: int = 8000,
        ms_per_char: int = 20,
        fail_rows: Sequence[str] = (),
        delay_s: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._sample_rate = sample_rate
        self._ms_per_char = ms_per_char
        self._fail_rows = set(fail_rows)
        self._delay_s = delay_s
        self._sleep = sleep
        self.calls: list[str] = []

    def is_available(self) -> bool:
        return True

    def synthesize(
        self,
        request: TtsRequest,
        *,
        cancel_event: threading.Event | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> TtsResult:
        self.calls.append(request.row_id)
        if self._delay_s > 0:
            waited = 0.0
            step = 0.01
            while waited < self._delay_s:
                if cancel_event is not None and cancel_event.is_set():
                    raise TtsError("cancelled", "已取消")
                if self._delay_s > timeout_s:
                    raise TtsError("backend_timeout", f"合成超时（>{timeout_s:.1f}s）")
                self._sleep(step)
                waited += step
        if request.row_id in self._fail_rows:
            raise TtsError("backend_failed", "假后端注入的失败")
        frames = max(1, int(self._sample_rate * max(1, len(request.text)) * self._ms_per_char / 1000))
        _write_silence_wav(request.output_path, sample_rate=self._sample_rate, frames=frames)
        return TtsResult(
            row_id=request.row_id,
            output_path=request.output_path,
            output_hash=sha256_file(request.output_path),
            duration_ms=wav_duration_ms(request.output_path),
            backend=self.name,
        )


def _write_silence_wav(path: Path, *, sample_rate: int, frames: int) -> None:
    """写一段静音 WAV（标准库，无依赖）。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frames)


class HttpWavBackend:
    """通用 HTTP 后端：POST JSON → WAV 字节流（服务进程外部托管）。"""

    name = "http-wav"

    def __init__(
        self,
        base_url: str,
        *,
        endpoint: str = "/synthesize",
        probe_endpoint: str = "/control",
        timeout_s: float = DEFAULT_TIMEOUT_S,
        payload_builder: Callable[[TtsRequest], dict[str, object]] | None = None,
        name: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint
        self.probe_endpoint = probe_endpoint
        self.timeout_s = timeout_s
        self._payload_builder = payload_builder or self.build_payload
        if name:
            self.name = name

    def build_payload(self, request: TtsRequest) -> dict[str, object]:
        """默认契约（与后端实际行为一致）。"""

        payload: dict[str, object] = {
            "text": request.text,
            "language": request.language,
            "voice": request.voice,
            "params": dict(request.params),
        }
        return payload

    def is_available(self) -> bool:
        """探活：**只要服务有 HTTP 应答即视为在运行**。

        GPT-SoVITS 的 ``/control`` 未带 command 时会返回 400（参数校验），
        不能把 4xx 当作"服务不可用"；只有连接层失败才判定为不可用。
        """

        if not self.base_url:
            return False
        try:
            with _NO_PROXY_OPENER.open(self.base_url + self.probe_endpoint, timeout=3.0):
                return True
        except urllib.error.HTTPError:
            return True  # 有应答（含 400/422 参数校验）即说明服务在跑
        except (urllib.error.URLError, OSError, ValueError):
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
        body = json.dumps(self._payload_builder(request), ensure_ascii=False).encode("utf-8")
        http_request = urllib.request.Request(
            self.base_url + self.endpoint,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        effective_timeout = min(timeout_s, self.timeout_s)
        try:
            with _NO_PROXY_OPENER.open(http_request, timeout=effective_timeout) as response:
                audio = response.read()
        except urllib.error.HTTPError as error:
            raise TtsError(f"backend_http_{error.code}", f"后端返回 HTTP {error.code}") from error
        except TimeoutError as error:
            raise TtsError("backend_timeout", f"合成超时（>{effective_timeout:.1f}s）") from error
        except (urllib.error.URLError, OSError) as error:
            raise TtsError("backend_unreachable", f"后端不可达：{error}") from error
        if not audio.startswith(WAV_MAGIC):
            raise TtsError("backend_bad_payload", "后端未返回 WAV 数据")
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_path.write_bytes(audio)
        return TtsResult(
            row_id=request.row_id,
            output_path=request.output_path,
            output_hash=sha256_file(request.output_path),
            duration_ms=wav_duration_ms(request.output_path),
            backend=self.name,
        )


class GptSovitsBackend(HttpWavBackend):
    """GPT-SoVITS ``api_v2.py`` 客户端（契约见 spike 报告 §二）。"""

    name = "gpt-sovits"

    def __init__(self, base_url: str, *, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        super().__init__(base_url, endpoint="/tts", probe_endpoint="/control", timeout_s=timeout_s)

    def build_payload(self, request: TtsRequest) -> dict[str, object]:
        params = dict(request.params)
        payload: dict[str, object] = {
            "text": request.text,
            "text_lang": request.language,
            "ref_audio_path": request.voice,
            "prompt_text": str(params.pop("prompt_text", "")),
            "prompt_lang": str(params.pop("prompt_lang", request.language)),
            "media_type": "wav",
            "streaming_mode": False,
        }
        payload.update(params)
        return payload

    def set_weights(self, gpt_path: str, sovits_path: str) -> tuple[bool, str]:
        """运行时热切换权重（api_v2 ``/set_gpt_weights`` / ``/set_sovits_weights``）。

        返回 (是否全部成功, 上游 message 摘要)；本机直连不走系统代理。

        **阻塞调用**：两个端点各发一次 HTTP，超时取 ``self.timeout_s``（默认 300s），
        绝不可在 GUI 线程直接调用。

        上游没有事务/回滚接口，两个端点是**先后生效**的：若 GPT 已切、SoVITS 失败，
        服务会停在"新 GPT + 旧 SoVITS"的错配状态。此时失败信息里会显式标注已半切换，
        避免调用方误以为"没生效"。
        """

        messages: list[str] = []
        applied: list[str] = []
        for endpoint, label, weights_path in (
            ("/set_gpt_weights", "GPT", gpt_path),
            ("/set_sovits_weights", "SoVITS", sovits_path),
        ):
            url = f"{self.base_url}{endpoint}?weights_path={urllib.parse.quote(weights_path)}"
            try:
                with _NO_PROXY_OPENER.open(url, timeout=self.timeout_s) as response:
                    messages.append(str(json.loads(response.read().decode("utf-8")).get("message", "")))
            except (OSError, ValueError) as error:
                detail = f"{label} 权重切换失败：{error}"
                if applied:
                    detail += f"（{'、'.join(applied)} 已生效，当前为混合权重状态，请重试或重启推理服务）"
                return False, detail
            applied.append(label)
        return True, "；".join(part for part in messages if part)


class CosyVoiceGgufBackend(HttpWavBackend):
    """CosyVoice 3 GGUF 外部 runner 客户端（契约见 spike 报告 §三）。"""

    name = "cosyvoice3-gguf"

    def __init__(self, base_url: str, *, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        super().__init__(base_url, endpoint="/synthesize", probe_endpoint="/health", timeout_s=timeout_s)


class SubprocessTtsService:
    """外部推理服务的子进程托管（启动 / 探活 / 停止）。

    ``command`` 为空表示"由用户自行启动服务"，此时只做探活。
    """

    def __init__(
        self,
        command: Sequence[str] = (),
        *,
        cwd: Path | None = None,
        probe: Callable[[], bool] | None = None,
        startup_timeout_s: float = 120.0,
        poll_interval_s: float = 0.5,
    ) -> None:
        self._command = list(command)
        self._cwd = cwd
        self._probe = probe
        self._startup_timeout_s = startup_timeout_s
        self._poll_interval_s = poll_interval_s
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def configured(self) -> bool:
        return bool(self._command)

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> bool:
        """启动服务并等待探活成功；失败返回 False（不抛错，交给调用方降级）。"""

        if self.running:
            return True
        if not self._command:
            return self._probe is not None and self._probe()
        try:
            self._process = subprocess.Popen(  # 命令来自本机配置，非用户输入拼接
                self._command,
                cwd=str(self._cwd) if self._cwd is not None else None,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            self._process = None
            return False
        if self._probe is None:
            return True
        deadline = time.monotonic() + self._startup_timeout_s
        while time.monotonic() < deadline:
            if self._probe():
                return True
            if not self.running:
                return False
            time.sleep(self._poll_interval_s)
        return False

    def stop(self, *, timeout_s: float = 10.0) -> None:
        process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            process.kill()


class SerialTtsRunner:
    """串行执行器：一次一条，逐项失败隔离；调用方负责放在工作线程里（勿在 UI 线程跑）。"""

    def __init__(self, backend: TtsBackend, *, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self.backend = backend
        self.timeout_s = timeout_s

    @property
    def backend_name(self) -> str:
        return getattr(self.backend, "name", type(self.backend).__name__)

    def run_batch(
        self,
        requests: Sequence[TtsRequest],
        *,
        cancel_event: threading.Event | None = None,
        on_started: Callable[[TtsRequest], None] | None = None,
        on_finished: Callable[[TtsResult], None] | None = None,
        on_failed: Callable[[str, TtsError], None] | None = None,
    ) -> BatchOutcome:
        """按顺序执行；单项失败不影响后续（除取消外）。"""

        outcome = BatchOutcome()
        for index, request in enumerate(requests):
            if cancel_event is not None and cancel_event.is_set():
                for pending in requests[index:]:
                    outcome.errors.append((pending.row_id, TtsError("cancelled", "已取消")))
                    if on_failed is not None:
                        on_failed(pending.row_id, TtsError("cancelled", "已取消"))
                break
            if on_started is not None:
                on_started(request)
            try:
                result = self.backend.synthesize(request, cancel_event=cancel_event, timeout_s=self.timeout_s)
            except TtsError as error:
                outcome.errors.append((request.row_id, error))
                if on_failed is not None:
                    on_failed(request.row_id, error)
                continue
            except Exception as error:  # noqa: BLE001 - 后端实现不可信，统一转错误码
                wrapped = TtsError("backend_internal", f"{type(error).__name__}: {error}")
                outcome.errors.append((request.row_id, wrapped))
                if on_failed is not None:
                    on_failed(request.row_id, wrapped)
                continue
            outcome.results.append(result)
            if on_finished is not None:
                on_finished(result)
        return outcome