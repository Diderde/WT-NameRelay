# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""采集 TTS 资源的**官方哈希**，生成 `tts_assets_manifest.txt`。

数据来源：HuggingFace 的 tree API（`/api/models/<repo>/tree/main?recursive=true`）。
- LFS 大文件（权重 / GGUF / ASR 模型）→ `lfs.oid` 即**官方 SHA-256**；
- 普通小文件（config.json 等）→ `oid` 是 **git blob SHA-1**，可按 git 算法在本地复算
  （`sha1("blob <size>\\0" + 内容)`），因此同样可作为官方基准。

采集一次、固化进仓库后，运行期校验就**不依赖网络**。

用法::

    python tools/collect_tts_asset_hashes.py            # 写入清单
    python tools/collect_tts_asset_hashes.py --dry-run  # 只打印不写

注意：本机**直连 huggingface.co 会超时**，必须走系统代理（脚本用默认 opener）。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "tts_assets_manifest.txt"

#: HF 仓库 → 本地基准目录（相对仓库根）；与两个 bat 里的目录定义一致
TARGETS: dict[str, str] = {
    "lj1995/GPT-SoVITS": "TTS model/GPT-SoVITS/GPT_SoVITS/pretrained_models",
    "cstr/cosyvoice3-0.5b-2512-GGUF": "TTS model/CosyVoice3",
    "Systran/faster-whisper-large-v3": "TTS model/GPT-SoVITS/tools/asr/models/faster-whisper-large-v3",
}

#: 下载脚本实际会拉取的文件（据此裁剪清单，保证与本地路径一一对应）
ASR_FILES = (
    "config.json",
    "model.bin",
    "preprocessor_config.json",
    "tokenizer.json",
    "vocabulary.json",
    "vocabulary.txt",
)

HEADER = (
    "# TTS 资源完整性清单（官方哈希）\n"
    "# 由 tools/collect_tts_asset_hashes.py 采集自 HuggingFace tree API，请勿手改。\n"
    "# 格式: <算法>|<哈希>|<字节数>|<相对仓库根的路径>\n"
    "#   sha256    —— LFS 文件的官方 SHA-256（HF lfs.oid）\n"
    "#   git-sha1  —— 普通文件的 git blob SHA-1（HF oid），校验算法同 git\n"
    "# 路径前缀与各组基准目录：\n"
    "#   TTS model/GPT-SoVITS/GPT_SoVITS/pretrained_models/  <- lj1995/GPT-SoVITS\n"
    "#   TTS model/CosyVoice3/                               <- cstr/cosyvoice3-0.5b-2512-GGUF\n"
    "#   TTS model/GPT-SoVITS/tools/asr/models/faster-whisper-large-v3/  <- Systran/faster-whisper-large-v3\n"
)


def fetch_tree(repo: str) -> list[dict]:
    """取仓库的递归文件树（走系统代理；直连本机不通）。"""

    url = f"https://huggingface.co/api/models/{repo}/tree/main?recursive=true"
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return [entry for entry in payload if entry.get("type") == "file"]


def weights_paths() -> list[str]:
    """权重清单里的相对路径（大小|路径），用于裁剪 HF 文件树。"""

    listing = REPO / "gpt_sovits_weights_list.txt"
    paths: list[str] = []
    for raw in listing.read_text(encoding="utf-8", errors="replace").splitlines():
        size, _, rel = raw.partition("|")
        if size.strip().isdigit() and rel.strip():
            paths.append(rel.strip())
    return paths


def wanted_files(repo: str, tree: list[dict]) -> list[dict]:
    """按"下载脚本实际会拉取的文件"裁剪文件树。"""

    by_path = {entry["path"]: entry for entry in tree}
    if repo == "lj1995/GPT-SoVITS":
        names = weights_paths()
        missing = [name for name in names if name not in by_path]
        if missing:
            print(f"  !! 权重清单里的 {len(missing)} 个文件在 HF 仓库中不存在: {missing[:3]}…")
        return [by_path[name] for name in names if name in by_path]
    if repo == "cstr/cosyvoice3-0.5b-2512-GGUF":
        return [entry for entry in tree if entry["path"].endswith(".gguf")]
    return [by_path[name] for name in ASR_FILES if name in by_path]


def entry_line(repo: str, entry: dict) -> tuple[str, str, int, str]:
    lfs = entry.get("lfs") or {}
    digest = lfs.get("oid") or ""
    algo = "sha256"
    size = int(lfs.get("size") or entry.get("size") or 0)
    if not digest:
        digest = str(entry.get("oid") or "")
        algo = "git-sha1"
        size = int(entry.get("size") or 0)
    local = f"{TARGETS[repo]}/{entry['path']}"
    return algo, digest, size, local


def main() -> int:
    parser = argparse.ArgumentParser(description="采集 TTS 资源官方哈希")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写文件")
    args = parser.parse_args()

    lines: list[str] = []
    total = 0
    for repo, base in TARGETS.items():
        print(f"== {repo} -> {base}")
        try:
            tree = fetch_tree(repo)
        except (urllib.error.URLError, OSError, ValueError) as error:
            print(f"  [失败] {type(error).__name__}: {error}")
            print("  （本机直连 huggingface.co 会超时，需走系统代理）")
            return 1
        picked = wanted_files(repo, tree)
        print(f"  仓库文件 {len(tree)} 个，按下载范围取 {len(picked)} 个")
        for item in sorted(picked, key=lambda entry: entry["path"]):
            algo, digest, size, local = entry_line(repo, item)
            if not digest:
                print(f"  !! 无哈希字段，跳过: {item['path']}")
                continue
            lines.append(f"{algo}|{digest}|{size}|{local}")
            total += size
        print()

    body = HEADER + "\n".join(sorted(lines)) + "\n"
    print(f"共 {len(lines)} 个文件，合计 {total / 1024 / 1024 / 1024:.2f} GB")

    if args.dry_run:
        print("--dry-run：未写入")
        print("\n".join(body.splitlines()[:12]) + "\n…")
        return 0

    MANIFEST.write_bytes(body.replace("\n", "\r\n").encode("utf-8"))
    print(f"已写入 {MANIFEST.name}（{len(body.encode('utf-8'))} 字节，CRLF）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
