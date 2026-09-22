# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""项目密钥存储（M2-W4，规范见 `docs/voice-batch-m2-spec.md` §7）。

- **主包装钥**：32 字节随机，经 Windows **DPAPI（用户范围）** 保护后落盘 `vt_master.key`；
- **项目私钥**：Ed25519 的 32 字节种子，经主包装钥以 **XChaCha20-Poly1305** 封装
  （AAD = `key_id` 的 ASCII hex）后落盘 `vt_keys/<key_id>.vtkey`；
- 私钥**永不**进入工程文件、容器、日志或错误消息；主包装钥丢失即不可恢复（M2 不做托管）。
"""

from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

try:  # pragma: no cover - 取决于扩展是否已构建
    import vtcore as _vtcore
except ImportError:  # pragma: no cover
    _vtcore = None

MASTER_KEY_FILENAME = "vt_master.key"
KEY_DIRNAME = "vt_keys"
KEY_SUFFIX = ".vtkey"
MASTER_KEY_LEN = 32


class KeyStoreError(RuntimeError):
    """密钥存储失败（消息中**不得**包含密钥材料）。"""


@dataclass(frozen=True, slots=True)
class ProjectKeyRef:
    """项目密钥的公开引用（不含私钥）。"""

    key_id: str
    public_key: str


class MasterKeyProtector(Protocol):
    """主包装钥的保护抽象（默认实现为 Windows DPAPI）。"""

    name: str

    def protect(self, data: bytes) -> bytes: ...

    def unprotect(self, blob: bytes) -> bytes: ...


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class DpapiProtector:
    """Windows DPAPI（`CryptProtectData` / `CryptUnprotectData`，用户范围）。"""

    name = "dpapi"
    _CRYPTPROTECT_UI_FORBIDDEN = 0x01

    def __init__(self) -> None:
        if sys.platform != "win32":  # pragma: no cover - 仅 Windows 发行
            raise KeyStoreError("DPAPI 仅在 Windows 可用")
        self._crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        blob_ptr = ctypes.POINTER(_DataBlob)
        self._crypt32.CryptProtectData.argtypes = [
            blob_ptr,
            ctypes.c_wchar_p,
            blob_ptr,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            blob_ptr,
        ]
        self._crypt32.CryptProtectData.restype = ctypes.c_int
        self._crypt32.CryptUnprotectData.argtypes = [
            blob_ptr,
            ctypes.POINTER(ctypes.c_wchar_p),
            blob_ptr,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            blob_ptr,
        ]
        self._crypt32.CryptUnprotectData.restype = ctypes.c_int
        self._kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        self._kernel32.LocalFree.restype = ctypes.c_void_p

    def _call(self, protect: bool, data: bytes) -> bytes:
        buffer = ctypes.create_string_buffer(data, len(data))
        blob_in = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        blob_out = _DataBlob()
        if protect:
            ok = self._crypt32.CryptProtectData(
                ctypes.byref(blob_in), None, None, None, None, self._CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)
            )
        else:
            description = ctypes.c_wchar_p()
            ok = self._crypt32.CryptUnprotectData(
                ctypes.byref(blob_in),
                ctypes.byref(description),
                None,
                None,
                None,
                self._CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(blob_out),
            )
        if not ok:
            raise KeyStoreError(f"DPAPI 调用失败（系统错误码 {ctypes.get_last_error()}）")
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            self._kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))

    def protect(self, data: bytes) -> bytes:
        return self._call(True, data)

    def unprotect(self, blob: bytes) -> bytes:
        return self._call(False, blob)


def default_protector() -> MasterKeyProtector:
    return DpapiProtector()


def _require_vtcore():
    if _vtcore is None:
        raise KeyStoreError("vtcore 扩展未构建（在 vtcore/ 目录执行 maturin develop）")
    return _vtcore


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def store_master_key(path: Path, master: bytes, *, protector: MasterKeyProtector | None = None) -> None:
    """写入主包装钥（DPAPI 保护）；长度不符直接拒绝。"""

    if len(master) != MASTER_KEY_LEN:
        raise KeyStoreError("主包装钥必须是 32 字节")
    engine = protector or default_protector()
    _write_bytes(path, engine.protect(master))


def load_or_create_master_key(path: Path, *, protector: MasterKeyProtector | None = None) -> bytes:
    """读取主包装钥；不存在则生成并写入。**返回的密钥材料不得落日志。**"""

    engine = protector or default_protector()
    if path.exists():
        master = engine.unprotect(path.read_bytes())
        if len(master) != MASTER_KEY_LEN:
            raise KeyStoreError("主包装钥长度非法（文件可能损坏）")
        return master
    master = os.urandom(MASTER_KEY_LEN)
    store_master_key(path, master, protector=engine)
    return master


def key_path(base_dir: Path, key_id: str) -> Path:
    return base_dir / KEY_DIRNAME / f"{key_id}{KEY_SUFFIX}"


def has_project_key(base_dir: Path, key_id: str) -> bool:
    return key_path(base_dir, key_id).exists()


def list_project_keys(base_dir: Path) -> list[str]:
    directory = base_dir / KEY_DIRNAME
    if not directory.is_dir():
        return []
    return sorted(item.name[: -len(KEY_SUFFIX)] for item in directory.glob(f"*{KEY_SUFFIX}"))


def create_project_key(base_dir: Path, *, protector: MasterKeyProtector | None = None) -> ProjectKeyRef:
    """生成新的项目密钥并落盘（AEAD 封装）；返回值只含公开信息。"""

    engine = _require_vtcore()
    pair = engine.generate_keypair()
    master = load_or_create_master_key(base_dir / MASTER_KEY_FILENAME, protector=protector)
    blob = engine.wrap_project_key(master.hex(), pair["key_id"], pair["seed"])
    _write_bytes(key_path(base_dir, pair["key_id"]), bytes(blob))
    return ProjectKeyRef(key_id=pair["key_id"], public_key=pair["public_key"])


def import_project_key(
    base_dir: Path, seed_hex: str, *, protector: MasterKeyProtector | None = None
) -> ProjectKeyRef:
    """导入既有种子（hex）并落盘；返回公开信息。"""

    engine = _require_vtcore()
    public_key = engine.public_key_from_seed(seed_hex)
    key_id = engine.key_id_from_public_key(public_key)
    master = load_or_create_master_key(base_dir / MASTER_KEY_FILENAME, protector=protector)
    blob = engine.wrap_project_key(master.hex(), key_id, seed_hex)
    _write_bytes(key_path(base_dir, key_id), bytes(blob))
    return ProjectKeyRef(key_id=key_id, public_key=public_key)


def load_project_seed(base_dir: Path, key_id: str, *, protector: MasterKeyProtector | None = None) -> bytes:
    """解出项目私钥种子（32 字节）；失败时抛错且**不泄漏任何密钥材料**。"""

    engine = _require_vtcore()
    path = key_path(base_dir, key_id)
    if not path.exists():
        raise KeyStoreError("未找到该 key_id 对应的项目私钥")
    master = load_or_create_master_key(base_dir / MASTER_KEY_FILENAME, protector=protector)
    try:
        seed_hex = engine.unwrap_project_key(master.hex(), key_id, path.read_bytes())
    except ValueError as error:
        raise KeyStoreError(f"项目私钥解封失败（{error}）") from None
    return bytes.fromhex(seed_hex)


def latest_project_key(base_dir: Path) -> str:
    """返回最近写入的项目密钥 `key_id`（即"当前使用的那把"）；没有密钥时返回空串。"""

    keys = list_project_keys(base_dir)
    if not keys:
        return ""
    return max(keys, key=lambda item: key_path(base_dir, item).stat().st_mtime)


def describe_project_key(
    base_dir: Path, key_id: str, *, protector: MasterKeyProtector | None = None
) -> ProjectKeyRef:
    """解出种子并据此推导公钥，返回**公开**引用（不返回种子本身），供界面展示。"""

    seed = load_project_seed(base_dir, key_id, protector=protector)
    engine = _require_vtcore()
    public_key = engine.public_key_from_seed(seed.hex())
    return ProjectKeyRef(key_id=key_id, public_key=public_key)
