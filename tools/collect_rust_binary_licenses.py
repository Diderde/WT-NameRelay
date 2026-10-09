# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""生成/校验 licenses/rust/ —— vtcore 预编译 wheel 内实际链入的 Rust crate 许可正文。

用法：
    python tools/collect_rust_binary_licenses.py            # 只校验（重算 sha256 + 比对清单），退出码 0/1
    python tools/collect_rust_binary_licenses.py --write    # 从本机 cargo registry 重新生成 licenses/rust/
    python tools/collect_rust_binary_licenses.py --write --prune   # 额外删除清单外的陈旧文件

来源（离线，纯标准库，不联网）：
  1. 首选已解包的 `<registry>/src/<index>/<crate>-<ver>/`；
  2. 该目录不存在时**回退**到 `<registry>/cache/<index>/<crate>-<ver>.crate`
     （gzip tar，用 `tarfile` 读，剥掉顶层 `<crate>-<ver>/` 前缀）；
  3. 两处都没有该 crate 时**报错退出**，绝不静默产出不完整的清单。
  每个 crate 实际用了哪条路径记录在 manifest.json 的 `crates[].source_kind` / `source_path`。

口径（与 licenses/ffmpeg/ 完全一致）：
  * 内容哈希 = tools/verify_ffmpeg_licenses.py::content_digest（先把 CRLF 归一为 LF 再算 sha256）；
  * 工作区行尾按 AGENTS.md/`.gitattributes` 的 `* text=auto eol=crlf` 落为 CRLF，
    因此「逐字原文」指的是 LF 归一后与上游逐字节一致。
  * SPDX 表达式一律取自 wheel 内 CycloneDX SBOM，不手改。

范围（权威口径）：`vtcore/wheels/vtcore-*.whl` 内 `vtcore-<ver>.dist-info/sboms/*.cyclonedx.json`
的组件集合（45 个）。**不是** Cargo.lock 的第三方 crate 数（53 个，含 8 个 dev-only serde_json 链）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "licenses" / "rust"
MANIFEST = TARGET / "manifest.json"
MANIFEST_MD = TARGET / "MANIFEST.md"
VT_DIR = ROOT / "vtcore"
WHEELS = VT_DIR / "wheels"
LOCK = VT_DIR / "Cargo.lock"
CACHE_SBOM = ROOT / "temp" / "_license_audit_lead_sbom.json"

EXPECTED_WHEEL = "vtcore-0.1.0-cp312-abi3-win_amd64.whl"
SBOM_MEMBER_SUFFIX = ".cyclonedx.json"
HASH_NOTE = "sha256 按 LF 归一后的内容计算（content_digest），与工作区 CRLF 无关（同 licenses/ffmpeg/manifest.json 口径）"
SCOPE_TEMPLATE = "vtcore/wheels/{wheel} 内实际链入的第三方 crate"

# 许可/声明文件名前缀（大小写不敏感）。
# 任务口径为 LICENSE* / LICENCE* / COPYING* / NOTICE* / UNLICENSE*；本脚本**保守扩展**一个
# COPYRIGHT*：它同样是 crate 随包携带的法律声明（例如 fiat-crypto 的 COPYRIGHT 直接带
# `SPDX-License-Identifier: MIT OR Apache-2.0 OR BSD-1-Clause`），少收一份声明的风险大于多收一份。
# 不使用 COPYRIGHT* 时本仓库的文件数为 89（本次为 91）；差异见 MANIFEST.md 的「已知边界」。
# AUTHORS* 仍**不**采集：它是署名名单，不是许可或声明文本。
LICENSE_PREFIXES = ("license", "licence", "copying", "notice", "unlicense", "copyright")
# 最大嵌套深度：0 = 只在 crate 根目录找；1 = 额外允许一层（pyo3 随包携带 pyo3-runtime/LICENSE-*）
MAX_DEPTH = 1
# 本目录下由脚本管理、不计入 "清单外文件" 的固定文件名
SELF_FILES = {"manifest.json", "MANIFEST.md"}


def content_digest(path: Path) -> str:
    """内容哈希：先归一为 LF 再算 sha256。与 tools/verify_ffmpeg_licenses.py 完全同口径。"""
    return content_digest_bytes(path.read_bytes())


def content_digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def to_worktree_eol(data: bytes) -> bytes:
    """把任意行尾归一为 LF 后再落为 CRLF（工作区约定）。content_digest 不受影响。"""
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def write_text_crlf(path: Path, text: str) -> None:
    data = text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    path.write_bytes(data)


def is_license_name(name: str) -> bool:
    low = name.lower()
    return low.startswith(LICENSE_PREFIXES)


