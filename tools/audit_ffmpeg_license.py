# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""审计随包 FFmpeg 二进制是否真的"只有 LGPL 组件"（发布前必跑）。

背景（2026-09 实测）：BtbN 的 `win64-lgpl-shared` 变体名义上是 LGPL，实际把
GPL-2.0-or-later 的 **FFTW 3.3.11** 经 chromaprint（`-DFFT_LIB=fftw3`）静态链进了
`avformat-63.dll`。根因是 BtbN 的 `scripts.d/25-fftw3.sh` 与 `50-chromaprint.sh`
缺少 `[[ $VARIANT == lgpl* ]] && return -1` 闸门（对比 `50-x264.sh` 是有的）。
FFmpeg 自报的 `license: LGPL-3.0-or-later` 只看自己的 configure 开关，**看不见经
第三方库间接引入的 GPL 代码**，所以不能作为依据——必须直接查二进制。

本工具做三件事：
  1. 从二进制里取出内嵌 configure 行，核对 GPL/nonfree 开关确实没开、version3 确实开了；
  2. **屏蔽 configure 行之后**，逐二进制扫描 GPL-only 组件的代码级特征串
     （必须屏蔽，否则 `--disable-libx264` 这种开关名会造成假阳性）；
  3. 把审计结论与程序界面声明的许可标签对拍：查不到 GPL 才算 LGPL 标注成立。

用法：python tools/audit_ffmpeg_license.py [--bin DIR] [--json]
全部通过返回 0，任一命中返回 1。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_BIN = REPO / "app" / "resources" / "ffmpeg" / "bin"

# configure 行里**不允许出现**的开关（开了就说明是 GPL / nonfree 构建）
FORBIDDEN_CONFIGURE = (
    "--enable-gpl",
    "--enable-nonfree",
    "--enable-libx264",
    "--enable-libx265",
    "--enable-libxvid",
    "--enable-libxavs",
    "--enable-libxavs2",
    "--enable-libfdk-aac",
    "--enable-libvidstab",
    "--enable-librubberband",
    "--enable-libcdio",
    "--enable-libsmbclient",
    "--enable-avisynth",
    "--enable-frei0r",
    "--enable-libquvi",
    "--enable-libndi-newtek",
)

# configure 行里**必须出现**的开关（LGPL v3 构建的标志）
REQUIRED_CONFIGURE = ("--enable-version3",)

# GPL-only 组件的**代码级**特征串（不用 configure 开关名，避免假阳性）
GPL_FINGERPRINTS: tuple[tuple[str, str, tuple[bytes, ...]], ...] = (
    ("FFTW", "GPL-2.0-or-later", (b"fftw_codelet_", b"fftw_dft_", b"fftw_wisdom", b"(fftw-", b"fftw_plan_dft")),
    ("x264", "GPL-2.0-or-later", (b"x264_encoder_open", b"x264_encoder_encode", b"x264_param_default")),
    ("x265", "GPL-2.0-or-later", (b"x265_encoder_open", b"x265_api_get", b"x265_param_alloc")),
    ("Xvid", "GPL-2.0-or-later", (b"xvid_global", b"xvid_encore", b"xvid_plugin_single")),
    ("xavs2", "GPL-2.0-or-later", (b"xavs2_encoder_",)),
    ("libpostproc", "GPL-2.0-or-later", (b"pp_postprocess", b"pp_get_context", b"postproc_version")),
    ("libfdk-aac", "nonfree", (b"aacEncOpen", b"aacEncEncode")),
    ("vidstab", "GPL-2.0-or-later", (b"VS_VidStab", b"vidstabtransform")),
    ("rubberband", "GPL-2.0-or-later", (b"RubberBandStretcher", b"RubberBand::")),
    ("frei0r", "GPL-2.0-or-later", (b"frei0r_",)),
    ("AviSynth", "GPL-2.0-or-later", (b"avisynth_",)),
    ("libsmbclient", "GPL-3.0-or-later", (b"smbc_",)),
    ("libcdio", "GPL-2.0-or-later", (b"cdio_",)),
)

# 界面里声明的 FFmpeg 许可标签（用于对拍）
LABEL_SOURCES = (
    ("app/i18n.py", re.compile(r"FFmpeg[^<]*?—\s*([A-Za-z0-9.\-]+)")),
    ("app/widgets/license_dialog.py", re.compile(r'FFmpeg[^"]*?—\s*([A-Za-z0-9.\-]+)"')),
)


def find_configure_line(data: bytes) -> tuple[int, int] | None:
    """返回内嵌 configure 行的 (起, 止) 偏移；找不到返回 None。

    **不能写死 prefix**：BtbN 的构建是 `--prefix=/ffbuild/prefix`，而自建构建的
    prefix 完全不同（形如 `--prefix=<构建机工作目录>`）。写死会让规则 1
    在非 BtbN 构建上**静默失效**——那正是"看起来全绿、其实没查"的最坏情况。
    改为按**形态**识别：一段较长的可打印 ASCII 串，含 `--prefix=`/`--enable-*`
    之类开关且 `--` 出现多次。
    """
    for m in re.finditer(rb"[\x20-\x7e]{60,}", data):
        s = m.group(0)
        if s.count(b"--") >= 3 and (b"--prefix=" in s or b"--enable-" in s or b"--disable-" in s):
            return m.start(), m.end()
    return None


