# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""audioprep Tier 2 最小运行时：契约 schema 之上的单写者调度器 + worker 派发。

复刻范围（对照 audioprep_contract 冻结件）：
- 控制面 SQLite 由冻结 schema 建库，131 触发器全量生效；
- 计划封印走冻结件的 validate_planning（build_plan_validation_report /
  compute_plan_fingerprint），封缄回执落 pipeline_plan_validation；
- 节点执行链 PENDING→DISPATCHED→RUNNING→SUCCEEDED 由真实子进程 worker 完成
  （worker 只写私有 tmp 并回 envelope，调度器校验后提交 CAS）；
- 源捕获（blob/artifact/artifact_reference/job 冻结五元组）与 checkpoint 按
  independent_regression 演示的合法插入链实现。

未复刻（后续轮次）：多节点 DAG 调度循环、HYBRID 决策流、lease 心跳/回收扫描、
GC 与 delivery manifest。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

BUNDLE_DIR = Path(__file__).resolve().parents[2] / "audioprep_contract"
WORKER_SCRIPT = Path(__file__).resolve().parent / "audioprep_worker.py"
PLANNER_VERSION = "wt-tier2/1"
NODE_TIMEOUT_S = 120
FAR_FUTURE = "2099-01-01T00:00:00.000Z"
DEFAULT_SEGMENT = (0.2, 0.8)


def utc_now_iso() -> str:
    """契约口径的 UTC 毫秒 RFC3339（24 字符，满足 schema 的 CHECK）。"""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _deadline(seconds: int) -> str:
    now = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _media_spec(role: str) -> dict:
    return {"artifact_type": "audio", "role": role, "media_kind": "audio",
            "cardinality": "required-single"}


def _json(value) -> str:
    return json.dumps(value, separators=(",", ":"))


_validator = None


def plan_validator():
    """加载冻结件的 validate_planning（只 import，不改动冻结件）。"""
    global _validator
    if _validator is None:
        spec = importlib.util.spec_from_file_location(
            "wt_audioprep_validate_planning", BUNDLE_DIR / "tools" / "validate_planning.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load frozen validate_planning")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _validator = module
    return _validator


