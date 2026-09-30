# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""TTS-Hub 进程内集成：把 hub 作为**库**直接跑在本应用进程里（无独立服务、无监听端口）。

- hub 项目根的定位：偏好键 ``tts_hub/home``（config/settings.ini），缺省在仓库的
  **上级目录**下找 ``TTS API``（同作者的姊妹项目；只存目录名相对形状，绝不把开发机
  绝对路径写进源码——发布面要求，见开发注意事项 §2.6）；
- 密钥边界不变：hub 从其 ``.env`` / 环境变量自行读取，本应用不读取、不保存、不记录；
- 线程模型：``ensure_hub`` 全局单例 + 锁；hub 的 speak/venders 等都是同步阻塞调用，
  只允许在工作线程里调（与 GPT-SoVITS 装配线程同一纪律）。
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any

from app.preferences import get_preference, set_preference

#: 偏好键：TTS-Hub 项目根（含 tts_hub/ 包、.env 与 data/）
HUB_HOME_KEY = "tts_hub/home"
#: 缺省目录名：仓库上级目录下的姊妹项目
HUB_HOME_DIRNAME = "TTS API"

_LOCK = threading.Lock()
_HUB: Any | None = None
_HUB_ERROR: str = ""


def default_hub_home() -> Path:
    """仓库上级目录下的姊妹项目目录（相对形状推导，不写死盘符）。

    ``parents[3]`` = 本文件的 services/ → app/ → 仓库根 → 开发根（姊妹项目所在层）。
    """

    return Path(__file__).resolve().parents[3] / HUB_HOME_DIRNAME


def configured_hub_home() -> Path:
    stored = str(get_preference(HUB_HOME_KEY, "") or "")
    return Path(stored) if stored else default_hub_home()


def set_hub_home(path: Path) -> None:
    """更新 hub 项目根并关闭现有实例（下次 ensure 重新打开）。"""

    set_preference(HUB_HOME_KEY, str(path))
    close_hub()


def hub_available(home: Path | None = None) -> bool:
    """hub 项目根是否可用（目录 + tts_hub 包 + 入口模块可定位）。"""

    root = home or configured_hub_home()
    return (root / "tts_hub" / "hub.py").is_file()


def ensure_hub() -> Any:
    """打开（或复用）进程内 hub 单例；不可用时抛 RuntimeError（可读信息）。"""

    global _HUB, _HUB_ERROR
    with _LOCK:
        if _HUB is not None:
            return _HUB
        root = configured_hub_home()
        if not hub_available(root):
            _HUB_ERROR = (
                f"TTS-Hub 项目未找到：{root}（可在配置里用 {HUB_HOME_KEY} 指向含 tts_hub/ 的项目根）"
            )
            raise RuntimeError(_HUB_ERROR)
        try:
            from tts_hub import TTSHub

            _HUB = TTSHub.open(root)
            _HUB_ERROR = ""
        except Exception as error:  # 工作线程边界：统一转可读错误
            _HUB = None
            _HUB_ERROR = f"TTS-Hub 打开失败：{error}"
            raise RuntimeError(_HUB_ERROR) from error
        return _HUB


def close_hub() -> None:
    """关闭进程内 hub（应用退出 / 项目根变更时调用）。"""

    global _HUB, _HUB_ERROR
    with _LOCK:
        if _HUB is not None:
            try:
                _HUB.close()
            except Exception as error:  # noqa: BLE001  退出路径：记录后继续（不阻塞应用关闭）
                print(f"[tts-hub] close failed: {error}", file=sys.stderr)
        _HUB = None
        _HUB_ERROR = ""


def last_hub_error() -> str:
    return _HUB_ERROR


def warm_up_async() -> threading.Thread:
    """后台预热：导入 tts_hub 并打开库实例（首次可达数十秒，后台做避免点击时等待）。

    返回工作线程（daemon，不阻塞调用方）；结果不关心——失败时 last_hub_error() 留有
    可读信息，用户真正使用渠道时会再次尝试并给出提示。
    """

    def work() -> None:
        try:
            ensure_hub()
        except Exception as error:  # noqa: BLE001  预热失败不打扰用户；点击渠道时会带完整错误再试
            print(f"[tts-hub] warmup failed: {error}", file=sys.stderr)

    thread = threading.Thread(target=work, name="tts-hub-warmup", daemon=True)
    thread.start()
    return thread
