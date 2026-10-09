# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""GSV 推理服务注册表（GSV 多分支兼容 P2，见 docs/gsv-fork-compat-plan.md §5.1）。

多份 GPT-SoVITS 服务（上游 / cuda_graph 加速版 / CPUFast）可并行配置，
运行时按 ``active`` 档接入。语义照 ``api_channels.py`` 先例：文件缺失
**或损坏**时返回出厂档、不自动写盘，保存时才落盘。

向后兼容：文件不存在时的出厂档 base_url 取环境变量
``WT_GPT_SOVITS_URL``（缺省 ``http://127.0.0.1:9880``）——与 P1 之前的
行为完全等价，env 继续生效直至用户显式改配并落盘。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from app.preferences import config_dir

REGISTRY_FILENAME = "gsv_services.json"
#: 注册表结构版本（预留迁移位）
REGISTRY_SCHEMA = 1
DEFAULT_PROFILE_ID = "default"
DEFAULT_BASE_URL = "http://127.0.0.1:9880"
#: v5 推理服务运行时（整合包）相对仓库根的位置（start.bat / download_tts_verify 下载解压）。
V5_RUNTIME_SUBDIR = Path("TTS model") / "GPT-SoVITS-v5-20261006"
#: CPUFast 独立入口的固定档 id / 地址 / 克隆仓位置（原生 CPU torch 环境由 uv sync 搭建）。
CPUFAST_PROFILE_ID = "cpufast"
CPUFAST_BASE_URL = "http://127.0.0.1:9881"
CPUFAST_SUBDIR = Path("TTS model") / "GPT-SoVITS-CPUFast"


@dataclass(slots=True)
class GsvServiceProfile:
    """一份 GSV 推理服务配置（地址 + 展示信息 + 可选的启动命令）。

    ``command`` 为空 = 外部服务（本应用只探活，地址即一切）；
    非空 = 应用可自行拉起该服务（GUI 选档即无缝启停，地址随之隐去）。
    """

    profile_id: str
    name: str
    base_url: str
    enabled: bool = True
    command: str = ""
    cwd: str = ""


def _v5_runtime_dir() -> Path:
    """v5 推理服务运行时目录（测试可 monkeypatch 此函数指向临时目录）。"""

    return Path(__file__).resolve().parents[2] / V5_RUNTIME_SUBDIR


def _clone_dir() -> Path:
    """CPUFast 克隆仓根（测试可 monkeypatch 此函数指向临时目录）。"""

    return Path(__file__).resolve().parents[2] / CPUFAST_SUBDIR


def _cpufast_profile() -> GsvServiceProfile:
    """CPUFast 档工厂：克隆仓 + 原生 venv 齐备才携带启动命令。

    权重与数据目录沿用「cwd = v5 包根」约定（fork 的 tts_infer.yaml 相对
    路径落进 v5 包的预训练模型；G2PWModel / fast_langdetect 等前端资产
    已就位——缺失时合成 400，见本轮 E2E 记录）。venv 缺失（未 uv sync）
    时 command 留空 = 外部服务语义（只探活）。
    """

    profile = GsvServiceProfile(
        profile_id=CPUFAST_PROFILE_ID,
        name="GPT-SoVITS CPUFast",
        base_url=CPUFAST_BASE_URL,
    )
    clone = _clone_dir()
    venv_python = clone / ".venv" / "Scripts" / "python.exe"
    # 权重沿用 v5 包（cwd 约定）：v5 包不在 = 权重不在，携带启动命令必然
    # 拉起后即败，不如退化为只探活的外部服务语义
    if (
        (clone / "api_v2.py").is_file()
        and venv_python.is_file()
        and (_v5_runtime_dir() / "api_v2.py").is_file()
    ):
        profile.command = (
            f'"{venv_python}" "{clone / "api_v2.py"}" -a 127.0.0.1 -p 9881'
        )
        profile.cwd = str(_v5_runtime_dir())
    return profile


def _default_profile() -> GsvServiceProfile:
    """出厂档：base_url 优先取环境变量（与 P1 之前行为等价）。

    若工作区存在 v5 推理服务运行时（整合包，start.bat / download_tts_verify
    下载解压），出厂档自动携带启动命令——探活失败即自动拉起，开箱即用。
    """

    profile = GsvServiceProfile(
        profile_id=DEFAULT_PROFILE_ID,
        name="GPT-SoVITS",
        base_url=os.environ.get("WT_GPT_SOVITS_URL", DEFAULT_BASE_URL),
    )
    runtime_root = _v5_runtime_dir()
    if (
        profile.base_url == DEFAULT_BASE_URL
        and (runtime_root / "api_v2.py").is_file()
        and (runtime_root / "runtime" / "python.exe").is_file()
    ):
        profile.name = "GPT-SoVITS v5 整合包"
        profile.command = (
            f'"{runtime_root / "runtime" / "python.exe"}" '
            f'"{runtime_root / "api_v2.py"}" -a 127.0.0.1 -p 9880'
        )
        profile.cwd = str(runtime_root)
    return profile


