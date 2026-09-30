#!/usr/bin/env python3
"""Independent R2.1.5.07 hardening regression.

This suite deliberately does not use the main Suite harness. Every negative case must
name an expected error substring; an unrelated exception is a failure, not a PASS.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import importlib.util, json, re, sqlite3, sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from validate_planning import (  # noqa: E402
    compute_plan_fingerprint,
    build_plan_validation_report,
    validate_manifest_document,
    validate_public_api_type_aliases,
    validate_artifact_vocabulary_sync,
)

SCHEMA = (ROOT / "sql/schema.sql").read_text(encoding="utf-8")
TS = "2026-08-09T05:00:00.000Z"
TS1 = "2026-08-09T05:01:00.000Z"
TS2 = "2026-08-09T05:02:00.000Z"
TS3 = "2026-08-09T05:03:00.000Z"
FUTURE = "2099-01-01T00:00:00.000Z"


def db() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA recursive_triggers=ON")
    c.executescript(SCHEMA)
    return c


def digest(ch: str) -> str:
    assert ch in "0123456789abcdef"
    return "sha256:" + ch * 64


def base(c: sqlite3.Connection, job="j1", batch="b1") -> None:
    c.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder) VALUES(?,?,?)", (batch,"TRUSTED",f"/{batch}"))
    c.execute("INSERT INTO job(job_id,batch_id,source_path) VALUES(?,?,?)", (job,batch,f"/{job}.wav"))


def plan(c: sqlite3.Connection, job="j1", pid="p1", nid="n1", revision=1, parent=None) -> None:
    c.execute("INSERT INTO pipeline_plan(plan_id,job_id,revision,parent_plan_id,planner_version) VALUES(?,?,?,?,?)", (pid,job,revision,parent,"v"))
    c.execute("""INSERT INTO pipeline_plan_node(plan_node_id,plan_id,node_key,ordinal,stage,node_type,
      implementation_id,implementation_version,implementation_fingerprint,hard_timeout_s,input_roles,output_roles,input_contracts,output_contracts)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (nid,pid,nid,0,"stage","type","impl", "1",f"fp-{nid}",60,"[]","[]","{}","{}"))
    report = build_plan_validation_report(c, pid)
    fp = compute_plan_fingerprint(c, pid)
    c.execute("INSERT INTO pipeline_plan_validation(plan_id,plan_fingerprint,validator_version,report_json,validated_at) VALUES(?,?,?,?,?)",
              (pid,fp,"independent/R2.1.5.07",json.dumps(report,separators=(",",":")),TS))
    c.execute("UPDATE pipeline_plan SET status='SEALED',plan_fingerprint=?,sealed_at=? WHERE plan_id=?", (fp,TS,pid))



def queue_job(c: sqlite3.Connection, job="j1", pid="p1") -> None:
    h = digest("a" if job == "j1" else "b")
    bid=f"srcblob-{job}"; aid=f"srcart-{job}"
    c.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES(?,?,?,1)",(bid,h,f"/cas/{bid}"))
    c.execute("INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,producer_component,retention_class,retention_until) VALUES(?,?,'audio','SOURCE_MEDIA','ingest','source',?)",(aid,bid,FUTURE))
    c.execute("INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) VALUES(?,'JOB',?,'source')",(aid,job))
    c.execute("UPDATE job SET source_size_bytes=1,source_mtime_ns=1,source_content_hash=?,source_artifact_id=?,source_identity_frozen_at=?,current_plan_id=?,status='QUEUED' WHERE job_id=?",(h,aid,TS,pid,job))


def media_spec(role: str, *, cardinality: str = "required-single") -> dict:
    return {"artifact_type":"audio","role":role,"media_kind":"audio","cardinality":cardinality}


