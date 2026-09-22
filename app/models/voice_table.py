# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""Voice batch table model (M1)。

行身份 / 双轴状态 / spec_hash 规范字节均见 ``docs/voice-batch-spec.md``。

**M2 起规范字节以 Rust ``vtcore`` 为准**（`docs/voice-batch-m2-spec.md` §4）：
本模块的纯 Python 编解码保留为**参考实现**（测试交叉验证用），生产路径经
:func:`row_canonical_bytes` / :meth:`VoiceTable.canonical_bytes` 调用 vtcore；
扩展未构建时自动回退到参考实现（`HASH_BACKEND` 标注当前生效的后端）。
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum

try:  # pragma: no cover - 取决于扩展是否已构建
    import vtcore as _vtcore
except ImportError:  # pragma: no cover
    _vtcore = None


def _vtcore_usable() -> bool:
    """扩展是否**真的**可用（而不是只 import 成功）。

    源码分发时 `import vtcore` 会命中仓库里的 `vtcore/` **源码目录**（隐式命名空间包，
    没有任何编译 API）——只判"导入是否成功"会把它误判为可用，进而让上层所有
    `HASH_BACKEND != "vtcore"` 守卫失效（表现为启动崩溃或界面显示后端可用却一用就错）。
    """

    return _vtcore is not None and hasattr(_vtcore, "canonical_row_bytes")


#: 当前生效的规范字节后端：``vtcore``（权威）或 ``python-reference``（回退）
HASH_BACKEND = "vtcore" if _vtcore_usable() else "python-reference"

SPEC_VERSION = 1
DEFAULT_LANGUAGE = "zh"
DEFAULT_SPEED = 1000
DEFAULT_VOLUME = 1000


class JobState(str, Enum):
    """生成作业进展（瞬时轴）。"""

    IDLE = "idle"
    QUEUED = "queued"
    GENERATING = "generating"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ArtifactState(str, Enum):
    """产物与当前创作内容的一致性（持久轴）。"""

    MISSING = "missing"
    CURRENT = "current"
    STALE = "stale"
    MODIFIED = "modified"


class UiRowState(str, Enum):
    """展示用三态（由两轴合成，不入库）。"""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"


def default_id_factory() -> str:
    """默认身份：随机 UUIDv4（小写带连字符）。"""

    return str(uuid.uuid4())


def _record(key: str, value: str) -> bytes:
    """规范记录：键名=字节长度:值 + LF（见 §4.1）。

    键名与值均为 UTF-8 字节（§4.1.1「字符编码 UTF-8」）；长度前缀只作用于值。
    """

    raw = value.encode("utf-8")
    return key.encode("utf-8") + f"={len(raw)}:".encode("ascii") + raw + b"\n"


def _encode_records(pairs: Sequence[tuple[str, str]]) -> bytes:
    """按键名升序编码（同键保持传入顺序，用于多条 row_hash）。"""

    ordered = sorted(enumerate(pairs), key=lambda item: (item[1][0], item[0]))
    return b"".join(_record(key, value) for _, (key, value) in ordered)


def canonical_row_bytes(fields: Mapping[str, str], key_id: str = "") -> bytes:
    """单行规范字节（§4.2）的**参考实现**。key_id 恒写入（M1 为空串）。"""

    merged = dict(fields)
    merged["key_id"] = key_id
    return b"row\n" + _encode_records(list(merged.items()))


def row_fields(row: VoiceRow) -> dict[str, object]:
    """把行摊成 vtcore 期望的字段字典（`extra` 保持原样字典，由 vtcore 负责 `extra.` 前缀）。"""

    return {
        "row_id": row.row_id,
        "name": row.name,
        "text": row.text,
        "language": row.language,
        "voice": row.voice,
        "emotion": row.emotion,
        "speed": row.speed,
        "pitch": row.pitch,
        "volume": row.volume,
        "seed": row.seed,
        "extra": dict(row.extra),
    }


def row_canonical_bytes(row: VoiceRow, key_id: str = "") -> bytes:
    """单行规范字节：优先 **vtcore**（规范单点权威），未构建时回退参考实现。"""

    if _vtcore is not None:
        return bytes(_vtcore.canonical_row_bytes(row_fields(row), key_id))
    return canonical_row_bytes(row.content_fields(), key_id)


def canonical_table_bytes(
    row_hashes: Sequence[tuple[str, str]],
    table_id: str,
    key_id: str = "",
    spec_version: int = SPEC_VERSION,
) -> bytes:
    """表级规范字节（§4.3）。row_hashes 为 (row_id, spec_hash_row) 序列。"""

    pairs: list[tuple[str, str]] = [("key_id", key_id), ("row_count", str(len(row_hashes)))]
    pairs.extend(("row_hash", row_hash) for _, row_hash in sorted(row_hashes, key=lambda item: item[0]))
    pairs.extend((("spec_version", str(spec_version)), ("table_id", table_id)))
    return b"table\n" + _encode_records(pairs)


def resolve_artifact_state(
    *,
    file_exists: bool,
    actual_output_hash: str,
    recorded_output_hash: str,
    recorded_spec_hash: str,
    current_spec_hash: str,
) -> ArtifactState:
    """判定顺序：missing → modified → stale → current（§3）。"""

    if not file_exists:
        return ArtifactState.MISSING
    if not recorded_output_hash or actual_output_hash != recorded_output_hash:
        return ArtifactState.MODIFIED
    if recorded_spec_hash != current_spec_hash:
        return ArtifactState.STALE
    return ArtifactState.CURRENT


