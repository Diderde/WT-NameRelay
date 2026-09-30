# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""核验 licenses/ffmpeg/ 的许可文本是否与清单一致（存在性 + sha256）。

用法：
    python tools/verify_ffmpeg_licenses.py            # 校验并列出差异
    python tools/verify_ffmpeg_licenses.py --write-md # 额外生成 licenses/ffmpeg/MANIFEST.md

背景：这些文本是随包 FFmpeg 构建所静态链接的第三方组件的许可原文，逐字取自上游；
清单 licenses/ffmpeg/manifest.json 记录每个文件的 sha256，本脚本负责可复现校验。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "licenses" / "ffmpeg"
MANIFEST = TARGET / "manifest.json"
VERSIONS = TARGET / "measured-versions.json"

# 许可性质分类（用于生成 MANIFEST.md 的"义务"列）
STRONG_COPYLEFT = ("GPL-2.0", "GPL-3.0")
WEAK_COPYLEFT = ("LGPL", "MPL")
PATENT_EXCLUSION = ("BSD-3-Clause-Clear",)
PATENT_GRANT = ("Patent", "PATENTS", "IP-Rights")


def classify(spdx: str) -> str:
    if any(token in spdx for token in STRONG_COPYLEFT):
        return "强著佐权（需对应源码）"
    if any(token in spdx for token in WEAK_COPYLEFT):
        return "弱著佐权（声明 + 源码可得/可替换）"
    if any(token in spdx for token in PATENT_EXCLUSION):
        return "宽松但排除专利授权"
    if any(token in spdx for token in PATENT_GRANT):
        return "宽松 + 专利许可（二进制分发须随附）"
    return "宽松（仅需署名/保留声明）"


def content_digest(path: Path) -> str:
    """内容哈希：先归一为 LF 再算 sha256。

    工作区行尾按仓库约定（AGENTS.md 第 1 节）为 CRLF，而上游行尾并不统一；
    用「内容哈希」才能既满足行尾约定，又保持与上游逐字可比 —— 清单里的 sha256 即此口径。
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    versions = json.loads(VERSIONS.read_text(encoding="utf-8"))["measured"]
    entries = manifest["files"]

    missing: list[str] = []
    mismatch: list[str] = []
    for entry in entries:
        path = TARGET / entry["file"]
        if not path.is_file():
            missing.append(entry["file"])
            continue
        digest = content_digest(path)
        if digest != entry["sha256"]:
            mismatch.append(f"{entry['file']}: 期望 {entry['sha256'][:12]}… 实际 {digest[:12]}…")

    print(f"清单条目: {len(entries)}")
    print(f"  存在且哈希一致: {len(entries) - len(missing) - len(mismatch)}")
    print(f"  缺失          : {len(missing)}" + ("  -> " + ", ".join(missing) if missing else ""))
    print(f"  哈希不符      : {len(mismatch)}")
    for item in mismatch:
        print("      " + item)

    known = {entry["file"] for entry in entries} | {"manifest.json", "measured-versions.json", "MANIFEST.md"}
    extra = sorted(p.name for p in TARGET.iterdir() if p.is_file() and p.name not in known)
    if extra:
        print(f"  清单外文件    : {len(extra)} -> " + ", ".join(extra))

    if "--write-md" in sys.argv:
        lines = [
            "# licenses/ffmpeg —— 随包 FFmpeg 第三方组件许可清单",
            "",
            "本目录的 `.txt` 均为**上游逐字原文**，由 `licenses/ffmpeg/manifest.json` 记录 sha256；",
            "校验：`python tools/verify_ffmpeg_licenses.py`（逐文件重算），`--write-md` 会重生成本文件。",
            "",
            f"共 {len(entries)} 个文本。**义务分类**列的判据见脚本 `classify()`。",
            "",
            "| 组件 | SPDX | 文本文件 | sha256 前 12 位 | 义务分类 |",
            "| --- | --- | --- | --- | --- |",
        ]
        for entry in sorted(entries, key=lambda e: (classify(e["spdx"]), e["lib"].lower())):
            lines.append(
                f"| {entry['lib']} | `{entry['spdx']}` | `{entry['file']}` | "
                f"`{entry['sha256'][:12]}` | {classify(entry['spdx'])} |"
            )
        lines += [
            "",
            "## 实测版本（取自随包二进制 banner）",
            "",
            "| 组件 | 实测版本 | 出处 |",
            "| --- | --- | --- |",
        ]
        for name, info in versions.items():
            lines.append(f"| {name} | {info['version']} | {info['evidence']} |")
        lines += [
            "",
            "## 需要注意的三类",
            "",
            "- **强著佐权**：`FFTW3`（GPL-2.0-or-later）——已实测静态链入 `avformat-63.dll`；",
            "  该 DLL 应按 GPL-3.0 对待，或改用去掉 `--enable-chromaprint` 的构建。",
            "- **弱著佐权**：多项 LGPL / MPL —— 除声明外还需库源码与可替换（relink）能力，",
            "  见 `THIRD_PARTY_LICENSES.md` 与 `FFMPEG_BUILD_INFO.md` 的源码披露节。",
            "- **专利条款**：`aom`/`dav1d`/`vpx`/`webp`/`libjxl`/`SVT-AV1`/`rav1e` 的 PATENTS 文件",
            "  与 `vmaf`（BSD-2-Clause-Patent）——其中 AOM 专利许可明文要求以二进制分发时随附该许可。",
            "",
            "> 本清单只证明「文本齐备且与上游逐字一致」，不构成法律意见，也不代表已满足全部许可义务。",
            "",
        ]
        (TARGET / "MANIFEST.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"已生成 {TARGET / 'MANIFEST.md'}")

    return 1 if (missing or mismatch) else 0


if __name__ == "__main__":
    raise SystemExit(main())