def render_plan(c: sqlite3.Connection, role: str) -> None:
    base(c); c.execute("INSERT INTO pipeline_plan(plan_id,job_id,planner_version) VALUES('rp','j1','v')")
    c.execute("""INSERT INTO pipeline_plan_node(plan_node_id,plan_id,node_key,ordinal,stage,node_type,implementation_id,implementation_version,implementation_fingerprint,hard_timeout_s,input_roles,output_roles,input_contracts,output_contracts)
      VALUES('src','rp','src',0,'audio','SOURCE','i','1','fp-src',60,'[]','["audio"]','{}',?)""",
      (json.dumps({"audio":media_spec(role)},separators=(",",":")),))
    c.execute("""INSERT INTO pipeline_plan_node(plan_node_id,plan_id,node_key,ordinal,stage,node_type,implementation_id,implementation_version,implementation_fingerprint,hard_timeout_s,input_roles,output_roles,input_contracts,output_contracts)
      VALUES('render','rp','render',1,'delivery','DELIVERY_RENDER','i','1','fp-render',60,'["audio"]','[]',?,'{}')""",
      (json.dumps({"audio":media_spec(role)},separators=(",",":")),))
    c.execute("INSERT INTO pipeline_plan_edge(plan_id,from_plan_node_id,to_plan_node_id,output_name,input_name) VALUES('rp','src','render','audio','audio')")

def activate(c: sqlite3.Connection, job="j1", pid="p1", token="r", worker="w") -> None:
    queue_job(c, job, pid)
    c.execute("UPDATE job SET status='RUNNING',dispatch_generation=1,active_run_token=?,lease_expires_at=?,worker_id=?,started_at=? WHERE job_id=?",(token,FUTURE,worker,TS,job))


def exec_pending(c: sqlite3.Connection, eid="e1", job="j1", pid="p1", nid="n1", gen=1) -> None:
    c.execute("INSERT INTO node_execution(execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,status,implementation_fingerprint) VALUES(?,?,?,?,1,?,'PENDING',?)",(eid,job,pid,nid,gen,f"fp-{nid}"))


def exec_success(c: sqlite3.Connection, eid="e1", job="j1", pid="p1", nid="n1", token="r", worker="w") -> None:
    exec_pending(c,eid,job,pid,nid)
    c.execute("UPDATE node_execution SET status='DISPATCHED' WHERE execution_id=?",(eid,))
    c.execute("UPDATE node_execution SET status='RUNNING',run_token=?,worker_id=?,started_at=?,hard_deadline_at=? WHERE execution_id=?",(token,worker,TS1,TS2,eid))
    c.execute("UPDATE node_execution SET status='SUCCEEDED',completed_at=?,run_token=NULL,worker_id=NULL WHERE execution_id=?",(TS3,eid))


results: list[tuple[str,bool,str]]=[]
def rejected(name: str, contains: str, fn) -> None:
    if not contains: raise AssertionError(f"{name}: expected substring is mandatory")
    try: fn()
    except Exception as e:
        text=f"{type(e).__name__}: {e}"
        results.append((name, contains in text, text if contains in text else f"wrong rejection, expected {contains!r}: {text}"))
    else: results.append((name,False,"invalid operation was accepted"))

def accepted(name: str, fn) -> None:
    try: fn(); results.append((name,True,"accepted"))
    except Exception as e: results.append((name,False,f"unexpected {type(e).__name__}: {e}"))

# B1/B20: execution insertion is live-parent only, not CREATED or terminal.
c=db(); base(c); plan(c)
rejected("CREATED Job cannot accept NodeExecution", "identity mismatch", lambda: exec_pending(c))
activate(c); c.execute("UPDATE job SET status='FAILED',active_run_token=NULL,lease_expires_at=NULL,worker_id=NULL,finished_at=?,error_code='INTERNAL_ERROR',error_type='SYSTEM' WHERE job_id='j1'",(TS3,))
rejected("terminal Job cannot accept NodeExecution", "identity mismatch", lambda: exec_pending(c,"e2"))

# B1 second gate: a stored PENDING row cannot dispatch after terminalization.
c=db(); base(c); plan(c); activate(c); exec_pending(c); c.execute("UPDATE job SET status='FAILED',active_run_token=NULL,lease_expires_at=NULL,worker_id=NULL,finished_at=?,error_code='INTERNAL_ERROR',error_type='SYSTEM' WHERE job_id='j1'",(TS3,))
rejected("terminal Job blocks PENDING to DISPATCHED", "terminal node execution", lambda: c.execute("UPDATE node_execution SET status='DISPATCHED' WHERE execution_id='e1'"))

