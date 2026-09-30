#!/usr/bin/env python3
"""R2.1.5.07 deterministic release verifier.

Checks syntax, JSON, SQLite inventory/revision, bilingual revision parity, re-runs both
validation suites and compares their exact deterministic evidence logs, then verifies
that SHA256SUMS.txt covers every release file exactly once.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SUM_FILE = ROOT / "SHA256SUMS.txt"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run_evidence(relative_script: str, relative_log: str) -> str | None:
    proc = subprocess.run(
        [sys.executable, "-B", str(ROOT / relative_script)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return f"{relative_script}: rerun failed rc={proc.returncode}: {proc.stderr.strip()}"
    expected_path = ROOT / relative_log
    if not expected_path.is_file():
        return f"{relative_log}: evidence log missing"
    expected = expected_path.read_text(encoding="utf-8")
    if proc.stdout != expected:
        return f"{relative_log}: deterministic evidence differs from fresh rerun"
    if proc.stderr:
        return f"{relative_script}: unexpected stderr during evidence rerun: {proc.stderr.strip()}"
    return None


def main() -> int:
    failures: list[str] = []

    # Python syntax without bytecode side effects.
    py_files = sorted((ROOT / "tools").glob("*.py")) + sorted((ROOT / "tests").glob("*.py")) + sorted((ROOT / "packages").glob("*/reference_api.py"))
    for path in py_files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            failures.append(f"{path.relative_to(ROOT)}: syntax error: {exc}")

    # Every JSON artifact must parse.
    json_files = sorted(ROOT.rglob("*.json"))
    for path in json_files:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            failures.append(f"{path.relative_to(ROOT)}: invalid JSON: {exc}")

    # SQLite schema inventory and release metadata.
    try:
        con = sqlite3.connect(":memory:")
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA recursive_triggers=ON")
        con.executescript((ROOT / "sql/schema.sql").read_text(encoding="utf-8"))
        inventory = (
            con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0],
            con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0],
            con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND sql IS NOT NULL").fetchone()[0],
        )
        if inventory != (23, 131, 9):
            failures.append(f"SQLite inventory mismatch: got {inventory}, expected (23, 131, 9)")
        meta = dict(con.execute("SELECT schema_key,schema_value FROM schema_meta"))
        if meta.get("design_revision") != "R2.1.5.07" or meta.get("schema_version") != "2.1.5.07":
            failures.append(f"schema_meta revision mismatch: {meta}")
    except Exception as exc:
        failures.append(f"schema load/inventory failed: {type(exc).__name__}: {exc}")

    # All normative chapters must have the same active revision.
    for lang, marker in (("en", "**Revision:** R2.1.5.07"), ("zh-CN", "**版本：** R2.1.5.07")):
        docs = sorted((ROOT / "docs" / lang).glob("*.md"))
        if len(docs) != 18:
            failures.append(f"docs/{lang}: expected 18 chapters, got {len(docs)}")
        for path in docs:
            if marker not in path.read_text(encoding="utf-8"):
                failures.append(f"{path.relative_to(ROOT)}: active revision marker mismatch")

    # B21/N6: evidence is regenerated, not trusted because a text file says PASS.
    for script, log in (
        ("tools/validate_planning.py", "validation/planning_validation.txt"),
        ("tests/independent_regression.py", "validation/independent_regression.txt"),
    ):
        err = run_evidence(script, log)
        if err:
            failures.append(err)

    # Checksum manifest must exactly cover all release files except itself.
    if not SUM_FILE.is_file():
        failures.append("SHA256SUMS.txt is missing")
    else:
        listed: dict[str, str] = {}
        for line_no, raw in enumerate(SUM_FILE.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            try:
                expected, relative = raw.split("  ", 1)
            except ValueError:
                failures.append(f"SHA256SUMS line {line_no}: malformed entry")
                continue
            if relative in listed:
                failures.append(f"SHA256SUMS line {line_no}: duplicate entry for {relative}")
                continue
            listed[relative] = expected
            path = ROOT / relative
            try:
                resolved = path.resolve()
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                failures.append(f"SHA256SUMS line {line_no}: path escapes root: {relative}")
                continue
            if resolved == SUM_FILE.resolve():
                failures.append(f"SHA256SUMS line {line_no}: checksum file must not list itself")
                continue
            if not path.is_file():
                failures.append(f"{relative}: missing")
                continue
            actual = sha256(path)
            if actual != expected:
                failures.append(f"{relative}: checksum mismatch expected {expected}, got {actual}")
        actual_files = {
            p.relative_to(ROOT).as_posix()
            for p in ROOT.rglob("*")
            if p.is_file() and p.resolve() != SUM_FILE.resolve()
        }
        for relative in sorted(actual_files - set(listed)):
            failures.append(f"{relative}: unlisted release file")
        for relative in sorted(set(listed) - actual_files):
            failures.append(f"{relative}: checksum entry has no release file")

    if failures:
        print("FAIL")
        for item in failures:
            print(f"- {item}")
        return 1
    print(
        f"PASS syntax={len(py_files)} json={len(json_files)} "
        "sqlite=23/131/9 evidence=2 checksum=exact"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