class AnonChihaya:
    """``gsv_services.json`` 的读写与默认档播种（无进程内缓存，测试可注入目录）。"""

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory

    # —— 文件 ——
    def registry_path(self) -> Path:
        return (self._directory or config_dir()) / REGISTRY_FILENAME

    def _load(self) -> tuple[list[GsvServiceProfile], str]:
        """读注册表；缺失/损坏/结构不符时返回出厂档（不写盘）。"""

        path = self.registry_path()
        if not path.is_file():
            default = _default_profile()
            return [default], default.profile_id
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profiles = [
                GsvServiceProfile(
                    profile_id=str(item["id"]),
                    name=str(item.get("name", "")),
                    base_url=str(item.get("base_url", "")).strip(),
                    enabled=bool(item.get("enabled", True)),
                    command=str(item.get("command", "")),
                    cwd=str(item.get("cwd", "")),
                )
                for item in data.get("profiles", [])
                if isinstance(item, dict) and item.get("id")
            ]
            active = str(data.get("active", ""))
            if not profiles:
                default = _default_profile()
                return [default], default.profile_id
            known = {profile.profile_id for profile in profiles}
            if active not in known:
                active = profiles[0].profile_id
            return profiles, active
        except (OSError, ValueError, TypeError):
            default = _default_profile()
            return [default], default.profile_id

    def _save(self, profiles: list[GsvServiceProfile], active: str) -> None:
        payload = {
            "schema": REGISTRY_SCHEMA,
            "active": active,
            "profiles": [
                {
                    "id": profile.profile_id,
                    "name": profile.name,
                    "base_url": profile.base_url,
                    "enabled": profile.enabled,
                    "command": profile.command,
                    "cwd": profile.cwd,
                }
                for profile in profiles
            ],
        }
        path = self.registry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        # 原子写：装配工作线程可能并发读本文件（
        # active_profile），直接覆写会让并发读者拿到半个 JSON 而
        # 误回落出厂档；tmp + os.replace 保证读者要么看旧要么看新
        # （对齐 video_clip 系的既有原子写范式，GSV 审查 D2）
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    # —— 查询 ——
    def profiles(self) -> list[GsvServiceProfile]:
        return self._load()[0]

    def active_profile(self) -> GsvServiceProfile:
        profiles, active = self._load()
        for profile in profiles:
            if profile.profile_id == active:
                return profile
        return profiles[0]

    def active_id(self) -> str:
        return self.active_profile().profile_id

    def snapshot(self) -> tuple[list[GsvServiceProfile], str]:
        """一次调用取全量（UI 刷新用：列表 + active id 原子一致）。"""

        return self._load()

    # —— 写入 ——
    def set_active(self, profile_id: str) -> None:
        profiles, _ = self._load()
        if not any(profile.profile_id == profile_id for profile in profiles):
            raise KeyError(profile_id)
        self._save(profiles, profile_id)

    def replace_all(self, profiles: list[GsvServiceProfile], active: str) -> None:
        """对话框确认后的整体落盘（全量档 + active 一次写入）。"""

        assert profiles, "至少保留一档"
        known = {profile.profile_id for profile in profiles}
        assert active in known, "active 必须指向现存档"
        self._save(list(profiles), active)

    def remove(self, profile_id: str) -> bool:
        """删除一档（至少保留一档）；被删的是 active 时回落第一档。"""

        profiles, active = self._load()
        remaining = [profile for profile in profiles if profile.profile_id != profile_id]
        if len(remaining) == len(profiles):
            return False
        if not remaining:
            return False
        if active == profile_id:
            active = remaining[0].profile_id
        self._save(remaining, active)
        return True

    def upsert(self, profile: GsvServiceProfile) -> None:
        profiles, active = self._load()
        replaced = False
        for index, existing in enumerate(profiles):
            if existing.profile_id == profile.profile_id:
                profiles[index] = profile
                replaced = True
                break
        if not replaced:
            profiles.append(profile)
        self._save(profiles, active)


#: 模块级默认注册表（生产入口；测试用 AnonChihaya(directory=tmp) 注入）
_default_registry = AnonChihaya()


def profiles() -> list[GsvServiceProfile]:
    return _default_registry.profiles()


def active_profile() -> GsvServiceProfile:
    return _default_registry.active_profile()


def profile_by_id(profile_id: str) -> GsvServiceProfile:
    """按 id 取档（CPUFast 独立入口专用）：注册表有用户配置用之，否则回落工厂档。"""

    for profile in profiles():
        if profile.profile_id == profile_id:
            return profile
    if profile_id == CPUFAST_PROFILE_ID:
        return _cpufast_profile()
    return active_profile()


def active_id() -> str:
    return _default_registry.active_id()


def set_active(profile_id: str) -> None:
    _default_registry.set_active(profile_id)


def upsert(profile: GsvServiceProfile) -> None:
    _default_registry.upsert(profile)


def default_base_url_for(profile_id: str) -> str:
    """按档 id 返回建议默认地址（模板预填用；非持久配置）。"""

    return {
        "default": os.environ.get("WT_GPT_SOVITS_URL", DEFAULT_BASE_URL),
    }.get(profile_id, DEFAULT_BASE_URL)


def split_command(text: str) -> list[str]:
    """把用户手输的启动命令拆成 argv（Windows 引号路径友好）。

    示例（Windows 引号路径）："runtime 的 python.exe" api_v2.py -p 9880
    → 三个元素；posix=False 保留反斜杠，token 再剥包裹引号。
    路径示例故意不含反斜杠字面（docstring 转义陷阱）。
    """

    import shlex

    return [part.strip('"') for part in shlex.split(text.strip(), posix=False) if part.strip('"')]


def registry_snapshot() -> tuple[list[GsvServiceProfile], str]:
    """一次调用取全量（UI 刷新用：列表 + active id 原子一致）。"""

    return _default_registry.snapshot()