# B2: stale generation/plan and Job fence ownership are rechecked at dispatch/start.
c=db(); base(c); plan(c); activate(c); exec_pending(c)
rejected("wrong generation cannot be inserted", "identity mismatch", lambda: exec_pending(c,"e2",gen=2))
c.execute("UPDATE node_execution SET status='DISPATCHED' WHERE execution_id='e1'")
rejected("RUNNING token must match Job active_run_token", "runtime fence fields", lambda: c.execute("UPDATE node_execution SET status='RUNNING',run_token='wrong',worker_id='w',started_at=?,hard_deadline_at=? WHERE execution_id='e1'",(TS1,TS2)))
rejected("RUNNING worker must match Job worker", "runtime fence fields", lambda: c.execute("UPDATE node_execution SET status='RUNNING',run_token='r',worker_id='wrong',started_at=?,hard_deadline_at=? WHERE execution_id='e1'",(TS1,TS2)))

# B3: installed current plan cannot be superseded.
c=db(); base(c); plan(c); activate(c)
rejected("installed current Plan cannot be SUPERSEDED", "cannot be superseded", lambda: c.execute("UPDATE pipeline_plan SET status='SUPERSEDED' WHERE plan_id='p1'"))

c=db(); base(c); plan(c); queue_job(c)
rejected("QUEUED current Plan cannot be SUPERSEDED", "uninstall current_plan_id", lambda: c.execute("UPDATE pipeline_plan SET status='SUPERSEDED' WHERE plan_id='p1'"))

# B4: receipt must contain a passed, structured per-rule report (SQL still documents trust boundary).
c=db(); base(c); c.execute("INSERT INTO pipeline_plan(plan_id,job_id,planner_version) VALUES('p','j1','v')")
c.execute("""INSERT INTO pipeline_plan_node(plan_node_id,plan_id,node_key,ordinal,stage,node_type,implementation_id,implementation_version,implementation_fingerprint,hard_timeout_s,input_roles,output_roles,input_contracts,output_contracts)
VALUES('n','p','n',0,'s','t','i','1','fp-n',60,'[]','[]','{}','{}')""")
fp=compute_plan_fingerprint(c,'p')
rejected("forged empty Plan validation receipt rejected", "Plan validation receipt", lambda: c.execute("INSERT INTO pipeline_plan_validation(plan_id,plan_fingerprint,validator_version,report_json,validated_at) VALUES('p',?,'fake','{}',?)",(fp,TS)))
report=build_plan_validation_report(c,'p'); report.pop('media_subsets')
rejected("Plan receipt requires media-subset evidence", "Plan validation receipt", lambda: c.execute(
    "INSERT INTO pipeline_plan_validation(plan_id,plan_fingerprint,validator_version,report_json,validated_at) VALUES('p',?,'fake',?,?)",
    (fp,json.dumps(report,separators=(",",":")),TS)))

# B6/B7: terminal jobs reject new Decision/Plan/Checkpoint; checkpoints require SUCCEEDED execution.
c=db(); base(c); plan(c); activate(c); exec_pending(c)
rejected("Checkpoint cannot attach PENDING execution", "checkpoint job/plan/node identity mismatch", lambda: c.execute("INSERT INTO checkpoint(checkpoint_id,job_id,plan_id,plan_node_id,execution_id,status) VALUES('cp','j1','p1','n1','e1','OPEN')"))
c.execute("UPDATE node_execution SET status='DISPATCHED' WHERE execution_id='e1'"); c.execute("UPDATE node_execution SET status='RUNNING',run_token='r',worker_id='w',started_at=?,hard_deadline_at=? WHERE execution_id='e1'",(TS1,TS2)); c.execute("UPDATE node_execution SET status='SUCCEEDED',completed_at=?,run_token=NULL,worker_id=NULL WHERE execution_id='e1'",(TS3,)); c.execute("UPDATE job SET status='FAILED',active_run_token=NULL,lease_expires_at=NULL,worker_id=NULL,finished_at=?,error_code='INTERNAL_ERROR',error_type='SYSTEM' WHERE job_id='j1'",(TS3,))
rejected("terminal Job rejects Decision insert", "decision job/batch/plan identity mismatch", lambda: c.execute("INSERT INTO decision(decision_id,origin_job_id,batch_id,plan_node_id,decision_type,join_signature,join_signature_components,policy_signature,policy_signature_components,expires_at) VALUES('d','j1','b1','n1','SELECT','j','{}','p','{}',?)",(FUTURE,)))
rejected("terminal Job rejects new Plan", "terminal Job", lambda: c.execute("INSERT INTO pipeline_plan(plan_id,job_id,planner_version) VALUES('p2','j1','v')"))
rejected("terminal Job rejects Checkpoint insert", "checkpoint job/plan/node identity mismatch", lambda: c.execute("INSERT INTO checkpoint(checkpoint_id,job_id,plan_id,plan_node_id,execution_id,status) VALUES('cp2','j1','p1','n1','e1','OPEN')"))
rejected("terminal Job rejects ResourceLease insert", "terminal or missing Job", lambda: c.execute("INSERT INTO resource_lease(lease_id,resource_kind,resource_key,job_id,token,expires_at) VALUES('l','CPU','0','j1','tok',?)",(FUTURE,)))

