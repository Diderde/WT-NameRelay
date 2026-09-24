#!/usr/bin/env python3
# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""用「有界 Range 分片」把 HuggingFace 上的大文件拉到本地，可断点续传。

为什么不用 `curl -C -`：实测某些 CDN 边缘节点**不支持开放式 Range**（`bytes=N-`），
curl 会直接报 `(33) HTTP server does not seem to support byte ranges. Cannot resume.`；
而**有界 Range**（`bytes=A-B`）在同一条链路上稳定返回 206。
所以这里把剩余部分切成固定大小的有界分片、逐片重试，最后按序追加到目标文件。

用法（由 download_tts_verify.bat 调用，也可单独用）：

    python tools/fetch_hf_chunks.py \
        --base https://hf-mirror.com/Systran/faster-whisper-large-v3/resolve/main \
        --name model.bin --dest "TTS model/.../model.bin" --size 3087284237 \
        --proxy http://127.0.0.1:<端口> \
        --fallback https://huggingface.co/Systran/faster-whisper-large-v3/resolve/main

约定：
  * 已存在且大小等于 --size 的文件直接跳过（退出 0）；
  * 已存在的部分文件被当作可信前缀，从它的长度继续；
  * 每片默认 32 MiB，失败重试 5 次（指数退避），全部成功后才按序追加；
  * 追加用二进制模式，完成后校验总大小，不符则退出 1 并保留残件。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_CHUNK = 32 * 1024 * 1024


def say(msg: str) -> None:
    print(msg, flush=True)


def file_size(path: Path) -> int:
    return path.stat().st_size if path.is_file() else 0


def fetch_chunk(
    url: str,
    start: int,
    end: int,
    dest: Path,
    proxy: str | None,
    attempts: int,
    timeout: int,
) -> bool:
    """下载 [start, end] 这一段（有界 Range），成功返回 True。"""
    want = end - start + 1
    for attempt in range(1, attempts + 1):
        if dest.is_file():
            dest.unlink()
        cmd = ["curl", "-sS", "-L"]
        if proxy:
            cmd += ["-x", proxy]
        cmd += [
            "--ssl-no-revoke", "--connect-timeout", "20", "--max-time", "900",
            "--retry", "5", "--retry-delay", "3", "--retry-all-errors",
            "-r", f"{start}-{end}", "-o", str(dest), url,
        ]
        t0 = time.time()
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        got = file_size(dest)
        say(
            f"    分片 [{start:,}-{end:,}] 第{attempt}次 exit={proc.returncode} "
            f"{got / 1048576:.1f}/{want / 1048576:.1f} MB {time.time() - t0:.0f}s"
        )
        if got == want:
            return True
        if proc.stderr.strip():
            say(f"      {(proc.stderr.strip().splitlines() or [''])[-1][:140]}")
        time.sleep(min(2 * attempt, 10))
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="有界分片下载（可续传）")
    parser.add_argument("--base", required=True, help="下载基地址（到 resolve/main 为止）")
    parser.add_argument("--name", required=True, help="文件名（拼在基地址后面）")
    parser.add_argument("--dest", required=True, help="目标文件路径")
    parser.add_argument("--size", type=int, required=True, help="期望的总字节数")
    parser.add_argument("--proxy", default="", help="HTTP 代理，如 http://127.0.0.1:<端口>（空=直连）")
    parser.add_argument("--fallback", default="", help="备用基地址（线路2）")
    parser.add_argument("--chunk", type=int, default=DEFAULT_CHUNK, help="分片大小（字节）")
    parser.add_argument("--attempts", type=int, default=5, help="每片重试次数")
    args = parser.parse_args()

    dest = Path(args.dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    proxy = args.proxy or None
    total = args.size

    have = file_size(dest)
    if have == total:
        say(f"  [完整] {args.name}（{have:,} B）")
        return 0
    if have > total:
        say(f"  [警告] {args.name} 比期望大（{have:,} > {total:,}），按前缀截断后继续")
        with dest.open("r+b") as fh:
            fh.truncate(total)
        have = total
        return 0

    say(f"  [分片下载] {args.name}：已有 {have / 1048576:.1f} MB，需要 {(total - have) / 1048576:.1f} MB，"
        f"分片 {args.chunk / 1048576:.0f} MB，代理 {proxy or '直连'}")

    tmp = dest.parent / "_chunks"
    tmp.mkdir(parents=True, exist_ok=True)

    bases = [args.base] + ([args.fallback] if args.fallback else [])
    pos = have
    index = 0
    parts: list[Path] = []
    while pos < total:
        end = min(pos + args.chunk, total) - 1
        part = tmp / f"{args.name}.part{index:04d}"
        ok = False
        for base in bases:
            url = f"{base}/{args.name}"
            if fetch_chunk(url, pos, end, part, proxy, args.attempts, 900):
                ok = True
                break
            say(f"    线路失败：{base}（换下一条线路）")
        if not ok:
            say(f"  [失败] 分片 {index} 在所有线路上都失败；已下好的分片保留在 {tmp}，可重跑本脚本继续")
            return 1
        parts.append(part)
        pos = end + 1
        index += 1

    say(f"  分片齐了（{len(parts)} 片），按序追加到 {dest.name} …")
    with dest.open("ab") as out:
        for part in parts:
            with part.open("rb") as src:
                shutil.copyfileobj(src, out, 4 * 1024 * 1024)
        out.flush()
        os.fsync(out.fileno())
    for part in parts:
        part.unlink()
    try:
        tmp.rmdir()
    except OSError:
        pass

    final = file_size(dest)
    if final != total:
        say(f"  [失败] 追加后大小不符：{final:,} != {total:,}")
        return 1
    say(f"  [完成] {args.name}（{final:,} B）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
