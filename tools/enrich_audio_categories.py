"""Attach reference-project category metadata without changing name groups.

This is a data-preparation tool only.  The application never accesses the
reference directories passed here; it reads the embedded JSON files instead.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

AUDIO_SUFFIXES = {".wav", ".flac", ".ogg", ".mp3", ".m4a", ".aac", ".opus"}
CREW_CATEGORIES = ("artillery", "aviation", "chief_m", "commander", "driver", "gunner", "loader")
RADIO_DIRECTORIES = {"additional_01": "additional_01", "\u6001\u52bf\u64ad\u62a5": "\u6001\u52bf", "\u4fe1\u606f": "\u4fe1\u606f"}


def scan(directory: Path) -> set[str]:
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    return {path.stem for path in directory.iterdir() if path.is_file() and path.suffix.casefold() in AUDIO_SUFFIXES}


def category_index(crew_root: Path, radio_root: Path) -> tuple[dict[str, tuple[str, str]], dict[str, object]]:
    index: dict[str, tuple[str, str]] = {}
    report: dict[str, object] = {"crew": {}, "radio": {}, "duplicates": []}
    for category in CREW_CATEGORIES:
        names = scan(crew_root / category)
        report["crew"][category] = len(names)
        for name in names:
            if name in index:
                report["duplicates"].append(name)
            index[name] = ("crew", category)
    for category, directory_name in RADIO_DIRECTORIES.items():
        names = scan(radio_root / directory_name)
        report["radio"][category] = len(names)
        for name in names:
            if name in index:
                report["duplicates"].append(name)
            index[name] = ("radio", category)
    return index, report


def enrich(path: Path, module: str, index: dict[str, tuple[str, str]]) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    groups = payload.get("groups", payload)
    classified = unclassified = conflicts = 0
    for entry in groups.values():
        locations = {index[name] for name in entry["names"] if name in index}
        entry["module"] = module
        if len(locations) == 1:
            actual_module, category = locations.pop()
            if actual_module == module:
                entry["category"] = category
                classified += 1
            else:
                entry.pop("category", None)
                conflicts += 1
        elif locations:
            entry.pop("category", None)
            conflicts += 1
        else:
            entry.pop("category", None)
            unclassified += 1
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"classified_groups": classified, "unclassified_groups": unclassified, "conflicting_groups": conflicts}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crew-reference", type=Path, required=True)
    parser.add_argument("--radio-reference", type=Path, required=True)
    parser.add_argument("--crew-json", type=Path, required=True)
    parser.add_argument("--radio-json", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    index, report = category_index(args.crew_reference, args.radio_reference)
    report["crew_json"] = enrich(args.crew_json, "crew", index)
    report["radio_json"] = enrich(args.radio_json, "radio", index)
    report["indexed_names"] = len(index)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
