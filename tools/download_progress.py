# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""下载进度监视器：实时显示已下载大小、用时、速度与预计剩余时间。

背景：`download_tts_verify.bat` 用 `curl -s` 在后台并行下载（GGUF 6 文件、权重 25 文件
/ 4.93 GB），静默意味着用户完全看不到进度。本工具**不参与下载**——下载仍由 curl 负责
（保留 `-C -` 断点续传与 `--ssl-no-revoke`），它只是每隔一会儿统计目标文件在磁盘上的
大小，据此算百分比、速度与 ETA。

用法::

    python tools/download_progress.py --manifest <file> [--url-base <前缀>] [--title <标题>]

清单每行一个目标：``<预期字节数>|<路径>``。预期字节数为 ``0`` 表示未知，
此时若给了 ``--url-base``，则用 HTTP HEAD 探测 ``<url-base>/<文件名>`` 的 Content-Length；
探测失败（代理/网络问题）不报错，降级为"总量未知、只显示已下载与速度"。

退出条件：全部文件达到预期大小，或系统中已无 ``curl.exe`` 进程（下载结束或失败）。
无论成功失败都以 0 退出——它只是显示层，绝不能影响下载流程。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

#: 与 curl 行为一致：直连，不走系统代理注册表
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def human_bytes(count: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(count) < 1024.0 or unit == "TB":
            return f"{count:.0f} {unit}" if unit == "B" else f"{count:.2f} {unit}"
        count /= 1024.0
    return f"{count:.2f} TB"


def human_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    if seconds >= 3600:
        return f"{int(seconds // 3600)}:{int(seconds % 3600 // 60):02d}:{int(seconds % 60):02d}"
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


def curl_running() -> bool:
    """是否有 curl.exe 在跑（下载是否仍在进行）。查不到就当作已结束。"""

    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq curl.exe", "/NH"],
            capture_output=True,
            check=False,
            text=True,
            errors="replace",
        )
    except OSError:
        return False
    return "curl.exe" in (result.stdout or "").lower()


def probe_size(url: str, timeout: float = 15.0) -> int:
    """HEAD 探测 Content-Length；失败返回 0（降级为未知）。"""

    request = urllib.request.Request(url, method="HEAD")
    try:
        with _DIRECT_OPENER.open(request, timeout=timeout) as response:
            return int(response.headers.get("Content-Length") or 0)
    except (urllib.error.URLError, OSError, ValueError):
        return 0


def read_manifest(path: Path, url_base: str | None) -> list[tuple[int, Path]]:
    entries: list[tuple[int, Path]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        expected_text, _, target = line.partition("|")
        target_path = Path(target.strip())
        try:
            expected = int(expected_text.strip())
        except ValueError:
            expected = 0
        if expected <= 0 and url_base:
            expected = probe_size(f"{url_base.rstrip('/')}/{target_path.name}")
        entries.append((max(0, expected), target_path))
    return entries


def render(
    entries: list[tuple[int, Path]],
    *,
    title: str,
    elapsed: float,
    known_total: int,
) -> tuple[str, int, bool]:
    downloaded = 0
    done = 0
    for expected, target in entries:
        size = _size(target)
        if expected > 0:
            downloaded += min(size, expected)
            if size >= expected:
                done += 1
        elif known_total == 0:
            # 总量未知时才把"预期未知"的条目计入已下载，避免与已知总量口径打架
            downloaded += size

    speed = downloaded / elapsed if elapsed > 0 else 0.0
    if known_total > 0:
        percent = downloaded * 100.0 / known_total
        remaining = (known_total - downloaded) / speed if speed > 0 else 0.0
        eta = f"剩余 {human_time(remaining)}" if speed > 0 else "剩余 --:--"
        body = (
            f"{title}  {human_bytes(downloaded)}/{human_bytes(known_total)}"
            f" ({percent:5.1f}%)  用时 {human_time(elapsed)}  {eta}  {human_bytes(speed)}/s"
        )
    else:
        body = (
            f"{title}  已下载 {human_bytes(downloaded)}  用时 {human_time(elapsed)}"
            f"  {human_bytes(speed)}/s  （总量未知，无法估算剩余）"
        )
    # 完成判定只看"预期已知"的条目：清单里可能夹着说明行（预期解析为 0），不能让它卡住完成
    known = [(expected, target) for expected, target in entries if expected > 0]
    complete = bool(known) and all(_size(target) >= expected for expected, target in known)
    return f"{body}  完成 {done}/{len(known)}", downloaded, complete


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="下载进度监视器（只读，不参与下载）")
    parser.add_argument("--manifest", required=True, help="清单文件：每行 <预期字节>|<路径>")
    parser.add_argument("--url-base", default="", help="预期字节为 0 时用 HEAD 探测的前缀")
    parser.add_argument("--title", default="下载中", help="进度行前缀")
    parser.add_argument("--interval", type=float, default=1.0, help="刷新间隔秒")
    parser.add_argument("--max-idle", type=float, default=30.0, help="curl 已退出后仍无进展的最大等待秒")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(errors="replace")  # 控制台/管道编码差异下不因中文崩掉
    except (AttributeError, ValueError):
        pass

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        print(f"[进度] 清单不存在：{manifest_path}（跳过进度显示）")
        return 0

    entries = read_manifest(manifest_path, args.url_base or None)
    if not entries:
        print("[进度] 清单为空（跳过进度显示）")
        return 0

    known_total = sum(expected for expected, _ in entries if expected > 0)
    started = time.monotonic()
    last_growth = started
    last_downloaded = -1

    while True:
        elapsed = time.monotonic() - started
        line, downloaded, complete = render(entries, title=args.title, elapsed=elapsed, known_total=known_total)
        width = max(len(line), 96)
        print("\r" + line.ljust(width), end="", flush=True)

        if complete:
            print(f"\r{line.ljust(width)}")
            return 0

        if downloaded != last_downloaded:
            last_downloaded = downloaded
            last_growth = time.monotonic()

        # curl 全部退出 + 一段时间没有新字节 => 判定结束（可能失败，交由 bat 的校验兜底）
        if not curl_running():
            if known_total > 0 and downloaded >= known_total:
                print(f"\r{line.ljust(width)}")
                return 0
            if time.monotonic() - last_growth >= args.max_idle:
                print(f"\r{line.ljust(width)}")
                print(f"[进度] 下载进程已结束，已落盘 {human_bytes(downloaded)}（未达预期者由后续校验列出）")
                return 0

        time.sleep(max(0.2, args.interval))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print()
        raise SystemExit(0) from None
