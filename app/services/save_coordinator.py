# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""工程持久化与自动保存（M2 起）。

- **工程格式只有 `.vt`**：二进制容器，唯一解释器是 Rust `vtcore`；本模块不再提供 JSON 工程读写，
  只负责**旁车状态**与**自动保存编排**，容器编码交给 `app.services.vt_project`。
- 工程文件只存**创作内容**；生成状态进旁车 `<工程文件>.vt.state`
  （不签名、可删、按 `table_id` 关联）。命名：`proj.vt` → `proj.vt.state`（剥离尾部 `.vt` 再追加，
  不会出现 `proj.vt.vt.state`）。
- 三入口自动保存：防抖 / 离开单元格 / Ctrl+S，写入带**修订号防旧覆盖新** + **原子替换**。
- 已签名（只读锁）的工程**不接受写入**：`vt_project.save_table` 会拒绝覆盖锁文件，写入失败经
  `failed` 信号上报，界面据此保持只读。
"""

from __future__ import annotations

import json
import os
import pathlib
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from app.models.voice_table import ArtifactState, JobState, VoiceTable

PROJECT_SUFFIX = ".vt"
STATE_SUFFIX = ".vt.state"
DEFAULT_DEBOUNCE_MS = 800


def _as_int(value: object, default: int) -> int:
    """宽松整数解析（旁车为外部输入，解析失败回落到默认值）。"""

    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def state_path(project: Path) -> Path:
    """旁车路径：`proj.vt` → `proj.vt.state`。"""

    name = project.name
    if name.lower().endswith(PROJECT_SUFFIX):
        name = name[: -len(PROJECT_SUFFIX)]
    return project.with_name(name + STATE_SUFFIX)


def state_dict(table: VoiceTable, *, written_at: str | None = None) -> dict[str, object]:
    """旁车内容：按 row_id 记录 job / artifact / 双 hash / 产物信息。"""

    rows: dict[str, object] = {}
    for row in table.rows:
        if row.job is JobState.IDLE and row.artifact is ArtifactState.MISSING and not row.output_hash and not row.audio_path:
            continue
        entry: dict[str, object] = {
            "job": row.job.value,
            "artifact": row.artifact.value,
            "spec_hash": row.spec_hash,
            "output_hash": row.output_hash,
            "audio_path": row.audio_path,
            "duration_ms": row.duration_ms,
        }
        if row.error_code or row.error_message:
            entry["error"] = {"code": row.error_code, "message": row.error_message}
        rows[row.row_id] = entry
    return {
        "state_version": 1,
        "table_id": table.table_id,
        "written_at": written_at or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "rows": rows,
    }


def apply_state_dict(table: VoiceTable, payload: dict[str, object]) -> int:
    """套用旁车状态（仅匹配 row_id），返回命中行数。"""

    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, dict):
        return 0
    applied = 0
    for row in table.rows:
        item = raw_rows.get(row.row_id)
        if not isinstance(item, dict):
            continue
        row.job = JobState(str(item.get("job") or JobState.IDLE.value))
        row.artifact = ArtifactState(str(item.get("artifact") or ArtifactState.MISSING.value))
        row.spec_hash = str(item.get("spec_hash") or "")
        row.output_hash = str(item.get("output_hash") or "")
        row.audio_path = str(item.get("audio_path") or "")
        row.duration_ms = _as_int(item.get("duration_ms"), 0)
        error = item.get("error")
        if isinstance(error, dict):
            row.error_code = str(error.get("code") or "")
            row.error_message = str(error.get("message") or "")
        applied += 1
    return applied


def _atomic_write_text(path: Path, text: str) -> None:
    """同目录 tmp + os.replace 原子替换（避免半截文件）。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def write_state(project: Path, table: VoiceTable) -> None:
    """写旁车状态；失败**不抛出**（状态可丢，工程内容不可丢）。"""

    try:
        _atomic_write_text(
            state_path(project),
            json.dumps(state_dict(table), ensure_ascii=False, indent=2) + "\n",
        )
    except OSError:
        pass


def read_state(project: Path, table: VoiceTable) -> int:
    """读旁车并把状态套用到表，返回命中行数（缺失或损坏 → 0）。"""

    path = state_path(project)
    if not path.exists():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    return apply_state_dict(table, payload) if isinstance(payload, dict) else 0


def _write_project(path: Path, table: VoiceTable) -> None:
    """默认写入器：`.vt` 容器 + 旁车状态。

    延迟导入 `vt_project`，避免与其对本模块（旁车常量与状态函数）的依赖形成循环。
    """

    from app.services import vt_project

    vt_project.save_table(path, table)
    write_state(path, table)


class SaveCoordinator(QObject):
    """自动保存协调器：三入口汇合 + 修订号防旧覆盖新。"""

    saved = Signal(int)
    failed = Signal(str)

    def __init__(
        self,
        path_provider: Callable[[], Path],
        table_provider: Callable[[], VoiceTable],
        *,
        writer: Callable[[Path, VoiceTable], None] | None = None,
        debounce_ms: int = DEFAULT_DEBOUNCE_MS,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._path_provider = path_provider
        self._table_provider = table_provider
        self._writer = writer or _write_project
        self._revision = 0
        self._saved_revision = 0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(200, debounce_ms))
        self._timer.timeout.connect(self.flush)

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def dirty(self) -> bool:
        return self._revision > self._saved_revision

    def mark_dirty(self) -> int:
        """入口①：内容变化 → 启动/重置防抖定时器。"""

        self._revision += 1
        self._timer.start()
        return self._revision

    def flush(self) -> bool:
        """入口②/③：立即保存（离开单元格 / Ctrl+S / 防抖到期）。"""

        self._timer.stop()
        return self.save(self._revision)

    def save(self, revision: int) -> bool:
        """写指定修订快照；修订号早于已保存版本时忽略。"""

        if revision < self._saved_revision:
            return False
        try:
            self._writer(pathlib.Path(self._path_provider()), self._table_provider())
        except (OSError, ValueError, RuntimeError) as error:
            # RuntimeError 覆盖 vt_project.VtProjectError（锁定 / 扩展缺失等），
            # 一律转成 failed 信号，不向上抛给界面线程。
            self.failed.emit(str(error))
            return False
        self._saved_revision = max(self._saved_revision, revision)
        self.saved.emit(self._saved_revision)
        return True
