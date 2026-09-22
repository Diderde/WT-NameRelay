# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""汇总 Rust 依赖的许可证（读 `vtcore/Cargo.lock` + 本地 cargo registry 元数据）。

用于维护 `THIRD_PARTY_LICENSES.md`：字段直接取自各 crate 的 `Cargo.toml`，**不依赖人工记忆**。

用法::

    ./.venv/Scripts/python.exe tools/collect_rust_licenses.py
    ./.venv/Scripts/python.exe tools/collect_rust_licenses.py --lock vtcore/Cargo.lock --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "vtcore" / "Cargo.lock"
_NAME = re.compile(r'^name\s*=\s*"([^"]+)"', re.MULTILINE)
_VERSION = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)
_LICENSE = re.compile(r'^license\s*=\s*"([^"]+)"', re.MULTILINE)
_LICENSE_FILE = re.compile(r'^license-file\s*=\s*"([^"]+)"', re.MULTILINE)


def parse_lock(lock_path: Path) -> list[tuple[str, str]]:
    """解析 Cargo.lock 的 `[[package]]` 条目。"""

    packages: list[tuple[str, str]] = []
    for block in lock_path.read_text(encoding="utf-8").split("[[package]]")[1:]:
        name = _NAME.search(block)
        version = _VERSION.search(block)
        if name and version:
            packages.append((name.group(1), version.group(1)))
    return sorted(packages)


def registry_roots(explicit: str | None) -> list[Path]:
    if explicit:
        return [Path(explicit)]
    home = Path(os.path.expanduser("~"))
    candidates = [home / ".cargo" / "registry" / "src", home / ".cargo" / "registry" / "cache"]
    return [item for item in candidates if item.is_dir()] or [home / ".cargo" / "registry" / "src"]


def find_crate(roots: list[Path], name: str, version: str) -> Path | None:
    for root in roots:
        for index_dir in sorted(root.glob("*")):
            candidate = index_dir / f"{name}-{version}" / "Cargo.toml"
            if candidate.is_file():
                return candidate
    return None


def licence_of(manifest: Path) -> str:
    text = manifest.read_text(encoding="utf-8", errors="replace")
    match = _LICENSE.search(text)
    if match:
        return match.group(1)
    match = _LICENSE_FILE.search(text)
    if match:
        return f"见文件 {match.group(1)}"
    return "（未声明）"


def main() -> int:
    parser = argparse.ArgumentParser(description="汇总 Rust 依赖许可证")
    parser.add_argument("--lock", default=str(DEFAULT_LOCK), help="Cargo.lock 路径")
    parser.add_argument("--registry", default=None, help="cargo registry src 目录（默认 ~/.cargo/registry/src）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 而非 Markdown")
    parser.add_argument("--out", default=None, help="写入指定文件（UTF-8，避免控制台编码影响中文）")
    args = parser.parse_args()

    lock_path = Path(args.lock)
    if not lock_path.is_file():
        print(f"找不到 {lock_path}", file=sys.stderr)
        return 1

    roots = registry_roots(args.registry)
    rows: list[dict[str, str]] = []
    for name, version in parse_lock(lock_path):
        if name == "vtcore":
            continue
        manifest = find_crate(roots, name, version)
        rows.append(
            {
                "name": name,
                "version": version,
                "license": licence_of(manifest) if manifest else "（本地未缓存，未能读取）",
            }
        )

    if args.json:
        payload = json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
        _emit(payload, args.out)
        return 0

    lock_label = lock_path.relative_to(ROOT).as_posix() if lock_path.is_relative_to(ROOT) else str(lock_path)
    lines = [f"共 {len(rows)} 个依赖（来自 {lock_label}）", "", "| 组件 | 版本 | 许可证 |", "| --- | --- | --- |"]
    lines.extend(f"| {row['name']} | {row['version']} | {row['license']} |" for row in rows)
    _emit("\n".join(lines) + "\n", args.out)
    return 0


def _emit(text: str, out: str | None) -> None:
    if out:
        Path(out).write_text(text, encoding="utf-8", newline="\n")
        print(f"已写入 {out}（{len(text)} 字节）")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    raise SystemExit(main())