# B8: TOMBSTONED blobs cannot gain new strong references.
c=db(); base(c); c.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('b',?,'/cas/b',1)",(digest('c'),)); c.execute("INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,producer_component,retention_class,retention_until) VALUES('a','b','audio','CACHE','test','temp',?)",(FUTURE,)); c.execute("UPDATE blob SET gc_state='TOMBSTONED',tombstoned_at=? WHERE blob_id='b'",(TS,))
rejected("TOMBSTONED Blob rejects strong reference", "not LIVE", lambda: c.execute("INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) VALUES('a','JOB','j1','cache')"))

# B4 API integration contract: package seal entrypoint cannot bypass validator invocation.
api_path=ROOT/'packages/audioprep-planner/reference_api.py'
spec=importlib.util.spec_from_file_location('audioprep_planner_reference_api_independent',api_path)
if spec is None or spec.loader is None: raise RuntimeError('cannot load planner reference API')
planner_api=importlib.util.module_from_spec(spec); sys.modules[spec.name]=planner_api; spec.loader.exec_module(planner_api)
c=db(); base(c); c.execute("INSERT INTO pipeline_plan(plan_id,job_id,planner_version) VALUES('api','j1','v')")
c.execute("""INSERT INTO pipeline_plan_node(plan_node_id,plan_id,node_key,ordinal,stage,node_type,implementation_id,implementation_version,implementation_fingerprint,hard_timeout_s,input_roles,output_roles,input_contracts,output_contracts)
VALUES('n','api','n',0,'s','t','i','1','fp-n',60,'[]','[]','{}','{}')""")
validator=planner_api.PlanSealValidator(build_plan_validation_report,compute_plan_fingerprint)
accepted("B4 package seal_plan invokes validator and seals", lambda: planner_api.seal_plan(c,'api',validator))
accepted("B4 package seal_plan persisted receipt", lambda: (_ for _ in ()).throw(AssertionError('receipt missing')) if c.execute("SELECT COUNT(*) FROM pipeline_plan_validation WHERE plan_id='api'").fetchone()[0]!=1 else True)

# N1/N2/B14: controlled vocabularies and stable identities.
accepted("N1 single artifact vocabulary source matches SQL/MediaPortSpec", validate_artifact_vocabulary_sync)
c=db(); base(c); c.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('b',?,'/cas/b',1)",(digest('d'),))
rejected("unknown artifact_role rejected", "CHECK constraint", lambda: c.execute("INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,producer_component,retention_class,retention_until) VALUES('a','b','audio','FREE_TEXT','x','temp',?)",(FUTURE,)))
c=db(); render_plan(c,"ANALYSIS_COPY")
rejected("DELIVERY_RENDER rejects ANALYSIS_COPY", "QUALITY_MASTER", lambda: build_plan_validation_report(c,"rp"))
c=db(); render_plan(c,"QUALITY_MASTER")
accepted("DELIVERY_RENDER accepts QUALITY_MASTER", lambda: build_plan_validation_report(c,"rp"))
c=db(); base(c); c.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('b',?,'/cas/b',1)",(digest('d'),))
c.execute("INSERT INTO execution_cache_output(job_id,execution_key,output_name,blob_id,artifact_type,artifact_role,retention_class) VALUES('j1','k','out','b','audio','CACHE','temp')")
rejected("execution cache identity is immutable", "immutable", lambda: c.execute("UPDATE execution_cache_output SET execution_key='other' WHERE job_id='j1'"))
rejected("schema_meta UPDATE rejected", "read-only", lambda: c.execute("UPDATE schema_meta SET schema_value='evil' WHERE schema_key='schema_version'"))
rejected("schema_meta DELETE rejected", "read-only", lambda: c.execute("DELETE FROM schema_meta WHERE schema_key='schema_version'"))

