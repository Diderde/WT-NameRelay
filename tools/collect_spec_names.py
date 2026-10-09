# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""从官方 Assets 目录收集音频名，生成路径分节规范 txt（v3）。

按官方文件夹结构逐类扫描，把每个叶子目录的音频文件名转换成规范形式
（去扩展名 + `.wav`），写进 ``#region <类别>/<次类>[/<弎类>[/<肆类>]]``
路径分节 txt——与语音批量工作台的四级下钻一一对应。

用法::

    python tools/collect_spec_names.py                       # 全量 → temp/spec-from-assets.txt
    python tools/collect_spec_names.py --sample 5            # 每条路径只取前 5 个（试运行）
    python tools/collect_spec_names.py --only tank,ship      # 只收集指定类别
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.services import tts_spec
from app.services.voice_filename_validator import VoiceFilenameValidator

#: 类别键 →（Assets 子目录, 国家/语音组目录 → 展示段, 子层级遍历定义）。
#: 子层级遍历定义按官方结构：(目录名, 路径段) 序列；flatten 表示该层之下
#: 全部递归收集（不再作为独立层级）。
COUNTRY_CODE: dict[str, dict[str, str]] = {
    "tank": {
        "english_uk": "UK", "english_us": "US", "german_new": "GE", "russian_new": "RU",
    },
    "ship": {
        "english": "EN", "english_us": "EN-US", "french": "FR", "german": "DE",
        "italian": "IT", "japanese": "JP", "russian": "RU",
    },
    "wopl": {"english": "EN", "german": "DE", "russian": "RU"},
    "radio": {"eng": "EN", "ru": "RU"},
}

#: tank/ship 的情绪目录（官方结构：tank 是 语言/情绪/职位，ship 是
#: 语言/成员/情绪——顺序不同，各自照官方来）。
TANK_EMOTIONS = ("high", "med")
SHIP_EMOTIONS = ("high", "low", "med")


def collect_tank(assets: Path) -> dict[str, list[str]]:
    """tank：语言/情绪(high|med)/职位/文件（.ogg）。"""
    root = assets / "dialogs_wt_tanks_2023"
    regions: dict[str, list[str]] = {}
    for lang_dir, code in COUNTRY_CODE["tank"].items():
        for emotion in TANK_EMOTIONS:
            for member_dir in sorted((root / lang_dir / emotion).iterdir()):
                if not member_dir.is_dir():
                    continue
                region = f"tank/{code}/{emotion}/{member_dir.name}"
                regions.setdefault(region, []).extend(
                    f.name for f in sorted(member_dir.iterdir()) if f.is_file()
                )
    return regions


def collect_ship(assets: Path) -> dict[str, list[str]]:
    """ship：语言/成员(commander|officer|sailor)/情绪(high|low|med)/文件（.wav）。"""
    root = assets / "dialogs_wt_ships_2022"
    regions: dict[str, list[str]] = {}
    for lang_dir, code in COUNTRY_CODE["ship"].items():
        for member_dir in sorted((root / lang_dir).iterdir()):
            if not member_dir.is_dir() or member_dir.name in ("high", "low", "med"):
                continue  # 顶层同名情绪目录为空壳（官方遗留），真实内容在成员之下
            for emotion_dir in sorted(member_dir.iterdir()):
                if not emotion_dir.is_dir():
                    continue
                region = f"ship/{code}/{member_dir.name}/{emotion_dir.name}"
                regions.setdefault(region, []).extend(
                    f.name for f in sorted(emotion_dir.iterdir()) if f.is_file()
                )
    return regions


def collect_wopl(assets: Path) -> dict[str, list[str]]:
    """wopl：语言/文件（两层，语言目录下递归全部 .wav）。"""
    root = assets / "dialogs_wopl"
    regions: dict[str, list[str]] = {}
    for lang_dir, code in COUNTRY_CODE["wopl"].items():
        region = f"wopl/{code}"
        regions.setdefault(region, []).extend(
            f.name for f in sorted((root / lang_dir).rglob("*")) if f.is_file()
        )
    return regions


