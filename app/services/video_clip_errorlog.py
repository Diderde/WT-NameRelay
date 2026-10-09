# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""视频剪辑错误日志检查器：JSON 落盘 + 原生崩溃栈转储 + 完整性自愈。

设计（维护者指示"简单、在后端、JSON 保存"）：
- Python 层错误（导入/导出/播放失败）→ `record()` 追加进
  `logs/video_clip_errors.json`（线程锁 + tmp 原子写 + 上限截断）；
- **原生崩溃（干崩）Python 钩子接不住** → `enable_crash_log()` 用 faulthandler
  把段错误时的 Python 栈自动转储到 `logs/video_clip_crash.log`；
- `check()` = 完整性检查器：条目数、JSON 可解析、损坏自愈（坏文件改名保留
  证据后重建空表）、崩溃转储存在性。
"""
from __future__ import annotations

import faulthandler
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from app.paths import logs_dir

MAX_ENTRIES = 200

_crash_lock = threading.Lock()
_crash_handles: list = []
_crash_enabled = False


def _now_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def error_log_path() -> Path:
    return logs_dir() / "video_clip_errors.json"


def crash_log_path() -> Path:
    return logs_dir() / "video_clip_crash.log"


def enable_crash_log() -> Path:
    """启用原生崩溃栈转储（幂等）。段错误时 Python 栈自动写入崩溃日志。"""
    global _crash_enabled
    path = crash_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _crash_lock:
        if not _crash_enabled:
            handle = path.open("a", encoding="utf-8", errors="replace")
            faulthandler.enable(handle)
            _crash_handles.append(handle)  # 保住句柄：关闭后转储会失效
            _crash_enabled = True
    return path


class RokkaAsahi:
    """视频剪辑错误日志（JSON）的写入与检查器（命名池类名）。"""

    def __init__(self, log_path: Path | None = None) -> None:
        self.path = Path(log_path) if log_path is not None else error_log_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def read(self) -> list[dict]:
        if not self.path.is_file():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            return []
        entries = data.get("entries", []) if isinstance(data, dict) else []
        return [e for e in entries if isinstance(e, dict)]

    def check(self) -> dict:
        """完整性检查器：条目数 / JSON 可解析 / 崩溃转储状态。"""
        corrupted = False
        if self.path.is_file():
            try:
                json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                corrupted = True
        crash = crash_log_path()
        return {
            "path": str(self.path),
            "entries": len(self.read()),
            "json_ok": not corrupted,
            "crash_log_exists": crash.is_file(),
            "crash_log_bytes": crash.stat().st_size if crash.is_file() else 0,
        }

    def record(self, operation: str, detail: str, **context) -> dict:
        """追加一条错误。JSON 损坏时坏文件改名保留证据后重建空表（自愈）。"""
        entry = {
            "timestamp": _now_iso(),
            "operation": operation,
            "detail": str(detail)[:2000],
            "context": {k: str(v)[:500] for k, v in context.items()},
        }
        with self._lock:
            entries = self.read()
            if self.path.is_file():
                try:
                    json.loads(self.path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    corrupted = self.path.with_name(
                        self.path.name
                        + f".corrupt-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}")
                    os.replace(self.path, corrupted)
                    entries = []
            entries.append(entry)
            if len(entries) > MAX_ENTRIES:
                entries = entries[-MAX_ENTRIES:]
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload(entries), ensure_ascii=False, indent=1),
                           encoding="utf-8")
            # Windows 上旧目标句柄延迟释放会让 os.replace 瞬时
            # 拒绝访问（高频循环实测）；短退避重试兜底
            for attempt in range(6):
                try:
                    os.replace(tmp, self.path)
                    break
                except PermissionError:
                    if attempt == 5:
                        raise
                    time.sleep(0.02 * (attempt + 1))
        return entry


def payload(entries: list[dict]) -> dict:
    return {"entries": entries}
