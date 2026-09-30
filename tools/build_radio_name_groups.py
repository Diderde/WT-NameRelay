"""Build the embedded radio name library from three read-only source directories.

The application never reads these source paths at runtime.  They are used only
to audit and regenerate ``radio_name_groups.json``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_AUDIO_SUFFIXES = frozenset({".wav", ".flac", ".ogg", ".mp3", ".m4a", ".aac", ".opus"})
V_SUFFIX = re.compile(r"^(?P<base>.+)_v(?P<index>[1-9]\d*)$")
MATRIX_SUFFIX = re.compile(r"^(?P<base>.+)_(?P<outer>\d+)_(?P<inner>[1-9]\d*)$")
NATURAL_PARTS = re.compile(r"(\d+)")


@dataclass(frozen=True, slots=True)
class AudioName:
    source_id: str
    source_path: Path
    stem: str


def natural_key(value: str) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part.casefold() for part in NATURAL_PARTS.split(value))


def scan_directory(source_id: str, directory: Path) -> tuple[list[AudioName], list[str]]:
    """Read only the selected directory itself; never descend into children."""
    if not directory.is_dir():
        return [], [f"目录不存在或不可访问：{directory}"]
    records: list[AudioName] = []
    for entry in sorted(directory.iterdir(), key=lambda path: natural_key(path.name)):
        if entry.is_file() and entry.suffix.casefold() in SUPPORTED_AUDIO_SUFFIXES:
            records.append(AudioName(source_id, directory, entry.stem))
    return records, []


def classify(records: Iterable[AudioName]) -> tuple[dict[str, dict[str, object]], dict[str, object]]:
    by_stem: dict[str, list[AudioName]] = defaultdict(list)
    v_members: dict[str, list[AudioName]] = defaultdict(list)
    numeric_members: dict[str, list[AudioName]] = defaultdict(list)
    unmatched: list[AudioName] = []
    for record in records:
        by_stem[record.stem].append(record)
        match = V_SUFFIX.match(record.stem)
        if match is not None:
            v_members[match["base"]].append(record)
            continue
        match = MATRIX_SUFFIX.match(record.stem)
        if match is not None:
            numeric_members[match["base"]].append(record)
            continue
        unmatched.append(record)

    groups: dict[str, dict[str, object]] = {}
    exceptions: list[dict[str, object]] = []
    consumed_v_bases: set[str] = set()
    candidates: dict[str, dict[int, list[AudioName]]] = defaultdict(dict)
    for base_name, members in v_members.items():
        outer_match = re.match(r"^(?P<prefix>.+?)(?P<outer>[1-9]\d*)$", base_name)
        if outer_match is not None:
            candidates[outer_match["prefix"]][int(outer_match["outer"])] = members
    for prefix, outer_groups in sorted(candidates.items(), key=lambda item: natural_key(item[0])):
        if sorted(outer_groups) != [1, 2, 3]:
            continue
        if not all(
            sorted(int(V_SUFFIX.match(record.stem)["index"]) for record in members) == [1, 2, 3]  # type: ignore[union-attr]
            and len(members) == 3
            for members in outer_groups.values()
        ):
            continue
        group_key = prefix.removesuffix("_")
        names = [record.stem for outer in (1, 2, 3) for record in sorted(outer_groups[outer], key=lambda item: natural_key(item.stem))]
        source_map = {name: sorted({record.source_id for record in by_stem[name]}) for name in names}
        if group_key in groups:
            raise ValueError(f"基础名称跨类型冲突：{group_key}")
        groups[group_key] = {"type": "v_matrix_suffix", "names": names, "sources": source_map}
        for outer in (1, 2, 3):
            consumed_v_bases.add(V_SUFFIX.match(outer_groups[outer][0].stem)["base"])  # type: ignore[union-attr]

    parsed: dict[tuple[str, str], list[AudioName]] = {
        ("v_suffix", base_name): members
        for base_name, members in v_members.items()
        if base_name not in consumed_v_bases
    }
    parsed.update({("matrix_suffix", base_name): members for base_name, members in numeric_members.items()})
    for (group_type, base_name), members in sorted(parsed.items(), key=lambda item: (item[0][0], natural_key(item[0][1]))):
        members.sort(key=lambda record: natural_key(record.stem))
        if group_type == "v_suffix":
            indexes = sorted(int(V_SUFFIX.match(record.stem)["index"]) for record in members)  # type: ignore[union-attr]
            is_valid = len(members) >= 2 and indexes == list(range(1, len(members) + 1))
        else:
            coordinates = [MATRIX_SUFFIX.match(record.stem) for record in members]
            outer_values = sorted({int(match["outer"]) for match in coordinates if match is not None})
            inner_values = sorted({int(match["inner"]) for match in coordinates if match is not None})
            is_valid = (
                len(members) >= 2
                and outer_values == list(range(len(outer_values)))
                and inner_values == list(range(1, len(inner_values) + 1))
                and len(members) == len(outer_values) * len(inner_values)
            )
        # A matrix is one logical group: e.g. ``attack_A_0_1`` through
        # ``attack_A_3_3``.  Do not split it into four final-suffix groups.
        if not is_valid:
            reason = "仅有一个成员" if len(members) == 1 else "编号不是完整的连续变体矩阵，疑似语义数字"
            exceptions.append({
                "reason": reason,
                "type": group_type,
                "base_name": base_name,
                "names": [record.stem for record in members],
                "sources": {record.stem: [record.source_id] for record in members},
            })
            continue
        names = [record.stem for record in members]
        source_map: dict[str, list[str]] = {}
        for name in names:
            source_map[name] = sorted({record.source_id for record in by_stem[name]})
        if base_name in groups:
            raise ValueError(f"基础名称跨类型冲突：{base_name}")
        groups[base_name] = {"type": group_type, "names": names, "sources": source_map}

    for record in unmatched:
        reason = "无可确认的末尾变体编号；名称中的数字或单位具有语义"
        exceptions.append({"reason": reason, "name": record.stem, "source": record.source_id})

    duplicate_stems = {
        stem: sorted({record.source_id for record in items})
        for stem, items in by_stem.items()
        if len(items) > 1
    }
    case_conflicts: dict[str, list[str]] = defaultdict(list)
    for stem in by_stem:
        case_conflicts[stem.casefold()].append(stem)
    return groups, {
        "logical_name_count": len(by_stem),
        "same_logical_name": duplicate_stems,
        "case_only_conflicts": {key: sorted(value) for key, value in case_conflicts.items() if len(value) > 1},
        "formal_group_types": dict(Counter(group["type"] for group in groups.values())),
        "exceptions": exceptions,
    }


def validate(groups: dict[str, dict[str, object]], actual_stems: set[str]) -> None:
    seen: set[str] = set()
    for base_name, group in groups.items():
        names = group["names"]
        if not isinstance(base_name, str) or not base_name or not isinstance(names, list) or len(names) < 2:
            raise ValueError(f"无效分组：{base_name}")
        if names != sorted(names, key=natural_key) or len(names) != len(set(names)):
            raise ValueError(f"名称排序或唯一性无效：{base_name}")
        for name in names:
            if Path(name).suffix or name not in actual_stems or name in seen:
                raise ValueError(f"名称校验失败：{name}")
            seen.add(name)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成无线电名称库（只读扫描）。")
    parser.add_argument("--voice1", required=True, type=Path)
    parser.add_argument("--additional-01", required=True, dest="additional_01", type=Path)
    parser.add_argument("--english", required=True, type=Path)
    parser.add_argument("--output", default=Path("app/resources/data/radio_name_groups.json"), type=Path)
    parser.add_argument("--report", default=Path("reports/radio_name_analysis.json"), type=Path)
    args = parser.parse_args()
    sources = (("voice1", args.voice1), ("additional_01", args.additional_01), ("english", args.english))
    public_sources = {source_id: f"<external-radio-source:{source_id}>" for source_id, _path in sources}
    records: list[AudioName] = []
    errors: list[str] = []
    for source_id, directory in sources:
        found, failures = scan_directory(source_id, directory)
        records.extend(found)
        errors.extend(failures)
    groups, analysis = classify(records)
    report = {
        "schema_version": 1,
        "module": "radio",
        "source_directories": public_sources,
        "directory_audio_counts": {source_id: sum(record.source_id == source_id for record in records) for source_id, _path in sources},
        "total_audio_files": len(records),
        "formal_group_count": len(groups),
        "formal_name_count": sum(len(group["names"]) for group in groups.values()),
        "excluded_name_count": len(records) - sum(len(group["names"]) for group in groups.values()),
        "errors": errors,
        **analysis,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        print("；".join(errors), file=sys.stderr)
        return 1
    validate(groups, {record.stem for record in records})
    payload = {
        "schema_version": 1,
        "module": "radio",
        "source_directories": list(public_sources.values()),
        "groups": dict(sorted(groups.items(), key=lambda item: natural_key(item[0]))),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"无线电名称库：{len(groups)} 组，{sum(len(group['names']) for group in groups.values())} 个名称")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
