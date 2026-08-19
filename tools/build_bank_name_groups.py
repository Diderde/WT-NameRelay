"""Read-only builder for the embedded Bank file-name library."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

PREFIXES = {"common": "_crew_dialogs_common_", "ground": "_crew_dialogs_ground_"}
ASSETS = re.compile(r"^_crew_dialogs_(common|ground)_(.+)\.assets\.bank$")
MAIN = re.compile(r"^_crew_dialogs_(common|ground)_(.+)\.bank$")


def parse_name(name: str) -> tuple[str, str, str] | None:
    """Parse assets before main so ``zh.assets`` can never become a country."""
    match = ASSETS.match(name)
    if match:
        return match[1], match[2], "assets"
    match = MAIN.match(name)
    if match:
        return match[1], match[2], "main"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="只读生成 Bank 名称库")
    parser.add_argument("--sound", required=True, type=Path)
    parser.add_argument("--output", default=Path("app/resources/data/bank_name_groups.json"), type=Path)
    parser.add_argument("--report", default=Path("reports/bank_name_analysis.json"), type=Path)
    args = parser.parse_args()
    sound = args.sound
    if not sound.is_dir():
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps({"error": "外部 Bank 参考目录不可用。"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"目录不存在：{sound}", file=sys.stderr)
        return 1

    all_files = sorted((entry for entry in sound.iterdir() if entry.is_file()), key=lambda entry: entry.name)
    matched: list[dict[str, str]] = []
    invalid: list[str] = []
    by_key: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for entry in all_files:
        if not any(entry.name.startswith(prefix) for prefix in PREFIXES.values()):
            continue
        parsed = parse_name(entry.name)
        if parsed is None:
            invalid.append(entry.name)
            continue
        category, country, role = parsed
        if role in by_key[(category, country)]:
            invalid.append(entry.name)
            continue
        by_key[(category, country)][role] = entry.name
        matched.append({"name": entry.name, "category": category, "country": country, "role": role})

    categories: dict[str, dict[str, object]] = {}
    for category, prefix in PREFIXES.items():
        countries: dict[str, dict[str, object]] = {}
        for (item_category, country), roles in sorted(by_key.items()):
            if item_category != category:
                continue
            missing = [role for role in ("assets", "main") if role not in roles]
            countries[country] = {
                "assets": roles.get("assets"), "main": roles.get("main"),
                "complete": not missing, "missing_roles": missing,
            }
        categories[category] = {"prefix": prefix, "countries": countries}

    report = {
        "schema_version": 1, "module": "bank", "source_directory": "<external-war-thunder-sound-directory>",
        "current_level_file_count": len(all_files), "matched_file_count": len(matched),
        "prefix_file_counts": {category: sum(item["category"] == category for item in matched) for category in PREFIXES},
        "files": matched, "unparseable_or_duplicate_files": invalid,
        "categories": categories,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if invalid:
        print("存在无法解析或重复的匹配 Bank 文件，详见报告。", file=sys.stderr)
        return 1
    # Residual source groups are valid audit data. They remain in the JSON with
    # ``complete: false`` and ``missing_roles`` so runtime code can never treat
    # them as a source group.
    payload = {
        "schema_version": 1,
        "module": "bank",
        "source_directory": "<external-war-thunder-sound-directory>",
        "categories": categories,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    complete = sum(entry["complete"] for category in categories.values() for entry in category["countries"].values())
    print(f"Bank 名称库：{complete} 个完整国家组，{len(matched)} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