# B12/B13: lowercase wav and segment/file identity are exact.
manifest=json.loads((ROOT/'examples/manifest.v1.json').read_text())
bad=deepcopy(manifest); bad['segments'][0]['wav']=bad['segments'][0]['wav'][:-4]+'.WAV'
rejected("uppercase WAV rejected", "schema error", lambda: validate_manifest_document(bad))
bad=deepcopy(manifest); bad['segments'][0]['segment_id']='not_the_stem'
rejected("manifest segment_id binds wav stem", "wav filename stem", lambda: validate_manifest_document(bad))

# B16/B17/B18: event deletion contract explicit, timestamps canonical, config namespace/value shape strict.
c=db(); base(c); c.execute("INSERT INTO event(job_id,event_type,payload_json) VALUES('j1','TEST','{}')")
rejected("Job with Event is RESTRICTed from delete", "FOREIGN KEY", lambda: c.execute("DELETE FROM job WHERE job_id='j1'"))
c=db(); rejected("malformed RFC3339 timestamp rejected", "CHECK constraint", lambda: c.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder,created_at) VALUES('b','TRUSTED','/','2026-08-09')"))
c=db(); rejected("calendar-invalid RFC3339 timestamp rejected", "CHECK constraint", lambda: c.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder,created_at) VALUES('b','TRUSTED','/','2026-02-31T00:00:00.000Z')"))
c=db(); rejected("RFC3339 24-hour special case rejected", "CHECK constraint", lambda: c.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder,created_at) VALUES('b','TRUSTED','/','2026-01-01T24:00:00.000Z')"))
c=db(); accepted("RFC3339 23:59:59.999 accepted", lambda: c.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder,created_at) VALUES('b','TRUSTED','/','2026-01-01T23:59:59.999Z')"))
rejected("unknown config namespace rejected", "namespace key/value schema", lambda: c.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder,config_snapshot) VALUES('b2','TRUSTED','/','{\"mystery\":1}')"))
rejected("wrong config value shape rejected", "namespace key/value schema", lambda: c.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder,config_snapshot) VALUES('b3','TRUSTED','/','{\"audio\":{\"sample_rate_hz\":\"48000\"}}')"))
rejected("experimental namespace requires enabled=true", "experimental namespace", lambda: c.execute("INSERT INTO batch(batch_id,workflow_mode,input_folder,config_snapshot) VALUES('b4','TRUSTED','/','{\"experimental\":{\"foo\":true}}')"))

# B19: Public API closure no longer accepts arbitrary ALLCAPS or object escape hatches.
api=json.loads((ROOT/'contracts/public_api.v1.json').read_text())
accepted("current Public API type closure valid", lambda: validate_public_api_type_aliases(api))
bad=deepcopy(api); bad['operations']['get_job']['returns']='TOTALLY_MISSING'
rejected("arbitrary ALLCAPS type token rejected", "undefined type", lambda: validate_public_api_type_aliases(bad))
bad=deepcopy(api); bad['types']['AsyncIterator']='object'
rejected("object escape hatch rejected", "undefined type object", lambda: validate_public_api_type_aliases(bad))

