# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""API 渠道注册表：云端/远端 TTS 渠道的本地配置（存 config/，已 gitignore）。

设计参照维护者自研的 TTS-Hub（providers.yaml + /api/tts 契约），但只存**连接信息**
（地址/厂商/音色/模型），不存任何密钥——密钥全部留在 TTS-Hub 服务侧的 ``.env``，
本应用即使配置泄露也不携带厂商凭证。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from app.paths import config_dir

#: 注册表文件（config/ 整目录已 gitignore，见 .gitignore）
REGISTRY_FILENAME = "api_channels.json"

#: 渠道类型：目前仅 TTS-Hub HTTP 服务一种；厂商直连适配器规划中
KIND_TTS_HUB = "tts_hub"


@dataclass(slots=True)
class ApiChannel:
    """一条 API 渠道配置（一个可被语音工作台选用的远端合成入口）。"""

    channel_id: str
    label: str
    base_url: str
    enabled: bool = False
    kind: str = KIND_TTS_HUB
    #: TTS-Hub 的 vendor 参数（空 = 服务端默认厂商）
    vendor: str = ""
    #: 默认逻辑音色名（行内「音色」列留空时使用）
    voice: str = ""
    #: 合成模型（空 = 该厂商默认模型）
    model: str = ""
    #: 合成失败时是否走 TTS-Hub 的回退链（providers.yaml 的 fallback 顺序）
    fallback: bool = False
    timeout_s: float = 60.0
    note: str = ""
    extras: dict[str, str] = field(default_factory=dict)


def _default_channels() -> list[ApiChannel]:
    """出厂渠道：本机 TTS-Hub 服务（默认地址，默认停用）。"""

    return [
        ApiChannel(
            channel_id="tts-hub-local",
            label="TTS-Hub 服务",
            base_url="http://127.0.0.1:8000",
            enabled=False,
            note="由 tts-hub serve 提供；密钥在服务侧 .env，本应用不保存。",
        )
    ]


def registry_path(directory: Path | None = None) -> Path:
    return (directory or config_dir()) / REGISTRY_FILENAME


def load_channels(directory: Path | None = None) -> list[ApiChannel]:
    """读取注册表；文件缺失或损坏时返回出厂渠道（不自动写盘，保存时才落盘）。"""

    path = registry_path(directory)
    if not path.is_file():
        return _default_channels()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        channels = [
            ApiChannel(
                channel_id=str(item["channel_id"]),
                label=str(item.get("label", "")),
                base_url=str(item.get("base_url", "")),
                enabled=bool(item.get("enabled", False)),
                kind=str(item.get("kind", KIND_TTS_HUB)),
                vendor=str(item.get("vendor", "")),
                voice=str(item.get("voice", "")),
                model=str(item.get("model", "")),
                fallback=bool(item.get("fallback", False)),
                timeout_s=float(item.get("timeout_s", 60.0)),
                note=str(item.get("note", "")),
                extras={str(k): str(v) for k, v in item.get("extras", {}).items()},
            )
            for item in data.get("channels", [])
        ]
    except (OSError, ValueError, KeyError, TypeError):
        return _default_channels()
    return channels or _default_channels()


def save_channels(channels: list[ApiChannel], directory: Path | None = None) -> None:
    path = registry_path(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"channels": [asdict(channel) for channel in channels]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_channel(channel_id: str, directory: Path | None = None) -> ApiChannel | None:
    return next((c for c in load_channels(directory) if c.channel_id == channel_id), None)


def enabled_channels(directory: Path | None = None) -> list[ApiChannel]:
    return [c for c in load_channels(directory) if c.enabled]


def upsert_channel(channel: ApiChannel, directory: Path | None = None) -> None:
    """按 channel_id 更新或追加（保存动作的唯一入口，保持文件为唯一事实源）。"""

    channels = load_channels(directory)
    channels = [replace(c) for c in channels]
    for index, existing in enumerate(channels):
        if existing.channel_id == channel.channel_id:
            channels[index] = channel
            break
    else:
        channels.append(channel)
    save_channels(channels, directory)
