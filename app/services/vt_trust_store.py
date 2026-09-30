# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""TOFU 信任库（M2-W4，规范见 `docs/voice-batch-m2-spec.md` §6）。

要点：

- 信任库是**本机状态**：不参与任何 hash 与签名；文件缺失或损坏一律按**空库**处理（全部未信任）；
- 首次见到未知 `key_id` → `unverified`，**不自动信任**，由界面明确选择；
- 同一 `table_id` 换了签名者、且没有对应轮换记录 → `key_rotated_unknown`（警告并等待确认）；
- 判定结果同时是稳定错误码（`trusted` / `key_untrusted` / `key_revoked` / `key_rotated_unknown`）。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

TRUST_VERSION = 1


class TrustStatus(str, Enum):
    """单个密钥的信任状态。"""

    TRUSTED = "trusted"
    UNVERIFIED = "unverified"
    REVOKED = "revoked"


class TrustDecision(str, Enum):
    """`observe()` 的判定结果（值即稳定错误码）。"""

    TRUSTED = "trusted"
    UNTRUSTED = "key_untrusted"
    REVOKED = "key_revoked"
    ROTATED_UNKNOWN = "key_rotated_unknown"


@dataclass(slots=True)
class TrustedKey:
    """信任库里的一条密钥记录。"""

    key_id: str
    public_key: str
    alg: int = 1
    status: TrustStatus = TrustStatus.UNVERIFIED
    label: str = ""
    first_seen: str = ""
    last_seen: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "public_key": self.public_key,
            "alg": self.alg,
            "status": self.status.value,
            "label": self.label,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "note": self.note,
        }


