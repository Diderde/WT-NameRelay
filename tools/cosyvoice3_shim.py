# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""CosyVoice3 本地推理服务（CrispASR 绑定的 HTTP 包装）。

**为什么需要它**：Windows 官方件只有 wheel（`crispasr.dll` + 绑定），
没有 `crispasr.exe`、也没有 `--server`；本工具用同一绑定提供等价服务，
让应用获得**进程隔离 / 硬超时与取消 / 崩溃隔离**（崩了只死本进程）。

契约（与 ``app/services/tts_runner.py`` 的 ``CosyVoiceGgufBackend`` 对齐）::

    GET  /health      -> 200 {"ok": true, "backend": "cosyvoice3-tts", "ready": bool, ...}
    POST /synthesize  <- {"text": "...", "language": "zh", "voice": "<可选参考音频>", "speed": 1.0}
                      -> 200 audio/wav（24 kHz 单声道）

也接受 ``/v1/audio/speech``（OpenAI 风格：``{"input": ..., "voice": ...}``）。

用法::

    <python> tools/cosyvoice3_shim.py --models "TTS model\\CosyVoice3" \\
        --runner "TTS model\\CosyVoice3\\runner" --voice "ref.wav" --port 8080

    --fake     不加载模型（确定性正弦波），用于接口联调与自测
    --selftest 起服务→自调 /health 与 /synthesize→打印结果并退出（可用 --fake）
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

SAMPLE_RATE = 24_000  # cosyvoice3-tts 输出 24 kHz 单声道
DEFAULT_LLM = "cosyvoice3-llm-q4_k.gguf"


def pcm_to_wav_bytes(pcm: Any, sample_rate: int = SAMPLE_RATE) -> bytes:
    """float32 [-1,1] PCM → 16-bit 单声道 WAV 字节。"""

    import array

    values = array.array("h", (int(max(-1.0, min(1.0, float(x))) * 32767) for x in pcm))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(values.tobytes())
    return buffer.getvalue()


class FakeEngine:
    """确定性假引擎：用于接口联调与自动化测试（不加载任何模型）。"""

    name = "fake"

    def synthesize(self, *, text: str, language: str, voice: str, seed: int = 0) -> tuple[bytes, int]:
        import math

        frames = max(SAMPLE_RATE // 10, len(text) * SAMPLE_RATE // 50)  # ≥100ms
        freq = 220.0 + (sum(ord(ch) for ch in text) % 200) + (seed % 97)
        pcm = [0.2 * math.sin(2 * math.pi * freq * index / SAMPLE_RATE) for index in range(frames)]
        return pcm_to_wav_bytes(pcm), SAMPLE_RATE


class CrispAsrEngine:
    """真实引擎：延迟加载 CrispASR 绑定与会话（首次请求时才载入模型）。"""

    name = "crispasr"

    def __init__(
        self,
        *,
        runner_dir: Path,
        models_dir: Path,
        voice: str = "",
        ref_text: str = "",
        language: str = "zh",
        threads: int = 4,
    ) -> None:
        self._runner_dir = runner_dir
        self._models_dir = models_dir
        self._voice = voice
        self._ref_text = ref_text
        self._language = language
        self._threads = threads
        self._session: Any = None
        self._lock = threading.Lock()
        self._engine_version = ""
        self._voice = voice
        self._seed_applied = 0
        self.last_error = ""

    # —— 生命周期 ——
    def _load(self) -> Any:
        with self._lock:
            if self._session is not None:
                return self._session
            package_dir = self._runner_dir / "crispasr"
            if not package_dir.is_dir():
                raise RuntimeError(f"未找到 CrispASR 包：{package_dir}（先运行 start.bat /only-runner）")
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(package_dir))
            sys.path.insert(0, str(self._runner_dir))
            import crispasr  # type: ignore[import-not-found]  # 延迟导入，避免无 runner 时启动失败

            self._engine_version = getattr(crispasr, "__version__", "")
            llm = self._pick_llm()
            session = crispasr.Session(str(llm), n_threads=self._threads, backend="cosyvoice3-tts")
            if self._voice:
                session.set_voice(str(self._voice), ref_text=self._ref_text or None)
            for setter, value in (("set_tts_reference_language", self._language),):
                func = getattr(session, setter, None)
                if callable(func) and value:
                    try:
                        func(value)
                    except Exception as error:  # noqa: BLE001 - 可选设置项失败不应阻断主流程
                        sys.stderr.write(f"[shim] 可选设置 {setter} 失败：{error}\n")
            self._session = session
            return session

    def _pick_llm(self) -> Path:
        preferred = self._models_dir / DEFAULT_LLM
        if preferred.exists():
            return preferred
        candidates = sorted(self._models_dir.glob("cosyvoice3-llm-*.gguf"))
        if not candidates:
            raise RuntimeError(f"未找到 CosyVoice3 LLM 权重：{self._models_dir}")
        # 优先 q4_k（低内存），否则取第一个
        for item in candidates:
            if "q4" in item.name:
                return item
        return candidates[0]

    @property
    def ready(self) -> bool:
        return self._session is not None

    def synthesize(self, *, text: str, language: str, voice: str, seed: int = 0) -> tuple[bytes, int]:
        """合成一帧。voice / seed / language 为**每请求**参数（CrispASR 会话级旋钮）。

        - `voice` 非空且与当前不同 → `set_voice()` 切换（参考调节有缓存，重复引用代价低）；
        - `seed > 0` → `set_tts_seed()` 固定随机性；0 = 随机；
        - `language` → `set_target_language()`（与参考语言同语种时等价普通零样本）。
        会话非线程安全：整套"设参 + 合成"在锁内串行执行。
        """

        session = self._load()
        with self._lock:
            if voice and voice != self._voice:
                session.set_voice(voice)
                self._voice = voice
            if seed != self._seed_applied:
                try:
                    session.set_tts_seed(seed)
                    self._seed_applied = seed
                except Exception as error:  # noqa: BLE001 — 种子设置失败按随机处理
                    sys.stderr.write(f"[shim] set_tts_seed 失败：{error}\n")
            try:
                session.set_target_language(language)
            except Exception as error:  # noqa: BLE001 — 可选设置项失败不应阻断主流程
                sys.stderr.write(f"[shim] set_target_language 失败：{error}\n")
            pcm = session.synthesize(text)
        return pcm_to_wav_bytes(pcm), SAMPLE_RATE