# B5 + B10/N4: selector fact and ref_kind are exact; RESOLVED -> CANCELLED is legal.
def resolved_decision_fixture(c: sqlite3.Connection, *, fact_key: str, fact_value: str, ref_kind: str) -> None:
    base(c); plan(c); activate(c); exec_success(c)
    c.execute("INSERT INTO checkpoint(checkpoint_id,job_id,plan_id,plan_node_id,execution_id,status) VALUES('cp','j1','p1','n1','e1','OPEN')")
    c.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('cb',?,'/cas/candidate',1)",(digest('e'),))
    c.execute("INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,producer_component,producer_execution_id,retention_class,retention_until) VALUES('ca','cb','audio','CANDIDATE','node','e1','candidate',?)",(FUTURE,))
    c.execute("INSERT INTO decision(decision_id,origin_job_id,batch_id,plan_node_id,decision_type,join_signature,join_signature_components,policy_signature,policy_signature_components,expires_at) VALUES('d','j1','b1','n1','SELECT','j','{}','p','{}',?)",(FUTURE,))
    c.execute("INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) VALUES('ca','DECISION','d','candidate')")
    c.execute("INSERT INTO decision_candidate(candidate_id,decision_id,selector_key,artifact_id) VALUES('dc','d','A','ca')")
    c.execute("UPDATE decision SET status='RESOLVED',resolution_action=?,resolver_type='HUMAN',resolved_at=? WHERE decision_id='d'",(json.dumps({"selector_key":"A"},separators=(",",":")),TS2))
    c.execute("INSERT INTO boundary_fact(fact_id,job_id,fact_key,value_json,source_decision_id) VALUES('f','j1',?,?, 'd')",(fact_key,json.dumps(fact_value)))
    c.execute("INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) VALUES('ca','CHECKPOINT','cp',?)",(ref_kind,))

c=db(); resolved_decision_fixture(c,fact_key='decision.d.selector',fact_value='A',ref_kind='cache')
rejected("Decision apply requires ref_kind selected", "transferred ownership", lambda: c.execute("UPDATE decision SET status='APPLIED',applied_at=? WHERE decision_id='d'",(TS3,)))
c=db(); resolved_decision_fixture(c,fact_key='decision.d.selector.wrong',fact_value='A',ref_kind='selected')
rejected("Decision apply requires exact selector BoundaryFact key", "Boundary fact", lambda: c.execute("UPDATE decision SET status='APPLIED',applied_at=? WHERE decision_id='d'",(TS3,)))
c=db(); resolved_decision_fixture(c,fact_key='decision.d.selector',fact_value='A',ref_kind='selected')
accepted("Decision apply accepts exact selector proof", lambda: c.execute("UPDATE decision SET status='APPLIED',applied_at=? WHERE decision_id='d'",(TS3,)))
c=db(); base(c); plan(c); activate(c); exec_success(c)
c.execute("INSERT INTO blob(blob_id,content_hash,path,size_bytes) VALUES('cb',?,'/cas/candidate',1)",(digest('e'),)); c.execute("INSERT INTO artifact(artifact_id,blob_id,artifact_type,artifact_role,producer_component,producer_execution_id,retention_class,retention_until) VALUES('ca','cb','audio','CANDIDATE','node','e1','candidate',?)",(FUTURE,)); c.execute("INSERT INTO decision(decision_id,origin_job_id,batch_id,plan_node_id,decision_type,join_signature,join_signature_components,policy_signature,policy_signature_components,expires_at) VALUES('d','j1','b1','n1','SELECT','j','{}','p','{}',?)",(FUTURE,)); c.execute("INSERT INTO artifact_reference(artifact_id,owner_type,owner_id,ref_kind) VALUES('ca','DECISION','d','candidate')"); c.execute("INSERT INTO decision_candidate(candidate_id,decision_id,selector_key,artifact_id) VALUES('dc','d','A','ca')"); c.execute("UPDATE decision SET status='RESOLVED',resolution_action=?,resolver_type='HUMAN',resolved_at=? WHERE decision_id='d'",(json.dumps({"selector_key":"A"},separators=(",",":")),TS2))
accepted("RESOLVED Decision may CANCEL", lambda: c.execute("UPDATE decision SET status='CANCELLED' WHERE decision_id='d'"))

# B15: expired rows recycle automatically instead of permanently occupying the resource key.
c=db(); base(c)
c.execute("INSERT INTO resource_lease(lease_id,resource_kind,resource_key,job_id,token,expires_at) VALUES('l1','CPU','0','j1','tok1',?)",(FUTURE,))
c.execute("UPDATE resource_lease SET expires_at='2000-01-01T00:00:00.000Z' WHERE lease_id='l1'")
accepted("expired ResourceLease row is recycled on next acquire", lambda: c.execute("INSERT INTO resource_lease(lease_id,resource_kind,resource_key,job_id,token,expires_at) VALUES('l2','CPU','0','j1','tok2',?)",(FUTURE,)))
accepted("expired lease row was removed", lambda: (_ for _ in ()).throw(AssertionError("expired lease was not recycled")) if c.execute("SELECT group_concat(lease_id) FROM resource_lease WHERE resource_kind='CPU' AND resource_key='0'").fetchone()[0] != 'l2' else True)
accepted("ResourceLease schema has recycler not permanent unique", lambda: (_ for _ in ()).throw(AssertionError("lease recycler missing")) if ("UNIQUE(resource_kind,resource_key)" in SCHEMA or "DELETE FROM resource_lease" not in SCHEMA) else True)