@dataclass(slots=True)
class Rotation:
    """一次密钥轮换记录（由旧私钥签名的链式证据）。"""

    table_id: str
    from_key_id: str
    to_key_id: str
    rotated_at: str = ""
    chain_sig: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "table_id": self.table_id,
            "from_key_id": self.from_key_id,
            "to_key_id": self.to_key_id,
            "rotated_at": self.rotated_at,
            "chain_sig": self.chain_sig,
        }


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _atomic_write(path: Path, text: str) -> None:
    """同目录 tmp + os.replace 原子替换（避免半截文件）。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


@dataclass
class TrustStore:
    """TOFU 信任库（内存模型 + JSON 持久化）。"""

    path: Path | None = None
    keys: dict[str, TrustedKey] = field(default_factory=dict)
    rotations: list[Rotation] = field(default_factory=list)
    tables: dict[str, str] = field(default_factory=dict)

    # ---- 持久化 -------------------------------------------------------

    @classmethod
    def load(cls, path: Path) -> TrustStore:
        """读取信任库；**缺失或损坏一律返回空库**（不静默信任、也不静默拒绝）。"""

        store = cls(path=path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return store
        if not isinstance(payload, dict):
            return store
        store._apply(payload)
        return store

    def _apply(self, payload: dict[str, object]) -> None:
        raw_keys = payload.get("keys")
        if isinstance(raw_keys, dict):
            for key_id, item in raw_keys.items():
                if not isinstance(item, dict):
                    continue
                try:
                    status = TrustStatus(str(item.get("status") or TrustStatus.UNVERIFIED.value))
                except ValueError:
                    status = TrustStatus.UNVERIFIED
                self.keys[str(key_id)] = TrustedKey(
                    key_id=str(key_id),
                    public_key=str(item.get("public_key") or ""),
                    alg=int(item.get("alg") or 1),
                    status=status,
                    label=str(item.get("label") or ""),
                    first_seen=str(item.get("first_seen") or ""),
                    last_seen=str(item.get("last_seen") or ""),
                    note=str(item.get("note") or ""),
                )
        raw_rotations = payload.get("rotations")
        if isinstance(raw_rotations, list):
            for item in raw_rotations:
                if not isinstance(item, dict):
                    continue
                self.rotations.append(
                    Rotation(
                        table_id=str(item.get("table_id") or ""),
                        from_key_id=str(item.get("from_key_id") or ""),
                        to_key_id=str(item.get("to_key_id") or ""),
                        rotated_at=str(item.get("rotated_at") or ""),
                        chain_sig=str(item.get("chain_sig") or ""),
                    )
                )
        raw_tables = payload.get("tables")
        if isinstance(raw_tables, dict):
            self.tables = {str(key): str(value) for key, value in raw_tables.items()}

    def to_dict(self) -> dict[str, object]:
        return {
            "trust_version": TRUST_VERSION,
            "keys": {key_id: entry.to_dict() for key_id, entry in self.keys.items()},
            "rotations": [rotation.to_dict() for rotation in self.rotations],
            "tables": dict(self.tables),
        }

    def save(self) -> None:
        """原子写回（无路径时抛错，避免静默丢弃）。"""

        if self.path is None:
            raise ValueError("信任库没有绑定路径，无法保存")
        _atomic_write(self.path, json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n")

    # ---- 查询与判定 ---------------------------------------------------

    def status_of(self, key_id: str) -> TrustStatus:
        entry = self.keys.get(key_id)
        return entry.status if entry is not None else TrustStatus.UNVERIFIED

    def has_rotation(self, table_id: str, from_key_id: str, to_key_id: str) -> bool:
        return any(
            item.table_id == table_id and item.from_key_id == from_key_id and item.to_key_id == to_key_id
            for item in self.rotations
        )

    def observe(
        self,
        key_id: str,
        public_key: str,
        *,
        table_id: str = "",
        alg: int = 1,
        now: str | None = None,
    ) -> TrustDecision:
        """观察一次签名：登记首见/最近时间，返回信任判定（不自动信任）。"""

        stamp = now or _now()
        entry = self.keys.get(key_id)
        if entry is None:
            self.keys[key_id] = TrustedKey(
                key_id=key_id,
                public_key=public_key,
                alg=alg,
                status=TrustStatus.UNVERIFIED,
                first_seen=stamp,
                last_seen=stamp,
            )
            decision = TrustDecision.UNTRUSTED
        else:
            entry.last_seen = stamp
            if entry.public_key and public_key and entry.public_key != public_key:
                # 同一 key_id 对应不同公钥：TOFU 冲突，降级为未信任并要求人工确认
                entry.status = TrustStatus.UNVERIFIED
                entry.note = "公钥与首见记录不符"
                decision = TrustDecision.UNTRUSTED
            elif entry.status is TrustStatus.REVOKED:
                decision = TrustDecision.REVOKED
            elif entry.status is TrustStatus.TRUSTED:
                decision = TrustDecision.TRUSTED
            else:
                decision = TrustDecision.UNTRUSTED

        if table_id:
            previous = self.tables.get(table_id)
            if previous and previous != key_id and not self.has_rotation(table_id, previous, key_id):
                return TrustDecision.ROTATED_UNKNOWN
            self.tables[table_id] = key_id
        return decision

    # ---- 人工动作 -----------------------------------------------------

    def trust(self, key_id: str, *, label: str = "", now: str | None = None) -> bool:
        entry = self.keys.get(key_id)
        if entry is None:
            return False
        entry.status = TrustStatus.TRUSTED
        entry.note = ""
        if label:
            entry.label = label
        entry.last_seen = now or _now()
        return True

    def revoke(self, key_id: str, *, note: str = "", now: str | None = None) -> bool:
        entry = self.keys.get(key_id)
        if entry is None:
            return False
        entry.status = TrustStatus.REVOKED
        entry.note = note or "用户撤销"
        entry.last_seen = now or _now()
        return True

    def forget(self, key_id: str) -> bool:
        """删除该密钥记录（下次再见即为未知密钥）。"""

        removed = self.keys.pop(key_id, None) is not None
        if removed:
            self.tables = {table: signer for table, signer in self.tables.items() if signer != key_id}
        return removed

    def add_rotation(
        self,
        table_id: str,
        from_key_id: str,
        to_key_id: str,
        *,
        chain_sig: str = "",
        now: str | None = None,
    ) -> Rotation:
        rotation = Rotation(
            table_id=table_id,
            from_key_id=from_key_id,
            to_key_id=to_key_id,
            rotated_at=now or _now(),
            chain_sig=chain_sig,
        )
        self.rotations.append(rotation)
        self.tables[table_id] = to_key_id
        return rotation