def collect_vws(assets: Path) -> dict[str, list[str]]:
    """vws：语音组(betty|rita|xiao906)/文件（两层，语音组即"国家"位）。"""
    root = assets / "vws"
    regions: dict[str, list[str]] = {}
    for group_dir in sorted(root.iterdir()):
        if not group_dir.is_dir():
            continue
        region = f"vws/{group_dir.name}"
        regions.setdefault(region, []).extend(
            f.name for f in sorted(group_dir.iterdir()) if f.is_file()
        )
    return regions


def collect_radio(assets: Path) -> dict[str, list[str]]:
    """radio：语言(eng|ru)/分组(common|voiceN)/文件（三层；情绪在文件名 mood_* 段）。"""
    root = assets / "radio_chat"
    regions: dict[str, list[str]] = {}
    for lang_dir, code in COUNTRY_CODE["radio"].items():
        for group_dir in sorted((root / lang_dir).iterdir()):
            if not group_dir.is_dir():
                continue
            region = f"radio/{code}/{group_dir.name}"
            regions.setdefault(region, []).extend(
                f.name for f in sorted(group_dir.iterdir()) if f.is_file()
            )
    return regions


COLLECTORS = {
    "tank": collect_tank,
    "ship": collect_ship,
    "wopl": collect_wopl,
    "vws": collect_vws,
    "radio": collect_radio,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="从官方 Assets 收集音频名生成路径分节规范 txt。")
    parser.add_argument(
        "--assets", type=Path, default=REPO / "fmod_studio_warthunder_for_modders" / "Assets",
        help="官方工程 Assets 目录（默认：工作区内整合工程）",
    )
    parser.add_argument(
        "--output", type=Path, default=REPO / "temp" / "spec-from-assets.txt",
        help="输出 txt（默认 temp/spec-from-assets.txt，CRLF / UTF-8 无 BOM）",
    )
    parser.add_argument("--sample", type=int, default=0, help="每条路径只取前 N 个名字（0 = 全量）")
    parser.add_argument("--only", default="", help="只收集指定类别（逗号分隔，如 tank,ship）")
    args = parser.parse_args()

    wanted = [segment.strip() for segment in args.only.split(",") if segment.strip()]
    categories = [c for c in tts_spec.SPEC_CATEGORIES if not wanted or c in wanted]

    validator = VoiceFilenameValidator()
    all_regions: dict[str, list[str]] = {}
    for category in categories:
        all_regions.update(COLLECTORS[category](args.assets))

    # 名字转换与校验：去扩展名 + .wav；非规范形式跳过并计数（不进名单）。
    # 官方目录里同一录音常有 .ogg/.wav 两种扩展名 → 转换后同路径内撞名，
    # 按区域去重（保留首个）。
    out_lines: list[str] = []
    total_names = 0
    skipped: list[str] = []
    for region, files in all_regions.items():
        names = []
        seen: set[str] = set()
        for file_name in files:
            candidate = Path(file_name).stem + ".wav"
            result = validator.validate(candidate, existing=())
            if not result.ok or candidate != validator.normalize(candidate):
                skipped.append(f"{region}: {file_name}")
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            names.append(candidate)
        if args.sample > 0:
            names = names[: args.sample]
        if not names:
            continue
        total_names += len(names)
        out_lines.append(f"#region {region}")
        out_lines.extend(names)
        out_lines.append("#endregion")
        out_lines.append("")

    if not out_lines:
        print("[错误] 没有收集到任何名字——请检查 Assets 目录是否正确")
        return 1

    payload = ("\r\n".join(out_lines) + "\r\n").encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)

    # 自校验：生成的 txt 必须能被解析器无损吃下
    document = tts_spec.parse_spec_file(args.output)
    errors = tts_spec.validate_spec_entries(document, validator)
    if wanted:
        # --only 部分收集：五类齐全校验不适用（缺的类别是有意不收集）
        errors = [error for error in errors if not error.startswith("缺少「")]
    print(f"已生成 {args.output}：{len(all_regions)} 条路径 / {total_names} 个名字（CRLF）")
    print(f"自校验：{len(document.paths)} 路径重新解析，校验错误 {len(errors)} 条")
    for error in errors[:5]:
        print("  ", error)
    if skipped:
        print(f"跳过非规范名 {len(skipped)} 个（前 5 个）：")
        for item in skipped[:5]:
            print("  ", item)
    print("提示：txt 已可直接在工作台「加载规范」使用；不需要的行手工删除即可。")
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
