# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""本轮（规范 txt 五类分节 + 工作台类别切换）过程日志写入器。

用法（每条事件一次调用，幂等追加）::

    .venv\\Scripts\\python.exe tools/spec_round_log.py "事件标题" "明细第一行" "明细第二行"

日志文件：``temp/spec-categories-round-log.txt``（UTF-8 无 BOM + CRLF）。
只做追加与行尾归一，不参与运行时链路；``temp/`` 已被 gitignore。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / "temp" / "spec-categories-round-log.txt"


def _stamp() -> str:
    # 带本机时区（astimezone()）：日志与其他门禁产物时间戳同为本地时刻
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def append_log(title: str, details: list[str]) -> Path:
    """追加一条日志（标题 + 明细行），返回日志文件路径。"""

    text = LOG_PATH.read_text(encoding="utf-8") if LOG_PATH.exists() else ""
    text = text.replace("\r\n", "\n")
    block = [f"[{_stamp()}] {title}", *[f"    {line}" for line in details]]
    if text and not text.endswith("\n"):
        text += "\n"
    text += "\n".join(block) + "\n"
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    return LOG_PATH


def main(argv: list[str]) -> int:
    if len(argv) < 2 or not argv[1].strip():
        print("usage: spec_round_log.py <title> [detail ...]")
        return 2
    path = append_log(argv[1], [arg for arg in argv[2:]])
    print(f"logged: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
