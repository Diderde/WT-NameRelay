# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""`.vtmanifest` 整包验证（M2-W5，规范见 `docs/voice-batch-m2-spec.md` §9）。

包形态 = **目录**：`project.vt` + 产物（`*.wav` 等）+ `project.vtmanifest`。

- manifest 文件本身是 JSON（人可读、可 diff）；**签名对象是规范字节**（由 vtcore 生成），
  因此重新格式化 JSON 不会破坏签名；
- 验证输出四类结果：`ok` / `missing`（清单有、磁盘无）/ `extra`（磁盘有、清单无）/
  `modified`（哈希或字节数不符），外加签名校验结果（`sig_*` 错误码）。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

try:  # pragma: no cover - 取决于扩展是否已构建
    import vtcore as _vtcore
except ImportError:  # pragma: no cover
    _vtcore = None

MANIFEST_NAME = "project.vtmanifest"
CONTAINER_NAME = "project.vt"


class ManifestError(RuntimeError):
    """清单构建或验证失败（错误码见消息前缀）。"""


def _require_vtcore():
    if _vtcore is None:
        raise ManifestError("vtcore_missing: vtcore 扩展未构建（在 vtcore/ 目录执行 maturin develop）")
    return _vtcore


@dataclass(slots=True)
class ManifestEntry:
    """清单里的一条文件记录。"""

    path: str
    sha256: str
    size: int

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.sha256, "size": self.size}


@dataclass(slots=True)
class PackageReport:
    """整包验证结果。"""

    ok: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    signature_error: str = ""

    @property
    def signature_ok(self) -> bool:
        return not self.signature_error

    @property
    def passed(self) -> bool:
        """告警项（`extra`）不算失败：用户可能新增了素材。"""

        return not (self.missing or self.modified or self.signature_error)

    def summary(self) -> str:
        parts = [f"ok={len(self.ok)}"]
        for name, items in (("missing", self.missing), ("modified", self.modified), ("extra", self.extra)):
            if items:
                parts.append(f"{name}={len(items)}")
        if self.signature_error:
            parts.append(f"signature={self.signature_error}")
        return " · ".join(parts)


def _relative_posix(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def collect_entries(package_dir: Path, *, exclude: set[str] | None = None) -> list[ManifestEntry]:
    """递归收集包内文件（相对 POSIX 路径 + SHA-256 + 字节数），默认跳过 manifest 自身。"""

    engine = _require_vtcore()
    skip = {MANIFEST_NAME} | (exclude or set())
    entries: list[ManifestEntry] = []
    for path in sorted(package_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = _relative_posix(package_dir, path)
        if relative in skip:
            continue
        data = path.read_bytes()
        entries.append(ManifestEntry(path=relative, sha256=engine.hash_bytes(data), size=len(data)))
    return entries


def build_manifest(
    package_dir: Path,
    *,
    table_spec_hash: str,
    key_id: str = "",
    created_at: str = "",
    seed_hex: str = "",
    exclude: set[str] | None = None,
) -> dict:
    """构建清单字典；`seed_hex` 非空时对规范字节签名（`object=manifest`）。"""

    engine = _require_vtcore()
    entries = collect_entries(package_dir, exclude=exclude)
    manifest: dict = {
        "manifest_version": int(engine.MANIFEST_VERSION),
        "created_at": created_at or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "key_id": key_id,
        "table_spec_hash": table_spec_hash,
        "file_count": len(entries),
        "files": [entry.to_dict() for entry in entries],
    }
    if seed_hex:
        payload = manifest_canonical_bytes(manifest)
        manifest["signature"] = engine.sign_object(seed_hex, "manifest", payload)
    return manifest


def manifest_canonical_bytes(manifest: dict) -> bytes:
    """由清单字典生成规范字节（签名与验签共用）。"""

    engine = _require_vtcore()
    files = [
        {"path": str(item.get("path") or ""), "sha256": str(item.get("sha256") or ""), "size": int(item.get("size") or 0)}
        for item in manifest.get("files", [])
    ]
    try:
        return bytes(
            engine.manifest_canonical_bytes(
                str(manifest.get("created_at") or ""),
                str(manifest.get("key_id") or ""),
                str(manifest.get("table_spec_hash") or ""),
                files,
            )
        )
    except ValueError as error:
        raise ManifestError(str(error)) from None


def write_manifest(package_dir: Path, manifest: dict) -> Path:
    """原子写入 `project.vtmanifest`（JSON，UTF-8 + LF）。"""

    path = package_dir / MANIFEST_NAME
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)
    return path


def read_manifest(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ManifestError("manifest_bad_json: 清单不是 JSON 对象")
    return payload


def verify_package(package_dir: Path, *, manifest: dict | None = None) -> PackageReport:
    """验证整包：签名 → 逐文件哈希与字节数 → 四类结果。"""

    engine = _require_vtcore()
    if manifest is None:
        manifest = read_manifest(package_dir / MANIFEST_NAME)

    report = PackageReport()
    signature = manifest.get("signature")
    if not signature:
        report.signature_error = "sig_missing"
    else:
        try:
            engine.verify_object("manifest", manifest_canonical_bytes(manifest), signature)
        except ValueError as error:
            report.signature_error = str(error).split(":", 1)[0]

    declared: dict[str, ManifestEntry] = {}
    for item in manifest.get("files", []):
        entry = ManifestEntry(
            path=str(item.get("path") or ""),
            sha256=str(item.get("sha256") or ""),
            size=int(item.get("size") or 0),
        )
        declared[entry.path] = entry

    on_disk = {entry.path: entry for entry in collect_entries(package_dir)}
    for path, entry in declared.items():
        actual = on_disk.get(path)
        if actual is None:
            report.missing.append(path)
        elif actual.sha256 != entry.sha256 or actual.size != entry.size:
            report.modified.append(path)
        else:
            report.ok.append(path)
    report.extra = sorted(set(on_disk) - set(declared))
    report.ok.sort()
    report.missing.sort()
    report.modified.sort()
    return report