class TaeHanazono:
    """单机调度器：契约 schema 之上的最小可运行控制面（命名池类名）。"""

    def __init__(self, db_path: Path, ffmpeg_exe: Path) -> None:
        self.db_path = Path(db_path)
        self.ffmpeg_exe = Path(ffmpeg_exe)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cas_dir = self.db_path.parent / "cas"
        self.cas_dir.mkdir(parents=True, exist_ok=True)
        fresh = not self.db_path.exists() or self.db_path.stat().st_size == 0
        self.con = sqlite3.connect(str(self.db_path))
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.execute("PRAGMA recursive_triggers=ON")
        if fresh:
            self.con.executescript(
                (BUNDLE_DIR / "sql" / "schema.sql").read_text(encoding="utf-8"))
            self.con.commit()

    def close(self) -> None:
        self.con.close()

    # ------------------------------------------------------------------ batch/job

    def create_batch(self, input_folder: str) -> str:
        batch_id = f"batch-{uuid.uuid4().hex[:12]}"
        self.con.execute(
            "INSERT INTO batch(batch_id,workflow_mode,input_folder) VALUES(?,?,?)",
            (batch_id, "TRUSTED", input_folder))
        self.con.commit()
        return batch_id

    def create_job(self, batch_id: str, source_path: Path) -> str:
        source = Path(source_path)
        if not source.is_file():
            raise FileNotFoundError(f"source not found: {source}")
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        self.con.execute(
            "INSERT INTO job(job_id,batch_id,source_path) VALUES(?,?,?)",
            (job_id, batch_id, str(source)))
        self.con.commit()
        return job_id

    # ------------------------------------------------------------------ plan

    def plan_default(self, job_id: str) -> str:
        """MVP 双节点计划：DECODE（源→QUALITY_MASTER）→ DELIVERY_RENDER（切片）。"""
        plan_id = f"plan-{uuid.uuid4().hex[:12]}"
        decode_id = f"node-{uuid.uuid4().hex[:12]}"
        render_id = f"node-{uuid.uuid4().hex[:12]}"
        con = self.con
        con.execute(
            "INSERT INTO pipeline_plan(plan_id,job_id,planner_version) VALUES(?,?,?)",
            (plan_id, job_id, PLANNER_VERSION))
        con.execute(
            """INSERT INTO pipeline_plan_node(plan_node_id,plan_id,node_key,ordinal,stage,
              node_type,implementation_id,implementation_version,implementation_fingerprint,
              hard_timeout_s,input_roles,output_roles,input_contracts,output_contracts)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (decode_id, plan_id, "decode", 0, "audio", "DECODE",
             "ffmpeg.decode", "1", "fp:ffmpeg-decode-v1", NODE_TIMEOUT_S,
             "[]", '["audio"]', "{}", _json({"audio": _media_spec("QUALITY_MASTER")})))
        con.execute(
            """INSERT INTO pipeline_plan_node(plan_node_id,plan_id,node_key,ordinal,stage,
              node_type,implementation_id,implementation_version,implementation_fingerprint,
              hard_timeout_s,input_roles,output_roles,input_contracts,output_contracts)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (render_id, plan_id, "render", 1, "delivery", "DELIVERY_RENDER",
             "ffmpeg.segment_render", "1", "fp:ffmpeg-segment-v1", NODE_TIMEOUT_S,
             '["audio"]', "[]", _json({"audio": _media_spec("QUALITY_MASTER")}), "{}"))
        con.execute(
            """INSERT INTO pipeline_plan_edge(plan_id,from_plan_node_id,to_plan_node_id,
              output_name,input_name) VALUES(?,?,?,?,?)""",
            (plan_id, decode_id, render_id, "audio", "audio"))
        validator = plan_validator()
        report = validator.build_plan_validation_report(con, plan_id)
        fingerprint = validator.compute_plan_fingerprint(con, plan_id)
        con.execute(
            """INSERT INTO pipeline_plan_validation(plan_id,plan_fingerprint,
              validator_version,report_json,validated_at) VALUES(?,?,?,?,?)""",
            (plan_id, fingerprint, PLANNER_VERSION, _json(report), utc_now_iso()))
        con.execute(
            "UPDATE pipeline_plan SET status='SEALED',plan_fingerprint=?,sealed_at=? "
            "WHERE plan_id=?", (fingerprint, utc_now_iso(), plan_id))
        con.commit()
        return plan_id

    # ------------------------------------------------------------------ queue/run

    def queue_job(self, job_id: str) -> None:
        row = self.con.execute(
            "SELECT source_path FROM job WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        plan_row = self.con.execute(
            "SELECT plan_id FROM pipeline_plan WHERE job_id=? AND status='SEALED' "
            "ORDER BY revision DESC LIMIT 1", (job_id,)).fetchone()
        if plan_row is None:
            raise ValueError("queue_job requires a sealed plan (plan_default first)")
        plan_id = plan_row[0]
        source_path = row[0]
        source = Path(source_path)
        stat = source.stat()
        digest = sha256_file(source)
        blob_id = f"blob-{uuid.uuid4().hex[:12]}"
        cas_path = self.cas_dir / blob_id
        shutil.copyfile(source, cas_path)
        artifact_id = f"art-{uuid.uuid4().hex[:12]}"
        self.con.execute(
            "INSERT INTO blob(blob_id,content_hash,path,size_bytes,media_type) "
            "VALUES(?,?,?,?,?)",
            (blob_id, "sha256:" + digest, str(cas_path), stat.st_size, "audio/wav"))
        self.con.execute(
            """INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,
              producer_component,retention_class,retention_until) VALUES(?,?,?,?,?,?,?)""",
            (artifact_id, blob_id, "audio", "SOURCE_MEDIA", "ingest", "source",
             FAR_FUTURE))
        self.con.execute(
            "INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) "
            "VALUES(?,'JOB',?,'source')", (artifact_id, job_id))
        self.con.execute(
            """UPDATE job SET source_size_bytes=?,source_mtime_ns=?,source_content_hash=?,
              source_artifact_id=?,source_identity_frozen_at=?,current_plan_id=?,status='QUEUED'
              WHERE job_id=?""",
            (stat.st_size, stat.st_mtime_ns, "sha256:" + digest, artifact_id,
             utc_now_iso(), plan_id, job_id))
        self.con.commit()

    def run_job(self, job_id: str) -> dict:
        plan_id, generation = self.con.execute(
            "SELECT current_plan_id,dispatch_generation FROM job WHERE job_id=?",
            (job_id,)).fetchone()
        if not plan_id:
            raise ValueError("job has no installed plan")
        token = f"run-{uuid.uuid4().hex[:12]}"
        worker = "wt-scheduler"
        generation = generation + 1
        self.con.execute(
            """UPDATE job SET status='RUNNING',dispatch_generation=?,active_run_token=?,
              lease_expires_at=?,worker_id=?,started_at=? WHERE job_id=?""",
            (generation, token, _deadline(300), worker, utc_now_iso(), job_id))
        self.con.commit()
        cas_source = self.con.execute(
            """SELECT b.path FROM job j JOIN artifact a ON a.artifact_id=j.source_artifact_id
              JOIN blob b ON b.blob_id=a.blob_id WHERE j.job_id=?""", (job_id,)).fetchone()[0]
        nodes = self.con.execute(
            """SELECT plan_node_id,node_type,implementation_fingerprint,hard_timeout_s
              FROM pipeline_plan_node WHERE plan_id=? ORDER BY ordinal""",
            (plan_id,)).fetchall()
        params = self._plan_params(plan_id)
        input_path: Path | None = None
        artifacts: list[dict] = []
        try:
            for index, (node_id, node_type, fingerprint, timeout_s) in enumerate(nodes):
                output_path = self._execute_node(
                    job_id, plan_id, node_id, node_type, fingerprint, timeout_s,
                    generation, token, worker, index,
                    Path(input_path or cas_source), params.get(node_type, {}))
                committed = self._commit_output(job_id, node_id, node_type, output_path)
                artifacts.append(committed)
                input_path = Path(committed["path"])
        except _NodeFailure as failure:
            self._fail_job(job_id, failure.error_code, failure.detail)
            return {"job_id": job_id, "status": "FAILED",
                    "error_code": failure.error_code, "detail": failure.detail}
        self.con.execute(
            """UPDATE job SET status='SUCCEEDED',finished_at=?,active_run_token=NULL,
              lease_expires_at=NULL,worker_id=NULL WHERE job_id=?""",
            (utc_now_iso(), job_id))
        self.con.commit()
        return {"job_id": job_id, "status": "SUCCEEDED", "artifacts": artifacts}

    # ------------------------------------------------------------------ internals

    def _plan_params(self, plan_id: str) -> dict:
        """节点参数：MVP 约定 render 节点按 DEFAULT_SEGMENT 切片。"""
        keys = [row[0] for row in self.con.execute(
            "SELECT node_key FROM pipeline_plan_node WHERE plan_id=? ORDER BY ordinal",
            (plan_id,))]
        params: dict = {}
        if "render" in keys:
            params["DELIVERY_RENDER"] = {"start_s": DEFAULT_SEGMENT[0],
                                         "end_s": DEFAULT_SEGMENT[1]}
        return params

    def _execute_node(self, job_id, plan_id, node_id, node_type, fingerprint,
                      timeout_s, generation, token, worker, index,
                      input_path: Path, params: dict) -> Path:
        seq = self.con.execute(
            "SELECT COUNT(*) FROM node_execution WHERE job_id=? AND plan_node_id=?",
            (job_id, node_id)).fetchone()[0] + 1
        exec_id = f"exec-{uuid.uuid4().hex[:12]}"
        self.con.execute(
            """INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,
              execution_seq,dispatch_generation,status,implementation_fingerprint)
              VALUES(?,?,?,?,?,?, 'PENDING',?)""",
            (exec_id, job_id, plan_id, node_id, seq, generation, fingerprint))
        self.con.execute(
            "UPDATE node_execution SET status='DISPATCHED' WHERE execution_id=?",
            (exec_id,))
        self.con.execute(
            """UPDATE node_execution SET status='RUNNING',run_token=?,worker_id=?,
              started_at=?,hard_deadline_at=? WHERE execution_id=?""",
            (token, worker, utc_now_iso(), _deadline(timeout_s), exec_id))
        self.con.commit()

        base = Path(tempfile.mkdtemp(prefix="wt_apc2_"))
        try:
            output_path = base / "output.wav"
            spec = {
                "node_type": node_type,
                "fingerprint": fingerprint,
                "input_path": str(input_path),
                "output_path": str(output_path),
                "params": params,
                "ffmpeg_exe": str(self.ffmpeg_exe),
            }
            job_file = base / "job.json"
            job_file.write_text(_json(spec), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-B", str(WORKER_SCRIPT), "--job", str(job_file)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout_s + 30, check=False)
            envelope_file = base / "envelope.json"
            if not envelope_file.is_file():
                raise _NodeFailure(
                    "NODE_CRASH",
                    (proc.stderr.strip() or proc.stdout.strip() or "worker 无 envelope")[-400:])
            envelope = json.loads(envelope_file.read_text(encoding="utf-8"))
            if not envelope.get("ok"):
                raise _NodeFailure(
                    envelope.get("error_code", "NODE_CRASH"),
                    str(envelope.get("detail", ""))[-400:])
            if envelope.get("fingerprint") != fingerprint:
                raise _NodeFailure("NODE_OUTPUT_INVALID", "envelope fingerprint mismatch")
            output = Path(envelope["outputs"][0]["path"])
            if not output.is_file() or output.stat().st_size == 0:
                raise _NodeFailure("NODE_OUTPUT_INVALID", "missing or empty output")
            self.con.execute(
                """UPDATE node_execution SET status='SUCCEEDED',completed_at=?,
                  run_token=NULL,worker_id=NULL WHERE execution_id=?""",
                (utc_now_iso(), exec_id))
            self.con.execute(
                """INSERT INTO checkpoint(checkpoint_id,job_id,plan_id,plan_node_id,
                  execution_id,status) VALUES(?,?,?,?,?,'OPEN')""",
                (f"cp-{uuid.uuid4().hex[:12]}", job_id, plan_id, node_id, exec_id))
            self.con.commit()
            return output
        except _NodeFailure as failure:
            self._fail_execution(exec_id, failure.error_code, failure.detail)
            raise
        except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError, KeyError) as exc:
            self._fail_execution(exec_id, "NODE_CRASH", f"{type(exc).__name__}: {exc}")
            raise _NodeFailure("NODE_CRASH", f"{type(exc).__name__}: {exc}") from exc

    def _fail_execution(self, exec_id: str, error_code: str, detail: str) -> None:
        self.con.execute(
            """UPDATE node_execution SET status='FAILED',completed_at=?,run_token=NULL,
              worker_id=NULL,error_code=?,error_detail=? WHERE execution_id=?""",
            (utc_now_iso(), error_code, detail, exec_id))
        self.con.commit()

    def _commit_output(self, job_id, node_id, node_type, output_path: Path) -> dict:
        digest = sha256_file(output_path)
        size = output_path.stat().st_size
        blob_id = f"blob-{uuid.uuid4().hex[:12]}"
        cas_path = self.cas_dir / blob_id
        shutil.move(str(output_path), cas_path)
        role = "QUALITY_MASTER" if node_type == "DECODE" else "DELIVERY_SEGMENT"
        retention = "pipeline" if node_type == "DECODE" else "delivery"
        artifact_id = f"art-{uuid.uuid4().hex[:12]}"
        self.con.execute(
            "INSERT INTO blob(blob_id,content_hash,path,size_bytes,media_type) "
            "VALUES(?,?,?,?,?)",
            (blob_id, "sha256:" + digest, str(cas_path), size, "audio/wav"))
        exec_id = self.con.execute(
            "SELECT execution_id FROM node_execution WHERE plan_node_id=? "
            "ORDER BY execution_seq DESC LIMIT 1", (node_id,)).fetchone()[0]
        self.con.execute(
            """INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,
              producer_component,producer_execution_id,output_name,retention_class,
              retention_until) VALUES(?,?,?,?,?,?,?,?,?)""",
            (artifact_id, blob_id, "audio", role, "node", exec_id, "audio",
             retention, FAR_FUTURE))
        self.con.execute(
            "INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) "
            "VALUES(?,'JOB',?,'output')", (artifact_id, job_id))
        self.con.commit()
        return {"artifact_id": artifact_id, "role": role, "path": str(cas_path),
                "sha256": digest, "size": size}

    def _fail_job(self, job_id: str, error_code: str, detail: str) -> None:
        self.con.execute(
            """UPDATE job SET status='FAILED',finished_at=?,active_run_token=NULL,
              lease_expires_at=NULL,worker_id=NULL,error_code=?,error_type='SYSTEM'
              WHERE job_id=?""", (utc_now_iso(), error_code, job_id))
        self.con.commit()
        _ = detail

    def job_state(self, job_id: str) -> dict:
        row = self.con.execute(
            """SELECT status,error_code,dispatch_generation,source_content_hash
              FROM job WHERE job_id=?""", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        artifacts = self.con.execute(
            """SELECT a.artifact_role,b.size_bytes FROM artifact a
              JOIN blob b ON b.blob_id=a.blob_id
              JOIN job j ON a.artifact_id=j.source_artifact_id WHERE j.job_id=?
              UNION ALL
              SELECT a.artifact_role,b.size_bytes FROM artifact a
              JOIN blob b ON b.blob_id=a.blob_id
              WHERE a.producer_execution_id IN
                (SELECT execution_id FROM node_execution WHERE job_id=?)""",
            (job_id, job_id)).fetchall()
        return {"job_id": job_id, "status": row[0], "error_code": row[1],
                "dispatch_generation": row[2], "artifacts": artifacts}


class _NodeFailure(Exception):
    def __init__(self, error_code: str, detail: str) -> None:
        super().__init__(detail)
        self.error_code = error_code
        self.detail = detail


def run_tier2_smoke(workdir: Path, ffmpeg_exe: Path) -> str:
    """端到端冒烟：stdlib 正弦 wav → 建库 → 计划封缄 → 双节点执行 → 交付切片。"""
    import math
    import struct
    import wave

    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    source = workdir / "sine_1s.wav"
    with wave.open(str(source), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        frames = [struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / 8000)))
                  for i in range(8000)]
        handle.writeframes(b"".join(frames))

    runtime = TaeHanazono(workdir / "control.sqlite", ffmpeg_exe)
    try:
        batch = runtime.create_batch(str(workdir))
        job = runtime.create_job(batch, source)
        runtime.plan_default(job)
        runtime.queue_job(job)
        summary = runtime.run_job(job)
        state = runtime.job_state(job)
        fk = runtime.con.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        runtime.close()
    lines = [
        f"batch={batch}",
        f"job={job}",
        f"status={summary['status']}",
        f"artifacts={len(state['artifacts'])}",
        f"foreign_key_check={'clean' if not fk else fk[:3]}",
    ]
    for item in summary.get("artifacts", []):
        lines.append(f"  {item['role']} size={item['size']} sha256={item['sha256'][:16]}…")
    return "\n".join(lines)
