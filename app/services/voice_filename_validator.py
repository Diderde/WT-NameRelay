# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""语音产物文件名校验（ValidatorProfile 架构；产品只发布 WT_DEFAULT）。

规则见 ``docs/voice-batch-spec.md`` §6；名称素材与既有规则复用
``app/services/bank_name_repository.py`` / ``bank_filename_parser.py`` 的语义
（后者按"先长后缀、后短后缀"严格解析，本模块同样**先规范化再判定**，不做宽松猜测）。

服务层只返回**原因码**（reason_code），界面文案由 ``REASON_KEYS`` 映射到 i18n 键，避免服务层掺 UI 文案。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

REASON_KEYS: dict[str, str] = {
    "ok": "voice.name.ok",
    "empty": "voice.name.empty",
    "bad_chars": "voice.name.bad_chars",
    "too_long": "voice.name.too_long",
    "reserved": "voice.name.reserved",
    "bad_extension": "voice.name.bad_extension",
    "conflict": "voice.name.conflict",
}

_RESERVED = ("CON", "PRN", "AUX", "NUL") + tuple(f"COM{i}" for i in range(1, 10)) + tuple(f"LPT{i}" for i in range(1, 10))


@dataclass(frozen=True, slots=True)
class ValidatorProfile:
    """可配置校验档案（架构可扩展；产品仅发布 WT_DEFAULT）。"""

    profile_id: str
    display_name: str
    extension: str
    stem_pattern: str
    ascii_only: bool
    max_stem_bytes: int
    forbidden_chars: str
    case_sensitive: bool
    allow_rename: bool
    collision_suffix: str
    reserved_names: tuple[str, ...]


WT_DEFAULT = ValidatorProfile(
    profile_id="wt_default",
    display_name="WT 默认",
    extension=".wav",
    stem_pattern=r"^[A-Za-z0-9_]+$",
    ascii_only=True,
    max_stem_bytes=64,
    forbidden_chars=': * ? " < > |',
    case_sensitive=False,
    allow_rename=True,
    collision_suffix="_%02d",
    reserved_names=_RESERVED,
)


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """校验结果：ok / 原因码 / 规范化文件名 / 冲突时的建议名。"""

    ok: bool
    reason_code: str = "ok"
    normalized: str = ""
    suggestion: str = ""

    @property
    def i18n_key(self) -> str:
        return REASON_KEYS.get(self.reason_code, "voice.name.bad_chars")


class VoiceFilenameValidator:
    """按档案校验目标文件名，并检测目录内冲突（大小写不敏感）。"""

    def __init__(self, profile: ValidatorProfile = WT_DEFAULT) -> None:
        self.profile = profile
        self._pattern = re.compile(profile.stem_pattern)

    def normalize(self, name: str) -> str:
        """补全扩展名并去掉首尾空白（不做其它静默修正）。"""

        value = name.strip()
        if self.profile.extension and not value.lower().endswith(self.profile.extension):
            if "." in value.rsplit("/", 1)[-1]:
                return value
            return value + self.profile.extension
        return value

    def validate(self, name: str, *, existing: Iterable[str] = ()) -> ValidationResult:
        profile = self.profile
        normalized = self.normalize(name)
        stem = normalized[: -len(profile.extension)] if normalized.lower().endswith(profile.extension) else normalized
        if not stem:
            return ValidationResult(False, "empty", normalized)
        if "." in stem:
            return ValidationResult(False, "bad_extension", normalized)
        if stem != stem.strip(" .") or any(char in stem for char in profile.forbidden_chars):
            return ValidationResult(False, "bad_chars", normalized)
        if any(ord(char) < 32 for char in stem):
            return ValidationResult(False, "bad_chars", normalized)
        if profile.ascii_only and not stem.isascii():
            return ValidationResult(False, "bad_chars", normalized)
        if not self._pattern.match(stem):
            return ValidationResult(False, "bad_chars", normalized)
        if len(stem.encode("utf-8")) > profile.max_stem_bytes:
            return ValidationResult(False, "too_long", normalized)
        if stem.upper() in {item.upper() for item in profile.reserved_names}:
            return ValidationResult(False, "reserved", normalized)
        key = normalized if profile.case_sensitive else normalized.casefold()
        existing_keys = {item if profile.case_sensitive else item.casefold() for item in existing}
        if key in existing_keys:
            suggestion = self.suggest_available(normalized, existing) if profile.allow_rename else ""
            return ValidationResult(False, "conflict", normalized, suggestion)
        return ValidationResult(True, "ok", normalized)

    def suggest_available(self, name: str, existing: Iterable[str]) -> str:
        """冲突时按 ``_%02d`` 追加序号，返回首个可用名；99 次仍冲突时返回空串。"""

        profile = self.profile
        normalized = self.normalize(name)
        stem = normalized[: -len(profile.extension)] if normalized.lower().endswith(profile.extension) else normalized
        existing_keys = {item if profile.case_sensitive else item.casefold() for item in existing}
        for index in range(1, 100):
            candidate = stem + (profile.collision_suffix % index) + profile.extension
            key = candidate if profile.case_sensitive else candidate.casefold()
            if key not in existing_keys:
                return candidate
        return ""

    def is_valid(self, name: str) -> bool:
        """便捷判定（不含冲突检查）。"""

        return self.validate(name).ok