# N3/N5: package-contract schema exists and docs/contracts are mechanically aligned.
pcs=json.loads((ROOT/'schemas/package_contract.schema.json').read_text())
accepted("package-contract JSON Schema exists", lambda: (_ for _ in ()).throw(AssertionError("wrong schema")) if pcs.get('$schema')!='https://json-schema.org/draft/2020-12/schema' else True)
def package_alignment():
    for cp in (ROOT/'packages').glob('*/contract.json'):
        d=json.loads(cp.read_text()); md=cp.with_name('PACKAGE.md').read_text()
        for item in d['must_not']:
            if item not in md: raise AssertionError(f"{cp.parent.name}: missing must_not {item}")
accepted("PACKAGE.md includes contract must_not entries", package_alignment)

# B21/N6: independently execute every matrix state pair against the actual transition trigger SQL.
def independent_transition_matrix_execution():
    matrix=json.loads((ROOT/'contracts/transition_test_matrix.v1.json').read_text())
    source=db()
    executed=[]
    for machine in matrix['machines']:
        row=source.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",(machine['schema_trigger'],)).fetchone()
        if not row or not row[0]: raise AssertionError(f"missing trigger {machine['schema_trigger']}")
        trigger_sql=row[0]
        table=re.search(r"\bON\s+([A-Za-z_][A-Za-z0-9_]*)",trigger_sql,re.I).group(1)
        if machine['name']!=table: raise AssertionError(f"machine/table mismatch {machine['name']} != {table}")
        prefix=table.upper()
        for case in machine['cases']:
            expected_id=f"TM-{prefix}-{case['from']}-TO-{case['to']}"
            if case['test_id']!=expected_id: raise AssertionError(f"noncanonical test id {case['test_id']}")
            m=sqlite3.connect(':memory:'); field=machine['field']
            if table=='blob':
                m.execute("CREATE TABLE blob(blob_id TEXT,gc_state TEXT NOT NULL)")
                m.execute("CREATE TABLE artifact(artifact_id TEXT,blob_id TEXT)"); m.execute("CREATE TABLE artifact_reference(artifact_id TEXT)")
                m.execute("INSERT INTO blob(blob_id,gc_state) VALUES('b',?)",(case['from'],))
            else:
                m.execute(f"CREATE TABLE {table}({field} TEXT NOT NULL)")
                m.execute(f"INSERT INTO {table}({field}) VALUES(?)",(case['from'],))
            m.executescript(trigger_sql)
            try: m.execute(f"UPDATE {table} SET {field}=?",(case['to'],))
            except sqlite3.DatabaseError:
                if case['allowed']: raise AssertionError(f"allowed case rejected {case['test_id']}")
            else:
                if not case['allowed']: raise AssertionError(f"forbidden case accepted {case['test_id']}")
            executed.append(case['test_id'])
    if len(executed)!=166 or len(set(executed))!=166: raise AssertionError(f"expected 166 executed transition IDs, got {len(executed)}/{len(set(executed))}")
accepted("B21/N6 independently executes all 166 transition matrix cases", independent_transition_matrix_execution)

# N7: expiration policy is explicitly scheduler-driven (not wall-clock SQL magic).
def expiry_doc():
    t=(ROOT/'docs/en/06-decisions.md').read_text()+ (ROOT/'docs/zh-CN/06-decisions.md').read_text()
    if 'Scheduler' not in t or 'expires_at' not in t: raise AssertionError('expiry scheduler contract missing')
accepted("Decision EXPIRED scheduler contract documented", expiry_doc)

passed=sum(ok for _,ok,_ in results)
print(f"PASS {passed}/{len(results)}")
for n,ok,d in results: print(f"{'PASS' if ok else 'FAIL':4} | {n} | {d}")
raise SystemExit(0 if passed==len(results) else 1)