def mask(data: bytes, span: tuple[int, int] | None) -> bytes:
    """把 configure 行挖成 NUL，避免开关名污染特征扫描。"""
    if span is None:
        return data
    s, e = span
    return data[:s] + b"\x00" * (e - s) + data[e:]


def scan_gpl(data: bytes) -> list[dict]:
    """在**已屏蔽 configure 行**的字节里扫描 GPL-only 组件特征。

    单独暴露出来是为了可测：测试可以把特征串塞进合成字节，验证扫描确实能抓到
    （防止"检测器坏了却报全绿"）。
    """
    body = mask(data, find_configure_line(data))
    hits: list[dict] = []
    for name, license_id, needles in GPL_FINGERPRINTS:
        for needle in needles:
            n = body.count(needle)
            if n:
                hits.append({"component": name, "license": license_id, "needle": needle.decode(), "count": n})
    return hits


def audit_binary(path: Path) -> dict:
    data = path.read_bytes()
    span = find_configure_line(data)
    cfg = data[span[0] : span[1]].decode("utf-8", "replace") if span else ""

    forbidden = [k for k in FORBIDDEN_CONFIGURE if k in cfg]
    missing = [k for k in REQUIRED_CONFIGURE if k not in cfg]

    return {
        "file": path.name,
        "bytes": len(data),
        "has_configure": span is not None,
        "forbidden_switches": forbidden,
        "missing_switches": missing,
        "gpl_hits": scan_gpl(data),
    }


def declared_labels() -> dict[str, str]:
    out: dict[str, str] = {}
    for rel, pattern in LABEL_SOURCES:
        f = REPO / rel
        if not f.is_file():
            continue
        m = pattern.search(f.read_text(encoding="utf-8", errors="replace"))
        if m:
            out[rel] = m.group(1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="审计随包 FFmpeg 是否真的只含 LGPL 组件")
    ap.add_argument("--bin", default=str(DEFAULT_BIN), help="二进制目录（缺省 app/resources/ffmpeg/bin）")
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    args = ap.parse_args()

    bdir = Path(args.bin)
    if not bdir.is_dir():
        print(f"FAIL 目录不存在：{bdir}")
        return 1

    files = sorted(p for p in bdir.iterdir() if p.is_file() and p.suffix.lower() in (".dll", ".exe"))
    if not files:
        print(f"FAIL 目录里没有 .dll/.exe：{bdir}")
        return 1

    results = [audit_binary(p) for p in files]

    configure_lines = {r["file"]: r for r in results if r["has_configure"]}
    bad_switches: list[tuple[str, list[str]]] = [
        (r["file"], r["forbidden_switches"]) for r in results if r["forbidden_switches"]
    ]
    miss_switches: list[tuple[str, list[str]]] = [
        (r["file"], r["missing_switches"]) for r in results if r["has_configure"] and r["missing_switches"]
    ]
    gpl_files = [(r["file"], r["gpl_hits"]) for r in results if r["gpl_hits"]]
    labels = declared_labels()

    if args.json:
        print(
            json.dumps(
                {
                    "results": results,
                    "gpl_files": [f for f, _ in gpl_files],
                    "labels": labels,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if (gpl_files or bad_switches) else 0

    print(f"审计目录：{bdir}")
    print(f"二进制 {len(files)} 个，其中 {len(configure_lines)} 个内嵌 configure 行\n")

    print("--- 1. configure 开关 ---")
    if not configure_lines:
        print("  FAIL 没找到内嵌 configure 行，无法核对构建开关")
    for name, r in configure_lines.items():
        print(f"  {name}")
        print(f"     禁止开关命中：{r['forbidden_switches'] or '无'}")
        print(f"     必需开关缺失：{r['missing_switches'] or '无'}")

    print("\n--- 2. GPL-only 组件代码级特征（已屏蔽 configure 行）---")
    if not gpl_files:
        print("  未发现任何 GPL-only 组件特征")
    for name, hits in gpl_files:
        print(f"  {name}")
        per: dict[str, dict] = {}
        for h in hits:
            d = per.setdefault(h["component"], {"license": h["license"], "count": 0, "needle": h["needle"]})
            d["count"] += h["count"]
        for comp, d in sorted(per.items()):
            print(f"     {comp:<14} {d['license']:<18} 命中 {d['count']:>6} 次（如 {d['needle']}）")

    print("\n--- 3. 界面声明的许可标签对拍 ---")
    for rel, label in labels.items():
        verdict = ""
        if gpl_files and "LGPL" in label:
            verdict = "  <- 不一致：实际含 GPL 组件，却标为 LGPL"
        elif not gpl_files and "LGPL" in label:
            verdict = "  <- 一致"
        print(f"  {rel}: {label}{verdict}")

    print("\n--- 结论 ---")
    ok = True
    if bad_switches:
        ok = False
        print("  FAIL 构建开关里出现了 GPL/nonfree 选项")
    if miss_switches:
        ok = False
        print("  FAIL 缺少 LGPL v3 构建标志 --enable-version3")
    if gpl_files:
        ok = False
        names = ", ".join(n for n, _ in gpl_files)
        print(f"  FAIL 含 GPL-only 组件：{names}")
        print("       这些二进制不能按 LGPL 分发。要么改用不含它们的构建")
        print("       （去掉 --enable-chromaprint 即可移除 FFTW），要么按 GPL 履行义务。")
    if ok:
        print("  所有二进制仅含 LGPL/宽松许可组件，LGPL 标注成立")

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