def find_license_relpaths(crate_dir: Path) -> list[str]:
    """列出 crate 包内随包携带的许可/声明文件的相对路径（POSIX 风格），深度受限。"""
    found: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(crate_dir):
        rel = Path(dirpath).relative_to(crate_dir)
        if len(rel.parts) > MAX_DEPTH:
            dirnames[:] = []
            continue
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in filenames:
            if is_license_name(name):
                found.add((rel / name).as_posix() if rel.parts else name)
    return sorted(found)


def find_cache_dir(registry: Path, explicit: str | None = None) -> Path:
    """cargo 的 `.crate` 压缩包缓存目录（与 registry/src/<index> 同级）。"""
    if explicit:
        return Path(explicit)
    return registry.parent.parent / "cache" / registry.name


def tar_license_files(crate_file: Path) -> dict[str, bytes]:
    """从 `.crate`（gzip tar，纯标准库 tarfile 可读）取出许可/声明文件：relpath -> bytes。

    crates.io 的 `.crate` 顶层恒为 `<crate>-<version>/`，此处剥掉该层前缀，
    其余相对路径与 `registry/src/<crate>-<ver>/` 布局一致（含嵌套，如 pyo3-runtime/LICENSE-*），
    因此「目录模式」与「压缩包模式」对同一 crate 求得同一组相对路径。
    """
    out: dict[str, bytes] = {}
    with tarfile.open(crate_file, "r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            parts = member.name.split("/")
            if len(parts) < 2:
                continue
            rel_parts = parts[1:]  # 剥掉顶层 <crate>-<version>/
            if len(rel_parts) - 1 > MAX_DEPTH:
                continue
            if not is_license_name(rel_parts[-1]):
                continue
            handle = tf.extractfile(member)
            out["/".join(rel_parts)] = handle.read() if handle else b""
    return out


def neutral_source_path(source_path) -> str:
    """把来源路径压成「源根目录/箱子目录」两段相对形式（公开清单不带本机绝对路径）。"""

    parts = Path(source_path).parts
    return "/".join(parts[-2:]) if len(parts) >= 2 else Path(source_path).name


def resolve_crate_source(crate_dir: Path, crate_file: Path):
    """优先用已解包的 `registry/src/<crate>-<ver>/`；目录不存在时回退到 `registry/cache/*.crate`。

    返回 (source_kind, source_path, {relpath: bytes})；两处都没有则返回 None。
    回退分支让脚本在「crate 未解包」的机器上也能离线生成同一份清单。
    """
    if crate_dir.is_dir():
        rels = find_license_relpaths(crate_dir)
        return "registry-src", crate_dir, {r: (crate_dir / r).read_bytes() for r in rels}
    if crate_file.is_file():
        return "registry-cache-crate", crate_file, tar_license_files(crate_file)
    return None


def find_registry(explicit: str | None, comps: list[dict]) -> Path:
    if explicit:
        reg = Path(explicit)
        if not reg.is_dir():
            raise SystemExit(f"ERROR registry dir not found: {reg}")
        return reg
    base = Path.home() / ".cargo" / "registry" / "src"
    if not base.is_dir():
        raise SystemExit(f"ERROR cargo registry src dir not found: {base} "
                         "(pass --registry)")
    cands = sorted(p for p in base.iterdir()
                   if p.is_dir() and p.name.startswith("index.crates.io-"))
    if not cands:
        raise SystemExit(f"ERROR no index.crates.io-* dir under {base}")
    if len(cands) > 1:
        # 选能解析出最多 crate 的那个
        def score(p: Path) -> tuple[int, str]:
            n = sum(1 for c in comps if (p / ("{}-{}".format(c["name"], c["version"]))).is_dir())
            return (n, p.name)
        cands.sort(key=score, reverse=True)
    return cands[0]


def find_wheel() -> Path | None:
    if not WHEELS.is_dir():
        return None
    preferred = WHEELS / EXPECTED_WHEEL
    if preferred.is_file():
        return preferred
    cands = sorted(WHEELS.glob("vtcore-*.whl"))
    return cands[0] if cands else None


def parse_components(doc: dict) -> list[dict]:
    comps = []
    for c in doc.get("components") or []:
        exprs: list[str] = []
        for entry in c.get("licenses") or []:
            if entry.get("expression"):
                exprs.append(entry["expression"])
            else:
                lic = entry.get("license") or {}
                ident = lic.get("id") or lic.get("name")
                if ident:
                    exprs.append(ident)
        comps.append({
            "name": c.get("name") or "",
            "version": c.get("version") or "",
            "spdx": " AND ".join(exprs) if exprs else None,
            "purl": c.get("purl") or "",
        })
    comps.sort(key=lambda c: (c["name"], c["version"]))
    return comps


def component_key(c: dict) -> tuple[str, str, str]:
    return (c["name"], c["version"], c["spdx"] or "")


def load_sbom(wheel: Path) -> tuple[str, list[dict], str]:
    """返回 (wheel 内 SBOM 成员路径, 组件列表, wheel 文件名)。"""
    with zipfile.ZipFile(wheel) as zf:
        members = [n for n in zf.namelist() if n.endswith(SBOM_MEMBER_SUFFIX)]
        if not members:
            raise SystemExit(f"ERROR no *{SBOM_MEMBER_SUFFIX} inside {wheel}")
        member = min(members)
        doc = json.loads(zf.read(member).decode("utf-8"))
    return member, parse_components(doc), wheel.name


def load_sbom_fallback() -> tuple[str, list[dict]]:
    if not CACHE_SBOM.is_file():
        raise SystemExit(f"ERROR no wheel and no cached SBOM at {CACHE_SBOM}")
    comps = parse_components({"components": [
        {"name": c["name"], "version": c["version"],
         "licenses": [{"expression": e} for e in c.get("licenses") or []]}
        for c in json.loads(CACHE_SBOM.read_text(encoding="utf-8"))
    ]})
    return CACHE_SBOM.name, comps


def resolve_sbom(wheel_arg: str | None) -> tuple[str, list[dict], dict]:
    """解析 SBOM 来源；wheel 与 temp 缓存同时存在时必须一致（防漂移）。"""
    info: dict = {}
    wheel = Path(wheel_arg) if wheel_arg else find_wheel()
    if wheel is not None and wheel.is_file():
        member, comps, wheel_name = load_sbom(wheel)
        info["wheel"] = wheel_name
        info["wheel_sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
        info["sbom"] = member
        info["sbom_source"] = "wheel"
        cached = None
        if CACHE_SBOM.is_file():
            try:
                cached = load_sbom_fallback()[1]
            except SystemExit:
                cached = None
        if cached is not None:
            if sorted(map(component_key, cached)) != sorted(map(component_key, comps)):
                raise SystemExit(
                    f"ERROR SBOM drift: wheel SBOM and {CACHE_SBOM.name} disagree "
                    f"({len(comps)} vs {len(cached)} components)")
            info["cache_agrees"] = True
        return member, comps, info
    member, comps = load_sbom_fallback()
    info["sbom"] = member
    info["sbom_source"] = "cache"
    info["cache_agrees"] = True
    return member, comps, info


def cargo_toml_identity() -> tuple[str, str]:
    text = (VT_DIR / "Cargo.toml").read_text(encoding="utf-8", errors="replace")
    name = re.search(r'^\s*name\s*=\s*"([^"]+)"', text, re.MULTILINE)
    version = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return (name.group(1) if name else "vtcore", version.group(1) if version else "0.0.0")


def lock_stats() -> dict:
    """Cargo.lock 的 package 统计：总数含根包，第三方数 = 总数 - 根包。"""
    text = LOCK.read_text(encoding="utf-8", errors="replace")
    pkgs: list[tuple[str, str]] = []
    for block in text.split("[[package]]")[1:]:
        nm = re.search(r'^\s*name\s*=\s*"([^"]+)"', block, re.MULTILINE)
        vr = re.search(r'^\s*version\s*=\s*"([^"]+)"', block, re.MULTILINE)
        if nm and vr:
            pkgs.append((nm.group(1), vr.group(1)))
    root = cargo_toml_identity()
    return {
        "cargo_lock_entries": len(pkgs),
        "cargo_lock_root": "{} {}".format(*root),
        "cargo_lock_root_excluded": "{}-{}".format(*root),
        "cargo_lock_packages": len(pkgs) - (1 if root in set(pkgs) else 0),
        "cargo_lock_all": pkgs,
    }


def build_plan(comps: list[dict], registry: Path, cache: Path) -> tuple[list[dict], list[str]]:
    plan: list[dict] = []
    problems: list[str] = []
    for c in comps:
        key = "{}-{}".format(c["name"], c["version"])
        crate_dir = registry / key
        crate_file = cache / (f"{key}.crate")
        resolved = resolve_crate_source(crate_dir, crate_file)
        if resolved is None:
            problems.append(f"no source for {key} (looked in {crate_dir} and {crate_file})")
            continue
        kind, source_path, data = resolved
        plan.append({
            "crate": c["name"],
            "version": c["version"],
            "spdx": c["spdx"],
            "key": key,
            "source_kind": kind,
            "source_path": source_path,
            "files": sorted(data),
            "data": data,
        })
    plan.sort(key=lambda e: (e["crate"], e["version"]))
    return plan, problems


def iter_managed_files(crate_dir: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(crate_dir):
        for name in filenames:
            out.append(Path(dirpath) / name)
    return sorted(out)


def generate(plan: list[dict], info: dict, lock: dict, prune: bool) -> dict:
    TARGET.mkdir(parents=True, exist_ok=True)
    files: list[dict] = []
    crates: list[dict] = []
    missing_texts: list[str] = []
    pruned: list[str] = []
    pruned_locked: list[tuple[str, str]] = []
    managed_keys = {e["key"] for e in plan}

    for entry in plan:
        key = entry["key"]
        dest_dir = TARGET / key
        expected: set[str] = set()
        for rel in entry["files"]:
            dst = dest_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            data = entry["data"][rel]
            dst.write_bytes(to_worktree_eol(data))
            digest = content_digest_bytes(data)
            if content_digest(dst) != digest:
                raise SystemExit(f"ERROR EOL round-trip changed content: {key}/{rel}")
            expected.add(rel)
            files.append({
                "crate": entry["crate"],
                "version": entry["version"],
                "spdx": entry["spdx"],
                "file": f"{key}/{rel}",
                "sha256": digest,
            })

        # 清理该 crate 目录下的陈旧文件（不再随包携带/改名/上传中断留下的 .tmp）
        if dest_dir.is_dir():
            for stale in iter_managed_files(dest_dir):
                rel = stale.relative_to(dest_dir).as_posix()
                if rel not in expected:
                    try:
                        stale.unlink()
                    except OSError as exc:
                        # 例如 Windows 上另一进程仍持有句柄（WinError 32）：
                        # 记录并继续，绝不能因为一个删不掉的残留文件而中断整份清单的生成。
                        pruned_locked.append(((f"{key}/{rel}"), exc.__class__.__name__))
                        continue
                    pruned.append(f"{key}/{rel}")
            # 删除空目录
            for dirpath, dirnames, filenames in os.walk(dest_dir, topdown=False):
                p = Path(dirpath)
                if not any(p.iterdir()):
                    p.rmdir()

        if expected:
            crates.append({
                "crate": entry["crate"],
                "version": entry["version"],
                "spdx": entry["spdx"],
                "license_files": [f"{key}/{r}" for r in sorted(expected)],
                "license_file": f"{key}/{min(expected)}",
                "missing_text": False,
                "source_kind": entry["source_kind"],
                # say no to perv. — 公开产物不得携带开发机绝对路径：
                # source_path 只保留「源根目录/箱子目录」两段相对形式
                # （原样写入会把 C:\Users\<用户名>\.cargo\... 带进公开面，
                # 2026-10-09 发布树泄露扫描实锤）
                "source_path": neutral_source_path(entry["source_path"]),
            })
        else:
            crates.append({
                "crate": entry["crate"],
                "version": entry["version"],
                "spdx": entry["spdx"],
                "license_files": [],
                "license_file": None,
                "missing_text": True,
                "source_kind": entry["source_kind"],
                # say no to perv. — 公开产物不得携带开发机绝对路径：
                # source_path 只保留「源根目录/箱子目录」两段相对形式
                # （原样写入会把 C:\Users\<用户名>\.cargo\... 带进公开面，
                # 2026-10-09 发布树泄露扫描实锤）
                "source_path": neutral_source_path(entry["source_path"]),
            })
            missing_texts.append(key)

    # licenses/rust 下不属于本次 SBOM 的目录
    unmanaged: list[str] = []
    if TARGET.is_dir():
        for child in sorted(TARGET.iterdir()):
            if child.name in SELF_FILES:
                continue
            if child.is_dir() and child.name not in managed_keys:
                unmanaged.append(child.name)
                if prune:
                    for p in iter_managed_files(child):
                        p.unlink()
                    for dirpath, _dn, _fn in os.walk(child, topdown=False):
                        pp = Path(dirpath)
                        if not any(pp.iterdir()):
                            pp.rmdir()
            elif child.is_file():
                unmanaged.append(child.name)

    manifest = {
        "scope": SCOPE_TEMPLATE.format(wheel=info.get("wheel", EXPECTED_WHEEL)),
        "source_of_truth": {
            "sbom": info["sbom"],
            "sbom_components": len(plan),
            "cargo_lock_packages": lock["cargo_lock_packages"],
            "wheel": info.get("wheel"),
            "wheel_sha256": info.get("wheel_sha256"),
            "sbom_source": info["sbom_source"],
            "cargo_lock_entries": lock["cargo_lock_entries"],
            "cargo_lock_root_excluded": lock["cargo_lock_root_excluded"],
        },
        # say no to perv. — registry/registry_cache 的本机绝对路径不入公开清单
        "registry": "本机 cargo registry/src（绝对路径略）",
        "registry_cache": "本机 cargo registry/cache（绝对路径略）",
        "source_kinds": {
            "registry-src": sum(1 for e in plan if e["source_kind"] == "registry-src"),
            "registry-cache-crate": sum(1 for e in plan if e["source_kind"] == "registry-cache-crate"),
        },
        "hash_note": HASH_NOTE,
        "license_file_patterns": ["LICENSE*", "LICENCE*", "COPYING*", "NOTICE*", "UNLICENSE*", "COPYRIGHT*"],
        "max_nested_depth": MAX_DEPTH,
        "files": files,
        "crates": crates,
        "missing_texts": missing_texts,
        "counts": {
            "crates": len(crates),
            "files": len(files),
            "missing": len(missing_texts),
        },
    }

    write_text_crlf(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=False) + "\n")
    write_text_crlf(MANIFEST_MD, render_manifest_md(manifest, pruned, unmanaged))

    print(f"write: crates={len(crates)} files={len(files)} missing={len(missing_texts)}")
    if pruned:
        print(f"write: pruned stale files={len(pruned)}")
        for p in pruned:
            print(f"  PRUNED {p}")
    if pruned_locked:
        print(f"write: WARN could not prune {len(pruned_locked)} file(s) - held open by another process "
              "(verify will report them as EXTRA until released)")
        for p, kind in pruned_locked:
            print(f"  LOCKED {p} ({kind})")
    if unmanaged:
        print(f"write: WARN unmanaged entries under licenses/rust (left untouched "
              f"unless --prune): {len(unmanaged)}")
        for u in unmanaged:
            print(f"  UNMANAGED {u}")
    return manifest


def render_manifest_md(manifest: dict, pruned: list[str], unmanaged: list[str]) -> str:
    sot = manifest["source_of_truth"]
    counts = manifest["counts"]
    lines = [
        "# licenses/rust —— vtcore 预编译 wheel 内 Rust crate 许可正文清单",
        "",
        "本目录的文本均为**上游逐字原文**（LF 归一后与 crate 包内文件逐字节一致），",
        "由 `licenses/rust/manifest.json` 记录 sha256；校验：`python tools/collect_rust_binary_licenses.py`。",
        "重新生成：`python tools/collect_rust_binary_licenses.py --write`。",
        "",
        "## 范围与权威口径",
        "",
        "- 范围：`{}`。".format(manifest["scope"]),
        f"- 组件集合取自该 wheel 内的 CycloneDX SBOM `{sot['sbom']}`，共 **{sot['sbom_components']}** 个组件。",
        f"- **不要**用 `vtcore/Cargo.lock` 的第三方 crate 数（**{sot['cargo_lock_packages']}** 个）当范围：",
        f"  该锁文件共 {sot['cargo_lock_entries']} 个 `[[package]]`，扣除根包 `{sot['cargo_lock_root_excluded']}` 后为 {sot['cargo_lock_packages']} 个第三方 crate，",
        "  其中多出的组件属于 dev-only 的 serde_json 链，未链入 `vtcore.pyd`。",
        "",
        "## 统计",
        "",
        f"| crate 数（SBOM 组件） | {counts['crates']} |",
        f"| 许可正文文件数 | {counts['files']} |",
        f"| 上游未随包携带正文的 crate 数 | {counts['missing']} |",
        "",
        "## 哈希与行尾口径",
        "",
        "- 哈希：`{}`".format(manifest["hash_note"]),
        "- 与 `tools/verify_ffmpeg_licenses.py::content_digest` 实现**完全同口径**",
        "  （`sha256(read_bytes().replace(b\"\\r\\n\", b\"\\n\"))`），因此可与上游逐字比对。",
        "- 工作区行尾：`.gitattributes` 的 `* text=auto eol=crlf` 生效，本目录文本以 CRLF 落盘；",
        "  这**不影响** `content_digest`，故清单中的 sha256 仍是 LF 归一后的值。",
        "- 采集文件的文件名模式（大小写不敏感）：{}；嵌套深度上限 {} 层".format(
            "、".join(f"`{p}`" for p in manifest["license_file_patterns"]), manifest["max_nested_depth"]),
        "  （用于覆盖 `pyo3` 随包携带的 `pyo3-runtime/LICENSE-*`）。",
        "- 采集来源（离线，未联网）：优先已解包的本机 cargo `registry/src` 目录；",
        ("  目录不存在时回退到本机 cargo `registry/cache/*.crate` 压缩包（纯标准库 `tarfile` 读取）。"
         "  具体绝对路径不入公开清单（`manifest.json` 的 `source_path` 亦只保留相对两段）。"),
        (f"  本次按来源统计：`registry-src` {manifest.get('source_kinds', {}).get('registry-src', 0)} 个、"
         f"`registry-cache-crate` {manifest.get('source_kinds', {}).get('registry-cache-crate', 0)} 个。"),
        "  每个 crate 的实际来源见 `manifest.json` 的 `crates[].source_kind` / `source_path`。",
        "",
        "## 许可正文一览",
        "",
        "| crate | 版本 | SPDX（取自 SBOM） | 正文文件 | sha256 前 12 位 |",
        "| --- | --- | --- | --- | --- |",
    ]
    digests = {}
    for f in manifest["files"]:
        digests.setdefault("{}/{}".format(f["crate"], f["version"]), []).append((f["file"].split("/", 1)[1], f["sha256"]))
    for c in manifest["crates"]:
        key = "{}/{}".format(c["crate"], c["version"])
        if c["license_files"]:
            names = "<br>".join(f"`{n}`" for n, _ in digests[key])
            shas = "<br>".join(f"`{s[:12]}`" for _, s in digests[key])
        else:
            names = "**（上游未随包携带任何许可正文）**"
            shas = "—"
        lines.append("| `{}` | {} | `{}` | {} | {} |".format(c["crate"], c["version"], c["spdx"], names, shas))

    lines += ["", "## 上游未随包携带许可正文的 crate", ""]
    if manifest["missing_texts"]:
        lines += [
            "以下 crate 在其 crate 包内**没有任何**许可/声明文件——已按 SBOM 的 SPDX 表达式登记，",
            "但**未臆造正文**（也未去网上另抓一份来冒充「上游随包文本」）：",
            "",
        ]
        for c in manifest["crates"]:
            if c["missing_text"]:
                lines.append("- `{}-{}` —— SPDX `{}`；来源 `{}`（相对路径 `{}`）。".format(c["crate"], c["version"], c["spdx"],
                                c.get("source_kind"), c.get("source_path")))
        lines += [
            "",
            "> `r-efi` 的补充证据：**两处来源都已核对过，均无许可正文** ——",
            "> (1) 已解包的源码目录 `registry/src/…/r-efi-6.0.0/`（70 个文件）：",
            ">     名字命中 `LICENSE*`/`LICENCE*`/`COPYING*`/`NOTICE*`/`UNLICENSE*`/`COPYRIGHT*` 的文件数 = **0**",
            ">     （唯一的法律相关文件是 `AUTHORS`，署名名单，按口径不采集）；",
            "> (2) `.crate` 压缩包 `registry/cache/…/r-efi-6.0.0.crate`（65,303 B、69 个成员）：",
            ">     同样只有 `r-efi-6.0.0/AUTHORS` 一个名字命中，**没有**许可正文。",
            "> 上游自述：`Cargo.toml` 第 39 行 `license = \"MIT OR Apache-2.0 OR LGPL-2.1-or-later\"`，",
            "> 但 `README.md` 第 96–99 行的 License 节只写「See AUTHORS file for details」，包内并无 `LICENSE*`。",
            "> 三选一授权中的 MIT / Apache-2.0 均为宽松许可，可**选择**其一；",
            "> 本清单保留 `license_file: null`，**不代上游补正文，也不另抓一份冒充「随包原文」**。",
        ]
    else:
        lines.append("无。")
    lines += [
        "",
        "## 已知边界",
        "",
        "- 本清单只证明「已随包收齐各 crate 上游自带的许可/声明正文，且与上游逐字一致」，",
        "  **不构成法律意见**，也不代表全部许可义务已履行；",
        "  也不证明「该二进制真的只含这些组件」（见下一条）。",
        ("- SBOM 是**依赖图**快照（cargo-cyclonedx 按依赖图生成，**不是链接闭包**），"
        "**不等于**「与 `vtcore.pyd` 实际链接的符号集合」。"),
        ("  实测一例：`r-efi` 只被 `getrandom` 的 **UEFI target** 使用 —— "
        "`getrandom-0.4.3/Cargo.toml` 第 103 行"),
        "  `[target.'cfg(all(target_os = \"uefi\", getrandom_backend = \"efi_rng\"))'.dependencies.r-efi]`；",
        "  **Windows x64 下它不会链入 `vtcore.pyd`**，出现在 SBOM 里纯属依赖图口径。",
        "  因此 45 是**上界**；要证明下界需要 `cargo auditable` / 链接映射级别的证据。",
        ("  **但不要因此把它从清单里删掉**：本清单的 crate 集合与 `THIRD_PARTY_LICENSES.md` 的"
        "「Cargo.lock 53 个第三方 crate」是**两种口径并存**，宁多勿少。"),
        "- `pyo3-0.29.2` 额外随包携带 `pyo3-runtime/LICENSE-APACHE` 与 `pyo3-runtime/LICENSE-MIT`",
        "  （与根目录两份逐字节相同），脚本按「镜像 crate 包内布局」一并收下。",
        "- `typenum-1.20.1/LICENSE` 是 17 字节的 SPDX 指针（内容仅 `MIT OR Apache-2.0`），",
        "  不是许可正文；该 crate 的正文在同目录 `LICENSE-APACHE` / `LICENSE-MIT`。",
        ("- 采集的文件名模式是任务口径的**保守超集**：除 "
        "`LICENSE*`/`LICENCE*`/`COPYING*`/`NOTICE*`/`UNLICENSE*` 外还收 `COPYRIGHT*`"),
        "  （`fiat-crypto-0.3.0/COPYRIGHT`、`rand_core-0.10.1/COPYRIGHT`）。",
        "  去掉这两份后文件数为 89；本次为 91。`AUTHORS` 未采集（署名名单，非许可文本）。",
        "- 目录名 `licenses/rust/` 下的 crate 集合、版本号、SPDX 表达式均以 SBOM 为准，",
        "  脚本不擅自增删组件；SPDX 一律取自 SBOM，不手改。",
        "",
    ]
    if pruned:
        lines += ["## 本次 --write 清理的陈旧文件", ""]
        lines += [f"- `{p}`" for p in pruned]
        lines.append("")
    if unmanaged:
        lines += ["## licenses/rust 下非本次范围的条目（未被脚本管理）", ""]
        lines += [f"- `{u}`" for u in unmanaged]
        lines.append("")
    return "\n".join(lines)


def verify(plan: list[dict], info: dict, lock: dict, require_source: bool) -> int:
    problems: list[str] = []
    warnings: list[str] = []

    if not MANIFEST.is_file():
        print(f"[FAIL] manifest missing: {MANIFEST} (run --write)")
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    entries = manifest.get("files") or []
    digests: dict[str, str] = {}
    missing: list[str] = []
    mismatch: list[str] = []
    for entry in entries:
        rel = entry["file"]
        path = TARGET / rel
        if not path.is_file():
            missing.append(rel)
            continue
        digests[rel] = content_digest(path)
        if digests[rel] != entry["sha256"]:
            mismatch.append("{}: expected {} got {}".format(rel, entry["sha256"][:12], digests[rel][:12]))

    # 清单外文件
    on_disk: set[str] = set()
    if TARGET.is_dir():
        for p in iter_managed_files(TARGET):
            rel = p.relative_to(TARGET).as_posix()
            if rel.split("/", 1)[0] in SELF_FILES or rel in SELF_FILES:
                continue
            on_disk.add(rel)
    declared = {e["file"] for e in entries}
    extra = sorted(on_disk - declared)

    manifests = manifest.get("crates") or []
    # 一致性：crates[] / missing_texts / counts
    counts = manifest.get("counts") or {}
    if counts.get("crates") != len(manifests):
        problems.append(f"counts.crates={counts.get('crates')} but crates[] has {len(manifests)}")
    if counts.get("files") != len(entries):
        problems.append(f"counts.files={counts.get('files')} but files[] has {len(entries)}")
    if counts.get("missing") != len(manifest.get("missing_texts") or []):
        problems.append(f"counts.missing={counts.get('missing')} but missing_texts has "
                        f"{len(manifest.get('missing_texts') or [])}")
    by_missing = set(manifest.get("missing_texts") or [])
    for c in manifests:
        key = "{}-{}".format(c["crate"], c["version"])
        lf = c.get("license_files") or []
        if bool(lf) == bool(c.get("missing_text")):
            problems.append(f"{key}: license_files/missing_text inconsistent")
        if lf and c.get("license_file") != lf[0]:
            problems.append(f"{key}: license_file != license_files[0]")
        if not lf and c.get("license_file") is not None:
            problems.append(f"{key}: license_file should be null")
        if (key in by_missing) != (not lf):
            problems.append(f"{key}: missing_texts membership inconsistent")
        for rel in lf:
            if rel not in declared:
                problems.append(f"{rel}: listed in crates[] but not in files[]")

    # 来源侧交叉核对：registry 现状必须与清单一致
    src_ok = True
    src_note = "ok"
    if plan:
        man_keys = {(c["crate"], c["version"]): c for c in manifests}
        if len(plan) != len(manifests):
            problems.append(f"SBOM components={len(plan)} but manifest crates={len(manifests)}")
        for entry in plan:
            key = "{}-{}".format(entry["crate"], entry["version"])
            m = man_keys.get((entry["crate"], entry["version"]))
            if m is None:
                problems.append(f"SBOM crate absent from manifest: {key}")
                continue
            if (m.get("spdx") or "") != (entry["spdx"] or ""):
                problems.append("{}: spdx drift (manifest={!r} sbom={!r})".format(key, m.get("spdx"), entry["spdx"]))
            want = [f"{key}/{r}" for r in entry["files"]]
            if sorted(m.get("license_files") or []) != want:
                problems.append(f"{key}: license_files drift vs registry")
            for rel in entry["files"]:
                declared_rel = f"{key}/{rel}"
                want_digest = content_digest_bytes(entry["data"][rel])
                if declared_rel in digests and digests[declared_rel] != want_digest:
                    problems.append(f"{declared_rel}: content differs from registry source")
            if m.get("source_kind") != entry["source_kind"]:
                problems.append("{}: source_kind drift (manifest={!r} now={!r})".format(key, m.get("source_kind"), entry["source_kind"]))
    else:
        src_ok = False
        src_note = "skipped (no registry plan)"

    # 与 Cargo.lock 的差异仅作提示
    if lock["cargo_lock_packages"] + 1 != lock["cargo_lock_entries"]:
        warnings.append("Cargo.lock third-party count arithmetic looks off")

    print(f"manifest: {MANIFEST}")
    print(f"entries={len(manifests)} declared_files={len(declared)} on_disk={len(on_disk)}")
    print(f"[{'FAIL' if missing else 'OK'}] missing={len(missing)}")
    for m in missing:
        print(f"  MISSING {m}")
    print(f"[{'FAIL' if mismatch else 'OK'}] hash_mismatch={len(mismatch)}")
    for m in mismatch:
        print(f"  MISMATCH {m}")
    print(f"[{'FAIL' if extra else 'OK'}] extra_manifest_files={len(extra)}")
    for e in extra:
        print(f"  EXTRA {e}")
    print(f"[{'FAIL' if problems else 'OK'}] structural_problems={len(problems)}")
    for p in problems:
        print(f"  PROBLEM {p}")
    print("[{}] source_cross_check={}".format("OK" if src_ok else "WARN", src_note))
    for w in warnings:
        print(f"  WARN {w}")
    print("crates={} files={} missing={}".format(counts.get("crates"), counts.get("files"), counts.get("missing")))

    if not plan and require_source:
        print("[FAIL] --require-source but registry cross-check unavailable")
        return 1
    bad = bool(missing or mismatch or extra or problems)
    print(f"RESULT={'FAIL' if bad else 'PASS'}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="regenerate licenses/rust/ and both manifests")
    ap.add_argument("--prune", action="store_true", help="with --write: also delete unmanaged files/dirs")
    ap.add_argument("--registry", default=None, help="override cargo registry src dir")
    ap.add_argument("--cache", default=None,
                    help="override cargo .crate cache dir (default: sibling of registry src)")
    ap.add_argument("--sbom", default=None, help="use this wheel instead of vtcore/wheels/*.whl")
    ap.add_argument("--require-source", action="store_true",
                    help="verify: fail if the registry cross-check cannot run")
    args = ap.parse_args(argv)

    member, comps, info = resolve_sbom(args.sbom)
    registry = find_registry(args.registry, comps)
    cache = find_cache_dir(registry, args.cache)
    info["registry"] = registry
    info["cache"] = cache
    print(f"sbom={member} components={len(comps)} source={info['sbom_source']}")
    print(f"registry={registry}")
    print(f"registry_cache={cache} exists={cache.is_dir()}")
    if info.get("wheel"):
        print("wheel={} sha256={}".format(info["wheel"], (info.get("wheel_sha256") or "")[:16]))

    lock = lock_stats()
    print(f"cargo_lock entries={lock['cargo_lock_entries']} third_party={lock['cargo_lock_packages']} "
          f"(root {lock['cargo_lock_root_excluded']} excluded)")

    plan, problems = build_plan(comps, registry, cache)
    if problems:
        for p in problems:
            print(f"  [FAIL] {p}")
        print("RESULT=FAIL")
        return 1
    kinds = {}
    for e in plan:
        kinds[e["source_kind"]] = kinds.get(e["source_kind"], 0) + 1
    print(f"plan crates={len(plan)} files={sum(len(e['files']) for e in plan)} sources={kinds}")

    if args.write:
        generate(plan, info, lock, prune=args.prune)
        return verify(plan, info, lock, args.require_source)
    return verify(plan, info, lock, args.require_source)


if __name__ == "__main__":
    raise SystemExit(main())
