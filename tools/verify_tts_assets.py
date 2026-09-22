# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""TTS 资源完整性校验：存在性 + 大小 + 官方哈希比对。

基准来自 `tts_assets_manifest.txt`（由 `tools/collect_tts_asset_hashes.py` 采集自
HuggingFace tree API，运行期**不依赖网络**）：

- `sha256`   —— LFS 大文件（权重 / GGUF / ASR 模型）的官方 SHA-256；
- `git-sha1` —— 普通小文件的 git blob SHA-1（`sha1("blob <size>\\0" + 内容)`）。

默认只做**存在性 + 大小**比对（快，仅 stat，适合每次启动跑）；加 `--hash` 才逐文件
计算哈希与官方值比对（慢，需读完全部字节，适合手动或首次校验）。

用法::

    python tools/verify_tts_assets.py                 # 全部组，仅大小
    python tools/verify_tts_assets.py --hash          # 全部组，含哈希
    python tools/verify_tts_assets.py --group asr     # 只查某一组
    python tools/verify_tts_assets.py --group-ascii   # 只打印组名与结论（供 bat 取用）

退出码：0=全部通过；1=存在缺失/不完整/哈希不符；2=清单缺失或不可读。
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "tts_assets_manifest.txt"

#: 组名 → 路径前缀（与两个 bat 的目录定义一致）
GROUPS: dict[str, str] = {
    "weights": "TTS model/GPT-SoVITS/GPT_SoVITS/pretrained_models/",
    "gguf": "TTS model/CosyVoice3/",
    "asr": "TTS model/GPT-SoVITS/tools/asr/models/faster-whisper-large-v3/",
}

#: 每次读取的块大小（哈希用）
CHUNK = 1024 * 1024


@dataclass(frozen=True, slots=True)
class Asset:
    algo: str
    digest: str
    size: int
    path: str

    @property
    def group(self) -> str:
        for name, prefix in GROUPS.items():
            if self.path.startswith(prefix):
                return name
        return "other"


@dataclass(frozen=True, slots=True)
class Verdict:
    asset: Asset
    status: str  # ok / missing / size / hash
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def load_manifest(path: Path = MANIFEST) -> list[Asset]:
    """读清单（忽略 `#` 注释与空行）。格式：`<算法>|<哈希>|<字节数>|<路径>`。"""

    assets: list[Asset] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) != 4:
            continue
        algo, digest, size_text, target = (part.strip() for part in parts)
        if algo not in ("sha256", "git-sha1") or not size_text.isdigit():
            continue
        assets.append(Asset(algo=algo, digest=digest, size=int(size_text), path=target))
    return assets


def compute_digest(path: Path, algo: str) -> str:
    """按算法计算文件摘要：sha256 直接算；git-sha1 按 git blob 规则加头。"""

    if algo == "git-sha1":
        hasher = hashlib.sha1()
        hasher.update(b"blob " + str(path.stat().st_size).encode("ascii") + b"\0")
    else:
        hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            hasher.update(chunk)
    return hasher.hexdigest()


def check(asset: Asset, *, with_hash: bool) -> Verdict:
    """校验单个资产。只读：绝不修改任何文件。"""

    target = REPO / asset.path
    if not target.is_file():
        return Verdict(asset, "missing", "文件不存在")
    actual_size = target.stat().st_size
    if actual_size != asset.size:
        return Verdict(asset, "size", f"大小 {actual_size}，应为 {asset.size}")
    if not with_hash:
        return Verdict(asset, "ok")
    actual = compute_digest(target, asset.algo)
    if actual != asset.digest:
        return Verdict(asset, "hash", f"{asset.algo} 应为 {asset.digest[:16]}…，实为 {actual[:16]}…")
    return Verdict(asset, "ok")


def apply_allow_missing(verdicts: list[Verdict]) -> list[Verdict]:
    """把"缺失"降级为"未选用"。

    GGUF 是按集合（q4 / full / all）选的，清单收录全部 11 个文件；用户只下其中一组时，
    其余文件"不存在"是**正常**的，不该算损坏。已存在但大小/哈希不符仍然算错。
    """

    return [
        Verdict(verdict.asset, "absent", "未选用（该 GGUF 集合未下载）") if verdict.status == "missing" else verdict
        for verdict in verdicts
    ]


def summarize(verdicts: list[Verdict]) -> dict[str, int]:
    counts: dict[str, int] = {"ok": 0, "missing": 0, "size": 0, "hash": 0, "absent": 0}
    for verdict in verdicts:
        counts[verdict.status] = counts.get(verdict.status, 0) + 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="TTS 资源完整性校验（只读）")
    parser.add_argument("--group", default="all", choices=(*GROUPS, "all"), help="只校验某一组")
    parser.add_argument("--hash", action="store_true", help="逐文件计算哈希与官方值比对（慢）")
    parser.add_argument("--quiet", action="store_true", help="只打印问题项与汇总")
    parser.add_argument("--group-ascii", action="store_true", help="只打印组名与结论（供 bat 解析）")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="把『不存在』视为『未选用』而非错误（GGUF 按集合下载时用）",
    )
    args = parser.parse_args()

    if not MANIFEST.is_file():
        print(f"[错误] 找不到清单 {MANIFEST.name}")
        return 2
    assets = load_manifest()
    if args.group != "all":
        assets = [asset for asset in assets if asset.group == args.group]
    if not assets:
        print(f"[错误] 清单里没有属于 {args.group} 的条目")
        return 2

    verdicts = [check(asset, with_hash=args.hash) for asset in assets]
    if args.allow_missing:
        verdicts = apply_allow_missing(verdicts)
    counts = summarize(verdicts)
    problems = [verdict for verdict in verdicts if verdict.status in ("missing", "size", "hash")]

    if args.group_ascii:
        print(f"{args.group}|{'OK' if not problems else 'BAD'}|{counts['ok']}|{len(problems)}")
        return 0 if not problems else 1

    mode = "哈希+大小" if args.hash else "大小"
    labels = {"missing": "缺失", "size": "不完整", "hash": "哈希不符"}
    for verdict in problems:
        print(f"  [{labels[verdict.status]}] {verdict.asset.path}  {verdict.detail}")
    if not args.quiet:
        for verdict in verdicts:
            if verdict.ok:
                print(f"  [OK] {verdict.asset.path}")
    print(
        f"{args.group}: 共 {len(verdicts)} 个文件（{mode}校验）—— "
        f"通过 {counts['ok']}，缺失 {counts['missing']}，不完整 {counts['size']}，"
        f"哈希不符 {counts['hash']}，未选用 {counts['absent']}"
    )
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