class _Handler(BaseHTTPRequestHandler):
    engine: Any = None
    server_version = "WT-Tool-CosyVoice3-Shim/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[shim] " + (fmt % args) + "\n")

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _wav(self, payload: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path.startswith(("/health", "/control")):
            engine = type(self).engine
            self._json(
                200,
                {
                    "ok": True,
                    "backend": "cosyvoice3-tts",
                    "ready": bool(getattr(engine, "ready", True)),
                    "engine": getattr(engine, "name", "unknown"),
                    "version": getattr(engine, "_engine_version", ""),
                    "last_error": getattr(engine, "last_error", ""),
                },
            )
            return
        self._json(404, {"error": {"code": "not_found", "message": self.path}})

    def do_POST(self) -> None:
        if not self.path.startswith(("/synthesize", "/v1/audio/speech")):
            self._json(404, {"error": {"code": "not_found", "message": self.path}})
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except ValueError:
            self._json(400, {"error": {"code": "bad_json", "message": "请求体必须是 JSON"}})
            return
        text = str(payload.get("text") or payload.get("input") or "").strip()
        if not text:
            self._json(400, {"error": {"code": "empty_text", "message": "缺少 text（或 input）字段"}})
            return
        language = str(payload.get("language") or "zh")
        voice = str(payload.get("voice") or "")
        try:
            seed = int(payload.get("seed") or 0)
        except (TypeError, ValueError):
            seed = 0
        try:
            audio, _rate = type(self).engine.synthesize(text=text, language=language, voice=voice, seed=seed)
        except Exception as error:  # noqa: BLE001 - 统一转错误响应
            type(self).engine.last_error = f"{type(error).__name__}: {error}"
            self._json(500, {"error": {"code": "engine_error", "message": type(self).engine.last_error}})
            return
        self._wav(audio)


def build_server(engine: Any, host: str, port: int) -> ThreadingHTTPServer:
    """构造（未启动的）HTTP 服务；测试可传 engine=FakeEngine()。"""

    handler = type("BoundHandler", (_Handler,), {"engine": engine})
    server: ThreadingHTTPServer = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def build_engine(args: argparse.Namespace) -> Any:
    if args.fake:
        return FakeEngine()
    return CrispAsrEngine(
        runner_dir=Path(args.runner),
        models_dir=Path(args.models),
        voice=args.voice or "",
        ref_text=args.ref_text or "",
        language=args.language,
        threads=args.threads,
    )


def _selftest(engine: Any, host: str, port: int) -> int:
    """起服务 → 自调 /health 与 /synthesize → 校验 WAV 头 → 退出码。"""

    server = build_server(engine, host, port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{host}:{server.server_address[1]}"
    try:
        import urllib.request

        # 本地服务必须直连：系统代理会拦截 127.0.0.1（返回 404）
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(base + "/health", timeout=10) as response:
            health = json.loads(response.read().decode("utf-8"))
        print("[selftest] /health ->", health)
        body = json.dumps({"text": "自检文本", "language": "zh"}).encode("utf-8")
        request = urllib.request.Request(base + "/synthesize", data=body, headers={"Content-Type": "application/json"})
        with opener.open(request, timeout=300) as response:
            audio = response.read()
        ok = audio[:4] == b"RIFF" and len(audio) > 44
        print(f"[selftest] /synthesize -> {len(audio)} bytes, WAV={ok}")
        return 0 if ok and health.get("ok") else 1
    finally:
        server.server_close()
        time.sleep(0.05)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CosyVoice3 本地推理服务（CrispASR 绑定包装）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--runner", default=str(Path("TTS model") / "CosyVoice3" / "runner"))
    parser.add_argument("--models", default=str(Path("TTS model") / "CosyVoice3"))
    parser.add_argument("--voice", default="", help="参考音频（wav）；留空则用模型默认音色")
    parser.add_argument("--ref-text", dest="ref_text", default="", help="参考音频的精确文本（可选，留空自动识别）")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--fake", action="store_true", help="不加载模型（确定性正弦波，用于联调/测试）")
    parser.add_argument("--selftest", action="store_true", help="起服务自检后退出")
    args = parser.parse_args(argv)

    engine = build_engine(args)
    if args.selftest:
        return _selftest(engine, args.host, args.port)

    server = build_server(engine, args.host, args.port)
    print(f"[shim] CosyVoice3 服务已启动：http://{args.host}:{args.port}（engine={engine.name}，模型延迟加载）", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())