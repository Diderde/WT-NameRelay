# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""把 GBK 的 bat 转写为 UTF-8 便于阅读（只读，不改原文件）。

用法：python tools/view_gbk_bat.py [源bat] [输出txt]
不给参数时默认处理仓库根目录的 start.bat，输出到 stdout（不落盘）。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "start.bat"
DST = Path(sys.argv[2]) if len(sys.argv) > 2 else None

raw = SRC.read_bytes()
text = raw.decode("gbk")
lines = text.splitlines()

print(f"{SRC}  {len(raw)} 字节  {len(lines)} 行")
if DST is not None:
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(text, encoding="utf-8")
    print(f"已转写到 {DST}")
for i, line in enumerate(lines, 1):
    print(f"{i:4}| {line}")
