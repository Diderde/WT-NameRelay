"""Configuration boundaries for name-copy modules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModuleConfig:
    module_id: str
    title: str
    module_label: str
    description: str
    data_path: str


CREW_MODULE = ModuleConfig(
    module_id="crew",
    title="车组文件复制",
    module_label="车组",
    description="自动识别并补齐车组语音文件名称",
    data_path=":/data/crew_name_groups.json",
)

RADIO_MODULE = ModuleConfig(
    module_id="radio",
    title="无线电文件复制",
    module_label="无线电",
    description="自动识别并补齐无线电语音文件名称",
    data_path=":/data/radio_name_groups.json",
)
