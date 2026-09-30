# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""audioprep Tier 2 worker 子进程：私有 tmp 内执行单节点，回 envelope。

契约语义（15-execution-runtime）：worker 只写私有 tmp、不碰控制面 SQLite、
不提交 CAS——输出与 envelope.json 都留在调度器给的临时目录里，由调度器校验
envelope（fingerprint 一致、输出存在非空）后代为入库。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _ffmpeg(ffmpeg_exe: str, args: list[str]) -> None:
    proc = subprocess.run(
        [ffmpeg_exe, "-y", "-hide_banner", "-loglevel", "error", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg exit {proc.returncode}: {proc.stderr.strip()[-400:]}")


def _run_node(spec: dict) -> dict:
    node_type = spec["node_type"]
    input_path = Path(spec["input_path"])
    output_path = Path(spec["output_path"])
    ffmpeg_exe = spec["ffmpeg_exe"]
    if not input_path.is_file():
        raise RuntimeError(f"input not found: {input_path}")
    if node_type == "DECODE":
        _ffmpeg(ffmpeg_exe, ["-i", str(input_path), "-vn",
                             "-c:a", "pcm_s16le", "-f", "wav", str(output_path)])
    elif node_type == "DELIVERY_RENDER":
        params = spec.get("params", {})
        start_s = float(params.get("start_s", 0.0))
        end_s = float(params.get("end_s", 0.0))
        if not 0.0 <= start_s < end_s:
            raise RuntimeError(f"invalid segment: {params}")
        _ffmpeg(ffmpeg_exe, ["-i", str(input_path),
                             "-af", f"atrim=start={start_s}:end={end_s}",
                             "-c:a", "pcm_s16le", "-f", "wav", str(output_path)])
    else:
        raise RuntimeError(f"unknown node_type: {node_type}")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("missing or empty output")
    return {"name": "audio", "path": str(output_path),
            "size": output_path.stat().st_size}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="audioprep tier2 node worker")
    parser.add_argument("--job", required=True, help="job spec json file")
    args = parser.parse_args(argv)
    spec = json.loads(Path(args.job).read_text(encoding="utf-8"))
    envelope: dict
    try:
        output = _run_node(spec)
        envelope = {"ok": True, "fingerprint": spec.get("fingerprint"),
                    "outputs": [output]}
        code = 0
    except Exception as exc:  # noqa: BLE001  # worker 边界：失败必须落 envelope 而非裸崩
        envelope = {"ok": False, "error_code": "NODE_CRASH",
                    "detail": f"{type(exc).__name__}: {exc}"}
        code = 1
    out_file = Path(args.job).parent / "envelope.json"
    out_file.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(envelope, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
