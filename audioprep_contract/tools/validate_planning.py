#!/usr/bin/env python3
# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: MIT
"""Executable planning validation for AudioPrep R2.1.5.07.

The first section contains reusable validator functions. The test suite is deliberately
negative-test heavy: a planning assertion is useful only when the invalid neighboring
states are also rejected.
"""
from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import sys
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from semantic_validation import (  # noqa: E402
    SemanticValidationError,
    validate_manifest_semantics,
    validate_timeline_rows,
)

PREDICATE_SCHEMA = "audioprep.predicate.v1"
MEDIA_DIMENSIONS = ("container", "sample_rate_hz", "channels", "sample_format", "timeline_alignment")
PORT_CARDINALITIES = {"required-single", "optional-single", "variadic"}
PLAN_VALIDATION_REPORT_SCHEMA = "audioprep.plan-validation-report.v1"
CANONICAL_TS = "2026-08-09T05:00:00.000Z"
FUTURE_TS = "2099-01-01T00:00:00.000Z"
ERROR_CODES = {
    "SOURCE_NOT_FOUND", "SOURCE_CHANGED", "SOURCE_UNREADABLE", "UNSUPPORTED_MEDIA",
    "PLAN_INVALID", "PLAN_STALE", "RESOURCE_UNAVAILABLE", "NODE_TIMEOUT",
    "NODE_CRASH", "NODE_OUTPUT_INVALID", "DECISION_EXPIRED", "DECISION_INVALID",
    "DELIVERY_FAILED", "DISK_FULL", "PERMISSION_DENIED", "CANCELLED",
    "INTERNAL_ERROR", "UNKNOWN_ERROR",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def parse_json(value: str, name: str) -> Any:
    try:
        return json.loads(value)
    except Exception as exc:
        raise ValueError(f"{name} is not valid JSON") from exc


def validate_predicate_document(document: Mapping[str, Any], declared_facts: Iterable[str], max_depth: int = 12) -> None:
    if not isinstance(document, dict) or set(document) != {"schema", "expr"}:
        raise ValueError("predicate.v1 requires exactly schema and expr")
    if document.get("schema") != PREDICATE_SCHEMA:
        raise ValueError("unsupported predicate schema")
    facts = set(declared_facts)

    def walk(expr: Any, depth: int) -> None:
        if depth > max_depth:
            raise ValueError("predicate depth limit exceeded")
        if not isinstance(expr, dict):
            raise ValueError("predicate expression must be an object")
        keys = set(expr)
        if keys == {"all"} or keys == {"any"}:
            items = expr[next(iter(keys))]
            if not isinstance(items, list) or not items:
                raise ValueError("all/any requires a non-empty array")
            for item in items:
                walk(item, depth + 1)
            return
        if keys == {"not"}:
            walk(expr["not"], depth + 1)
            return
        if keys != {"fact", "op", "value"}:
            raise ValueError("predicate leaf requires fact, op and value")
        fact = expr["fact"]
        op = expr["op"]
        if not isinstance(fact, str) or fact not in facts:
            raise ValueError(f"unknown fact: {fact}")
        if op not in {"eq", "ne", "gt", "gte", "lt", "lte", "in"}:
            raise ValueError(f"unsupported predicate operator: {op}")
        if op == "in" and not isinstance(expr["value"], list):
            raise ValueError("in operator requires array value")

    walk(document["expr"], 0)


def evaluate_predicate(document: Mapping[str, Any], facts: Mapping[str, Any]) -> bool:
    validate_predicate_document(document, facts.keys())

    def ev(expr: Mapping[str, Any]) -> bool:
        if "all" in expr:
            return all(ev(x) for x in expr["all"])
        if "any" in expr:
            return any(ev(x) for x in expr["any"])
        if "not" in expr:
            return not ev(expr["not"])
        left, right, op = facts[expr["fact"]], expr["value"], expr["op"]
        return {
            "eq": lambda: left == right,
            "ne": lambda: left != right,
            "gt": lambda: left > right,
            "gte": lambda: left >= right,
            "lt": lambda: left < right,
            "lte": lambda: left <= right,
            "in": lambda: left in right,
        }[op]()

    return ev(document["expr"])


def validate_media_port_spec(spec: Mapping[str, Any], *, is_input: bool) -> dict[str, Any]:
    """Validate against the normative MediaPortSpec v2 JSON Schema, then apply Plan-only cardinality rules."""
    schema = json.loads((ROOT / "schemas/media_port.schema.json").read_text(encoding="utf-8"))
    try:
        import jsonschema
    except ImportError as exc:
        raise RuntimeError("jsonschema is required to validate MediaPortSpec v2") from exc
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(spec), key=lambda e: list(e.absolute_path))
    if errors:
        first = errors[0]
        path = ".".join(map(str, first.absolute_path)) or "$"
        raise ValueError(f"MediaPortSpec schema error at {path}: {first.message}")
    normalized = dict(spec)
    cardinality = normalized.get("cardinality", "required-single")
    if not is_input and cardinality != "required-single":
        raise ValueError("output ports are single occurrences in Plan v2")
    normalized["cardinality"] = cardinality
    return normalized


def media_contract_compatible(producer: Mapping[str, Any], consumer: Mapping[str, Any]) -> bool:
    src = validate_media_port_spec(producer, is_input=False)
    dst = validate_media_port_spec(consumer, is_input=True)
    for key in ("artifact_type", "role", "media_kind"):
        if src[key] != dst[key]:
            return False
    for key in MEDIA_DIMENSIONS:
        if key in dst and key not in src:
            return False  # unresolved producer output cannot satisfy a narrowed consumer
        if key in src and key in dst:
            src_values = {canonical_json(v) for v in src[key]}
            dst_values = {canonical_json(v) for v in dst[key]}
            if not src_values.issubset(dst_values):
                return False
    return True


def compute_plan_fingerprint(con: sqlite3.Connection, plan_id: str) -> str:
    plan = con.execute(
        "SELECT plan_id,job_id,revision,parent_plan_id,planner_version FROM pipeline_plan WHERE plan_id=?",
        (plan_id,),
    ).fetchone()
    if plan is None:
        raise ValueError("unknown plan")
    nodes = []
    for row in con.execute(
        """SELECT plan_node_id,node_key,ordinal,stage,node_type,implementation_id,
                  implementation_version,implementation_fingerprint,hard_timeout_s,
                  activation_mode,activation_predicate,input_roles,output_roles,
                  input_contracts,output_contracts,resource_requirements
             FROM pipeline_plan_node WHERE plan_id=? ORDER BY ordinal,plan_node_id""",
        (plan_id,),
    ):
        values = list(row)
        for i in (10, 11, 12, 13, 14, 15):
            values[i] = parse_json(values[i], "plan JSON")
        nodes.append(values)
    edges = [list(row) for row in con.execute(
        """SELECT from_plan_node_id,to_plan_node_id,output_name,input_name
             FROM pipeline_plan_edge WHERE plan_id=?
             ORDER BY from_plan_node_id,to_plan_node_id,output_name,input_name""",
        (plan_id,),
    )]
    payload = {"plan": list(plan), "nodes": nodes, "edges": edges, "fingerprint_schema": 2}
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def validate_plan_graph(con: sqlite3.Connection, plan_id: str, declared_facts: Iterable[str] = frozenset()) -> bool:
    plan = con.execute("SELECT status FROM pipeline_plan WHERE plan_id=?", (plan_id,)).fetchone()
    if plan is None:
        raise ValueError("unknown plan")
    rows = con.execute(
        """SELECT plan_node_id,ordinal,node_type,activation_mode,activation_predicate,
                  input_roles,output_roles,input_contracts,output_contracts
             FROM pipeline_plan_node WHERE plan_id=? ORDER BY ordinal""",
        (plan_id,),
    ).fetchall()
    if not rows:
        raise ValueError("plan must contain at least one node")

    nodes: dict[str, dict[str, Any]] = {}
    for row in rows:
        node_id, ordinal, node_type, mode, pred_raw, in_roles_raw, out_roles_raw, in_contracts_raw, out_contracts_raw = row
        in_roles = parse_json(in_roles_raw, "input_roles")
        out_roles = parse_json(out_roles_raw, "output_roles")
        in_contracts = parse_json(in_contracts_raw, "input_contracts")
        out_contracts = parse_json(out_contracts_raw, "output_contracts")
        if not isinstance(in_roles, list) or any(not isinstance(x, str) or not x for x in in_roles) or len(set(in_roles)) != len(in_roles):
            raise ValueError("input_roles must be a unique non-empty string array")
        if not isinstance(out_roles, list) or any(not isinstance(x, str) or not x for x in out_roles) or len(set(out_roles)) != len(out_roles):
            raise ValueError("output_roles must be a unique non-empty string array")
        if not isinstance(in_contracts, dict) or set(in_roles) != set(in_contracts):
            raise ValueError("every input role requires exactly one MediaPortSpec")
        if not isinstance(out_contracts, dict) or set(out_roles) != set(out_contracts):
            raise ValueError("every output role requires exactly one MediaPortSpec")
        in_specs = {name: validate_media_port_spec(spec, is_input=True) for name, spec in in_contracts.items()}
        out_specs = {name: validate_media_port_spec(spec, is_input=False) for name, spec in out_contracts.items()}
        if mode == "IF_FACT":
            validate_predicate_document(parse_json(pred_raw, "activation_predicate"), declared_facts)
        if node_type == "DELIVERY_RENDER":
            audio_inputs = [spec for spec in in_specs.values() if spec["artifact_type"] == "audio"]
            if not audio_inputs or any(spec["role"] != "QUALITY_MASTER" for spec in audio_inputs):
                raise ValueError("DELIVERY_RENDER audio inputs must use QUALITY_MASTER")
        nodes[node_id] = {"ordinal": ordinal, "node_type": node_type, "inputs": in_specs, "outputs": out_specs, "input_roles": in_roles}

    edges = con.execute(
        "SELECT from_plan_node_id,to_plan_node_id,output_name,input_name FROM pipeline_plan_edge WHERE plan_id=?",
        (plan_id,),
    ).fetchall()
    incoming: dict[tuple[str, str], list[str]] = defaultdict(list)
    adjacency: dict[str, list[str]] = defaultdict(list)
    for src_id, dst_id, output_name, input_name in edges:
        if src_id not in nodes or dst_id not in nodes:
            raise ValueError("edge references unknown node")
        if nodes[src_id]["ordinal"] >= nodes[dst_id]["ordinal"]:
            raise ValueError("edge must move forward by ordinal")
        if output_name not in nodes[src_id]["outputs"]:
            raise ValueError("edge output port is not declared")
        if input_name not in nodes[dst_id]["inputs"]:
            raise ValueError("edge input port is not declared")
        if not media_contract_compatible(nodes[src_id]["outputs"][output_name], nodes[dst_id]["inputs"][input_name]):
            raise ValueError("edge media contract incompatible")
        incoming[(dst_id, input_name)].append(src_id)
        adjacency[src_id].append(dst_id)

    for node_id, node in nodes.items():
        for input_name, spec in node["inputs"].items():
            count = len(incoming[(node_id, input_name)])
            card = spec["cardinality"]
            if card == "required-single" and count != 1:
                raise ValueError(f"required input {node_id}.{input_name} must have exactly one producer")
            if card == "optional-single" and count > 1:
                raise ValueError(f"optional input {node_id}.{input_name} accepts at most one producer")
            if card == "variadic" and count < 1:
                raise ValueError(f"variadic input {node_id}.{input_name} requires at least one producer")
            if card != "variadic" and count > 1:
                raise ValueError(f"single input {node_id}.{input_name} rejects fan-in")

    roots = [node_id for node_id, node in nodes.items() if not node["input_roles"]]
    if not roots:
        raise ValueError("plan requires at least one source/root node")
    seen = set(roots)
    queue = deque(roots)
    while queue:
        current = queue.popleft()
        for nxt in adjacency[current]:
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    if seen != set(nodes):
        missing = sorted(set(nodes) - seen)
        raise ValueError(f"unreachable PlanNode(s): {missing}")
    return True


def build_plan_validation_report(con: sqlite3.Connection, plan_id: str, declared_facts: Iterable[str] = frozenset()) -> dict[str, Any]:
    """Run PlanSealValidator rules and return structured, auditable per-rule evidence."""
    validate_plan_graph(con, plan_id, declared_facts)
    rows = con.execute(
        """SELECT plan_node_id,input_roles,input_contracts,output_contracts
             FROM pipeline_plan_node WHERE plan_id=? ORDER BY ordinal,plan_node_id""",
        (plan_id,),
    ).fetchall()
    nodes = [row[0] for row in rows]
    roots: list[str] = []
    cardinality = {"required-single": 0, "optional-single": 0, "variadic": 0}
    input_specs: dict[tuple[str, str], dict[str, Any]] = {}
    output_specs: dict[tuple[str, str], dict[str, Any]] = {}
    for node_id, input_roles_raw, input_contracts_raw, output_contracts_raw in rows:
        input_roles = parse_json(input_roles_raw, "input_roles")
        if not input_roles:
            roots.append(node_id)
        for name, spec in parse_json(input_contracts_raw, "input_contracts").items():
            normalized = validate_media_port_spec(spec, is_input=True)
            cardinality[normalized["cardinality"]] += 1
            input_specs[(node_id, name)] = normalized
        for name, spec in parse_json(output_contracts_raw, "output_contracts").items():
            output_specs[(node_id, name)] = validate_media_port_spec(spec, is_input=False)

    media_evidence: list[dict[str, Any]] = []
    for src_id, dst_id, output_name, input_name in con.execute(
        """SELECT from_plan_node_id,to_plan_node_id,output_name,input_name
             FROM pipeline_plan_edge WHERE plan_id=?
             ORDER BY from_plan_node_id,to_plan_node_id,output_name,input_name""",
        (plan_id,),
    ):
        media_evidence.append({
            "from": src_id,
            "output": output_name,
            "to": dst_id,
            "input": input_name,
            "compatible": media_contract_compatible(
                output_specs[(src_id, output_name)], input_specs[(dst_id, input_name)]),
        })

    return {
        "schema": PLAN_VALIDATION_REPORT_SCHEMA,
        "passed": True,
        "counts": {"nodes": len(nodes), "edges": len(media_evidence)},
        "cardinality": cardinality,
        "media_subsets": media_evidence,
        "reachability": {"roots": roots, "reachable": nodes, "unreachable": []},
        "checks": {
            "port_cardinality": True,
            "media_subsets": True,
            "reachability": True,
            "predicate_validation": True,
            "ordinal_acyclicity": True,
            "delivery_render_quality_master": True,
        },
    }


def record_plan_validation_receipt(con: sqlite3.Connection, plan_id: str, validator_version: str = "PlanSealValidator/R2.1.5.07") -> str:
    """Production-facing contract helper: validate, fingerprint, and persist the immutable receipt."""
    report = build_plan_validation_report(con, plan_id)
    fp = compute_plan_fingerprint(con, plan_id)
    con.execute(
        """INSERT INTO pipeline_plan_validation(
               plan_id,plan_fingerprint,validator_version,report_json,validated_at)
           VALUES(?,?,?,?,?)""",
        (plan_id, fp, validator_version, canonical_json(report), CANONICAL_TS),
    )
    return fp


def validate_manifest_document(document: Mapping[str, Any]) -> bool:
    schema = json.loads((ROOT / "schemas/manifest.schema.json").read_text(encoding="utf-8"))
    try:
        import jsonschema
    except ImportError as exc:
        raise RuntimeError("jsonschema is required to validate Manifest v1") from exc
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path))
    if errors:
        first = errors[0]
        path = ".".join(map(str, first.absolute_path)) or "$"
        raise ValueError(f"manifest schema error at {path}: {first.message}")
    validate_manifest_semantics(document)
    return True


def validate_package_graph(document: Mapping[str, Any]) -> bool:
    if document.get("schema") != "audioprep.package-graph.v1":
        raise ValueError("invalid package graph schema")
    packages = document.get("packages")
    if not isinstance(packages, list) or document.get("package_count") != 18 or len(packages) != 18:
        raise ValueError("package graph must contain exactly 18 packages")
    names = [p.get("name") for p in packages]
    if len(set(names)) != 18 or any(not isinstance(n, str) or not n.startswith("audioprep-") for n in names):
        raise ValueError("package names must be 18 unique audioprep-* values")
    by_name = {p["name"]: p for p in packages}
    indegree = {name: 0 for name in names}
    reverse: dict[str, list[str]] = defaultdict(list)
    for p in packages:
        deps = p.get("depends_on")
        if not isinstance(deps, list) or len(set(deps)) != len(deps):
            raise ValueError("depends_on must be a unique array")
        for dep in deps:
            if dep not in by_name or dep == p["name"]:
                raise ValueError("package dependency is unknown or self-referential")
            if by_name[dep].get("layer", -1) >= p.get("layer", -1):
                raise ValueError("package dependency must point to a lower layer")
            indegree[p["name"]] += 1
            reverse[dep].append(p["name"])
    q = deque(name for name, degree in indegree.items() if degree == 0)
    visited = 0
    while q:
        name = q.popleft(); visited += 1
        for nxt in reverse[name]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                q.append(nxt)
    if visited != 18:
        raise ValueError("package dependency graph contains a cycle")
    return True


