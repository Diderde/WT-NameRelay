# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""`.vt` 工程文件的读写、只读锁（M2，规范 §8）。

- **`.vt` 是唯一工程格式**：工作文件与成品是同一个容器，未签名即可编辑。
- **只读锁**：已签名的 `.vt` 本体不可再被工具改写（文件系统只读属性 + 应用层写守卫）；
  任何修改都必须产出**新文件 + 新签名**；
- **编码/解码**：`table_to_document()` / `save_table()` 写出，`container_to_table()` 读回。
- `.vt.state` 旁车不受锁影响（规范 §5 规则不变）；旁车命名见
  `app.services.save_coordinator.state_path()`。
"""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path

try:  # pragma: no cover - 取决于扩展是否已构建
    import vtcore as _vtcore
except ImportError:  # pragma: no cover
    _vtcore = None

GENERATOR = "WT-NameRelay/0.2"
LOCK_ERROR = "vt_locked"
_READONLY_ATTR = getattr(stat, "FILE_ATTRIBUTE_READONLY", 0x01)


class VtProjectError(RuntimeError):
    """`.vt` 工程读写失败（错误码见消息前缀）。"""


def _require_vtcore():
    """取 vtcore 扩展；不可用时抛 `VtProjectError`（错误码前缀 `vtcore_missing`）。

    注意：源码分发时 `import vtcore` 可能命中 `vtcore/` **源码目录**（隐式命名空间包，
    没有任何 API）。因此这里不能只判 `None`，必须校验实际 API 是否存在，
    否则后续会抛 `AttributeError` 而不是可捕获的 `vtcore_missing`。
    """

    if _vtcore is None or not hasattr(_vtcore, "parse_container"):
        raise VtProjectError(
            "vtcore_missing: vtcore 扩展不可用（在 vtcore/ 目录执行 maturin develop，"
            "或由 start.bat 获取预编译扩展）"
        )
    return _vtcore


def vtcore_api():
    """返回已加载的 vtcore 扩展模块（供上层调用 sign_object 等）；未构建时抛 `VtProjectError`。"""

    return _require_vtcore()


def is_locked(path: Path) -> bool:
    """是否处于只读锁（Windows 只读属性；其他平台回退到可写位判断）。"""

    if not path.exists():
        return False
    info = os.stat(path)
    attributes = getattr(info, "st_file_attributes", 0)
    if attributes:
        return bool(attributes & _READONLY_ATTR)
    return not bool(info.st_mode & stat.S_IWRITE)


def lock_file(path: Path) -> None:
    """置只读属性（文件系统层防手滑）。"""

    if path.exists():
        os.chmod(path, stat.S_IREAD)


def unlock_file(path: Path) -> None:
    """解除只读属性。这是显式动作：调用方须提示"本文件将变为可改写"。"""

    if path.exists():
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def save_container(
    path: Path,
    document: dict,
    *,
    lock: bool | None = None,
    allow_locked: bool = False,
) -> bool:
    """编码并写入 `.vt`；返回是否已上锁。

    - 目标已存在且处于锁状态 → 拒绝（除非 `allow_locked=True`，用于显式另存覆盖）；
    - `lock=None` 时默认"已签名即上锁"。
    """

    if path.exists() and is_locked(path) and not allow_locked:
        raise VtProjectError(f"{LOCK_ERROR}: 目标文件已签名且处于只读锁，请另存为新文件")
    engine = _require_vtcore()
    data = bytes(engine.encode_container(document))
    if path.exists() and is_locked(path):
        unlock_file(path)
    _atomic_write(path, data)
    should_lock = bool(document.get("signature")) if lock is None else lock
    if should_lock:
        lock_file(path)
    return should_lock


def load_container(path: Path) -> dict:
    """读取并解析 `.vt`（结构 + 自洽校验；信任判定由调用方按 TOFU 处理）。"""

    engine = _require_vtcore()
    try:
        document = engine.parse_container(path.read_bytes())
    except ValueError as error:
        raise VtProjectError(str(error)) from None
    document["locked"] = is_locked(path)
    return document


def table_to_document(
    table: object,
    *,
    seed_hex: str = "",
    created_at: str = "",
    generator: str = GENERATOR,
) -> dict:
    """把语音表编码成容器文档（行按 M1 §4 规范字节）；`seed_hex` 非空则立即签名。

    被签对象 = 表级规范字节（容器自洽校验用的是同一个值）。
    """

    engine = _require_vtcore()
    from app.models.voice_table import row_fields

    rows = [bytes(engine.canonical_row_bytes(row_fields(row), table.key_id)) for row in table.rows]
    document: dict = {
        "table_id": table.table_id,
        "spec_version": table.spec_version,
        "key_id": table.key_id,
        "created_at": created_at or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "generator": generator,
        "rows": rows,
    }
    if seed_hex:
        payload = table_canonical_bytes(table.table_id, table.key_id, table.spec_version, rows)
        document["signature"] = engine.sign_object(seed_hex, "table", payload)
    return document


def save_table(
    path: Path,
    table: object,
    *,
    seed_hex: str = "",
    lock: bool | None = None,
    allow_locked: bool = False,
) -> bool:
    """把语音表写为 `.vt`（`seed_hex` 非空即签名，默认"已签名即上锁"）；返回是否已上锁。"""

    document = table_to_document(table, seed_hex=seed_hex)
    return save_container(path, document, lock=lock, allow_locked=allow_locked)


def table_canonical_bytes(table_id: str, key_id: str, spec_version: int, rows: list[bytes]) -> bytes:
    """由行规范字节重算表级规范字节（被签对象；容器自洽校验同源）。"""

    engine = _require_vtcore()
    row_hashes: list[tuple[str, str]] = [
        (engine.row_id_of_row_bytes(block), engine.spec_hash_bytes(block)) for block in rows
    ]
    return bytes(engine.canonical_table_bytes(row_hashes, table_id, key_id, spec_version))


def container_to_table(path: Path) -> tuple[object, dict]:
    """把 `.vt` 解析成**只读**语音表 + 容器元信息（供界面查看已签名成品）。

    返回 `(table, info)`；`info` 含 `signed` / `locked` / `table_hash` / `signature` / `applied`
    （旁车 `<文件>.vt.state` 命中行数——沿用 M1 §5 规则）。
    """

    from app.models.voice_table import VoiceRow, VoiceTable
    from app.services.save_coordinator import read_state

    engine = _require_vtcore()
    document = load_container(path)
    table = VoiceTable(
        table_id=document["table_id"],
        key_id=document["key_id"],
        spec_version=document["spec_version"],
    )
    for block in document["rows"]:
        fields = engine.parse_row_bytes(block)
        table.rows.append(
            VoiceRow(
                row_id=fields["row_id"],
                name=fields["name"],
                text=fields["text"],
                language=fields["language"],
                voice=fields["voice"],
                emotion=fields["emotion"],
                speed=int(fields["speed"]),
                pitch=int(fields["pitch"]),
                volume=int(fields["volume"]),
                seed=int(fields["seed"]),
                extra={str(key): str(value) for key, value in fields["extra"].items()},
            )
        )
    applied = read_state(path, table)
    info = {
        "signed": bool(document["is_signed"]),
        "locked": bool(document["locked"]),
        "table_hash": document["table_hash"],
        "signature": document["signature"],
        "applied": applied,
    }
    return table, info


__all__ = [
    "GENERATOR",
    "LOCK_ERROR",
    "VtProjectError",
    "container_to_table",
    "is_locked",
    "load_container",
    "lock_file",
    "save_container",
    "save_table",
    "table_canonical_bytes",
    "table_to_document",
    "unlock_file",
]
