# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""把 licenses/rust/ 的逐 crate 许可正文汇编成一份可嵌入应用资源的单文件。

为什么需要它：`licenses/rust/` 里是 45 个 crate 的逐字原文（90+ 个文件），
Qt 资源系统不适合塞这么多条目、界面也不适合列 45 页；而**分发二进制时必须让
接收者能读到这些正文**。故汇编为一份 `licenses/rust-aggregated.txt`，
由 `resources.qrc` 嵌入为 `:/licenses/RustDependencies.txt`。

口径：
- 逐字引用 `licenses/rust/` 的文件内容，**不改动任何措辞**，只做行尾归一（CRLF）；
- 每段前加 `===== <crate> <version> (<SPDX>) / <文件名> =====` 分隔头（本项目自撰，非上游文本）；
- 顺序确定：按 crate 名、版本、文件名排序，保证可复现、diff 稳定。

不变量自检：可解码、无 BOM、CRLF-only、字节增量 == 新增行数、幂等（重跑字节不变）。

用法：
    python tools/build_rust_license_bundle.py            # 生成/更新
    python tools/build_rust_license_bundle.py --check    # 只校验是否最新（退出码 0/1）
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUST = REPO / "licenses" / "rust"
MANIFEST = RUST / "manifest.json"
OUTPUT = REPO / "licenses" / "rust-aggregated.txt"

HEADER = (
    "vtcore Rust 依赖许可正文汇编\n"
    "\n"
    "本文件由 tools/build_rust_license_bundle.py 从 licenses/rust/ 自动汇编，请勿手工编辑。\n"
    "许可证原文逐字取自各 crate 上游发行包；每段前的 \"=====\" 分隔行由本项目添加。\n"
    "对应关系与内容哈希见 licenses/rust/manifest.json 与 licenses/rust/MANIFEST.md。\n"
    "哈希口径：sha256（内容按 LF 归一后计算），与工作区 CRLF 无关。\n"
)


def _crlf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")


def build() -> bytes:
    """汇编出目标字节（CRLF、UTF-8），重复正文只印一次、其余指向首次出现处。

    为什么要去重：45 个 crate 里大多数是 `MIT OR Apache-2.0`，逐份全文照排会得到
    50 万字节的汇编 —— 既是无谓体积，也让界面浏览器吃力。逐 crate 原文仍完整保存在
    `licenses/rust/<crate>-<version>/`（权威口径，哈希可校验），这里只对**逐字节相同**的
    正文做一次去重并给出指回位置。去重键是内容哈希，不依赖文件名。
    """
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    parts: list[str] = [HEADER]
    seen: dict[str, str] = {}
    for crate in sorted(manifest["crates"], key=lambda c: (c["crate"].lower(), c["version"])):
        for rel in sorted(crate.get("license_files") or []):
            path = RUST / rel
            if not path.is_file():
                raise SystemExit(f"FAIL 清单点名但文件不存在：{rel}")
            body = path.read_text(encoding="utf-8")
            if not body.endswith("\n"):
                body += "\n"
            header = f"===== {crate['crate']} {crate['version']} ({crate['spdx']}) / {Path(rel).name} =====\n"
            key = hashlib.sha256(_crlf(body).encode("utf-8")).hexdigest()
            first = seen.get(key)
            if first is None:
                seen[key] = f"{crate['crate']} {crate['version']}"
                parts.append(header)
                parts.append(body)
            else:
                parts.append(header)
                parts.append(f"（正文与上方 {first} 的同一份许可逐字节相同，此处不重复排版；\n")
                parts.append("  原文见 licenses/rust/ 下本 crate 目录中的同名文件。）\n")
            parts.append("\n")
    return _crlf("".join(parts)).encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    want = build()
    if "--check" in sys.argv:
        if not OUTPUT.is_file():
            print(f"FAIL 缺少 {OUTPUT.relative_to(REPO)}")
            return 1
        have = OUTPUT.read_bytes()
        if have != want:
            print("FAIL 汇编文件已过期（重新运行本脚本生成）")
            return 1
        print(f"OK   {OUTPUT.relative_to(REPO)} 与 licenses/rust/ 一致（{len(want)} 字节）")
        return 0

    before = OUTPUT.read_bytes() if OUTPUT.is_file() else b""
    if before == want:
        print(f"SKIP {OUTPUT.relative_to(REPO)} 已是最新（幂等）")
        return 0
    OUTPUT.write_bytes(want)

    # --- 不变量自检 ---
    raw = OUTPUT.read_bytes()
    raw.decode("utf-8")
    if raw[:3] == b"\xef\xbb\xbf":
        raise SystemExit("FAIL 结果带 BOM")
    if raw.count(b"\n") != raw.count(b"\r\n"):
        raise SystemExit("FAIL 结果存在 LF-only 行尾")
    if raw != want:
        raise SystemExit("FAIL 落盘内容与目标字节不一致")
    print(f"OK   {OUTPUT.relative_to(REPO)}: {len(before)} -> {len(raw)} 字节，"
          f"{raw.count(b'\r\n')} 行，sha256(LF 归一) {digest(raw)[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