def validate_public_api_type_references(document: Mapping[str, Any]) -> bool:
    types = document.get("types")
    enums = document.get("enums")
    value_objects = document.get("value_objects")
    operations = document.get("operations")
    if not isinstance(types, dict) or not types:
        raise ValueError("Public API types must be a non-empty object")
    if not isinstance(enums, dict) or not isinstance(value_objects, dict) or not isinstance(operations, dict):
        raise ValueError("Public API enums, value_objects and operations must be objects")

    declared = set(types) | set(enums) | set(value_objects)
    builtins = {"str", "int", "float", "bool", "None", "list", "dict", "set", "tuple"}
    enum_members = {member for values in enums.values() if isinstance(values, list) for member in values if isinstance(member, str)}
    token_re = re.compile(r"(?<!\.)\b[A-Za-z_][A-Za-z0-9_]*\b")

    def check_expression(expression: Any, context: str) -> None:
        if not isinstance(expression, str) or not expression.strip():
            raise ValueError(f"{context} must be a non-empty type expression")
        # os.PathLike is the only qualified external intrinsic admitted by Public API v1.
        scrubbed = re.sub(r"\bos\.PathLike\b", "PathLikeIntrinsic", expression)
        for token in token_re.findall(scrubbed):
            if token == "PathLikeIntrinsic" or token in builtins or token in declared:
                continue
            if token.isupper() and token in enum_members:
                continue
            raise ValueError(f"{context} references undefined type {token}")

    for alias, expression in types.items():
        if not isinstance(alias, str):
            raise ValueError("Public API type aliases must use string names")
        check_expression(expression, f"Public API type alias {alias}")

    for name, spec in value_objects.items():
        if not isinstance(spec, dict):
            raise ValueError(f"Public API value object {name} must be an object")
        for section in ("required", "optional"):
            fields = spec.get(section, {})
            if not isinstance(fields, dict):
                raise ValueError(f"Public API value object {name}.{section} must be an object")
            for field, expression in fields.items():
                check_expression(expression, f"Public API value object {name}.{field}")

    for name, operation in operations.items():
        if not isinstance(operation, dict):
            raise ValueError(f"Public API operation {name} must be an object")
        params = operation.get("params")
        if not isinstance(params, dict):
            raise ValueError(f"Public API operation {name}.params must be an object")
        for param, expression in params.items():
            check_expression(expression, f"Public API operation {name} param {param}")
        check_expression(operation.get("returns"), f"Public API operation {name} return")
    return True


def validate_public_api_type_aliases(document: Mapping[str, Any]) -> bool:
    # Compatibility entry point retained for callers of R2.1.5.04/05; validation is now full-contract closure.
    return validate_public_api_type_references(document)


def validate_artifact_vocabulary_sync() -> bool:
    """N1: one normative vocabulary source must exactly match SQL and MediaPortSpec v2."""
    vocab = json.loads((ROOT / "contracts/artifact_vocabulary.v1.json").read_text(encoding="utf-8"))
    if vocab.get("schema") != "audioprep.artifact-vocabulary.v1" or vocab.get("design_revision") != "R2.1.5.07":
        raise ValueError("artifact vocabulary identity mismatch")
    types = vocab.get("artifact_types")
    roles = vocab.get("artifact_roles")
    if not isinstance(types, list) or not types or len(types) != len(set(types)):
        raise ValueError("artifact_types vocabulary must be a unique non-empty list")
    if not isinstance(roles, list) or not roles or len(roles) != len(set(roles)):
        raise ValueError("artifact_roles vocabulary must be a unique non-empty list")

    media = json.loads((ROOT / "schemas/media_port.schema.json").read_text(encoding="utf-8"))
    props = media.get("properties", {})
    if props.get("artifact_type", {}).get("enum") != types:
        raise ValueError("MediaPortSpec artifact_type drift from artifact vocabulary")
    if props.get("media_kind", {}).get("enum") != types:
        raise ValueError("MediaPortSpec media_kind drift from artifact vocabulary")
    if props.get("role", {}).get("enum") != roles:
        raise ValueError("MediaPortSpec role drift from artifact vocabulary")

    schema_text = (ROOT / "sql/schema.sql").read_text(encoding="utf-8")
    type_blocks = re.findall(r"artifact_type TEXT NOT NULL CHECK \(artifact_type IN \(([^)]*)\)\)", schema_text)
    role_blocks = re.findall(r"artifact_role TEXT NOT NULL CHECK \(artifact_role IN \(([^)]*)\)\)", schema_text)
    expected_types = types
    expected_roles = roles
    if len(type_blocks) != 2 or any(re.findall(r"'([^']+)'", block) != expected_types for block in type_blocks):
        raise ValueError("SQL artifact_type vocabulary drift from normative source")
    if len(role_blocks) != 2 or any(re.findall(r"'([^']+)'", block) != expected_roles for block in role_blocks):
        raise ValueError("SQL artifact_role vocabulary drift from normative source")
    return True


def load_planner_reference_api():
    path = ROOT / "packages/audioprep-planner/reference_api.py"
    spec = importlib.util.spec_from_file_location("audioprep_planner_reference_api", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load audioprep-planner reference API")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def execute_transition_matrix_case(trigger_sql: str, machine: Mapping[str, Any], case: Mapping[str, Any]) -> bool:
    """Execute one matrix state pair against the real transition trigger SQL in isolation."""
    table_match = re.search(r"\bON\s+([A-Za-z_][A-Za-z0-9_]*)", trigger_sql, re.I)
    if not table_match:
        raise AssertionError("cannot parse transition trigger table")
    table = table_match.group(1)
    field = machine["field"]
    con = sqlite3.connect(":memory:")
    # blob_gc_transition_guard also reads OLD.blob_id and strong-reference tables; keep
    # the support tables empty so this generated suite isolates only state legality.
    if table == "blob":
        con.execute("CREATE TABLE blob(blob_id TEXT, gc_state TEXT NOT NULL)")
        con.execute("CREATE TABLE artifact(artifact_id TEXT, blob_id TEXT)")
        con.execute("CREATE TABLE artifact_reference(artifact_id TEXT)")
        con.execute("INSERT INTO blob(blob_id,gc_state) VALUES('b',?)", (case["from"],))
    else:
        con.execute(f"CREATE TABLE {table}({field} TEXT NOT NULL)")
        con.execute(f"INSERT INTO {table}({field}) VALUES(?)", (case["from"],))
    con.executescript(trigger_sql)
    try:
        con.execute(f"UPDATE {table} SET {field}=?", (case["to"],))
    except sqlite3.DatabaseError as exc:
        if case["allowed"]:
            raise AssertionError(f"allowed transition rejected: {exc}") from exc
        return True
    if not case["allowed"]:
        raise AssertionError("forbidden transition was accepted")
    return True


def open_schema_db() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA recursive_triggers=ON")
    con.executescript((ROOT / "sql/schema.sql").read_text(encoding="utf-8"))
    return con


# reusable-prefix-padding-341
# reusable-prefix-padding-342
# reusable-prefix-padding-343
# reusable-prefix-padding-344
# reusable-prefix-padding-345
# reusable-prefix-padding-346
# reusable-prefix-padding-347
# reusable-prefix-padding-348
# reusable-prefix-padding-349
# reusable-prefix-padding-350
# reusable-prefix-padding-351
# reusable-prefix-padding-352
# reusable-prefix-padding-353
# reusable-prefix-padding-354
# reusable-prefix-padding-355
# reusable-prefix-padding-356
# reusable-prefix-padding-357
# reusable-prefix-padding-358
# reusable-prefix-padding-359
# reusable-prefix-padding-360
# reusable-prefix-padding-361
# reusable-prefix-padding-362
# reusable-prefix-padding-363
# reusable-prefix-padding-364
# reusable-prefix-padding-365
# reusable-prefix-padding-366
# reusable-prefix-padding-367
# reusable-prefix-padding-368
# reusable-prefix-padding-369
# reusable-prefix-padding-370
# reusable-prefix-padding-371
# reusable-prefix-padding-372
# reusable-prefix-padding-373
# reusable-prefix-padding-374
# reusable-prefix-padding-375
# reusable-prefix-padding-376
# reusable-prefix-padding-377
# reusable-prefix-padding-378
# reusable-prefix-padding-379
# reusable-prefix-padding-380
# reusable-prefix-padding-381
# reusable-prefix-padding-382
# reusable-prefix-padding-383
# reusable-prefix-padding-384
# reusable-prefix-padding-385
# reusable-prefix-padding-386
# reusable-prefix-padding-387
# reusable-prefix-padding-388
# reusable-prefix-padding-389
# reusable-prefix-padding-390
# reusable-prefix-padding-391
# reusable-prefix-padding-392
# reusable-prefix-padding-393
# reusable-prefix-padding-394
# reusable-prefix-padding-395
def sha(ch: str) -> str:
    return "sha256:" + ch * 64


def add_batch_job(con: sqlite3.Connection, job_id: str = "j1", batch_id: str = "b1") -> None:
    con.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder) VALUES(?,?,?)", (batch_id, "TRUSTED", "/input"))
    con.execute("INSERT INTO job(job_id,batch_id,source_path) VALUES(?,?,?)", (job_id, batch_id, f"/input/{job_id}.wav"))


def port(*, rates: list[int] | None = None, cardinality: str | None = None, role: str = "PIPELINE_AUDIO") -> dict[str, Any]:
    result: dict[str, Any] = {"artifact_type": "audio", "role": role, "media_kind": "audio"}
    if rates is not None:
        result["sample_rate_hz"] = rates
    if cardinality is not None:
        result["cardinality"] = cardinality
    return result


