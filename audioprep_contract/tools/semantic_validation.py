"""Semantic validators that JSON Schema and SQLite row constraints cannot express.

These functions are intentionally dependency-light so the same logic can be reused by
CLI validation, scheduler pre-commit checks, and contract tests.
"""
from __future__ import annotations

from pathlib import PurePosixPath
from fractions import Fraction
from typing import Any, Mapping, Sequence
import re

SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SEGMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class SemanticValidationError(ValueError):
    """Raised when a structurally valid document violates a cross-field invariant."""


def _require_int(value: Any, name: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SemanticValidationError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise SemanticValidationError(f"{name} must be >= {minimum}")
    return value


def validate_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise SemanticValidationError(f"{name} must be sha256:<64 lowercase hex>")
    return value


def validate_deliverable_relative_path(value: Any, name: str = "wav") -> str:
    if not isinstance(value, str):
        raise SemanticValidationError(f"{name} must be a string")
    if "\\" in value or "\x00" in value:
        raise SemanticValidationError(f"{name} must use safe POSIX separators")
    p = PurePosixPath(value)
    if p.is_absolute() or any(part in ("", ".", "..") for part in p.parts):
        raise SemanticValidationError(f"{name} must be a normalized relative path")
    if len(p.parts) != 2 or p.parts[0] != "segments" or p.suffix != ".wav":
        raise SemanticValidationError(f"{name} must be segments/<safe-name>.wav")
    if not SEGMENT_ID_RE.fullmatch(p.stem):
        raise SemanticValidationError(f"{name} contains an unsafe filename")
    return value


def validate_time_map_ticks(
    entries: Sequence[Mapping[str, Any]],
    *,
    dst_end_tick: int,
    mapping_kind: str,
    src_timebase: Mapping[str, Any],
    dst_timebase: Mapping[str, Any],
    name: str,
) -> None:
    if not isinstance(entries, list) or not entries:
        raise SemanticValidationError(f"{name} must be a non-empty array")
    expected_dst_start = 0
    previous_src_end: int | None = None
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SemanticValidationError(f"{name}[{index}] must be an object")
        if set(entry) - {"op", "src", "dst"}:
            raise SemanticValidationError(f"{name}[{index}] has unknown keys")
        op = entry.get("op")
        if op not in {"MAP", "SILENCE"}:
            raise SemanticValidationError(f"{name}[{index}].op is invalid")
        dst = entry.get("dst")
        if not isinstance(dst, list) or len(dst) != 2:
            raise SemanticValidationError(f"{name}[{index}].dst must be [start,end]")
        dst_start = _require_int(dst[0], f"{name}[{index}].dst[0]", 0)
        dst_stop = _require_int(dst[1], f"{name}[{index}].dst[1]", 1)
        if dst_stop <= dst_start:
            raise SemanticValidationError(f"{name}[{index}].dst must be increasing")
        if dst_start != expected_dst_start:
            raise SemanticValidationError(f"{name} destination spans must be contiguous from zero")
        expected_dst_start = dst_stop

        if op == "MAP":
            src = entry.get("src")
            if not isinstance(src, list) or len(src) != 2:
                raise SemanticValidationError(f"{name}[{index}].src must be [start,end] for MAP")
            src_start = _require_int(src[0], f"{name}[{index}].src[0]", 0)
            src_stop = _require_int(src[1], f"{name}[{index}].src[1]", 1)
            if src_stop <= src_start:
                raise SemanticValidationError(f"{name}[{index}].src must be increasing")
            if previous_src_end is not None and src_start < previous_src_end:
                raise SemanticValidationError(f"{name} mapped source spans must not overlap or move backward")
            previous_src_end = src_stop
        elif "src" in entry:
            raise SemanticValidationError(f"{name}[{index}] SILENCE must not contain src")

    if expected_dst_start != dst_end_tick:
        raise SemanticValidationError(f"{name} must completely cover [0,dst_end_tick)")

    if mapping_kind == "IDENTITY_SLICE":
        if len(entries) != 1 or entries[0].get("op") != "MAP":
            raise SemanticValidationError("IDENTITY_SLICE requires exactly one MAP span")
        if src_timebase != dst_timebase:
            raise SemanticValidationError("IDENTITY_SLICE requires equal source and destination timebases")
        src = entries[0]["src"]
        dst = entries[0]["dst"]
        if src[1] - src[0] != dst[1] - dst[0]:
            raise SemanticValidationError("IDENTITY_SLICE must preserve tick duration")


def validate_manifest_semantics(document: Mapping[str, Any]) -> None:
    if not isinstance(document, dict):
        raise SemanticValidationError("manifest must be an object")
    if document.get("schema") != "audioprep.manifest.v1" or document.get("manifest_version") != 1:
        raise SemanticValidationError("unsupported manifest schema/version")
    source = document.get("source")
    if not isinstance(source, dict):
        raise SemanticValidationError("source must be an object")
    validate_sha256(source.get("content_hash"), "source.content_hash")

    segments = document.get("segments")
    if not isinstance(segments, list) or not segments:
        raise SemanticValidationError("segments must be a non-empty array")

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    seen_artifacts: set[str] = set()
    seen_ordinals: set[int] = set()
    previous_source_end: Fraction | None = None
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise SemanticValidationError(f"segments[{index}] must be an object")
        sid = segment.get("segment_id")
        if not isinstance(sid, str) or not SEGMENT_ID_RE.fullmatch(sid):
            raise SemanticValidationError(f"segments[{index}].segment_id is invalid")
        if sid in seen_ids:
            raise SemanticValidationError("segment_id values must be unique")
        seen_ids.add(sid)

        ordinal = _require_int(segment.get("ordinal"), f"segments[{index}].ordinal", 0)
        if ordinal in seen_ordinals:
            raise SemanticValidationError("segment ordinal values must be unique")
        if ordinal != index:
            raise SemanticValidationError("segments must be ordered with contiguous ordinals from zero")
        seen_ordinals.add(ordinal)

        wav = validate_deliverable_relative_path(segment.get("wav"), f"segments[{index}].wav")
        if PurePosixPath(wav).stem != sid:
            raise SemanticValidationError(f"segments[{index}].segment_id must equal the wav filename stem")
        if wav in seen_paths:
            raise SemanticValidationError("segment wav paths must be unique")
        seen_paths.add(wav)

        artifact_id = segment.get("artifact_id")
        if not isinstance(artifact_id, str) or not artifact_id:
            raise SemanticValidationError(f"segments[{index}].artifact_id is invalid")
        if artifact_id in seen_artifacts:
            raise SemanticValidationError("segment artifact_id values must be unique")
        seen_artifacts.add(artifact_id)
        validate_sha256(segment.get("blob_hash"), f"segments[{index}].blob_hash")

        src_start = _require_int(segment.get("src_start_ms"), f"segments[{index}].src_start_ms", 0)
        src_end = _require_int(segment.get("src_end_ms"), f"segments[{index}].src_end_ms", 1)
        if src_end <= src_start:
            raise SemanticValidationError(f"segments[{index}] source interval must be increasing")

        timebase = segment.get("timebase")
        if not isinstance(timebase, dict) or set(timebase) != {"src", "dst"}:
            raise SemanticValidationError(f"segments[{index}].timebase is invalid")
        for side in ("src", "dst"):
            tb = timebase[side]
            if not isinstance(tb, dict) or set(tb) != {"num", "den"}:
                raise SemanticValidationError(f"segments[{index}].timebase.{side} is invalid")
            _require_int(tb["num"], f"segments[{index}].timebase.{side}.num", 1)
            _require_int(tb["den"], f"segments[{index}].timebase.{side}.den", 1)

        mapping_kind = segment.get("mapping_kind")
        if mapping_kind not in {"IDENTITY_SLICE", "PIECEWISE"}:
            raise SemanticValidationError(f"segments[{index}].mapping_kind is invalid")
        dst_end_tick = _require_int(segment.get("dst_end_tick"), f"segments[{index}].dst_end_tick", 1)
        entries = segment.get("time_map_ticks")
        validate_time_map_ticks(
            entries,
            dst_end_tick=dst_end_tick,
            mapping_kind=mapping_kind,
            src_timebase=timebase["src"],
            dst_timebase=timebase["dst"],
            name=f"segments[{index}].time_map_ticks",
        )

        # Tick mapping is authoritative; millisecond bounds are derived convenience fields.
        mapped = [entry for entry in entries if entry.get("op") == "MAP"]
        if not mapped:
            raise SemanticValidationError(f"segments[{index}] manifest timeline requires at least one MAP span")
        src_tb = timebase["src"]
        first_tick = mapped[0]["src"][0]
        last_tick = mapped[-1]["src"][1]
        start_numerator = first_tick * src_tb["num"] * 1000
        end_numerator = last_tick * src_tb["num"] * 1000
        expected_start_ms = start_numerator // src_tb["den"]
        expected_end_ms = (end_numerator + src_tb["den"] - 1) // src_tb["den"]
        if src_start != expected_start_ms or src_end != expected_end_ms:
            raise SemanticValidationError(
                f"segments[{index}] src_start_ms/src_end_ms must be derived from authoritative time_map_ticks "
                f"(expected {expected_start_ms}..{expected_end_ms})"
            )
        authoritative_start = Fraction(first_tick * src_tb["num"], src_tb["den"])
        authoritative_end = Fraction(last_tick * src_tb["num"], src_tb["den"])
        if previous_source_end is not None and authoritative_start < previous_source_end:
            raise SemanticValidationError("segments must be ordered and non-overlapping in authoritative source time")
        previous_source_end = authoritative_end


def validate_timeline_rows(mapping: Mapping[str, Any], spans: Sequence[Mapping[str, Any]]) -> None:
    entries = []
    for span in spans:
        entry: dict[str, Any] = {
            "op": span["op"],
            "dst": [span["dst_start_tick"], span["dst_end_tick"]],
        }
        if span["op"] == "MAP":
            entry["src"] = [span["src_start_tick"], span["src_end_tick"]]
        entries.append(entry)
    validate_time_map_ticks(
        entries,
        dst_end_tick=mapping["dst_end_tick"],
        mapping_kind=mapping["mapping_kind"],
        src_timebase={"num": mapping["src_timebase_num"], "den": mapping["src_timebase_den"]},
        dst_timebase={"num": mapping["dst_timebase_num"], "den": mapping["dst_timebase_den"]},
        name="timeline spans",
    )
