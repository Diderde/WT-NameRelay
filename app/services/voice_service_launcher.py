# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""CosyVoice3 推理服务装配（B 方案：独立子进程 + HTTP 契约）。

Windows 官方件只有 CrispASR wheel（无 exe/--server），因此由本仓库的
``tools/cosyvoice3_shim.py`` 提供等价服务；本模块负责：

1. 判断 runner 与权重是否就位（就位才尝试拉起服务）；
2. 组装启动命令（应用自身 venv 的解释器 + shim 脚本 + 端口/目录参数）；
3. 通过 ``SubprocessTtsService`` 启动并探活，返回 :class:`CosyVoiceGgufBackend` 客户端。

失败时返回 ``None``，由调用方回落到演示后端。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from app.services.tts_runner import CosyVoiceGgufBackend, SubprocessTtsService

DEFAULT_PORT = 8080
DEFAULT_URL = f"http://127.0.0.1:{DEFAULT_PORT}"
SHIM_RELATIVE = Path("tools") / "cosyvoice3_shim.py"
MODELS_RELATIVE = Path("TTS model") / "CosyVoice3"
RUNNER_RELATIVE = MODELS_RELATIVE / "runner"


@dataclass(frozen=True, slots=True)
class ShimPlan:
    """启动计划：命令、工作目录、健康探针与客户端。"""

    argv: tuple[str, ...]
    cwd: Path
    backend: CosyVoiceGgufBackend


def runner_assets_present(repo_root: Path) -> bool:
    """runner（crispasr.dll）与 LLM 权重是否就位。"""

    dll = repo_root / RUNNER_RELATIVE / "crispasr" / "crispasr.dll"
    models = repo_root / MODELS_RELATIVE
    has_llm = any(models.glob("cosyvoice3-llm-*.gguf"))
    return dll.exists() and has_llm


def build_shim_plan(repo_root: Path, *, port: int = DEFAULT_PORT, voice: str = "", python_exe: Path | None = None) -> ShimPlan:
    """组装 shim 启动计划（不做任何启动动作，便于测试）。"""

    executable = python_exe or Path(sys.executable)
    argv: list[str] = [
        str(executable),
        str(repo_root / SHIM_RELATIVE),
        "--port",
        str(port),
        "--models",
        str(repo_root / MODELS_RELATIVE),
        "--runner",
        str(repo_root / RUNNER_RELATIVE),
    ]
    if voice:
        argv.extend(["--voice", voice])
    backend = CosyVoiceGgufBackend(os.environ.get("WT_COSY_URL", f"http://127.0.0.1:{port}"))
    return ShimPlan(argv=tuple(argv), cwd=repo_root, backend=backend)


@dataclass(frozen=True, slots=True)
class ServiceHandle:
    """服务句柄：service=None 表示复用已存在的外部服务（无需托管）。"""

    service: SubprocessTtsService | None
    backend: CosyVoiceGgufBackend


def start_cosyvoice3_service(repo_root: Path, *, port: int = DEFAULT_PORT, voice: str = "") -> ServiceHandle | None:
    """按需启动 CosyVoice3 服务；资产缺失或启动失败返回 None。"""

    if not runner_assets_present(repo_root):
        return None
    plan = build_shim_plan(repo_root, port=port, voice=voice)
    if plan.backend.is_available():
        # 已有外部服务在跑（例如用户手动启动）：直接复用，不重复拉起
        return ServiceHandle(service=None, backend=plan.backend)
    service = SubprocessTtsService(list(plan.argv), cwd=plan.cwd, probe=plan.backend.is_available, startup_timeout_s=180.0)
    if not service.start():
        service.stop()
        return None
    return ServiceHandle(service=service, backend=plan.backend)