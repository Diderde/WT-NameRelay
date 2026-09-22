# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
r"""TTS 服务接口探活工具（**只做 HTTP 探活，不启动任何模型、不触发推理**）。

用法：
    .venv\Scripts\python.exe tools\check_tts_services.py
    .venv\Scripts\python.exe tools\check_tts_services.py --require gsv

端点与默认端口：
    GPT-SoVITS   http://127.0.0.1:9880/control   （可用 WT_GPT_SOVITS_URL 覆盖）
    CosyVoice3   http://127.0.0.1:8080/health    （可用 WT_COSY_URL 覆盖）
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.tts_runner import CosyVoiceGgufBackend, GptSovitsBackend

MODEL_ROOT = Path(__file__).resolve().parents[1] / "TTS model"
GSV_READY_HINT = ('启动示例：cd "TTS model\\GPT-SoVITS" && <你的python> api_v2.py -a 127.0.0.1 -p 9880 '
                  '-c GPT_SoVITS/configs/tts_infer.yaml')
COSY_READY_HINT = "CosyVoice3 GGUF 需要外部 runner 暴露 POST /synthesize 与 GET /health（M1 只约定契约）"


def weights_present() -> dict[str, bool]:
    """仅检查权重文件是否就位（不加载、不推理）。"""

    gsv_models = MODEL_ROOT / "GPT-SoVITS" / "GPT_SoVITS" / "pretrained_models"
    cosy_dir = MODEL_ROOT / "CosyVoice3"
    return {
        "gpt_sovits_weights": gsv_models.is_dir() and any(gsv_models.rglob("s2Gv*.pth")),
        "cosyvoice_gguf": cosy_dir.is_dir() and len(list(cosy_dir.glob("*.gguf"))) >= 6,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="TTS 服务接口探活（不启动模型）")
    parser.add_argument("--require", choices=("gsv", "cosy", "all"), default=None, help="要求的服务；未就绪时以非零码退出")
    args = parser.parse_args()

    gsv = GptSovitsBackend(os.environ.get("WT_GPT_SOVITS_URL", "http://127.0.0.1:9880"))
    cosy = CosyVoiceGgufBackend(os.environ.get("WT_COSY_URL", "http://127.0.0.1:8080"))
    gsv_up = gsv.is_available()
    cosy_up = cosy.is_available()
    assets = weights_present()

    print("=== TTS 接口探活（不启动模型）===")
    print(f"权重资产：GPT-SoVITS={assets['gpt_sovits_weights']}  CosyVoice3 GGUF={assets['cosyvoice_gguf']}")
    print(f"服务探测：GPT-SoVITS {gsv.base_url}{gsv.probe_endpoint} -> {'在线' if gsv_up else '离线'}")
    if not gsv_up:
        print(f"          {GSV_READY_HINT}")
    print(f"           CosyVoice3 {cosy.base_url}{cosy.probe_endpoint} -> {'在线' if cosy_up else '离线'}")
    if not cosy_up:
        print(f"          {COSY_READY_HINT}")

    if args.require == "gsv" and not gsv_up:
        return 1
    if args.require == "cosy" and not cosy_up:
        return 1
    if args.require == "all" and not (gsv_up and cosy_up):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())