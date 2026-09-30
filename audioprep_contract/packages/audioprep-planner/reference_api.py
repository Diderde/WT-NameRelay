#!/usr/bin/env python3
"""Reference PlanSealValidator API contract for the planning bundle.

This is an executable reference surface, not a claim that a production binary is
attested by SQLite.  The public ``seal_plan`` entry point is deliberately unable to
write SEALED directly: it first calls ``PlanSealValidator.validate_and_record``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
import sqlite3

CANONICAL_SEALED_AT = "2026-08-09T05:00:00.000Z"


@dataclass(frozen=True)
class PlanSealValidator:
    report_builder: Callable[[sqlite3.Connection, str], dict[str, Any]]
    fingerprint_builder: Callable[[sqlite3.Connection, str], str]
    validator_version: str = "PlanSealValidator/R2.1.5.07"
    validated_at: str = CANONICAL_SEALED_AT

    def validate_and_record(self, con: sqlite3.Connection, plan_id: str) -> str:
        row = con.execute("SELECT status FROM pipeline_plan WHERE plan_id=?", (plan_id,)).fetchone()
        if row is None:
            raise ValueError("unknown plan")
        if row[0] != "DRAFT":
            raise ValueError("PlanSealValidator accepts DRAFT Plan only")
        report = self.report_builder(con, plan_id)
        if not isinstance(report, dict) or report.get("passed") is not True:
            raise ValueError("PlanSealValidator report must be a passed structured report")
        fingerprint = self.fingerprint_builder(con, plan_id)
        con.execute(
            """INSERT INTO pipeline_plan_validation(
                   plan_id,plan_fingerprint,validator_version,report_json,validated_at)
               VALUES(?,?,?,?,?)""",
            (plan_id, fingerprint, self.validator_version,
             __import__("json").dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
             self.validated_at),
        )
        return fingerprint


def seal_plan(
    con: sqlite3.Connection,
    plan_id: str,
    validator: PlanSealValidator,
    *,
    sealed_at: str = CANONICAL_SEALED_AT,
) -> str:
    """Seal a DRAFT Plan only through the validator receipt-producing API."""
    if not isinstance(validator, PlanSealValidator):
        raise TypeError("seal_plan requires a PlanSealValidator instance")
    fingerprint = validator.validate_and_record(con, plan_id)
    con.execute(
        "UPDATE pipeline_plan SET status='SEALED',plan_fingerprint=?,sealed_at=? WHERE plan_id=?",
        (fingerprint, sealed_at, plan_id),
    )
    return fingerprint