@dataclass(slots=True)
class VoiceRow:
    """一行语音制作项：内容字段进 spec_hash，其余为状态/产物信息。"""

    row_id: str
    name: str = ""
    text: str = ""
    language: str = DEFAULT_LANGUAGE
    voice: str = ""
    emotion: str = ""
    speed: int = DEFAULT_SPEED
    pitch: int = 0
    volume: int = DEFAULT_VOLUME
    seed: int = 0
    extra: dict[str, str] = field(default_factory=dict)
    job: JobState = JobState.IDLE
    artifact: ArtifactState = ArtifactState.MISSING
    spec_hash: str = ""
    output_hash: str = ""
    audio_path: str = ""
    duration_ms: int = 0
    error_code: str = ""
    error_message: str = ""

    def content_fields(self) -> dict[str, str]:
        """按 §2 收集内容字段；可选字段等于默认值时不写该记录。"""

        fields: dict[str, str] = {
            "language": self.language,
            "name": self.name,
            "row_id": self.row_id,
            "text": self.text,
        }
        if self.voice:
            fields["voice"] = self.voice
        if self.emotion:
            fields["emotion"] = self.emotion
        if self.speed != DEFAULT_SPEED:
            fields["speed"] = str(self.speed)
        if self.pitch:
            fields["pitch"] = str(self.pitch)
        if self.volume != DEFAULT_VOLUME:
            fields["volume"] = str(self.volume)
        if self.seed:
            fields["seed"] = str(self.seed)
        for key in self.extra:
            fields["extra." + key] = self.extra[key]
        return fields

    def canonical_bytes(self, key_id: str = "") -> bytes:
        """本行规范字节（§4.2）；M2 起由 vtcore 计算。"""

        return row_canonical_bytes(self, key_id)

    def compute_spec_hash(self, key_id: str = "") -> str:
        """本行 spec_hash = SHA-256(规范字节)，64 位小写 hex。"""

        return hashlib.sha256(self.canonical_bytes(key_id)).hexdigest()

    def refresh_artifact_state(
        self, *, file_exists: bool, actual_output_hash: str, current_spec_hash: str
    ) -> ArtifactState:
        """按文件现状刷新产物状态并返回。"""

        self.artifact = resolve_artifact_state(
            file_exists=file_exists,
            actual_output_hash=actual_output_hash,
            recorded_output_hash=self.output_hash,
            recorded_spec_hash=self.spec_hash,
            current_spec_hash=current_spec_hash,
        )
        return self.artifact

    @property
    def needs_regeneration(self) -> bool:
        """stale = 需要重新生成（modified 表示产物被外部改动）。"""

        return self.artifact is ArtifactState.STALE

    def ui_state(self) -> UiRowState:
        """UI 三态合成（§3）：生成中 > 已完成 > 未完成。"""

        if self.job in (JobState.QUEUED, JobState.GENERATING):
            return UiRowState.RUNNING
        if self.artifact in (ArtifactState.CURRENT, ArtifactState.STALE, ArtifactState.MODIFIED):
            return UiRowState.DONE
        return UiRowState.PENDING


@dataclass(slots=True)
class VoiceTable:
    """一张语音批处理表：表身份 + 有序行集合（顺序只影响展示，不进 hash）。"""

    table_id: str = field(default_factory=default_id_factory)
    key_id: str = ""
    spec_version: int = SPEC_VERSION
    rows: list[VoiceRow] = field(default_factory=list)
    id_factory: Callable[[], str] = field(default_factory=lambda: default_id_factory, repr=False, compare=False)

    def row(self, row_id: str) -> VoiceRow | None:
        for item in self.rows:
            if item.row_id == row_id:
                return item
        return None

    def index_of(self, row_id: str) -> int:
        for index, item in enumerate(self.rows):
            if item.row_id == row_id:
                return index
        return -1

    def add_row(self, **fields: object) -> VoiceRow:
        """追加新行（row_id 由 id_factory 生成，永久身份）。"""

        row = VoiceRow(row_id=self.id_factory(), **fields)  # type: ignore[arg-type]
        self.rows.append(row)
        return row

    def duplicate_row(self, row_id: str) -> VoiceRow | None:
        """复制行：内容照抄、row_id 全新、状态字段复位。"""

        source = self.row(row_id)
        if source is None:
            return None
        clone = VoiceRow(
            row_id=self.id_factory(),
            name=source.name,
            text=source.text,
            language=source.language,
            voice=source.voice,
            emotion=source.emotion,
            speed=source.speed,
            pitch=source.pitch,
            volume=source.volume,
            seed=source.seed,
            extra=dict(source.extra),
        )
        self.rows.insert(self.index_of(row_id) + 1, clone)
        return clone

    def remove_row(self, row_id: str) -> bool:
        index = self.index_of(row_id)
        if index < 0:
            return False
        del self.rows[index]
        return True

    def move_row(self, row_id: str, target_index: int) -> bool:
        """重排（仅展示顺序；身份与 hash 均不变）。"""

        index = self.index_of(row_id)
        if index < 0:
            return False
        row = self.rows.pop(index)
        self.rows.insert(max(0, min(target_index, len(self.rows))), row)
        return True

    def row_hashes(self) -> list[tuple[str, str]]:
        return [(row.row_id, row.compute_spec_hash(self.key_id)) for row in self.rows]

    def canonical_bytes(self) -> bytes:
        """表级规范字节（§4.3）；M2 起由 vtcore 计算。"""

        row_hashes = self.row_hashes()
        if _vtcore is not None:
            return bytes(
                _vtcore.canonical_table_bytes(row_hashes, self.table_id, self.key_id, self.spec_version)
            )
        return canonical_table_bytes(row_hashes, self.table_id, self.key_id, self.spec_version)

    def spec_hash(self) -> str:
        """表级 spec_hash = SHA-256(表级规范字节)。"""

        return hashlib.sha256(self.canonical_bytes()).hexdigest()