def add_node(
    con: sqlite3.Connection,
    plan_id: str,
    node_id: str,
    ordinal: int,
    inputs: Mapping[str, Mapping[str, Any]],
    outputs: Mapping[str, Mapping[str, Any]],
    *,
    activation_mode: str = "ALWAYS",
    predicate: Mapping[str, Any] | None = None,
) -> None:
    con.execute(
        """INSERT INTO pipeline_plan_node(
               plan_node_id,plan_id,node_key,ordinal,stage,node_type,implementation_id,
               implementation_version,implementation_fingerprint,hard_timeout_s,
               activation_mode,activation_predicate,input_roles,output_roles,input_contracts,output_contracts)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            node_id, plan_id, node_id, ordinal, node_id, node_id, f"impl.{node_id}", "1.0", f"fp-{node_id}", 60,
            activation_mode, canonical_json(predicate or {}), canonical_json(list(inputs)), canonical_json(list(outputs)),
            canonical_json(inputs), canonical_json(outputs),
        ),
    )


def add_minimal_plan(con: sqlite3.Connection, job_id: str = "j1", plan_id: str = "p1") -> None:
    con.execute("INSERT INTO pipeline_plan(plan_id,job_id,planner_version) VALUES(?,?,?)", (plan_id, job_id, "planner-r21503"))
    add_node(con, plan_id, f"{plan_id}-source", 0, {}, {"out": port(rates=[16000])})


def seal_plan(con: sqlite3.Connection, plan_id: str) -> str:
    fp = record_plan_validation_receipt(con, plan_id)
    con.execute(
        "UPDATE pipeline_plan SET status='SEALED',plan_fingerprint=?,sealed_at=? WHERE plan_id=?",
        (fp, CANONICAL_TS, plan_id),
    )
    return fp


def freeze_source(con: sqlite3.Connection, job_id: str = "j1", suffix: str = "a") -> str:
    blob_id, artifact_id = f"blob-{job_id}", f"source-{job_id}"
    digest = 'sha256:' + hashlib.sha256(f'{job_id}:{suffix}'.encode('utf-8')).hexdigest()
    con.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES(?,?,?,?)", (blob_id, digest, f"/cas/source-{job_id}-{suffix}", 100))
    con.execute(
        """INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,producer_component,
                                retention_class,retention_until)
           VALUES(?,?,?,?,?,?,?)""",
        (artifact_id, blob_id, "audio", "SOURCE_MEDIA", "source-ingest", "source", FUTURE_TS),
    )
    con.execute(
        "INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) VALUES(?, 'JOB', ?, 'source')",
        (artifact_id, job_id),
    )
    con.execute(
        """UPDATE job SET source_size_bytes=100,source_mtime_ns=1,source_content_hash=?,
                          source_artifact_id=?,source_identity_frozen_at=?
             WHERE job_id=?""",
        (digest, artifact_id, CANONICAL_TS, job_id),
    )
    return artifact_id


def activate_job_for_execution(
    con: sqlite3.Connection,
    plan_id: str = "p1",
    job_id: str = "j1",
    *,
    run_token: str = "r",
    worker_id: str = "w",
) -> int:
    """Bind a SEALED Plan and enter RUNNING with the canonical Job fence for execution fixtures."""
    row = con.execute("SELECT status,source_identity_frozen_at,current_plan_id,dispatch_generation FROM job WHERE job_id=?", (job_id,)).fetchone()
    if row is None:
        raise ValueError("unknown job")
    status, frozen, current_plan, generation = row
    if frozen is None:
        freeze_source(con, job_id, suffix="0")
    if current_plan is None:
        con.execute("UPDATE job SET current_plan_id=? WHERE job_id=?", (plan_id, job_id))
    elif current_plan != plan_id:
        raise ValueError("fixture Job already bound to a different Plan")
    if status == "CREATED":
        con.execute("UPDATE job SET status='QUEUED' WHERE job_id=?", (job_id,))
        status = "QUEUED"
    if status in ("QUEUED", "WAITING_DECISION"):
        generation += 1
        con.execute(
            """UPDATE job SET status='RUNNING',dispatch_generation=?,active_run_token=?,
                      lease_expires_at=?,worker_id=?,started_at=COALESCE(started_at,?) WHERE job_id=?""",
            (generation, run_token, FUTURE_TS, worker_id, CANONICAL_TS, job_id),
        )
    elif status != "RUNNING":
        raise ValueError(f"fixture Job cannot enter RUNNING from {status}")
    return con.execute("SELECT dispatch_generation FROM job WHERE job_id=?", (job_id,)).fetchone()[0]


@dataclass
class Suite:
    passed: int = 0
    total: int = 0
    lines: list[str] | None = None

    def __post_init__(self) -> None:
        self.lines = []

    def ok(self, name: str, detail: str = "") -> None:
        self.total += 1; self.passed += 1
        self.lines.append(f"OK   {name}" + (f" — {detail}" if detail else ""))

    def fail(self, name: str, detail: str) -> None:
        self.total += 1
        self.lines.append(f"FAIL {name} — {detail}")

    def expect_ok(self, name: str, fn: Callable[[], Any]) -> None:
        try:
            result = fn()
            if isinstance(result, sqlite3.Cursor):
                detail = "accepted"
            elif result is None or result is True:
                detail = ""
            else:
                detail = str(result)
            self.ok(name, detail)
        except Exception as exc:
            self.fail(name, f"{type(exc).__name__}: {exc}")

    def expect_rejected(self, name: str, fn: Callable[[], Any], contains: str) -> None:
        if not isinstance(contains, str) or not contains:
            raise ValueError("expect_rejected requires a non-empty expected message substring")
        try:
            fn()
        except Exception as exc:
            text = str(exc)
            if contains not in text:
                self.fail(name, f"wrong rejection: {type(exc).__name__}: {text}")
            else:
                self.ok(name, text)
        else:
            self.fail(name, "invalid operation was accepted")


def run_validation() -> int:
    s = Suite()

    # Schema inventory and basic contract markers.
    con = open_schema_db()
    s.expect_ok("schema executes with 23 tables", lambda: (_ for _ in ()).throw(AssertionError("wrong table count"))
                if con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0] != 23 else True)
    s.expect_ok("schema has exactly 131 invariant triggers", lambda: (_ for _ in ()).throw(AssertionError("too few triggers"))
                if con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0] != 131 else True)
    s.expect_ok("design revision marker", lambda: (_ for _ in ()).throw(AssertionError("revision mismatch"))
                if (ROOT / "DESIGN_REVISION.txt").read_text(encoding="utf-8").strip() != "R2.1.5.07" else True)

    s.expect_ok("N1 normative artifact vocabulary exactly matches SQL and MediaPortSpec", validate_artifact_vocabulary_sync)

    # Immutable CAS and Artifact identity.
    con = open_schema_db(); add_batch_job(con); freeze_source(con)
    for column, value in [("content_hash", sha("b")), ("path", "/cas/new"), ("size_bytes", 999)]:
        s.expect_rejected(f"Blob {column} immutable", lambda c=column, v=value: con.execute(f"UPDATE blob SET {c}=? WHERE blob_id='blob-j1'", (v,)), "immutable")
    for column, value in [("blob_id", "missing"), ("artifact_role", "QUALITY_MASTER"), ("artifact_type", "candidate"), ("producer_component", "other")]:
        s.expect_rejected(f"Artifact {column} immutable", lambda c=column, v=value: con.execute(f"UPDATE artifact SET {c}=? WHERE artifact_id='source-j1'", (v,)), "immutable")
    s.expect_rejected("frozen SOURCE_MEDIA ownership cannot be released", lambda: con.execute("DELETE FROM artifact_reference WHERE artifact_id='source-j1'"), "frozen")
    s.expect_rejected("frozen SourceIdentity cannot change", lambda: con.execute("UPDATE job SET source_mtime_ns=2 WHERE job_id='j1'"), "immutable")

    # B4: package-level production-facing seal entrypoint must invoke PlanSealValidator.
    planner_api = load_planner_reference_api()
    con = open_schema_db(); add_batch_job(con, "api-job", "api-batch"); add_minimal_plan(con, "api-job", "api-plan")
    api_validator = planner_api.PlanSealValidator(build_plan_validation_report, compute_plan_fingerprint)
    s.expect_ok("B4 planner package seal_plan invokes PlanSealValidator and seals", lambda: planner_api.seal_plan(con, "api-plan", api_validator))
    s.expect_ok("B4 planner package seal path persisted exactly one receipt", lambda: (_ for _ in ()).throw(AssertionError("receipt missing")) if con.execute("SELECT COUNT(*) FROM pipeline_plan_validation WHERE plan_id='api-plan'").fetchone()[0] != 1 else True)
    con = open_schema_db(); add_batch_job(con, "api-job2", "api-batch2"); add_minimal_plan(con, "api-job2", "api-plan2")
    class RejectingValidator(planner_api.PlanSealValidator):
        def validate_and_record(self, con, plan_id):
            raise RuntimeError("validator-sentinel")
    rejecting = RejectingValidator(build_plan_validation_report, compute_plan_fingerprint)
    s.expect_rejected("B4 seal_plan cannot bypass a rejecting PlanSealValidator", lambda: planner_api.seal_plan(con, "api-plan2", rejecting), "validator-sentinel")
    s.expect_ok("B4 rejected validator leaves Plan DRAFT without receipt", lambda: (_ for _ in ()).throw(AssertionError("seal bypassed validator")) if con.execute("SELECT status,(SELECT COUNT(*) FROM pipeline_plan_validation WHERE plan_id='api-plan2') FROM pipeline_plan WHERE plan_id='api-plan2'").fetchone() != ("DRAFT",0) else True)

    # Job/Plan binding including INSERT bypass.
    con = open_schema_db(); add_batch_job(con, "j1", "b1"); add_minimal_plan(con); seal_plan(con, "p1")
    con.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder) VALUES('b2','TRUSTED','/b2')")
    s.expect_rejected("Job INSERT cannot preload current_plan_id", lambda: con.execute("INSERT INTO job(job_id,batch_id,source_path,current_plan_id) VALUES('j2','b2','/x','p1')"), "installed after Job creation")
    con.execute("INSERT INTO job(job_id,batch_id,source_path) VALUES('j2','b2','/x')")
    s.expect_rejected("cross-Job current_plan_id rejected", lambda: con.execute("UPDATE job SET current_plan_id='p1' WHERE job_id='j2'"), "same-job SEALED")
    s.expect_ok("same-Job SEALED current_plan_id accepted", lambda: con.execute("UPDATE job SET current_plan_id='p1' WHERE job_id='j1'"))

    # Plan seal and immutable draft receipt behavior.
    con = open_schema_db(); add_batch_job(con)
    s.expect_rejected("Plan INSERT cannot start SEALED", lambda: con.execute("INSERT INTO pipeline_plan(plan_id,job_id,status,planner_version,plan_fingerprint,sealed_at) VALUES('p','j1','SEALED','v',?, 'x')", (sha('a'),)), "unsealed DRAFT")
    con.execute("INSERT INTO pipeline_plan(plan_id,job_id,planner_version) VALUES('p','j1','v')")
    add_node(con, "p", "n", 0, {}, {"out": port(rates=[16000])})
    fp = record_plan_validation_receipt(con, "p", "PlanSealValidator/test")
    s.expect_rejected("validated DRAFT node update rejected", lambda: con.execute("UPDATE pipeline_plan_node SET stage='changed' WHERE plan_node_id='n'"), "validated DRAFT")
    s.expect_rejected("validated DRAFT planner metadata update rejected", lambda: con.execute("UPDATE pipeline_plan SET planner_version='changed' WHERE plan_id='p'"), "validated DRAFT")
    s.expect_rejected("seal fingerprint mismatch rejected", lambda: con.execute("UPDATE pipeline_plan SET status='SEALED',plan_fingerprint=?,sealed_at='2026-08-09T05:00:00.000Z' WHERE plan_id='p'", (sha('f'),)), "matching")
    s.expect_ok("matching PlanSealValidator receipt seals plan", lambda: con.execute("UPDATE pipeline_plan SET status='SEALED',plan_fingerprint=?,sealed_at='2026-08-09T05:00:00.000Z' WHERE plan_id='p'", (fp,)))
    s.expect_rejected("sealed node INSERT rejected", lambda: add_node(con, "p", "n2", 1, {}, {}), "immutable")
    s.expect_rejected("sealed plan metadata immutable", lambda: con.execute("UPDATE pipeline_plan SET planner_version='other' WHERE plan_id='p'"), "immutable")

    # B4: a structurally valid receipt must carry plan-bound detailed evidence, not only pass booleans.
    con = open_schema_db(); add_batch_job(con)
    con.execute("INSERT INTO pipeline_plan(plan_id,job_id,planner_version) VALUES('pr','j1','v')")
    add_node(con, "pr", "src", 0, {}, {"out": port(rates=[16000])})
    add_node(con, "pr", "dst", 1, {"in": port(rates=[16000], cardinality="required-single")}, {})
    con.execute("INSERT INTO pipeline_plan_edge(plan_id,from_plan_node_id,to_plan_node_id,output_name,input_name) VALUES('pr','src','dst','out','in')")
    report = build_plan_validation_report(con, "pr")
    fp = compute_plan_fingerprint(con, "pr")
    missing = deepcopy(report); missing.pop("cardinality")
    s.expect_rejected("Plan receipt requires cardinality evidence", lambda: con.execute(
        "INSERT INTO pipeline_plan_validation(plan_id,plan_fingerprint,validator_version,report_json,validated_at) VALUES('pr',?,'fake',?,'2026-08-09T05:00:00.000Z')",
        (fp, canonical_json(missing))), "structured PlanSealValidator report")
    tampered = deepcopy(report); tampered["reachability"]["reachable"] = ["src"]
    s.expect_rejected("Plan receipt reachability evidence is bound to Plan nodes", lambda: con.execute(
        "INSERT INTO pipeline_plan_validation(plan_id,plan_fingerprint,validator_version,report_json,validated_at) VALUES('pr',?,'fake',?,'2026-08-09T05:00:00.000Z')",
        (fp, canonical_json(tampered))), "structured PlanSealValidator report")
    tampered = deepcopy(report); tampered["media_subsets"][0]["to"] = "src"
    s.expect_rejected("Plan receipt media evidence is bound to Plan edges", lambda: con.execute(
        "INSERT INTO pipeline_plan_validation(plan_id,plan_fingerprint,validator_version,report_json,validated_at) VALUES('pr',?,'fake',?,'2026-08-09T05:00:00.000Z')",
        (fp, canonical_json(tampered))), "structured PlanSealValidator report")

    # Plan graph cardinality and media contracts.
    def plan_case(builder: Callable[[sqlite3.Connection], None]) -> sqlite3.Connection:
        c = open_schema_db(); add_batch_job(c); c.execute("INSERT INTO pipeline_plan(plan_id,job_id,planner_version) VALUES('p','j1','v')"); builder(c); return c

    c = plan_case(lambda c: add_node(c, "p", "src", 0, {}, {"out": port(rates=[16000])}))
    s.expect_ok("canonical one-node Plan validates", lambda: validate_plan_graph(c, "p"))

    def missing_required(c: sqlite3.Connection) -> None:
        add_node(c, "p", "src", 0, {}, {"out": port(rates=[16000])})
        add_node(c, "p", "dst", 1, {"a": port(rates=[16000]), "b": port(rates=[16000])}, {})
        c.execute("INSERT INTO pipeline_plan_edge VALUES('p','src','dst','out','a')")
    c = plan_case(missing_required)
    s.expect_rejected("required input cannot be unbound", lambda: validate_plan_graph(c, "p"), "exactly one")

    def optional_unbound(c: sqlite3.Connection) -> None:
        add_node(c, "p", "src", 0, {}, {"out": port(rates=[16000])})
        add_node(c, "p", "dst", 1, {"in": port(rates=[16000], cardinality="optional-single")}, {})
        c.execute("INSERT INTO pipeline_plan_edge VALUES('p','src','dst','out','in')")
    c = plan_case(optional_unbound)
    s.expect_ok("optional-single with one producer accepted", lambda: validate_plan_graph(c, "p"))
    c.execute("DELETE FROM pipeline_plan_edge")
    s.expect_rejected("unreachable optional-only node still rejected", lambda: validate_plan_graph(c, "p"), "unreachable")

    def duplicate_fanin(c: sqlite3.Connection, card: str = "required-single") -> None:
        add_node(c, "p", "s1", 0, {}, {"out": port(rates=[16000])})
        add_node(c, "p", "s2", 1, {"x": port(rates=[16000])}, {"out": port(rates=[16000])})
        add_node(c, "p", "d", 2, {"in": port(rates=[16000], cardinality=card)}, {})
        c.execute("INSERT INTO pipeline_plan_edge VALUES('p','s1','s2','out','x')")
        c.execute("INSERT INTO pipeline_plan_edge VALUES('p','s1','d','out','in')")
        c.execute("INSERT INTO pipeline_plan_edge VALUES('p','s2','d','out','in')")
    c = plan_case(duplicate_fanin)
    s.expect_rejected("single input rejects two producers", lambda: validate_plan_graph(c, "p"), "exactly one")
    c = plan_case(lambda c: duplicate_fanin(c, "variadic"))
    s.expect_ok("variadic input explicitly accepts fan-in", lambda: validate_plan_graph(c, "p"))

    def subset_bad(c: sqlite3.Connection) -> None:
        add_node(c, "p", "s", 0, {}, {"out": port(rates=[16000, 48000])})
        add_node(c, "p", "d", 1, {"in": port(rates=[16000])}, {})
        c.execute("INSERT INTO pipeline_plan_edge VALUES('p','s','d','out','in')")
    c = plan_case(subset_bad)
    s.expect_rejected("producer media set must be subset of consumer set", lambda: validate_plan_graph(c, "p"), "incompatible")

    def subset_good(c: sqlite3.Connection) -> None:
        add_node(c, "p", "s", 0, {}, {"out": port(rates=[16000])})
        add_node(c, "p", "d", 1, {"in": port(rates=[16000, 48000])}, {})
        c.execute("INSERT INTO pipeline_plan_edge VALUES('p','s','d','out','in')")
    c = plan_case(subset_good)
    s.expect_ok("producer subset of consumer media set accepted", lambda: validate_plan_graph(c, "p"))
    s.expect_rejected("MediaPortSpec rejects unknown media_kind", lambda: validate_media_port_spec({"artifact_type":"audio","role":"PIPELINE_AUDIO","media_kind":"NOT_REAL"}, is_input=True), "schema error")
    s.expect_rejected("MediaPortSpec rejects sample rates below schema minimum", lambda: validate_media_port_spec({"artifact_type":"audio","role":"PIPELINE_AUDIO","media_kind":"audio","sample_rate_hz":[1]}, is_input=True), "schema error")
    s.expect_rejected("MediaPortSpec rejects invalid timeline alignment enum", lambda: validate_media_port_spec({"artifact_type":"audio","role":"PIPELINE_AUDIO","media_kind":"audio","timeline_alignment":["BROKEN"]}, is_input=True), "schema error")
    s.expect_rejected("MediaPortSpec rejects wrong dimension scalar types", lambda: validate_media_port_spec({"artifact_type":"audio","role":"PIPELINE_AUDIO","media_kind":"audio","container":[123]}, is_input=True), "schema error")

    c = open_schema_db(); add_batch_job(c); c.execute("INSERT INTO pipeline_plan(plan_id,job_id,planner_version) VALUES('p','j1','v')")
    add_node(c, "p", "a", 1, {}, {"out": port(rates=[16000])}); add_node(c, "p", "b", 0, {"in": port(rates=[16000])}, {})
    s.expect_rejected("back-edge rejected by ordinal trigger", lambda: c.execute("INSERT INTO pipeline_plan_edge VALUES('p','a','b','out','in')"), "forward")

    # Predicate behavior.
    pred = {"schema": PREDICATE_SCHEMA, "expr": {"all": [
        {"fact": "cap.gpu", "op": "eq", "value": True},
        {"not": {"fact": "source.clipped", "op": "eq", "value": True}},
    ]}}
    s.expect_ok("predicate deterministic evaluation true", lambda: (_ for _ in ()).throw(AssertionError()) if not evaluate_predicate(pred, {"cap.gpu": True, "source.clipped": False}) else True)
    s.expect_ok("predicate deterministic evaluation false", lambda: (_ for _ in ()).throw(AssertionError()) if evaluate_predicate(pred, {"cap.gpu": False, "source.clipped": False}) else True)
    s.expect_rejected("predicate rejects unknown fact", lambda: validate_predicate_document(pred, {"cap.gpu"}), "unknown fact")
    deep: dict[str, Any] = {"fact": "x", "op": "eq", "value": 1}
    for _ in range(14): deep = {"not": deep}
    s.expect_rejected("predicate depth bound", lambda: validate_predicate_document({"schema": PREDICATE_SCHEMA, "expr": deep}, {"x"}), "depth")

    # Job state machine and execution fence prerequisites.
    con = open_schema_db(); add_batch_job(con); add_minimal_plan(con); seal_plan(con, "p1"); freeze_source(con)
    con.execute("UPDATE job SET current_plan_id='p1' WHERE job_id='j1'")
    con.execute("UPDATE job SET status='QUEUED' WHERE job_id='j1'")
    s.expect_rejected("RUNNING requires full fence fields", lambda: con.execute("UPDATE job SET status='RUNNING' WHERE job_id='j1'"), "CHECK constraint failed")
    s.expect_ok("QUEUED to RUNNING with fence accepted", lambda: con.execute("""UPDATE job SET status='RUNNING',dispatch_generation=1,
        active_run_token='rt',lease_expires_at='2099-01-01T00:00:00.000Z',worker_id='w',started_at='2026-01-01T00:00:00.000Z' WHERE job_id='j1'"""))
    s.expect_ok("RUNNING to FAILED accepted with closure fields", lambda: con.execute("""UPDATE job SET status='FAILED',active_run_token=NULL,
        lease_expires_at=NULL,worker_id=NULL,finished_at='2026-01-02T00:00:00.000Z',error_code='NODE_CRASH',error_type='SYSTEM' WHERE job_id='j1'"""))
    s.expect_rejected("terminal FAILED Job cannot reopen", lambda: con.execute("UPDATE job SET status='QUEUED' WHERE job_id='j1'"), "terminal Job")
    s.expect_rejected("terminal Job error evidence immutable", lambda: con.execute("UPDATE job SET error_code='UNKNOWN_ERROR' WHERE job_id='j1'"), "terminal Job")

    # NodeExecution identity/lifecycle and STOP behavior.
    con = open_schema_db(); add_batch_job(con); add_minimal_plan(con); seal_plan(con, "p1"); activate_job_for_execution(con, "p1")
    s.expect_rejected("NodeExecution cross-plan identity rejected", lambda: con.execute("""INSERT INTO node_execution(
        execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,implementation_fingerprint)
        VALUES('e','j1','wrong','p1-source',1,1,'PENDING','fp-p1-source')"""), "identity mismatch")
    s.expect_rejected("NodeExecution fingerprint must match sealed PlanNode", lambda: con.execute("""INSERT INTO node_execution(
        execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,implementation_fingerprint)
        VALUES('efp','j1','p1','p1-source',1,1,'PENDING','wrong-fingerprint')"""), "fingerprint mismatch")
    s.expect_rejected("PENDING NodeExecution cannot preload hard deadline", lambda: con.execute("""INSERT INTO node_execution(
        execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,implementation_fingerprint,hard_deadline_at)
        VALUES('edeadline','j1','p1','p1-source',1,1,'PENDING','fp-p1-source','x')"""), "PENDING")
    s.expect_rejected("PENDING NodeExecution cannot preload error detail", lambda: con.execute("""INSERT INTO node_execution(
        execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,implementation_fingerprint,error_detail)
        VALUES('edetail','j1','p1','p1-source',1,1,'PENDING','fp-p1-source','premature')"""), "PENDING")
    con.execute("""INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,
        dispatch_generation,status,implementation_fingerprint) VALUES('e','j1','p1','p1-source',1,1,'PENDING','fp-p1-source')""")
    con.execute("UPDATE node_execution SET status='DISPATCHED' WHERE execution_id='e'")
    s.expect_rejected("RUNNING NodeExecution requires deadline/token/worker", lambda: con.execute("UPDATE node_execution SET status='RUNNING',started_at='2026-08-09T05:01:00.000Z' WHERE execution_id='e'"), "runtime fence fields")
    con.execute("UPDATE node_execution SET status='RUNNING',started_at='2026-08-09T05:01:00.000Z',hard_deadline_at='2026-08-09T05:02:00.000Z',run_token='r',worker_id='w' WHERE execution_id='e'")
    con.execute("UPDATE node_execution SET status='FAILED',completed_at='2026-08-09T05:02:00.000Z',error_code='NODE_TIMEOUT',run_token=NULL,worker_id=NULL WHERE execution_id='e'")
    s.expect_rejected("terminal NodeExecution cannot reopen", lambda: con.execute("UPDATE node_execution SET status='RUNNING' WHERE execution_id='e'"), "terminal node execution")
    s.expect_rejected("terminal NodeExecution cannot be deleted", lambda: con.execute("DELETE FROM node_execution WHERE execution_id='e'"), "immutable")

    con = open_schema_db(); add_batch_job(con); add_minimal_plan(con); seal_plan(con, "p1"); freeze_source(con); con.execute("UPDATE job SET current_plan_id='p1',status='QUEUED' WHERE job_id='j1'")
    con.execute("UPDATE job SET status='RUNNING',dispatch_generation=1,active_run_token='r',lease_expires_at='2099-01-01T00:00:00.000Z',worker_id='w',started_at='2026-08-09T05:00:00.000Z' WHERE job_id='j1'")
    con.execute("""INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,
        implementation_fingerprint) VALUES('e','j1','p1','p1-source',1,1,'PENDING','fp-p1-source')""")
    con.execute("UPDATE node_execution SET status='DISPATCHED' WHERE execution_id='e'")
    con.execute("UPDATE node_execution SET status='RUNNING',run_token='r',worker_id='w',started_at='2026-08-09T05:01:00.000Z',hard_deadline_at='2026-08-09T05:02:00.000Z' WHERE execution_id='e'")
    con.execute("UPDATE job SET status='STOPPED',active_run_token=NULL,lease_expires_at=NULL,worker_id=NULL,finished_at='2026-08-09T05:03:00.000Z' WHERE job_id='j1'")
    s.expect_ok("STOP closes active NodeExecution as ABORTED", lambda: (_ for _ in ()).throw(AssertionError()) if con.execute("SELECT status FROM node_execution WHERE execution_id='e'").fetchone()[0] != "ABORTED" else True)

    # Ownership counters and GC state machine.
    con = open_schema_db(); add_batch_job(con)
    con.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('b',?,'/cas/b',1)", (sha('b'),))
    con.execute("INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,producer_component,retention_class,retention_until) VALUES('a','b','audio','CACHE','test','temp','2099-01-01T00:00:00.000Z')")
    con.execute("INSERT INTO artifact_reference VALUES('a','JOB','j1','owned',strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
    s.expect_ok("strong reference increments Artifact and Blob counters", lambda: (_ for _ in ()).throw(AssertionError()) if con.execute("SELECT a.strong_refcount,b.strong_refcount FROM artifact a JOIN blob b ON b.blob_id=a.blob_id WHERE a.artifact_id='a'").fetchone() != (1,1) else True)
    s.expect_rejected("Artifact derived strong_refcount cannot be tampered", lambda: con.execute("UPDATE artifact SET strong_refcount=9 WHERE artifact_id='a'"), "derived")
    s.expect_rejected("Blob derived strong_refcount cannot be tampered", lambda: con.execute("UPDATE blob SET strong_refcount=4 WHERE blob_id='b'"), "derived")
    s.expect_rejected("strongly referenced Blob cannot enter TOMBSTONED", lambda: con.execute("UPDATE blob SET gc_state='TOMBSTONED',tombstoned_at='2026-08-09T05:00:00.000Z' WHERE blob_id='b'"), "strong ArtifactReference")
    s.expect_rejected("Blob cannot skip LIVE directly to PURGING", lambda: con.execute("UPDATE blob SET gc_state='PURGING',tombstoned_at='2026-08-09T05:00:00.000Z' WHERE blob_id='b'"), "illegal Blob GC transition")
    con.execute("DELETE FROM artifact_reference WHERE artifact_id='a'")
    s.expect_ok("strong reference deletion decrements counters", lambda: (_ for _ in ()).throw(AssertionError()) if con.execute("SELECT strong_refcount FROM blob WHERE blob_id='b'").fetchone()[0] != 0 else True)
    con.execute("UPDATE blob SET gc_state='TOMBSTONED',tombstoned_at='2026-08-09T05:00:00.000Z' WHERE blob_id='b'")
    s.expect_rejected("TOMBSTONED Blob cannot return to LIVE", lambda: con.execute("UPDATE blob SET gc_state='LIVE',tombstoned_at=NULL WHERE blob_id='b'"), "illegal Blob GC transition")
    con.execute("UPDATE blob SET gc_state='PURGING' WHERE blob_id='b'")
    s.expect_rejected("PURGING Blob rejects new ownership", lambda: con.execute("INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) VALUES('a','JOB','j1','again')"), "not LIVE")

    # Decision lifecycle.
    con = open_schema_db(); add_batch_job(con); add_minimal_plan(con); seal_plan(con, "p1"); activate_job_for_execution(con, "p1")
    con.execute("""INSERT INTO decision(decision_id,origin_job_id,batch_id,plan_node_id,decision_type,
        join_signature,join_signature_components,policy_signature,policy_signature_components,expires_at)
        VALUES('d','j1','b1','p1-source','SELECT','join','{}','policy','{}','2099-01-01T00:00:00.000Z')""")
    con.execute("""INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,
        implementation_fingerprint) VALUES('de','j1','p1','p1-source',1,1,'PENDING','fp-p1-source')""")
    con.execute("UPDATE node_execution SET status='DISPATCHED' WHERE execution_id='de'")
    con.execute("UPDATE node_execution SET status='RUNNING',run_token='r',worker_id='w',started_at='2026-08-09T05:01:00.000Z',hard_deadline_at='2026-08-09T05:02:00.000Z' WHERE execution_id='de'")
    con.execute("UPDATE node_execution SET status='SUCCEEDED',completed_at='2026-08-09T05:03:00.000Z',run_token=NULL,worker_id=NULL WHERE execution_id='de'")
    con.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('db',?,'/cas/decision',1)", (sha('e'),))
    con.execute("""INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,producer_component,
        producer_execution_id,retention_class,retention_until) VALUES('da','db','audio','CANDIDATE','node','de','candidate','2099-01-01T00:00:00.000Z')""")
    con.execute("INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) VALUES('da','DECISION','d','candidate')")
    con.execute("INSERT INTO decision_candidate(candidate_id,decision_id,selector_key,artifact_id) VALUES('dc','d','x','da')")
    s.expect_rejected("Decision cannot jump PENDING to APPLIED", lambda: con.execute("UPDATE decision SET status='APPLIED' WHERE decision_id='d'"), "illegal Decision")
    s.expect_rejected("PENDING Decision cannot receive resolution fields without transition", lambda: con.execute("UPDATE decision SET resolution_action='{\"selector_key\":\"x\"}',resolver_type='HUMAN',resolved_at='2026-08-09T05:04:00.000Z' WHERE decision_id='d'"), "exactly once")
    con.execute("UPDATE decision SET status='RESOLVED',resolution_action='{\"selector_key\":\"x\"}',resolver_type='HUMAN',resolved_at='2026-08-09T05:04:00.000Z',confidence=0.9 WHERE decision_id='d'")
    s.expect_rejected("RESOLVED Decision resolution cannot be rewritten", lambda: con.execute("UPDATE decision SET resolution_action='{\"selector_key\":\"y\"}' WHERE decision_id='d'"), "exactly once")
    con.execute("INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) VALUES('da','JOB','j1','selected')")
    con.execute("INSERT INTO boundary_fact(fact_id,job_id,fact_key,value_json,source_decision_id) VALUES('df','j1','decision.d.selector','\"x\"','d')")
    s.expect_rejected("plain Job ownership does not satisfy Decision selected transfer", lambda: con.execute(
        "UPDATE decision SET status='APPLIED',applied_at='2026-08-09T05:05:00.000Z' WHERE decision_id='d'"), "transferred ownership")
    con.execute("DELETE FROM artifact_reference WHERE artifact_id='da' AND owner_type='JOB' AND owner_id='j1' AND ref_kind='selected'")
    con.execute("INSERT INTO checkpoint(checkpoint_id,job_id,plan_id,plan_node_id,execution_id,status) VALUES('dcp','j1','p1','p1-source','de','OPEN')")
    con.execute("INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) VALUES('da','CHECKPOINT','dcp','selected')")
    s.expect_rejected("RESOLVED Decision candidate ref cannot be released manually", lambda: con.execute(
        "DELETE FROM artifact_reference WHERE artifact_id='da' AND owner_type='DECISION' AND owner_id='d'"), "terminal Decision transition")
    con.execute("UPDATE decision SET status='APPLIED',applied_at='2026-08-09T05:05:00.000Z' WHERE decision_id='d'")
    s.expect_ok("APPLIED transition releases Decision candidate refs atomically", lambda: (_ for _ in ()).throw(
        AssertionError("Decision refs remain")) if con.execute("SELECT COUNT(*) FROM artifact_reference WHERE owner_type='DECISION' AND owner_id='d'").fetchone()[0] else True)
    s.expect_rejected("APPLIED Decision is immutable", lambda: con.execute("UPDATE decision SET applied_at='2026-08-09T05:06:00.000Z' WHERE decision_id='d'"), "terminal Decision")

    con = open_schema_db(); add_batch_job(con)
    con.execute("INSERT INTO boundary_fact(fact_id,job_id,fact_key,value_json) VALUES('f','j1','choice','\"A\"')")
    s.expect_rejected("Boundary fact cannot be overwritten", lambda: con.execute("UPDATE boundary_fact SET value_json='\"B\"' WHERE fact_id='f'"), "append-only")
    s.expect_rejected("Boundary fact cannot be deleted", lambda: con.execute("DELETE FROM boundary_fact WHERE fact_id='f'"), "append-only")

    # Timeline helpers and tests.
    def timeline_db() -> sqlite3.Connection:
        c = open_schema_db(); add_batch_job(c); add_minimal_plan(c); seal_plan(c, "p1"); activate_job_for_execution(c, "p1")
        c.execute("""INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,
            implementation_fingerprint) VALUES('e','j1','p1','p1-source',1,1,'PENDING','fp-p1-source')""")
        c.execute("UPDATE node_execution SET status='DISPATCHED' WHERE execution_id='e'")
        c.execute("UPDATE node_execution SET status='RUNNING',run_token='r',worker_id='w',started_at='2026-08-09T05:01:00.000Z',hard_deadline_at='2026-08-09T05:02:00.000Z' WHERE execution_id='e'")
        c.execute("UPDATE node_execution SET status='SUCCEEDED',completed_at='2026-08-09T05:03:00.000Z',run_token=NULL,worker_id=NULL WHERE execution_id='e'")
        c.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('b',?,'/cas/t',1)", (sha('c'),))
        c.execute("""INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,producer_component,
            producer_execution_id,retention_class,retention_until) VALUES('a','b','audio','ASR_SEGMENT','node','e','audio','2099-01-01T00:00:00.000Z')""")
        c.execute("""INSERT INTO timeline_mapping(job_id,segment_id,artifact_id,mapping_kind,src_timebase_den,dst_timebase_den,dst_end_tick)
            VALUES('j1','seg','a','PIECEWISE',48000,16000,100)""")
        return c
    con = timeline_db()
    s.expect_rejected("first Timeline span must start at zero", lambda: con.execute("INSERT INTO timeline_span VALUES('j1','seg',0,'MAP',0,10,5,15)"), "tick zero")
    con.execute("INSERT INTO timeline_span VALUES('j1','seg',0,'MAP',0,40,0,40)")
    s.expect_rejected("Timeline destination gap rejected", lambda: con.execute("INSERT INTO timeline_span VALUES('j1','seg',1,'MAP',40,60,50,70)"), "contiguous")
    s.expect_rejected("Timeline source overlap rejected", lambda: con.execute("INSERT INTO timeline_span VALUES('j1','seg',1,'MAP',30,60,40,70)"), "non-overlapping")
    con.execute("INSERT INTO timeline_span VALUES('j1','seg',1,'MAP',40,80,40,80)")
    s.expect_rejected("Timeline cannot seal with incomplete destination coverage", lambda: con.execute("UPDATE timeline_mapping SET status='SEALED',sealed_at='2026-08-09T05:07:00.000Z' WHERE job_id='j1' AND segment_id='seg'"), "completely cover")
    con.execute("INSERT INTO timeline_span VALUES('j1','seg',2,'SILENCE',NULL,NULL,80,100)")
    s.expect_ok("contiguous Timeline seals with complete coverage", lambda: con.execute("UPDATE timeline_mapping SET status='SEALED',sealed_at='2026-08-09T05:07:00.000Z' WHERE job_id='j1' AND segment_id='seg'"))
    s.expect_rejected("sealed Timeline span INSERT rejected", lambda: con.execute("INSERT INTO timeline_span VALUES('j1','seg',3,'SILENCE',NULL,NULL,100,101)"), "destination end")
    s.expect_rejected("sealed Timeline metadata immutable", lambda: con.execute("UPDATE timeline_mapping SET dst_end_tick=101 WHERE job_id='j1' AND segment_id='seg'"), "immutable")

    # Manifest structural and semantic checks.
    manifest = json.loads((ROOT / "examples/manifest.v1.json").read_text(encoding="utf-8"))
    s.expect_ok("Manifest example passes schema and semantics", lambda: validate_manifest_document(manifest))
    bad = deepcopy(manifest); bad["source"]["content_hash"] = "sha256:x"
    s.expect_rejected("Manifest malformed source hash rejected", lambda: validate_manifest_document(bad), "schema error")
    bad = deepcopy(manifest); bad["segments"][0]["wav"] = "..\\outside.wav"
    s.expect_rejected("Manifest Windows traversal rejected", lambda: validate_manifest_document(bad), "schema error")
    bad = deepcopy(manifest); bad["segments"][0]["src_start_ms"] = 5000; bad["segments"][0]["src_end_ms"] = 100
    s.expect_rejected("Manifest reversed source interval rejected", lambda: validate_manifest_document(bad), "increasing")
    bad = deepcopy(manifest); bad["segments"][0]["time_map_ticks"][0]["dst"] = [5, 48000]
    s.expect_rejected("Manifest Timeline must start at zero", lambda: validate_manifest_document(bad), "contiguous")
    bad = deepcopy(manifest); bad["segments"].append(deepcopy(bad["segments"][0])); bad["segments"][1]["segment_id"] = "seg_2"; bad["segments"][1]["wav"] = "segments/seg_2.wav"; bad["segments"][1]["artifact_id"] = "a2"; bad["segments"][1]["blob_hash"] = sha('d'); bad["segments"][1]["ordinal"] = 0
    s.expect_rejected("Manifest duplicate ordinal rejected", lambda: validate_manifest_document(bad), "unique")

    # Public API and package graph.
    package_graph = json.loads((ROOT / "contracts/package_graph.v1.json").read_text(encoding="utf-8"))
    s.expect_ok("package graph contains exactly 18 packages and is acyclic", lambda: validate_package_graph(package_graph))
    bad_graph = deepcopy(package_graph); bad_graph["packages"][0]["depends_on"] = [bad_graph["packages"][-1]["name"]]
    s.expect_rejected("package graph rejects upward/cyclic dependency", lambda: validate_package_graph(bad_graph), "lower layer")
    api = json.loads((ROOT / "contracts/public_api.v1.json").read_text(encoding="utf-8"))
    s.expect_ok("Public API type aliases have closed references", lambda: validate_public_api_type_aliases(api))
    bad_api_types = deepcopy(api); bad_api_types["types"].pop("JSONValue", None)
    s.expect_rejected("Public API type aliases reject dangling references", lambda: validate_public_api_type_aliases(bad_api_types), "undefined type JSONValue")
    required_ops = {"open_context","close_context","create_batch","start","stop","get_job","list_jobs","list_pending_decisions","resolve_decision","subscribe_events","get_manifest","reconcile"}
    s.expect_ok("Public API v1 has frozen operation set and runtime semantics", lambda: (_ for _ in ()).throw(AssertionError("API incomplete"))
                if api.get("schema") != "audioprep.public-api.v1" or set(api.get("operations", {})) != required_ops or not api.get("runtime") else True)

    # Documentation/layout consistency.
    en_docs = sorted((ROOT / "docs/en").glob("*.md")); zh_docs = sorted((ROOT / "docs/zh-CN").glob("*.md"))
    s.expect_ok("bilingual module count is 18 + 18", lambda: (_ for _ in ()).throw(AssertionError("wrong doc count")) if (len(en_docs), len(zh_docs)) != (18, 18) else True)
    readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    packages = set(re.findall(r"`(audioprep-[a-z0-9-]+)`", readme_zh))
    s.expect_ok("README package map unique count is 18", lambda: (_ for _ in ()).throw(AssertionError(str(sorted(packages)))) if len(packages) != 18 else True)
    critical = ["SOURCE_MEDIA", "PlanSealValidator", "MediaPortSpec", "ABORTED", "NODE_TIMEOUT", "deliverable_id"]
    s.expect_ok("bilingual critical contract tokens present", lambda: (_ for _ in ()).throw(AssertionError("missing token")) if any(t not in readme_zh + (ROOT / "README.md").read_text(encoding="utf-8") for t in critical) else True)

    # Additional bypass-path regression coverage.
    con = open_schema_db()
    con.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder) VALUES('b','TRUSTED','/in')")
    s.expect_rejected("Job INSERT must begin CREATED", lambda: con.execute(
        "INSERT INTO job(job_id,batch_id,source_path,status,finished_at,error_code,error_type) VALUES('j','b','/x','FAILED','x','INTERNAL_ERROR','SYSTEM')"), "empty CREATED")
    s.expect_rejected("Job INSERT cannot preload SourceIdentity", lambda: con.execute(
        "INSERT INTO job(job_id,batch_id,source_path,source_size_bytes,source_mtime_ns,source_content_hash,source_artifact_id,source_identity_frozen_at) VALUES('j','b','/x',1,1,?,'a','x')", (sha('a'),)), "empty CREATED")

    con = open_schema_db(); add_batch_job(con)
    s.expect_rejected("Job batch identity immutable", lambda: con.execute("UPDATE job SET batch_id='other' WHERE job_id='j1'"), "identity")
    s.expect_rejected("Job source_path identity immutable", lambda: con.execute("UPDATE job SET source_path='/other.wav' WHERE job_id='j1'"), "identity")
    s.expect_rejected("started_at cannot be written outside QUEUED to RUNNING", lambda: con.execute("UPDATE job SET started_at='2026-08-09T05:01:00.000Z' WHERE job_id='j1'"), "only during")

    con = open_schema_db()
    s.expect_rejected("Blob rejects short SHA-256", lambda: con.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('b','sha256:x','/b',1)"), "CHECK constraint failed")
    s.expect_rejected("Blob rejects uppercase SHA-256", lambda: con.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('b',?,'/b',1)", ('sha256:' + 'A'*64,)), "CHECK constraint failed")
    for secret_key in ("hf_token", "review_token", "api_key", "password"):
        s.expect_rejected(f"Batch config snapshot rejects {secret_key}", lambda key=secret_key: con.execute(
            "INSERT INTO batch(batch_id,workflow_mode,input_folder,config_snapshot) VALUES(?,?,?,?)",
            (f"b-{key}", "TRUSTED", "/in", json.dumps({key: "secret"}))), "namespace key/value schema")
    s.expect_rejected("Batch config snapshot rejects nested secret keys", lambda: con.execute(
        "INSERT INTO batch(batch_id,workflow_mode,input_folder,config_snapshot) VALUES('b-nested','TRUSTED','/in',?)",
        (json.dumps({"backend":{"api_key":"secret"}}),)), "persisted secret")

    # Parent Plan and validation receipt identity.
    con = open_schema_db(); add_batch_job(con, 'j1', 'b1')
    con.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder) VALUES('b2','TRUSTED','/b2')")
    con.execute("INSERT INTO job(job_id,batch_id,source_path) VALUES('j2','b2','/j2.wav')")
    add_minimal_plan(con, 'j1', 'p1'); seal_plan(con, 'p1')
    add_minimal_plan(con, 'j2', 'p2'); seal_plan(con, 'p2')
    s.expect_rejected("Plan parent cannot cross Job", lambda: con.execute(
        "INSERT INTO pipeline_plan(plan_id,job_id,revision,parent_plan_id,planner_version) VALUES('p3','j2',2,'p1','v')"), "same Job")
    con.execute("INSERT INTO pipeline_plan(plan_id,job_id,revision,planner_version) VALUES('draft-parent','j1',2,'v')")
    s.expect_rejected("Plan parent must already be sealed", lambda: con.execute(
        "INSERT INTO pipeline_plan(plan_id,job_id,revision,parent_plan_id,planner_version) VALUES('child','j1',3,'draft-parent','v')"), "sealed revision")
    s.expect_ok("same-Job earlier sealed parent accepted", lambda: con.execute(
        "INSERT INTO pipeline_plan(plan_id,job_id,revision,parent_plan_id,planner_version) VALUES('child-ok','j1',3,'p1','v')"))
    s.expect_rejected("DRAFT Plan identity cannot move Job", lambda: con.execute("UPDATE pipeline_plan SET job_id='j2' WHERE plan_id='draft-parent'"), "identity")
    s.expect_rejected("DRAFT Plan cannot jump to SUPERSEDED", lambda: con.execute("UPDATE pipeline_plan SET status='SUPERSEDED',plan_fingerprint=?,sealed_at='2026-08-09T05:07:00.000Z' WHERE plan_id='draft-parent'", (sha('f'),)), "illegal")
    s.expect_rejected("validation receipt cannot be created for SEALED Plan", lambda: record_plan_validation_receipt(con, 'p1', 'PlanSealValidator/test'), "DRAFT")
    s.expect_rejected("sealed validation receipt cannot be updated", lambda: con.execute("UPDATE pipeline_plan_validation SET validator_version='other' WHERE plan_id='p1'"), "immutable")
    s.expect_rejected("sealed validation receipt cannot be deleted", lambda: con.execute("DELETE FROM pipeline_plan_validation WHERE plan_id='p1'"), "immutable")

    # Initial execution/checkpoint and polymorphic owner guards.
    con = open_schema_db(); add_batch_job(con); add_minimal_plan(con); seal_plan(con, 'p1'); activate_job_for_execution(con, 'p1')
    s.expect_rejected("NodeExecution INSERT must begin PENDING", lambda: con.execute(
        """INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,
        implementation_fingerprint,run_token,worker_id,started_at,hard_deadline_at)
        VALUES('e','j1','p1','p1-source',1,1,'RUNNING','fp-p1-source','r','w','2026-08-09T05:01:00.000Z','2026-08-09T05:02:00.000Z')"""), "inserted as PENDING")
    con.execute("""INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,implementation_fingerprint)
        VALUES('e','j1','p1','p1-source',1,1,'PENDING','fp-p1-source')""")
    con.execute("UPDATE node_execution SET status='DISPATCHED' WHERE execution_id='e'")
    con.execute("UPDATE node_execution SET status='RUNNING',run_token='r',worker_id='w',started_at='2026-08-09T05:01:00.000Z',hard_deadline_at='2026-08-09T05:02:00.000Z' WHERE execution_id='e'")
    con.execute("UPDATE node_execution SET status='SUCCEEDED',completed_at='2026-08-09T05:03:00.000Z',run_token=NULL,worker_id=NULL WHERE execution_id='e'")
    s.expect_rejected("Checkpoint INSERT must begin OPEN", lambda: con.execute(
        "INSERT INTO checkpoint(checkpoint_id,job_id,plan_id,plan_node_id,execution_id,status) VALUES('c','j1','p1','p1-source','e','COMMITTED')"), "inserted OPEN")
    con.execute("INSERT INTO checkpoint(checkpoint_id,job_id,plan_id,plan_node_id,execution_id,status) VALUES('c','j1','p1','p1-source','e','OPEN')")
    s.expect_ok("Checkpoint OPEN to COMMITTED accepted", lambda: con.execute("UPDATE checkpoint SET status='COMMITTED' WHERE checkpoint_id='c'"))
    s.expect_ok("Checkpoint COMMITTED to RELEASED accepted", lambda: con.execute("UPDATE checkpoint SET status='RELEASED' WHERE checkpoint_id='c'"))
    s.expect_rejected("released Checkpoint cannot reopen", lambda: con.execute("UPDATE checkpoint SET status='OPEN' WHERE checkpoint_id='c'"), "immutable")
    con.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('ob',?,'/owner',1)", (sha('f'),))
    con.execute("INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,producer_component,retention_class,retention_until) VALUES('oa','ob','audio','CACHE','test','temp','2099-01-01T00:00:00.000Z')")
    for owner_type, owner_id in (("JOB","missing"),("CHECKPOINT","missing"),("DECISION","missing"),("DELIVERABLE","missing")):
        s.expect_rejected(f"ArtifactReference rejects missing {owner_type} owner", lambda ot=owner_type, oid=owner_id: con.execute(
            "INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) VALUES('oa',?,?, 'x')", (ot, oid)), "live owner")

    # Decision candidate ownership, identity and apply preconditions.
    con = open_schema_db(); add_batch_job(con); add_minimal_plan(con); seal_plan(con, 'p1'); activate_job_for_execution(con, 'p1')
    con.execute("""INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,implementation_fingerprint)
        VALUES('e','j1','p1','p1-source',1,1,'PENDING','fp-p1-source')""")
    con.execute("UPDATE node_execution SET status='DISPATCHED' WHERE execution_id='e'")
    con.execute("UPDATE node_execution SET status='RUNNING',run_token='r',worker_id='w',started_at='2026-08-09T05:01:00.000Z',hard_deadline_at='2026-08-09T05:02:00.000Z' WHERE execution_id='e'")
    con.execute("UPDATE node_execution SET status='SUCCEEDED',completed_at='2026-08-09T05:03:00.000Z',run_token=NULL,worker_id=NULL WHERE execution_id='e'")
    con.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('b',?,'/candidate',1)", (sha('1'),))
    con.execute("INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,producer_component,producer_execution_id,retention_class,retention_until) VALUES('a','b','audio','CANDIDATE','node','e','candidate','2099-01-01T00:00:00.000Z')")
    con.execute("""INSERT INTO decision(decision_id,origin_job_id,batch_id,plan_node_id,decision_type,
        join_signature,join_signature_components,policy_signature,policy_signature_components,expires_at)
        VALUES('d','j1','b1','p1-source','SELECT','j','{}','p','{}','2099-01-01T00:00:00.000Z')""")
    s.expect_rejected("Decision candidate requires strong reference", lambda: con.execute(
        "INSERT INTO decision_candidate(candidate_id,decision_id,selector_key,artifact_id) VALUES('c','d','A','a')"), "strong ArtifactReference")
    con.execute("INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) VALUES('a','DECISION','d','candidate')")
    con.execute("INSERT INTO decision_candidate(candidate_id,decision_id,selector_key,artifact_id) VALUES('c','d','A','a')")
    s.expect_rejected("DecisionCandidate metrics_json must be an object", lambda: con.execute(
        "INSERT INTO decision_candidate(candidate_id,decision_id,selector_key,artifact_id,metrics_json) VALUES('c2','d','B','a','[]')"), 'CHECK constraint failed')
    s.expect_rejected("Decision resolution_action stores only selector_key", lambda: con.execute(
        "UPDATE decision SET status='RESOLVED',resolution_action='{\"selector_key\":\"A\",\"extra\":\"unexpected\"}',resolver_type='HUMAN',resolved_at='2026-08-09T05:04:00.000Z' WHERE decision_id='d'"), 'CHECK constraint failed')
    s.expect_rejected("Decision candidate is immutable", lambda: con.execute("UPDATE decision_candidate SET selector_key='B' WHERE candidate_id='c'"), "immutable")
    s.expect_rejected("Decision resolution selector must exist", lambda: con.execute(
        "UPDATE decision SET status='RESOLVED',resolution_action='{\"selector_key\":\"B\"}',resolver_type='HUMAN',resolved_at='2026-08-09T05:04:00.000Z' WHERE decision_id='d'"), "existing candidate")
    con.execute("UPDATE decision SET status='RESOLVED',resolution_action='{\"selector_key\":\"A\"}',resolver_type='HUMAN',resolved_at='2026-08-09T05:04:00.000Z' WHERE decision_id='d'")
    s.expect_rejected("Decision apply requires ownership transfer and Boundary fact", lambda: con.execute(
        "UPDATE decision SET status='APPLIED',applied_at='2026-08-09T05:05:00.000Z' WHERE decision_id='d'"), "transferred ownership")
    s.expect_rejected("Boundary fact cannot cite PENDING Decision", lambda: (
        con.execute("""INSERT INTO decision(decision_id,origin_job_id,batch_id,plan_node_id,decision_type,
        join_signature,join_signature_components,policy_signature,policy_signature_components,expires_at)
        VALUES('d2','j1','b1','p1-source','SELECT','j2','{}','p2','{}','2099-01-01T00:00:00.000Z')"""),
        con.execute("INSERT INTO boundary_fact(fact_id,job_id,fact_key,value_json,source_decision_id) VALUES('f','j1','k','1','d2')")
    ), "RESOLVED/APPLIED")

    # Cross-Job candidate Artifact.
    con.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder) VALUES('b2','TRUSTED','/b2')")
    con.execute("INSERT INTO job(job_id,batch_id,source_path) VALUES('j2','b2','/j2.wav')")
    con.execute("INSERT INTO pipeline_plan(plan_id,job_id,planner_version) VALUES('p2','j2','v')")
    add_node(con,'p2','n2',0,{}, {'out':port(rates=[16000])}); seal_plan(con,'p2'); activate_job_for_execution(con,'p2','j2',run_token='r2',worker_id='w2')
    con.execute("INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,implementation_fingerprint) VALUES('e2','j2','p2','n2',1,1,'PENDING','fp-n2')")
    con.execute("UPDATE node_execution SET status='DISPATCHED' WHERE execution_id='e2'")
    con.execute("UPDATE node_execution SET status='RUNNING',run_token='r2',worker_id='w2',started_at='2026-08-09T05:01:00.000Z',hard_deadline_at='2026-08-09T05:02:00.000Z' WHERE execution_id='e2'")
    con.execute("UPDATE node_execution SET status='SUCCEEDED',completed_at='2026-08-09T05:03:00.000Z',run_token=NULL,worker_id=NULL WHERE execution_id='e2'")
    con.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('b2x',?,'/candidate2',1)", (sha('2'),))
    con.execute("INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,producer_component,producer_execution_id,retention_class,retention_until) VALUES('a2','b2x','audio','CANDIDATE','node','e2','candidate','2099-01-01T00:00:00.000Z')")
    con.execute("""INSERT INTO decision(decision_id,origin_job_id,batch_id,plan_node_id,decision_type,
        join_signature,join_signature_components,policy_signature,policy_signature_components,expires_at)
        VALUES('dx','j1','b1','p1-source','SELECT','jx','{}','px','{}','2099-01-01T00:00:00.000Z')""")
    con.execute("INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) VALUES('a2','DECISION','dx','candidate')")
    s.expect_rejected("Decision candidate cannot use cross-Job Artifact", lambda: con.execute(
        "INSERT INTO decision_candidate(candidate_id,decision_id,selector_key,artifact_id) VALUES('cx','dx','X','a2')"), "origin Job")

    # Timeline insert/seal bypasses and IDENTITY_SLICE semantics.
    con = timeline_db()
    s.expect_rejected("Timeline mapping INSERT cannot start SEALED", lambda: con.execute(
        "INSERT INTO timeline_mapping(job_id,segment_id,artifact_id,mapping_kind,status,src_timebase_den,dst_timebase_den,dst_end_tick,sealed_at) VALUES('j1','bad','a','PIECEWISE','SEALED',1,1,1,'x')"), "inserted DRAFT")
    con.execute("INSERT INTO timeline_span VALUES('j1','seg',0,'MAP',0,30,0,30)")
    con.execute("INSERT INTO timeline_span VALUES('j1','seg',1,'MAP',30,60,30,60)")
    con.execute("INSERT INTO timeline_span VALUES('j1','seg',2,'MAP',60,100,60,100)")
    con.execute("DELETE FROM timeline_span WHERE job_id='j1' AND segment_id='seg' AND span_index=1")
    s.expect_rejected("Timeline cannot seal after deleting a middle span", lambda: con.execute(
        "UPDATE timeline_mapping SET status='SEALED',sealed_at='2026-08-09T05:07:00.000Z' WHERE job_id='j1' AND segment_id='seg'"), "contiguous")

    con = timeline_db()
    con.execute("UPDATE timeline_mapping SET mapping_kind='IDENTITY_SLICE',src_timebase_den=48000,dst_timebase_den=16000 WHERE job_id='j1' AND segment_id='seg'")
    con.execute("INSERT INTO timeline_span VALUES('j1','seg',0,'MAP',0,100,0,100)")
    s.expect_rejected("IDENTITY_SLICE rejects unequal timebases", lambda: con.execute(
        "UPDATE timeline_mapping SET status='SEALED',sealed_at='2026-08-09T05:07:00.000Z' WHERE job_id='j1' AND segment_id='seg'"), "equal timebases")
    con = timeline_db()
    con.execute("UPDATE timeline_mapping SET mapping_kind='IDENTITY_SLICE',src_timebase_den=16000,dst_timebase_den=16000 WHERE job_id='j1' AND segment_id='seg'")
    con.execute("INSERT INTO timeline_span VALUES('j1','seg',0,'MAP',100,300,0,100)")
    s.expect_rejected("IDENTITY_SLICE rejects unequal tick duration", lambda: con.execute(
        "UPDATE timeline_mapping SET status='SEALED',sealed_at='2026-08-09T05:07:00.000Z' WHERE job_id='j1' AND segment_id='seg'"), "equal tick duration")
    con = timeline_db()
    con.execute("UPDATE timeline_mapping SET mapping_kind='IDENTITY_SLICE',src_timebase_den=16000,dst_timebase_den=16000 WHERE job_id='j1' AND segment_id='seg'")
    con.execute("INSERT INTO timeline_span VALUES('j1','seg',0,'MAP',100,200,0,100)")
    s.expect_ok("valid IDENTITY_SLICE seals", lambda: con.execute(
        "UPDATE timeline_mapping SET status='SEALED',sealed_at='2026-08-09T05:07:00.000Z' WHERE job_id='j1' AND segment_id='seg'"))

    # Deliverable and event immutability.
    con = timeline_db()
    s.expect_rejected("Deliverable INSERT must start STAGING", lambda: con.execute(
        "INSERT INTO deliverable(deliverable_id,job_id,status,staging_path,published_path,manifest_hash,published_at) VALUES('d','j1','PUBLISHED','/s','/p',?,'x')", (sha('3'),)), "inserted STAGING")
    s.expect_rejected("Deliverable rejects REFLINK mode", lambda: con.execute(
        "INSERT INTO deliverable(deliverable_id,job_id,materialization_mode,staging_path) VALUES('d','j1','REFLINK','/s')"), 'CHECK constraint failed')
    con.execute("INSERT INTO deliverable(deliverable_id,job_id,staging_path) VALUES('d','j1','/s')")
    s.expect_rejected("Deliverable cannot publish without segments", lambda: con.execute(
        "UPDATE deliverable SET status='PUBLISHED',published_path='/p',manifest_hash=?,published_at='2026-08-09T05:09:00.000Z' WHERE deliverable_id='d'", (sha('3'),)), "without segments")
    s.expect_rejected("Deliverable segment rejects traversal path", lambda: con.execute(
        "INSERT INTO deliverable_segment(deliverable_id,segment_id,artifact_id,relative_path,ordinal) VALUES('d','s','a','../a.wav',0)"), "segment_id")
    s.expect_rejected("Deliverable segment rejects empty unsafe filename", lambda: con.execute(
        "INSERT INTO deliverable_segment(deliverable_id,segment_id,artifact_id,relative_path,ordinal) VALUES('d','empty','a','segments/.wav',1)"), "segment_id")
    s.expect_rejected("Deliverable segment rejects a single Windows separator", lambda: con.execute(
        "INSERT INTO deliverable_segment(deliverable_id,segment_id,artifact_id,relative_path,ordinal) VALUES('d','win','a','segments/a\\b.wav',1)"), "segment_id")
    s.expect_rejected("Deliverable segment_id matches Manifest safe-name grammar", lambda: con.execute(
        "INSERT INTO deliverable_segment(deliverable_id,segment_id,artifact_id,relative_path,ordinal) VALUES('d','bad/id','a','segments/bad.wav',1)"), "segment_id")
    s.expect_ok("Deliverable segment accepts safe repeated-dot filename matching Manifest", lambda: con.execute(
        "INSERT INTO deliverable_segment(deliverable_id,segment_id,artifact_id,relative_path,ordinal) VALUES('d','a..b','a','segments/a..b.wav',1)"))
    con.execute("DELETE FROM deliverable_segment WHERE deliverable_id='d' AND segment_id='a..b'")
    con.execute("INSERT INTO deliverable_segment(deliverable_id,segment_id,artifact_id,relative_path,ordinal) VALUES('d','s','a','segments/s.wav',0)")
    s.expect_rejected("Deliverable segment Artifact occurrences are unique", lambda: con.execute(
        "INSERT INTO deliverable_segment(deliverable_id,segment_id,artifact_id,relative_path,ordinal) VALUES('d','s2','a','segments/s2.wav',1)"), "UNIQUE")
    s.expect_rejected("Deliverable publish requires strong segment reference", lambda: con.execute(
        "UPDATE deliverable SET status='PUBLISHED',published_path='/p',manifest_hash=?,published_at='2026-08-09T05:09:00.000Z' WHERE deliverable_id='d'", (sha('3'),)), "strong ArtifactReference")
    con.execute("INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) VALUES('a','DELIVERABLE','d','segment')")
    con.execute("UPDATE deliverable SET status='PUBLISHED',published_path='/p',manifest_hash=?,published_at='2026-08-09T05:09:00.000Z' WHERE deliverable_id='d'", (sha('3'),))
    s.expect_rejected("published Deliverable manifest immutable", lambda: con.execute(
        "UPDATE deliverable SET manifest_hash=? WHERE deliverable_id='d'", (sha('4'),)), "immutable")
    s.expect_rejected("published Deliverable segment immutable", lambda: con.execute(
        "UPDATE deliverable_segment SET relative_path='segments/b.wav' WHERE deliverable_id='d' AND segment_id='s'"), "immutable")
    con2 = open_schema_db(); add_batch_job(con2)
    con2.execute("INSERT INTO deliverable(deliverable_id,job_id,staging_path) VALUES('faild','j1','/stage-fail')")
    s.expect_rejected("FAILED Deliverable cannot carry publication metadata", lambda: con2.execute("UPDATE deliverable SET status='FAILED',published_path='/published',manifest_hash=?,published_at='2026-08-09T05:09:00.000Z',closed_at='2026-08-09T05:10:00.000Z' WHERE deliverable_id='faild'", (sha('7'),)), 'CHECK constraint failed')
    s.expect_ok("FAILED Deliverable closes without publication metadata", lambda: con2.execute("UPDATE deliverable SET status='FAILED',closed_at='2026-08-09T05:10:00.000Z' WHERE deliverable_id='faild'"))
    s.expect_rejected("Event payload must be a JSON object", lambda: con.execute("INSERT INTO event(job_id,event_type,payload_json) VALUES('j1','BAD','[]')"), "CHECK constraint failed")
    con.execute("INSERT INTO event(job_id,event_type,payload_json) VALUES('j1','TEST','{}')")
    s.expect_rejected("Event rows are append-only on UPDATE", lambda: con.execute("UPDATE event SET event_type='OTHER'"), "append-only")
    s.expect_rejected("Event rows are append-only on DELETE", lambda: con.execute("DELETE FROM event"), "append-only")

    # Additional identity and update-bypass coverage introduced in R2.1.5 hardening.
    con = open_schema_db(); add_batch_job(con)
    s.expect_rejected("Batch resolved config snapshot is immutable", lambda: con.execute(
        "UPDATE batch SET config_snapshot='{\"changed\":true}' WHERE batch_id='b1'"), "immutable")

    con = open_schema_db(); add_batch_job(con)
    con.execute("INSERT INTO pipeline_plan(plan_id,job_id,planner_version) VALUES('p','j1','v')")
    add_node(con,'p','s',0,{}, {'out':port(rates=[16000])})
    add_node(con,'p','d',1,{'in':port(rates=[16000])}, {})
    con.execute("INSERT INTO pipeline_plan_edge VALUES('p','s','d','out','in')")
    s.expect_rejected("Plan edge rows cannot move across validated identities by UPDATE", lambda: con.execute(
        "UPDATE pipeline_plan_edge SET output_name='other' WHERE plan_id='p'"), "immutable rows")

    con = open_schema_db(); add_batch_job(con); add_minimal_plan(con); seal_plan(con,'p1'); activate_job_for_execution(con,'p1')
    con.execute("INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,implementation_fingerprint) VALUES('e','j1','p1','p1-source',1,1,'PENDING','fp-p1-source')")
    s.expect_rejected("NodeExecution start fields cannot be preloaded by UPDATE", lambda: con.execute(
        "UPDATE node_execution SET started_at='2026-08-09T05:01:00.000Z' WHERE execution_id='e'"), "start or terminal close")
    s.expect_rejected("PENDING NodeExecution error_detail cannot be preloaded by UPDATE", lambda: con.execute(
        "UPDATE node_execution SET error_detail='premature' WHERE execution_id='e'"), "terminal close")
    con.execute("UPDATE node_execution SET status='DISPATCHED' WHERE execution_id='e'")
    con.execute("UPDATE node_execution SET status='RUNNING',run_token='r',worker_id='w',started_at='2026-08-09T05:01:00.000Z',hard_deadline_at='2026-08-09T05:02:00.000Z' WHERE execution_id='e'")
    s.expect_rejected("terminal NodeExecution must clear runtime fence ownership", lambda: con.execute(
        "UPDATE node_execution SET status='SUCCEEDED',completed_at='2026-08-09T05:03:00.000Z' WHERE execution_id='e'"), "clear run_token")
    con.execute("UPDATE node_execution SET status='SUCCEEDED',completed_at='2026-08-09T05:03:00.000Z',run_token=NULL,worker_id=NULL WHERE execution_id='e'")
    con.execute("INSERT INTO checkpoint(checkpoint_id,job_id,plan_id,plan_node_id,execution_id,status) VALUES('c','j1','p1','p1-source','e','OPEN')")
    s.expect_rejected("Checkpoint identity cannot be rebound", lambda: con.execute(
        "UPDATE checkpoint SET execution_id='other' WHERE checkpoint_id='c'"), "identity is immutable")
    con.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('cb',?,'/checkpoint',1)",(sha('8'),))
    con.execute("INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,producer_component,producer_execution_id,retention_class,retention_until) VALUES('ca','cb','audio','CHECKPOINT','node','e','temp','2099-01-01T00:00:00.000Z')")
    con.execute("INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) VALUES('ca','CHECKPOINT','c','state')")
    s.expect_rejected("Checkpoint cannot RELEASE while owning ArtifactReferences", lambda: con.execute("UPDATE checkpoint SET status='RELEASED' WHERE checkpoint_id='c'"), "release checkpoint refs")
    con.execute("DELETE FROM artifact_reference WHERE artifact_id='ca' AND owner_type='CHECKPOINT' AND owner_id='c'")
    s.expect_ok("Checkpoint RELEASE succeeds after refs are released", lambda: con.execute("UPDATE checkpoint SET status='RELEASED' WHERE checkpoint_id='c'"))

    con = open_schema_db(); add_batch_job(con); freeze_source(con)
    s.expect_rejected("ArtifactReference cannot be rebound by UPDATE", lambda: con.execute(
        "UPDATE artifact_reference SET ref_kind='other' WHERE owner_type='JOB' AND owner_id='j1'"), "immutable")

    con = open_schema_db(); add_batch_job(con); add_minimal_plan(con); seal_plan(con,'p1'); activate_job_for_execution(con,'p1')
    con.execute("INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,implementation_fingerprint) VALUES('e','j1','p1','p1-source',1,1,'PENDING','fp-p1-source')")
    con.execute("UPDATE node_execution SET status='DISPATCHED' WHERE execution_id='e'")
    con.execute("UPDATE node_execution SET status='RUNNING',run_token='r',worker_id='w',started_at='2026-08-09T05:01:00.000Z',hard_deadline_at='2026-08-09T05:02:00.000Z' WHERE execution_id='e'")
    con.execute("UPDATE node_execution SET status='SUCCEEDED',completed_at='2026-08-09T05:03:00.000Z',run_token=NULL,worker_id=NULL WHERE execution_id='e'")
    con.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('b',?,'/candidate',1)",(sha('9'),))
    con.execute("INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,producer_component,producer_execution_id,retention_class,retention_until) VALUES('a','b','audio','CANDIDATE','node','e','candidate','2099-01-01T00:00:00.000Z')")
    con.execute("""INSERT INTO decision(decision_id,origin_job_id,batch_id,plan_node_id,decision_type,join_signature,join_signature_components,policy_signature,policy_signature_components,expires_at)
        VALUES('d','j1','b1','p1-source','SELECT','j','{}','p','{}','2099-01-01T00:00:00.000Z')""")
    con.execute("INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) VALUES('a','DECISION','d','candidate')")
    con.execute("INSERT INTO decision_candidate(candidate_id,decision_id,selector_key,artifact_id) VALUES('c','d','A','a')")
    con.execute("INSERT INTO decision_job(decision_id,job_id,execution_id) VALUES('d','j1','e')")
    s.expect_rejected("Decision policy identity cannot be edited", lambda: con.execute(
        "UPDATE decision SET expires_at='2100-01-01T00:00:00.000Z' WHERE decision_id='d'"), "identity are immutable")
    s.expect_rejected("Decision candidate audit rows cannot be deleted", lambda: con.execute(
        "DELETE FROM decision_candidate WHERE candidate_id='c'"), "append-only")
    s.expect_rejected("decision_job audit links cannot be deleted", lambda: con.execute(
        "DELETE FROM decision_job WHERE decision_id='d' AND job_id='j1'"), "append-only")

    con = timeline_db()
    s.expect_rejected("Timeline mapping Artifact identity cannot be rebound", lambda: con.execute(
        "UPDATE timeline_mapping SET artifact_id='other' WHERE job_id='j1' AND segment_id='seg'"), "identity is immutable")
    con.execute("INSERT INTO deliverable(deliverable_id,job_id,staging_path) VALUES('d','j1','/stage')")
    con.execute("INSERT INTO deliverable_segment(deliverable_id,segment_id,artifact_id,relative_path,ordinal) VALUES('d','s','a','segments/s.wav',0)")
    s.expect_rejected("STAGING Deliverable Job identity cannot move", lambda: con.execute(
        "UPDATE deliverable SET staging_path='/other' WHERE deliverable_id='d'"), "identity are immutable")
    s.expect_rejected("STAGING Deliverable segment rows cannot be rebound", lambda: con.execute(
        "UPDATE deliverable_segment SET relative_path='segments/other.wav' WHERE deliverable_id='d'"), "immutable")

    con = open_schema_db(); add_batch_job(con)
    s.expect_rejected("Job primary identifier is immutable", lambda: con.execute("UPDATE job SET job_id='j2' WHERE job_id='j1'"), "immutable")

    con = open_schema_db(); add_batch_job(con); add_minimal_plan(con); seal_plan(con,'p1'); activate_job_for_execution(con,'p1')
    s.expect_rejected("sealed Plan created_at is immutable", lambda: con.execute("UPDATE pipeline_plan SET created_at='tampered' WHERE plan_id='p1'"), "immutable")
    con.execute("INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,implementation_fingerprint) VALUES('e','j1','p1','p1-source',1,1,'PENDING','fp-p1-source')")
    s.expect_rejected("NodeExecution PENDING error detail UPDATE is rejected", lambda: con.execute("UPDATE node_execution SET error_detail='premature' WHERE execution_id='e'"), "terminal close")
    con.execute("UPDATE node_execution SET status='DISPATCHED' WHERE execution_id='e'")
    con.execute("UPDATE node_execution SET status='RUNNING',run_token='r',worker_id='w',started_at='2026-08-09T05:01:00.000Z',hard_deadline_at='2026-08-09T05:02:00.000Z' WHERE execution_id='e'")
    con.execute("UPDATE node_execution SET status='SUCCEEDED',completed_at='2026-08-09T05:03:00.000Z',run_token=NULL,worker_id=NULL WHERE execution_id='e'")
    con.execute("INSERT INTO checkpoint(checkpoint_id,job_id,plan_id,plan_node_id,execution_id,status) VALUES('cpid','j1','p1','p1-source','e','OPEN')")
    s.expect_rejected("Checkpoint primary identifier is immutable", lambda: con.execute("UPDATE checkpoint SET checkpoint_id='cpid2' WHERE checkpoint_id='cpid'"), "immutable")
    s.expect_rejected("terminal NodeExecution created_at is immutable", lambda: con.execute("UPDATE node_execution SET created_at='tampered' WHERE execution_id='e'"), "terminal node execution")

    con = open_schema_db(); add_batch_job(con)
    con.execute("UPDATE job SET status='FAILED',finished_at='2026-08-09T05:08:00.000Z',error_code='INTERNAL_ERROR',error_type='SYSTEM' WHERE job_id='j1'")
    s.expect_rejected("terminal Job created_at is immutable", lambda: con.execute("UPDATE job SET created_at='tampered' WHERE job_id='j1'"), "terminal Job")
    s.expect_rejected("terminal Job cannot be deleted", lambda: con.execute("DELETE FROM job WHERE job_id='j1'"), "immutable")

    con = open_schema_db(); add_batch_job(con); add_minimal_plan(con); seal_plan(con,'p1')
    con.execute("INSERT INTO decision(decision_id,origin_job_id,batch_id,plan_node_id,decision_type,join_signature,join_signature_components,policy_signature,policy_signature_components,expires_at) VALUES('dterm','j1','b1','p1-source','SELECT','j','{}','p','{}','2099-01-01T00:00:00.000Z')")
    con.execute("UPDATE decision SET status='CANCELLED' WHERE decision_id='dterm'")
    s.expect_rejected("terminal Decision cannot be deleted", lambda: con.execute("DELETE FROM decision WHERE decision_id='dterm'"), "immutable")

    con = open_schema_db(); add_batch_job(con); add_minimal_plan(con); seal_plan(con,'p1'); activate_job_for_execution(con,'p1')
    con.execute("INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,implementation_fingerprint) VALUES('e','j1','p1','p1-source',1,1,'PENDING','fp-p1-source')")
    con.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder) VALUES('b2','TRUSTED','/b2')")
    con.execute("INSERT INTO job(job_id,batch_id,source_path) VALUES('j2','b2','/j2.wav')")
    s.expect_rejected("Resource lease execution cannot cross Job", lambda: con.execute(
        "INSERT INTO resource_lease(lease_id,resource_kind,resource_key,job_id,execution_id,token,expires_at) VALUES('l','CPU','cpu0','j2','e','t','2099-01-01T00:00:00.000Z')"), "same Job")
    con.execute("INSERT INTO resource_lease(lease_id,resource_kind,resource_key,job_id,execution_id,token,expires_at) VALUES('l','CPU','cpu0','j1','e','t','2099-01-01T00:00:00.000Z')")
    s.expect_rejected("Resource lease token and identity are immutable", lambda: con.execute(
        "UPDATE resource_lease SET token='other' WHERE lease_id='l'"), "immutable")

    # R2.1.5.07 comprehensive hardening regressions.
    con = open_schema_db(); add_batch_job(con); add_minimal_plan(con); seal_plan(con,'p1'); freeze_source(con)
    con.execute("UPDATE job SET current_plan_id='p1',status='QUEUED' WHERE job_id='j1'")
    con.execute("UPDATE job SET status='RUNNING',dispatch_generation=1,active_run_token='rt1',lease_expires_at='2099-01-01T00:00:00.000Z',worker_id='w1',started_at='2026-08-09T05:01:00.000Z' WHERE job_id='j1'")
    s.expect_rejected("RUNNING Job generation is fenced", lambda: con.execute("UPDATE job SET dispatch_generation=99 WHERE job_id='j1'"), "execution fence")
    s.expect_rejected("RUNNING Job run token is fenced", lambda: con.execute("UPDATE job SET active_run_token='evil' WHERE job_id='j1'"), "execution fence")
    s.expect_rejected("RUNNING Job worker is fenced", lambda: con.execute("UPDATE job SET worker_id='evil' WHERE job_id='j1'"), "execution fence")
    s.expect_rejected("RUNNING Job lease deadline is fenced", lambda: con.execute("UPDATE job SET lease_expires_at='evil' WHERE job_id='j1'"), "execution fence")
    con.execute("UPDATE job SET status='WAITING_DECISION',active_run_token=NULL,lease_expires_at=NULL,worker_id=NULL WHERE job_id='j1'")
    s.expect_rejected("Job resume generation cannot skip", lambda: con.execute("UPDATE job SET status='RUNNING',dispatch_generation=3,active_run_token='rt3',lease_expires_at='2099-01-03T00:00:00.000Z',worker_id='w3' WHERE job_id='j1'"), "execution fence")
    s.expect_ok("Job resume advances exactly one generation", lambda: con.execute("UPDATE job SET status='RUNNING',dispatch_generation=2,active_run_token='rt2',lease_expires_at='2099-01-02T00:00:00.000Z',worker_id='w2' WHERE job_id='j1'"))

    con = open_schema_db(); add_batch_job(con)
    con.execute("INSERT INTO pipeline_plan(plan_id,job_id,revision,planner_version) VALUES('pold','j1',1,'v')")
    add_node(con,'pold','nold',0,{},{}); seal_plan(con,'pold')
    con.execute("INSERT INTO pipeline_plan(plan_id,job_id,revision,parent_plan_id,planner_version) VALUES('pcur','j1',2,'pold','v')")
    add_node(con,'pcur','ncur',0,{},{}); seal_plan(con,'pcur'); freeze_source(con)
    con.execute("UPDATE job SET current_plan_id='pcur',status='QUEUED' WHERE job_id='j1'")
    con.execute("UPDATE job SET status='RUNNING',dispatch_generation=1,active_run_token='r',lease_expires_at='2099-01-01T00:00:00.000Z',worker_id='w',started_at='2026-08-09T05:01:00.000Z' WHERE job_id='j1'")
    s.expect_rejected("NodeExecution rejects non-current Plan", lambda: con.execute("INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,implementation_fingerprint) VALUES('estale','j1','pold','nold',1,1,'PENDING','fp-nold')"), "stale plan")
    s.expect_rejected("NodeExecution rejects stale/foreign generation", lambda: con.execute("INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,implementation_fingerprint) VALUES('egen','j1','pcur','ncur',1,1234,'PENDING','fp-ncur')"), "generation")
    con.execute("INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,implementation_fingerprint) VALUES('ecur','j1','pcur','ncur',1,1,'PENDING','fp-ncur')")
    s.expect_rejected("Job cannot SUCCEED with active NodeExecution", lambda: con.execute("UPDATE job SET status='SUCCEEDED',active_run_token=NULL,lease_expires_at=NULL,worker_id=NULL,finished_at='2026-08-09T05:08:00.000Z' WHERE job_id='j1'"), "active NodeExecution")
    con.execute("UPDATE job SET status='FAILED',active_run_token=NULL,lease_expires_at=NULL,worker_id=NULL,finished_at='2026-08-09T05:08:00.000Z',error_code='NODE_CRASH',error_type='SYSTEM' WHERE job_id='j1'")
    s.expect_ok("FAILED Job aborts active child execution", lambda: (_ for _ in ()).throw(AssertionError('child not aborted')) if con.execute("SELECT status FROM node_execution WHERE execution_id='ecur'").fetchone()[0] != 'ABORTED' else True)

    con = open_schema_db()
    s.expect_ok("known config namespaces accepted", lambda: con.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder,config_snapshot) VALUES('cfgok','TRUSTED','/in','{\"audio\":{\"sample_rate_hz\":48000},\"cache\":{\"enabled\":true}}')"))
    s.expect_rejected("unknown config namespace fails closed", lambda: con.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder,config_snapshot) VALUES('cfgunknown','TRUSTED','/in','{\"mystery\":1}')"), "namespace key/value schema")
    s.expect_rejected("unknown nested config key fails closed", lambda: con.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder,config_snapshot) VALUES('cfgnested','TRUSTED','/in','{\"audio\":{\"mystery\":1}}')"), "namespace key/value schema")
    for secret_key in ("token","auth_token","access_token","client_secret","secret","authorization","credential"):
        s.expect_rejected(f"Batch config recursively rejects {secret_key}", lambda key=secret_key: con.execute(
            "INSERT INTO batch(batch_id,workflow_mode,input_folder,config_snapshot) VALUES(?,?,?,?)",
            ("cfg-"+key,"TRUSTED","/in",canonical_json({"review":{key:"VERY_SECRET"}}))), "persisted secret")
    s.expect_rejected("experimental config requires explicit enable", lambda: con.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder,config_snapshot) VALUES('cfgexpbad','TRUSTED','/in','{\"experimental\":{\"foo\":true}}')"), "experimental namespace")
    s.expect_ok("explicitly enabled experimental config accepted", lambda: con.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder,config_snapshot) VALUES('cfgexpok','TRUSTED','/in','{\"experimental\":{\"enabled\":true,\"foo\":true}}')"))
    s.expect_rejected("calendar-invalid RFC3339 date fails closed", lambda: con.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder,created_at) VALUES('cfgdate','TRUSTED','/in','2026-02-29T00:00:00.000Z')"), "CHECK constraint")
    con = open_schema_db()
    s.expect_rejected("RFC3339 24-hour special case fails closed", lambda: con.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder,created_at) VALUES('cfg24','TRUSTED','/in','2026-01-01T24:00:00.000Z')"), "CHECK constraint")
    s.expect_ok("RFC3339 maximum canonical hour 23 accepted", lambda: con.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder,created_at) VALUES('cfg23','TRUSTED','/in','2026-01-01T23:59:59.999Z')"))
    s.expect_ok("all 33 persisted timestamp checks enforce hour 00-23", lambda: (_ for _ in ()).throw(AssertionError("timestamp hour guard coverage mismatch")) if len(re.findall(r"substr\((\w+),12,2\) BETWEEN '00' AND '23' AND julianday\(\1\)", (ROOT / "sql/schema.sql").read_text(encoding="utf-8"))) != 33 else True)

    con = open_schema_db(); add_batch_job(con); add_minimal_plan(con,plan_id='pgc'); seal_plan(con,'pgc'); activate_job_for_execution(con,'pgc')
    con.execute("INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,implementation_fingerprint) VALUES('egc','j1','pgc','pgc-source',1,1,'PENDING','fp-pgc-source')")
    con.execute("UPDATE node_execution SET status='DISPATCHED' WHERE execution_id='egc'")
    con.execute("UPDATE node_execution SET status='RUNNING',run_token='r',worker_id='w',started_at='2026-08-09T05:01:00.000Z',hard_deadline_at='2026-08-09T05:02:00.000Z' WHERE execution_id='egc'")
    con.execute("UPDATE node_execution SET status='SUCCEEDED',completed_at='2026-08-09T05:03:00.000Z',run_token=NULL,worker_id=NULL WHERE execution_id='egc'")
    con.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('bgc',?,'/cas/gc',1)",(sha('7'),))
    con.execute("INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,producer_component,producer_execution_id,retention_class,retention_until) VALUES('agc','bgc','audio','CANDIDATE','node','egc','temp','2000-01-01T00:00:00.000Z')")
    con.execute("INSERT INTO decision(decision_id,origin_job_id,batch_id,plan_node_id,decision_type,join_signature,join_signature_components,policy_signature,policy_signature_components,expires_at) VALUES('dgc','j1','b1','pgc-source','SELECT','j','{}','p','{}','2099-01-01T00:00:00.000Z')")
    con.execute("INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) VALUES('agc','DECISION','dgc','candidate')")
    con.execute("INSERT INTO decision_candidate(candidate_id,decision_id,selector_key,artifact_id) VALUES('cgc','dgc','A','agc')")
    con.execute("UPDATE decision SET status='CANCELLED' WHERE decision_id='dgc'")
    s.expect_ok("Decision audit identity does not block Artifact GC", lambda: con.execute("DELETE FROM artifact WHERE artifact_id='agc'"))
    s.expect_ok("DecisionCandidate audit identity survives Artifact GC", lambda: (_ for _ in ()).throw(AssertionError('audit identity lost')) if con.execute("SELECT artifact_id FROM decision_candidate WHERE candidate_id='cgc'").fetchone()[0] != 'agc' else True)
    s.expect_ok("Blob can be removed after Artifact GC", lambda: con.execute("DELETE FROM blob WHERE blob_id='bgc'"))
    con = open_schema_db(); add_batch_job(con)
    con.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('bcache',?,'/cas/cache',1)",(sha('8'),))
    con.execute("INSERT INTO execution_cache_output(job_id,execution_key,output_name,blob_id,artifact_type,artifact_role,retention_class) VALUES('j1','k','out','bcache','audio','CACHE','temp')")
    con.execute("DELETE FROM blob WHERE blob_id='bcache'")
    s.expect_ok("weak cache row cascades with purged Blob", lambda: (_ for _ in ()).throw(AssertionError('cache row remains')) if con.execute("SELECT COUNT(*) FROM execution_cache_output").fetchone()[0] else True)

    s.expect_ok("Public API declares RFC3339 and AsyncIterator", lambda: (_ for _ in ()).throw(AssertionError('missing type declarations')) if not {"RFC3339","AsyncIterator"}.issubset(api.get("types",{})) else True)
    bad_api_ref = deepcopy(api); bad_api_ref["operations"]["get_job"]["returns"] = "TotallyMissingType"
    s.expect_rejected("Public API rejects dangling operation return type", lambda: validate_public_api_type_aliases(bad_api_ref), "undefined type")
    bad_api_ref = deepcopy(api); bad_api_ref["value_objects"]["JobSnapshot"]["required"]["job_id"] = "TotallyMissingType"
    s.expect_rejected("Public API rejects dangling value-object type", lambda: validate_public_api_type_aliases(bad_api_ref), "undefined type")

    con = open_schema_db(); add_batch_job(con)
    con.execute("INSERT INTO pipeline_plan(plan_id,job_id,planner_version) VALUES('pdraft','j1','v')")
    add_node(con,'pdraft','d1',0,{}, {'out': port(rates=[16000])}); add_node(con,'pdraft','d2',1,{'in':port(rates=[16000])},{})
    con.execute("INSERT INTO pipeline_plan_edge VALUES('pdraft','d1','d2','out','in')")
    validate_plan_graph(con,'pdraft'); fpd=record_plan_validation_receipt(con,'pdraft','PlanSealValidator/test')
    s.expect_ok("validated DRAFT Plan can be deleted as a whole", lambda: con.execute("DELETE FROM pipeline_plan WHERE plan_id='pdraft'"))
    s.expect_ok("DRAFT Plan parent delete cascades child graph", lambda: (_ for _ in ()).throw(AssertionError('children remain')) if con.execute("SELECT COUNT(*) FROM pipeline_plan_node WHERE plan_id='pdraft'").fetchone()[0] else True)

    con = open_schema_db(); con.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder) VALUES('bid','TRUSTED','/in')")
    s.expect_rejected("Batch primary key immutable without children", lambda: con.execute("UPDATE batch SET batch_id='bid2' WHERE batch_id='bid'"), "immutable")
    con = open_schema_db(); add_batch_job(con); con.execute("INSERT INTO pipeline_plan(plan_id,job_id,planner_version) VALUES('pid','j1','v')")
    s.expect_rejected("DRAFT Plan primary key immutable", lambda: con.execute("UPDATE pipeline_plan SET plan_id='pid2' WHERE plan_id='pid'"), "immutable")
    con = open_schema_db(); add_batch_job(con); add_minimal_plan(con); seal_plan(con,'p1'); activate_job_for_execution(con,'p1')
    con.execute("INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,implementation_fingerprint) VALUES('eid','j1','p1','p1-source',1,1,'PENDING','fp-p1-source')")
    s.expect_rejected("NodeExecution primary key immutable while PENDING", lambda: con.execute("UPDATE node_execution SET execution_id='eid2' WHERE execution_id='eid'"), "immutable")
    con.execute("INSERT INTO resource_lease(lease_id,resource_kind,resource_key,job_id,execution_id,token,expires_at) VALUES('lid','CPU','cpu','j1','eid','tok','2099-01-01T00:00:00.000Z')")
    s.expect_rejected("ResourceLease primary key immutable", lambda: con.execute("UPDATE resource_lease SET lease_id='lid2' WHERE lease_id='lid'"), "immutable")
    con = open_schema_db(); con.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('blid',?,'/cas/id',1)",(sha('a'),))
    s.expect_rejected("Blob primary key immutable without Artifact", lambda: con.execute("UPDATE blob SET blob_id='blid2' WHERE blob_id='blid'"), "immutable")
    con.execute("INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,producer_component,retention_class,retention_until) VALUES('aid','blid','audio','CACHE','test','temp','2000-01-01T00:00:00.000Z')")
    s.expect_rejected("Artifact primary key immutable without strong refs", lambda: con.execute("UPDATE artifact SET artifact_id='aid2' WHERE artifact_id='aid'"), "immutable")

    # Additional manifest/package/API semantic checks.
    bad = deepcopy(manifest); bad["segments"].append(deepcopy(manifest["segments"][0])); bad["segments"][1]["ordinal"] = 1
    s.expect_rejected("Manifest duplicate segment_id rejected", lambda: validate_manifest_document(bad), "unique")
    bad = deepcopy(manifest); bad["segments"][0]["segment_id"] = "different_stem"
    s.expect_rejected("Manifest segment_id must equal wav filename stem", lambda: validate_manifest_document(bad), "wav filename stem")
    bad = deepcopy(manifest); second = deepcopy(manifest["segments"][0]); second.update({"segment_id":"seg_2","ordinal":1,"wav":"segments/seg_2.wav","artifact_id":"a2","blob_hash":sha('5'),"src_start_ms":3000,"src_end_ms":6000,"time_map_ticks":[{"op":"MAP","src":[48000,96000],"dst":[0,48000]}]}); bad["segments"].append(second)
    s.expect_rejected("Manifest source intervals cannot overlap", lambda: validate_manifest_document(bad), "non-overlapping")
    adjacent = deepcopy(manifest)
    first = adjacent["segments"][0]
    first.update({"src_start_ms":0,"src_end_ms":1,"dst_end_tick":1,"timebase":{"src":{"num":1,"den":44100},"dst":{"num":1,"den":44100}},"time_map_ticks":[{"op":"MAP","src":[0,1],"dst":[0,1]}]})
    first["format"]["sample_rate_hz"] = 44100
    second = deepcopy(first)
    second.update({"segment_id":"seg_tick_adjacent","ordinal":1,"wav":"segments/seg_tick_adjacent.wav","artifact_id":"art_tick_adjacent","blob_hash":sha('6'),"src_start_ms":0,"src_end_ms":1,"time_map_ticks":[{"op":"MAP","src":[1,2],"dst":[0,1]}]})
    adjacent["segments"].append(second)
    s.expect_ok("Manifest accepts exactly adjacent authoritative ticks despite rounded millisecond overlap", lambda: validate_manifest_document(adjacent))
    bad = deepcopy(manifest); bad["segments"][0]["quality_flags"] = ["lowercase"]
    s.expect_rejected("Manifest quality flags use stable uppercase vocabulary", lambda: validate_manifest_document(bad), "schema error")
    bad = deepcopy(manifest); bad["segments"][0]["src_start_ms"] = 999999; bad["segments"][0]["src_end_ms"] = 1000000
    s.expect_rejected("Manifest display milliseconds must match authoritative tick mapping", lambda: validate_manifest_document(bad), "derived from authoritative time_map_ticks")
    bad_graph = deepcopy(package_graph); bad_graph["package_count"] = 17
    s.expect_rejected("package graph rejects count mismatch", lambda: validate_package_graph(bad_graph), "exactly 18")
    s.expect_ok("every Public API operation declares params, returns and errors", lambda: (_ for _ in ()).throw(
        AssertionError("operation shape incomplete")) if any(not {"params","returns","errors"}.issubset(op) for op in api["operations"].values()) else True)
    used_api_errors = {code for op in api["operations"].values() for code in op["errors"]}
    s.expect_ok("Public API error codes are completely declared", lambda: (_ for _ in ()).throw(
        AssertionError("API error declaration mismatch")) if used_api_errors != set(api.get("error_codes", {}))
        or any(not isinstance(meta.get("retryable"), bool) or not isinstance(meta.get("description"), str) or not meta["description"]
               for meta in api.get("error_codes", {}).values()) else True)
    required_values = {"Context","BatchSnapshot","JobSnapshot","DecisionSnapshot","Event","ReconcileReport"}
    s.expect_ok("Public API return value objects are declared", lambda: (_ for _ in ()).throw(
        AssertionError("missing public value object")) if not required_values.issubset(api.get("value_objects", {})) else True)
    s.expect_ok("all 18 packages declare a concrete responsibility", lambda: (_ for _ in ()).throw(
        AssertionError("missing package responsibility")) if any(not isinstance(pkg.get("responsibility"), str) or not pkg["responsibility"].strip()
        for pkg in package_graph["packages"]) else True)
    package_dirs = sorted(p.name for p in (ROOT / "packages").iterdir() if p.is_dir())
    s.expect_ok("physical planning contracts exist for exactly 18 packages", lambda: (_ for _ in ()).throw(
        AssertionError("package directory mismatch")) if package_dirs != sorted(pkg["name"] for pkg in package_graph["packages"]) else True)
    def validate_package_contract_files() -> bool:
        try:
            import jsonschema
        except ImportError as exc:
            raise RuntimeError("jsonschema is required for package contract validation") from exc
        contract_schema = json.loads((ROOT / "schemas/package_contract.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(contract_schema)
        validator = jsonschema.Draft202012Validator(contract_schema)
        by_name = {pkg["name"]: pkg for pkg in package_graph["packages"]}
        for name in package_dirs:
            folder = ROOT / "packages" / name
            if not (folder / "PACKAGE.md").is_file() or not (folder / "contract.json").is_file():
                raise AssertionError(f"missing package contract files: {name}")
            contract = json.loads((folder / "contract.json").read_text(encoding="utf-8"))
            errors = sorted(validator.iter_errors(contract), key=lambda e: list(e.absolute_path))
            if errors:
                raise AssertionError(f"package contract schema violation {name}: {errors[0].message}")
            graph_item = by_name[name]
            if contract.get("name") != name or contract.get("layer") != graph_item["layer"]:
                raise AssertionError(f"package contract identity differs from graph: {name}")
            if set(contract.get("depends_on", [])) != set(graph_item["depends_on"]):
                raise AssertionError(f"package contract dependency set differs from graph: {name}")
            if contract.get("responsibility") != graph_item.get("responsibility"):
                raise AssertionError(f"package responsibility differs from graph: {name}")
            md = (folder / "PACKAGE.md").read_text(encoding="utf-8")
            def section_items(title: str) -> list[str]:
                match = re.search(rf"^## {re.escape(title)}\s*$\n(.*?)(?=^## |\Z)", md, re.M | re.S)
                if not match:
                    raise AssertionError(f"PACKAGE.md missing {title}: {name}")
                return [line.strip()[2:].strip().strip('`') for line in match.group(1).splitlines() if line.strip().startswith('- ')]
            if section_items("Planned public surface") != contract["public_surface"]:
                raise AssertionError(f"PACKAGE.md public_surface drift: {name}")
            if section_items("Must not own") != contract["must_not"]:
                raise AssertionError(f"PACKAGE.md must_not drift: {name}")
        return True
    s.expect_ok("all package-local contracts match schema, graph and PACKAGE.md", validate_package_contract_files)

    # Schema revision must advance with persistence-layer changes.
    con = open_schema_db()
    s.expect_ok("schema_meta reports persistence revision 2.1.5.07", lambda: (_ for _ in ()).throw(
        AssertionError("schema_version mismatch")) if con.execute("SELECT schema_value FROM schema_meta WHERE schema_key='schema_version'").fetchone()[0] != "2.1.5.07" else True)

    # Stable error vocabulary.
    schema_text = (ROOT / "sql/schema.sql").read_text(encoding="utf-8")
    def extract_error_code_sets() -> list[set[str]]:
        blocks = re.findall(r"error_code TEXT CHECK \(error_code IS NULL OR error_code IN \((.*?)\)\)", schema_text, re.S)
        return [set(re.findall(r"'([A-Z_]+)'", block)) for block in blocks]
    s.expect_ok("stable ErrorCode vocabulary is an exact 18-value set in every SQL declaration", lambda: (_ for _ in ()).throw(
        AssertionError("error vocabulary mismatch")) if len(ERROR_CODES) != 18 or extract_error_code_sets() != [ERROR_CODES, ERROR_CODES] else True)

    # B21/N6: every transition-matrix row is an executable test against the actual SQL transition trigger.
    transition_matrix = json.loads((ROOT / "contracts/transition_test_matrix.v1.json").read_text(encoding="utf-8"))
    transition_trigger_sql: dict[str, str] = {}
    expected_transition_ids: set[str] = set()

    def validate_transition_test_matrix_structure() -> bool:
        if transition_matrix.get("schema") != "audioprep.transition-test-matrix.v1" or transition_matrix.get("design_revision") != "R2.1.5.07":
            raise AssertionError("transition matrix identity mismatch")
        seen_ids: set[str] = set()
        for machine in transition_matrix.get("machines", []):
            states = machine["states"]
            field = machine["field"]
            trigger_name = machine["schema_trigger"]
            row = con.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (trigger_name,)).fetchone()
            if not row or not row[0]:
                raise AssertionError(f"missing transition trigger: {trigger_name}")
            trigger_sql = row[0]
            transition_trigger_sql[trigger_name] = trigger_sql
            table_match = re.search(r"\bON\s+([A-Za-z_][A-Za-z0-9_]*)", trigger_sql, re.I)
            if not table_match or machine.get("name") != table_match.group(1):
                raise AssertionError(f"transition machine name/table mismatch: {machine.get('name')!r}")
            parsed: set[tuple[str, str]] = set()
            for old, values in re.findall(
                rf"OLD\.{re.escape(field)}='([^']+)'\s+AND\s+NEW\.{re.escape(field)}\s+IN\s*\(([^)]*)\)",
                trigger_sql, re.I | re.S):
                for new_state in re.findall(r"'([^']+)'", values):
                    parsed.add((old, new_state))
            for values in re.findall(
                rf"OLD\.{re.escape(field)}\s+IN\s*\(([^)]*)\)\s+AND\s+NEW\.{re.escape(field)}\s*=\s*OLD\.{re.escape(field)}",
                trigger_sql, re.I | re.S):
                for state in re.findall(r"'([^']+)'", values):
                    parsed.add((state, state))
            for old, new_state in re.findall(
                rf"OLD\.{re.escape(field)}='([^']+)'\s+AND\s+NEW\.{re.escape(field)}='([^']+)'",
                trigger_sql, re.I | re.S):
                parsed.add((old, new_state))
            if re.search(rf"WHEN\s+NEW\.{re.escape(field)}\s*<>\s*OLD\.{re.escape(field)}", trigger_sql, re.I):
                parsed.update((state, state) for state in states)
            expected_pairs = {(case["from"], case["to"]) for case in machine["cases"] if case["allowed"]}
            if parsed != expected_pairs:
                raise AssertionError(f"transition matrix differs from {trigger_name}: parsed={sorted(parsed)} expected={sorted(expected_pairs)}")
            all_pairs = {(a, b) for a in states for b in states}
            case_pairs = {(case["from"], case["to"]) for case in machine["cases"]}
            if case_pairs != all_pairs or len(machine["cases"]) != len(all_pairs):
                raise AssertionError(f"transition matrix not exhaustive: {machine['name']}")
            prefix = machine["name"].upper()
            for case in machine["cases"]:
                tid = case.get("test_id", "")
                canonical_tid = f"TM-{prefix}-{case['from']}-TO-{case['to']}"
                if tid != canonical_tid:
                    raise AssertionError(f"transition test_id is not canonical for its state pair: {tid!r} != {canonical_tid!r}")
                if tid in seen_ids:
                    raise AssertionError(f"duplicate transition test_id: {tid!r}")
                seen_ids.add(tid)
                if bool(case["allowed"]) != ((case["from"], case["to"]) in parsed):
                    raise AssertionError(f"transition case expectation mismatch: {tid}")
        expected_transition_ids.update(seen_ids)
        return True

    s.expect_ok("transition matrix structure/canonical IDs exactly match SQL guards", validate_transition_test_matrix_structure)
    executed_transition_ids: set[str] = set()
    for machine in transition_matrix.get("machines", []):
        trigger_sql = transition_trigger_sql.get(machine["schema_trigger"])
        if not trigger_sql:
            continue
        for case in machine["cases"]:
            tid = case["test_id"]
            def run_case(m=machine, c=case, sql=trigger_sql, test_id=tid):
                execute_transition_matrix_case(sql, m, c)
                executed_transition_ids.add(test_id)
                return True
            s.expect_ok(tid, run_case)
    s.expect_ok("all transition matrix test IDs were actually executed", lambda: (_ for _ in ()).throw(
        AssertionError(f"transition execution coverage mismatch missing={sorted(expected_transition_ids-executed_transition_ids)} extra={sorted(executed_transition_ids-expected_transition_ids)}"))
        if executed_transition_ids != expected_transition_ids else True)

    # D1: bilingual normative clauses must advance together; this blocks a new-version stamp on stale zh-CN text.
    def validate_bilingual_clause_parity() -> bool:
        pairs = {
            "03-invariants.md": (["Stable primary", "terminal Job", "ABORTED"], ["稳定主键", "终态 Job", "ABORTED"]),
            "04-data-model.md": (["immutable identifier strings", "garbage-collected", "ON DELETE RESTRICT"], ["不可变标识串", "GC", "ON DELETE RESTRICT"]),
            "08-cache-and-gc.md": (["DecisionCandidate", "TimelineMapping", "DeliverableSegment", "not LIVE"], ["DecisionCandidate", "TimelineMapping", "DeliverableSegment", "不再是 LIVE"]),
            "11-configuration.md": (["audio`, `pipeline", "recursively", "experimental.enabled=true"], ["audio`、`pipeline", "递归", "experimental.enabled=true"]),
            "15-execution-runtime.md": (["current_plan_id", "dispatch_generation", "active_run_token", "WAITING_DECISION"], ["current_plan_id", "dispatch_generation", "active_run_token", "WAITING_DECISION"]),
        }
        for name, (en_tokens, zh_tokens) in pairs.items():
            en = (ROOT / "docs/en" / name).read_text(encoding="utf-8")
            zh = (ROOT / "docs/zh-CN" / name).read_text(encoding="utf-8")
            if "**Revision:** R2.1.5.07" not in en or "**版本：** R2.1.5.07" not in zh:
                raise AssertionError(f"bilingual revision drift: {name}")
            for token in en_tokens:
                if token not in en:
                    raise AssertionError(f"English clause token missing {name}: {token}")
            for token in zh_tokens:
                if token not in zh:
                    raise AssertionError(f"Chinese clause token missing {name}: {token}")
        for lang, prefix in (("en", "**Revision:** R2.1.5.07"), ("zh-CN", "**版本：** R2.1.5.07")):
            docs = sorted((ROOT / "docs" / lang).glob("*.md"))
            if len(docs) != 18 or any(prefix not in d.read_text(encoding="utf-8") for d in docs):
                raise AssertionError(f"{lang} chapter revision/count mismatch")
        return True
    s.expect_ok("18×2 bilingual normative chapters contain R2.1.5.07 parity clauses", validate_bilingual_clause_parity)

    def validate_documented_inventory() -> bool:
        con = open_schema_db()
        actual = {
            "tables": con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0],
            "triggers": con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0],
            "indexes": con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND sql IS NOT NULL").fetchone()[0],
        }
        if actual != {"tables": 23, "triggers": 131, "indexes": 9}:
            raise AssertionError(f"unexpected live schema inventory: {actual}")
        required = (ROOT / "README.md", ROOT / "README.zh-CN.md", ROOT / "VALIDATION_REPORT.md", ROOT / "REPAIR_REPORT.md")
        for path in required:
            text = path.read_text(encoding="utf-8")
            if "R2.1.5.07" not in text:
                raise AssertionError(f"revision fact missing from {path.name}")
            # Any explicit table/trigger/index inventory claim in release-facing docs must agree with live SQLite.
            claims = [
                (r"(\d+)\s+(?:SQLite\s+)?tables?", actual["tables"], "tables"),
                (r"(\d+)\s+(?:invariant\s+)?triggers?", actual["triggers"], "triggers"),
                (r"(\d+)\s+(?:explicit\s+)?indexes?", actual["indexes"], "indexes"),
                (r"(\d+)\s*张表", actual["tables"], "tables"),
                (r"(\d+)\s*个(?:\s*invariant)?\s*trigger", actual["triggers"], "triggers"),
                (r"(\d+)\s*个索引", actual["indexes"], "indexes"),
            ]
            for pattern, expected, label in claims:
                for found in re.findall(pattern, text, re.I):
                    if int(found) != expected:
                        raise AssertionError(f"stale {label} count in {path.name}: {found} != {expected}")
        return True
    s.expect_ok("release docs inventory claims match live 23/131/9 SQLite inventory", validate_documented_inventory)

    # Print authoritative result.
    print(f"PASS {s.passed}/{s.total}" if s.passed == s.total else f"FAIL {s.passed}/{s.total}")
    for line in s.lines:
        print(line)
    return 0 if s.passed == s.total else 1


if __name__ == "__main__":
    raise SystemExit(run_validation())
