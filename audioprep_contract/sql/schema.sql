PRAGMA foreign_keys = ON;
PRAGMA recursive_triggers = ON;

-- AudioPrep planning schema R2.1.5.07
-- SQLite >= 3.38 is required for JSON1 and modern UPSERT behavior.

CREATE TABLE schema_meta (
    schema_key TEXT PRIMARY KEY,
    schema_value TEXT NOT NULL
);
INSERT INTO schema_meta(schema_key, schema_value) VALUES
('design_revision', 'R2.1.5.07'),
('schema_version', '2.1.5.07'),
('manifest_version', '1'),
('public_api_version', '1');

CREATE TABLE batch (
    batch_id TEXT PRIMARY KEY,
    workflow_mode TEXT NOT NULL CHECK (workflow_mode IN ('TRUSTED','REVIEW')),
    input_folder TEXT NOT NULL,
    config_snapshot TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(config_snapshot) AND json_type(config_snapshot)='object'),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK (length(created_at)=24 AND created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(created_at,12,2) BETWEEN '00' AND '23' AND julianday(created_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at)=created_at)
);

CREATE TABLE job (
    job_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES batch(batch_id) ON DELETE RESTRICT,
    source_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'CREATED'
        CHECK (status IN ('CREATED','QUEUED','RUNNING','WAITING_DECISION','SUCCEEDED','FAILED','STOPPED')),
    error_code TEXT CHECK (error_code IS NULL OR error_code IN (
        'SOURCE_NOT_FOUND','SOURCE_CHANGED','SOURCE_UNREADABLE','UNSUPPORTED_MEDIA',
        'PLAN_INVALID','PLAN_STALE','RESOURCE_UNAVAILABLE','NODE_TIMEOUT',
        'NODE_CRASH','NODE_OUTPUT_INVALID','DECISION_EXPIRED','DECISION_INVALID',
        'DELIVERY_FAILED','DISK_FULL','PERMISSION_DENIED','CANCELLED',
        'INTERNAL_ERROR','UNKNOWN_ERROR')),
    error_type TEXT CHECK (error_type IS NULL OR error_type IN ('USER','SYSTEM','POLICY','DATA')),
    source_size_bytes INTEGER CHECK (source_size_bytes IS NULL OR source_size_bytes >= 0),
    source_mtime_ns INTEGER CHECK (source_mtime_ns IS NULL OR source_mtime_ns >= 0),
    source_content_hash TEXT CHECK (
        source_content_hash IS NULL OR
        (length(source_content_hash)=71 AND substr(source_content_hash,1,7)='sha256:'
         AND substr(source_content_hash,8) NOT GLOB '*[^0-9a-f]*')),
    source_artifact_id TEXT REFERENCES artifact(artifact_id) DEFERRABLE INITIALLY DEFERRED,
    source_identity_frozen_at TEXT CHECK (source_identity_frozen_at IS NULL OR (length(source_identity_frozen_at)=24 AND source_identity_frozen_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(source_identity_frozen_at,12,2) BETWEEN '00' AND '23' AND julianday(source_identity_frozen_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',source_identity_frozen_at)=source_identity_frozen_at)),
    current_plan_id TEXT REFERENCES pipeline_plan(plan_id) DEFERRABLE INITIALLY DEFERRED,
    dispatch_generation INTEGER NOT NULL DEFAULT 0 CHECK (dispatch_generation >= 0),
    active_run_token TEXT,
    lease_expires_at TEXT CHECK (lease_expires_at IS NULL OR (length(lease_expires_at)=24 AND lease_expires_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(lease_expires_at,12,2) BETWEEN '00' AND '23' AND julianday(lease_expires_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',lease_expires_at)=lease_expires_at)),
    worker_id TEXT,
    started_at TEXT CHECK (started_at IS NULL OR (length(started_at)=24 AND started_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(started_at,12,2) BETWEEN '00' AND '23' AND julianday(started_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',started_at)=started_at)),
    finished_at TEXT CHECK (finished_at IS NULL OR (length(finished_at)=24 AND finished_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(finished_at,12,2) BETWEEN '00' AND '23' AND julianday(finished_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',finished_at)=finished_at)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK (length(created_at)=24 AND created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(created_at,12,2) BETWEEN '00' AND '23' AND julianday(created_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at)=created_at),
    CHECK ((source_identity_frozen_at IS NULL AND source_size_bytes IS NULL
            AND source_mtime_ns IS NULL AND source_content_hash IS NULL
            AND source_artifact_id IS NULL)
        OR (source_identity_frozen_at IS NOT NULL AND source_size_bytes IS NOT NULL
            AND source_mtime_ns IS NOT NULL AND source_content_hash IS NOT NULL
            AND source_artifact_id IS NOT NULL)),
    CHECK ((status='RUNNING' AND dispatch_generation>0 AND active_run_token IS NOT NULL
            AND lease_expires_at IS NOT NULL AND worker_id IS NOT NULL
            AND source_identity_frozen_at IS NOT NULL AND current_plan_id IS NOT NULL
            AND started_at IS NOT NULL AND finished_at IS NULL)
        OR (status<>'RUNNING' AND active_run_token IS NULL
            AND lease_expires_at IS NULL AND worker_id IS NULL)),
    CHECK ((status IN ('SUCCEEDED','FAILED','STOPPED') AND finished_at IS NOT NULL)
        OR (status NOT IN ('SUCCEEDED','FAILED','STOPPED') AND finished_at IS NULL)),
    CHECK ((status='FAILED' AND error_code IS NOT NULL AND error_type IS NOT NULL)
        OR (status<>'FAILED' AND error_code IS NULL AND error_type IS NULL))
);

CREATE TABLE pipeline_plan (
    plan_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES job(job_id) ON DELETE RESTRICT,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    parent_plan_id TEXT REFERENCES pipeline_plan(plan_id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','SEALED','SUPERSEDED')),
    planner_version TEXT NOT NULL,
    plan_fingerprint TEXT,
    sealed_at TEXT CHECK (sealed_at IS NULL OR (length(sealed_at)=24 AND sealed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(sealed_at,12,2) BETWEEN '00' AND '23' AND julianday(sealed_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',sealed_at)=sealed_at)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK (length(created_at)=24 AND created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(created_at,12,2) BETWEEN '00' AND '23' AND julianday(created_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at)=created_at),
    UNIQUE(job_id, revision),
    CHECK ((status='DRAFT' AND plan_fingerprint IS NULL AND sealed_at IS NULL)
        OR (status IN ('SEALED','SUPERSEDED') AND plan_fingerprint IS NOT NULL AND sealed_at IS NOT NULL))
);

CREATE TABLE pipeline_plan_node (
    plan_node_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES pipeline_plan(plan_id) ON DELETE CASCADE,
    node_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    stage TEXT NOT NULL,
    node_type TEXT NOT NULL,
    implementation_id TEXT NOT NULL,
    implementation_version TEXT NOT NULL,
    implementation_fingerprint TEXT NOT NULL,
    hard_timeout_s INTEGER NOT NULL CHECK (hard_timeout_s > 0),
    activation_mode TEXT NOT NULL DEFAULT 'ALWAYS' CHECK (activation_mode IN ('ALWAYS','IF_FACT','NOOP')),
    activation_predicate TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(activation_predicate)
          AND ((activation_mode='IF_FACT'
                AND json_type(activation_predicate)='object'
                AND json_extract(activation_predicate,'$.schema')='audioprep.predicate.v1'
                AND json_type(activation_predicate,'$.expr')='object')
            OR (activation_mode IN ('ALWAYS','NOOP') AND activation_predicate='{}'))),
    input_roles TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(input_roles) AND json_type(input_roles)='array'),
    output_roles TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(output_roles) AND json_type(output_roles)='array'),
    input_contracts TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(input_contracts) AND json_type(input_contracts)='object'),
    output_contracts TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(output_contracts) AND json_type(output_contracts)='object'),
    resource_requirements TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(resource_requirements) AND json_type(resource_requirements)='object'),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK (length(created_at)=24 AND created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(created_at,12,2) BETWEEN '00' AND '23' AND julianday(created_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at)=created_at),
    UNIQUE(plan_id,node_key),
    UNIQUE(plan_id,ordinal),
    UNIQUE(plan_id,plan_node_id)
);

CREATE TABLE pipeline_plan_edge (
    plan_id TEXT NOT NULL REFERENCES pipeline_plan(plan_id) ON DELETE CASCADE,
    from_plan_node_id TEXT NOT NULL,
    to_plan_node_id TEXT NOT NULL,
    output_name TEXT NOT NULL,
    input_name TEXT NOT NULL,
    PRIMARY KEY(plan_id,from_plan_node_id,to_plan_node_id,output_name,input_name),
    FOREIGN KEY(plan_id,from_plan_node_id) REFERENCES pipeline_plan_node(plan_id,plan_node_id) ON DELETE CASCADE,
    FOREIGN KEY(plan_id,to_plan_node_id) REFERENCES pipeline_plan_node(plan_id,plan_node_id) ON DELETE CASCADE,
    CHECK (from_plan_node_id <> to_plan_node_id)
);

CREATE TABLE pipeline_plan_validation (
    plan_id TEXT PRIMARY KEY REFERENCES pipeline_plan(plan_id) ON DELETE CASCADE,
    plan_fingerprint TEXT NOT NULL,
    validator_version TEXT NOT NULL,
    validation_profile TEXT NOT NULL DEFAULT 'STRUCTURAL_MEDIA_PREDICATE_V2',
    report_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(report_json)),
    validated_at TEXT NOT NULL CHECK (length(validated_at)=24 AND validated_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(validated_at,12,2) BETWEEN '00' AND '23' AND julianday(validated_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',validated_at)=validated_at)
);

CREATE TABLE node_execution (
    execution_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES job(job_id) ON DELETE RESTRICT,
    plan_id TEXT NOT NULL REFERENCES pipeline_plan(plan_id) ON DELETE RESTRICT,
    plan_node_id TEXT NOT NULL REFERENCES pipeline_plan_node(plan_node_id) ON DELETE RESTRICT,
    execution_seq INTEGER NOT NULL CHECK (execution_seq > 0),
    dispatch_generation INTEGER NOT NULL CHECK (dispatch_generation > 0),
    run_token TEXT,
    worker_id TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','DISPATCHED','RUNNING','SUCCEEDED','FAILED','ABORTED','SKIPPED')),
    implementation_fingerprint TEXT NOT NULL,
    hard_deadline_at TEXT CHECK (hard_deadline_at IS NULL OR (length(hard_deadline_at)=24 AND hard_deadline_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(hard_deadline_at,12,2) BETWEEN '00' AND '23' AND julianday(hard_deadline_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',hard_deadline_at)=hard_deadline_at)),
    started_at TEXT CHECK (started_at IS NULL OR (length(started_at)=24 AND started_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(started_at,12,2) BETWEEN '00' AND '23' AND julianday(started_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',started_at)=started_at)),
    completed_at TEXT CHECK (completed_at IS NULL OR (length(completed_at)=24 AND completed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(completed_at,12,2) BETWEEN '00' AND '23' AND julianday(completed_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',completed_at)=completed_at)),
    error_code TEXT CHECK (error_code IS NULL OR error_code IN (
        'SOURCE_NOT_FOUND','SOURCE_CHANGED','SOURCE_UNREADABLE','UNSUPPORTED_MEDIA',
        'PLAN_INVALID','PLAN_STALE','RESOURCE_UNAVAILABLE','NODE_TIMEOUT',
        'NODE_CRASH','NODE_OUTPUT_INVALID','DECISION_EXPIRED','DECISION_INVALID',
        'DELIVERY_FAILED','DISK_FULL','PERMISSION_DENIED','CANCELLED',
        'INTERNAL_ERROR','UNKNOWN_ERROR')),
    error_detail TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK (length(created_at)=24 AND created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(created_at,12,2) BETWEEN '00' AND '23' AND julianday(created_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at)=created_at),
    UNIQUE(job_id,plan_node_id,execution_seq),
    CHECK (status<>'RUNNING' OR (hard_deadline_at IS NOT NULL AND started_at IS NOT NULL
           AND run_token IS NOT NULL AND worker_id IS NOT NULL)),
    CHECK ((status IN ('SUCCEEDED','FAILED','ABORTED','SKIPPED') AND completed_at IS NOT NULL)
        OR (status NOT IN ('SUCCEEDED','FAILED','ABORTED','SKIPPED') AND completed_at IS NULL)),
    CHECK ((status='FAILED' AND error_code IS NOT NULL)
        OR (status<>'FAILED' AND error_code IS NULL))
);

CREATE TABLE checkpoint (
    checkpoint_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES job(job_id) ON DELETE RESTRICT,
    plan_id TEXT NOT NULL REFERENCES pipeline_plan(plan_id) ON DELETE RESTRICT,
    plan_node_id TEXT NOT NULL REFERENCES pipeline_plan_node(plan_node_id) ON DELETE RESTRICT,
    execution_id TEXT NOT NULL REFERENCES node_execution(execution_id) ON DELETE RESTRICT,
    status TEXT NOT NULL CHECK (status IN ('OPEN','COMMITTED','RELEASED')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK (length(created_at)=24 AND created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(created_at,12,2) BETWEEN '00' AND '23' AND julianday(created_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at)=created_at)
);

CREATE TABLE blob (
    blob_id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL UNIQUE
        CHECK (length(content_hash)=71 AND substr(content_hash,1,7)='sha256:'
           AND substr(content_hash,8) NOT GLOB '*[^0-9a-f]*'),
    path TEXT NOT NULL UNIQUE,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    media_type TEXT,
    gc_state TEXT NOT NULL DEFAULT 'LIVE' CHECK (gc_state IN ('LIVE','TOMBSTONED','PURGING')),
    strong_refcount INTEGER NOT NULL DEFAULT 0 CHECK (strong_refcount >= 0),
    tombstoned_at TEXT CHECK (tombstoned_at IS NULL OR (length(tombstoned_at)=24 AND tombstoned_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(tombstoned_at,12,2) BETWEEN '00' AND '23' AND julianday(tombstoned_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',tombstoned_at)=tombstoned_at)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK (length(created_at)=24 AND created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(created_at,12,2) BETWEEN '00' AND '23' AND julianday(created_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at)=created_at),
    CHECK ((gc_state='LIVE' AND tombstoned_at IS NULL)
        OR (gc_state IN ('TOMBSTONED','PURGING') AND tombstoned_at IS NOT NULL))
);

CREATE TABLE artifact (
    artifact_id TEXT PRIMARY KEY,
    blob_id TEXT NOT NULL REFERENCES blob(blob_id) ON DELETE RESTRICT,
    artifact_type TEXT NOT NULL CHECK (artifact_type IN ('audio','timeline','metrics','metadata','candidate')),
    artifact_role TEXT NOT NULL CHECK (artifact_role IN ('SOURCE_MEDIA','QUALITY_MASTER','ANALYSIS_COPY','PIPELINE_AUDIO','ASR_SEGMENT','CANDIDATE','CHECKPOINT','CACHE','TIMELINE','METRICS','METADATA','DELIVERY_SEGMENT')),
    producer_component TEXT NOT NULL,
    producer_execution_id TEXT REFERENCES node_execution(execution_id) ON DELETE RESTRICT,
    output_name TEXT,
    ordinal INTEGER NOT NULL DEFAULT 0 CHECK (ordinal >= 0),
    retention_class TEXT NOT NULL,
    retention_until TEXT NOT NULL CHECK (length(retention_until)=24 AND retention_until GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(retention_until,12,2) BETWEEN '00' AND '23' AND julianday(retention_until) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',retention_until)=retention_until),
    pinned INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0,1)),
    strong_refcount INTEGER NOT NULL DEFAULT 0 CHECK (strong_refcount >= 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK (length(created_at)=24 AND created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(created_at,12,2) BETWEEN '00' AND '23' AND julianday(created_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at)=created_at),
    UNIQUE(producer_execution_id,output_name,ordinal)
);

CREATE TABLE artifact_reference (
    artifact_id TEXT NOT NULL REFERENCES artifact(artifact_id) ON DELETE RESTRICT,
    owner_type TEXT NOT NULL CHECK (owner_type IN ('JOB','CHECKPOINT','DECISION','DELIVERABLE')),
    owner_id TEXT NOT NULL,
    ref_kind TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK (length(created_at)=24 AND created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(created_at,12,2) BETWEEN '00' AND '23' AND julianday(created_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at)=created_at),
    PRIMARY KEY(artifact_id,owner_type,owner_id,ref_kind)
);

CREATE TABLE execution_cache_output (
    job_id TEXT NOT NULL REFERENCES job(job_id) ON DELETE CASCADE,
    execution_key TEXT NOT NULL,
    output_name TEXT NOT NULL,
    blob_id TEXT NOT NULL REFERENCES blob(blob_id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL CHECK (artifact_type IN ('audio','timeline','metrics','metadata','candidate')),
    artifact_role TEXT NOT NULL CHECK (artifact_role IN ('SOURCE_MEDIA','QUALITY_MASTER','ANALYSIS_COPY','PIPELINE_AUDIO','ASR_SEGMENT','CANDIDATE','CHECKPOINT','CACHE','TIMELINE','METRICS','METADATA','DELIVERY_SEGMENT')),
    retention_class TEXT NOT NULL,
    PRIMARY KEY(job_id,execution_key,output_name)
);

CREATE TABLE decision (
    decision_id TEXT PRIMARY KEY,
    origin_job_id TEXT NOT NULL REFERENCES job(job_id) ON DELETE RESTRICT,
    batch_id TEXT NOT NULL REFERENCES batch(batch_id) ON DELETE RESTRICT,
    plan_node_id TEXT NOT NULL REFERENCES pipeline_plan_node(plan_node_id) ON DELETE RESTRICT,
    decision_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','RESOLVED','APPLIED','EXPIRED','CANCELLED')),
    join_signature TEXT NOT NULL,
    join_signature_components TEXT NOT NULL CHECK (json_valid(join_signature_components)),
    policy_signature TEXT NOT NULL,
    policy_signature_components TEXT NOT NULL CHECK (json_valid(policy_signature_components)),
    resolution_action TEXT CHECK (resolution_action IS NULL OR
        (json_valid(resolution_action)
         AND json_type(resolution_action)='object'
         AND json_type(resolution_action,'$.selector_key')='text'
         AND json_remove(resolution_action,'$.selector_key')='{}')),
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
    resolver_type TEXT CHECK (resolver_type IS NULL OR resolver_type IN ('POLICY','HUMAN')),
    resolved_at TEXT CHECK (resolved_at IS NULL OR (length(resolved_at)=24 AND resolved_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(resolved_at,12,2) BETWEEN '00' AND '23' AND julianday(resolved_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',resolved_at)=resolved_at)),
    expires_at TEXT NOT NULL CHECK (length(expires_at)=24 AND expires_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(expires_at,12,2) BETWEEN '00' AND '23' AND julianday(expires_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',expires_at)=expires_at),
    applied_at TEXT CHECK (applied_at IS NULL OR (length(applied_at)=24 AND applied_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(applied_at,12,2) BETWEEN '00' AND '23' AND julianday(applied_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',applied_at)=applied_at)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK (length(created_at)=24 AND created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(created_at,12,2) BETWEEN '00' AND '23' AND julianday(created_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at)=created_at),
    CHECK ((status='PENDING' AND resolution_action IS NULL AND confidence IS NULL
            AND resolver_type IS NULL AND resolved_at IS NULL AND applied_at IS NULL)
        OR (status='RESOLVED' AND resolution_action IS NOT NULL
            AND resolver_type IS NOT NULL AND resolved_at IS NOT NULL AND applied_at IS NULL)
        OR (status='APPLIED' AND resolution_action IS NOT NULL
            AND resolver_type IS NOT NULL AND resolved_at IS NOT NULL AND applied_at IS NOT NULL)
        OR (status IN ('EXPIRED','CANCELLED') AND applied_at IS NULL))
);

CREATE TABLE decision_candidate (
    candidate_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES decision(decision_id) ON DELETE RESTRICT,
    selector_key TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    score REAL,
    metrics_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metrics_json) AND json_type(metrics_json)='object'),
    UNIQUE(decision_id,selector_key),
    UNIQUE(decision_id,artifact_id)
);

CREATE TABLE decision_job (
    decision_id TEXT NOT NULL REFERENCES decision(decision_id) ON DELETE RESTRICT,
    job_id TEXT NOT NULL REFERENCES job(job_id) ON DELETE RESTRICT,
    execution_id TEXT REFERENCES node_execution(execution_id) ON DELETE RESTRICT,
    PRIMARY KEY(decision_id,job_id)
);

CREATE TABLE boundary_fact (
    fact_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES job(job_id) ON DELETE RESTRICT,
    fact_key TEXT NOT NULL,
    value_json TEXT NOT NULL CHECK (json_valid(value_json)
        AND json_type(value_json) IN ('text','integer','real','true','false','null')),
    source_decision_id TEXT REFERENCES decision(decision_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK (length(created_at)=24 AND created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(created_at,12,2) BETWEEN '00' AND '23' AND julianday(created_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at)=created_at),
    UNIQUE(job_id,fact_key)
);

CREATE TABLE timeline_mapping (
    job_id TEXT NOT NULL REFERENCES job(job_id) ON DELETE RESTRICT,
    segment_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    mapping_kind TEXT NOT NULL CHECK (mapping_kind IN ('IDENTITY_SLICE','PIECEWISE')),
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','SEALED')),
    src_timebase_num INTEGER NOT NULL DEFAULT 1 CHECK (src_timebase_num > 0),
    src_timebase_den INTEGER NOT NULL CHECK (src_timebase_den > 0),
    dst_timebase_num INTEGER NOT NULL DEFAULT 1 CHECK (dst_timebase_num > 0),
    dst_timebase_den INTEGER NOT NULL CHECK (dst_timebase_den > 0),
    dst_end_tick INTEGER NOT NULL CHECK (dst_end_tick > 0),
    sealed_at TEXT CHECK (sealed_at IS NULL OR (length(sealed_at)=24 AND sealed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(sealed_at,12,2) BETWEEN '00' AND '23' AND julianday(sealed_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',sealed_at)=sealed_at)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK (length(created_at)=24 AND created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(created_at,12,2) BETWEEN '00' AND '23' AND julianday(created_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at)=created_at),
    PRIMARY KEY(job_id,segment_id),
    UNIQUE(job_id,segment_id,artifact_id),
    CHECK ((status='DRAFT' AND sealed_at IS NULL) OR (status='SEALED' AND sealed_at IS NOT NULL))
);

CREATE TABLE timeline_span (
    job_id TEXT NOT NULL,
    segment_id TEXT NOT NULL,
    span_index INTEGER NOT NULL CHECK (span_index >= 0),
    op TEXT NOT NULL CHECK (op IN ('MAP','SILENCE')),
    src_start_tick INTEGER,
    src_end_tick INTEGER,
    dst_start_tick INTEGER NOT NULL CHECK (dst_start_tick >= 0),
    dst_end_tick INTEGER NOT NULL CHECK (dst_end_tick > dst_start_tick),
    PRIMARY KEY(job_id,segment_id,span_index),
    FOREIGN KEY(job_id,segment_id) REFERENCES timeline_mapping(job_id,segment_id) ON DELETE CASCADE,
    CHECK ((op='MAP' AND src_start_tick IS NOT NULL AND src_end_tick IS NOT NULL
            AND src_start_tick >= 0 AND src_end_tick > src_start_tick)
        OR (op='SILENCE' AND src_start_tick IS NULL AND src_end_tick IS NULL))
);

CREATE TABLE deliverable (
    deliverable_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES job(job_id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'STAGING' CHECK (status IN ('STAGING','PUBLISHED','DELETED','FAILED')),
    materialization_mode TEXT NOT NULL DEFAULT 'COPY' CHECK (materialization_mode='COPY'),
    staging_path TEXT NOT NULL,
    published_path TEXT,
    manifest_hash TEXT CHECK (manifest_hash IS NULL OR
        (length(manifest_hash)=71 AND substr(manifest_hash,1,7)='sha256:'
         AND substr(manifest_hash,8) NOT GLOB '*[^0-9a-f]*')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK (length(created_at)=24 AND created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(created_at,12,2) BETWEEN '00' AND '23' AND julianday(created_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at)=created_at),
    published_at TEXT CHECK (published_at IS NULL OR (length(published_at)=24 AND published_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(published_at,12,2) BETWEEN '00' AND '23' AND julianday(published_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',published_at)=published_at)),
    closed_at TEXT CHECK (closed_at IS NULL OR (length(closed_at)=24 AND closed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(closed_at,12,2) BETWEEN '00' AND '23' AND julianday(closed_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',closed_at)=closed_at)),
    CHECK ((status='STAGING' AND published_path IS NULL AND manifest_hash IS NULL
            AND published_at IS NULL AND closed_at IS NULL)
        OR (status='PUBLISHED' AND published_path IS NOT NULL AND manifest_hash IS NOT NULL
            AND published_at IS NOT NULL AND closed_at IS NULL)
        OR (status='DELETED' AND published_path IS NOT NULL AND manifest_hash IS NOT NULL
            AND published_at IS NOT NULL AND closed_at IS NOT NULL)
        OR (status='FAILED' AND published_path IS NULL AND manifest_hash IS NULL
            AND published_at IS NULL AND closed_at IS NOT NULL))
);

CREATE TABLE deliverable_segment (
    deliverable_id TEXT NOT NULL REFERENCES deliverable(deliverable_id) ON DELETE RESTRICT,
    segment_id TEXT NOT NULL CHECK (length(segment_id) BETWEEN 1 AND 128
        AND substr(segment_id,1,1) GLOB '[A-Za-z0-9]'
        AND segment_id NOT GLOB '*[^A-Za-z0-9._-]*'),
    artifact_id TEXT NOT NULL,
    relative_path TEXT NOT NULL CHECK (relative_path GLOB 'segments/*.wav'
        AND length(relative_path) BETWEEN 14 AND 141
        AND instr(relative_path,'\')=0
        AND substr(relative_path,1,1)<>'/' AND instr(substr(relative_path,10),'/')=0
        AND substr(relative_path,10,1) GLOB '[A-Za-z0-9]'
        AND substr(relative_path,10,length(relative_path)-13) NOT GLOB '*[^A-Za-z0-9._-]*'),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    PRIMARY KEY(deliverable_id,segment_id),
    UNIQUE(deliverable_id,ordinal),
    UNIQUE(deliverable_id,relative_path),
    UNIQUE(deliverable_id,artifact_id)
);

CREATE TABLE event (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES job(job_id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(payload_json) AND json_type(payload_json)='object'),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK (length(created_at)=24 AND created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(created_at,12,2) BETWEEN '00' AND '23' AND julianday(created_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at)=created_at)
);

CREATE TABLE resource_lease (
    lease_id TEXT PRIMARY KEY,
    resource_kind TEXT NOT NULL CHECK (resource_kind IN ('CPU','GPU','IO','MODEL')),
    resource_key TEXT NOT NULL,
    job_id TEXT NOT NULL REFERENCES job(job_id) ON DELETE RESTRICT,
    execution_id TEXT REFERENCES node_execution(execution_id) ON DELETE RESTRICT,
    token TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL CHECK (length(expires_at)=24 AND expires_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(expires_at,12,2) BETWEEN '00' AND '23' AND julianday(expires_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',expires_at)=expires_at),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK (length(created_at)=24 AND created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9]Z' AND substr(created_at,12,2) BETWEEN '00' AND '23' AND julianday(created_at) IS NOT NULL AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at)=created_at)
);

-- -------------------------------------------------------------------------
-- Release metadata is immutable after bootstrap.
-- -------------------------------------------------------------------------
CREATE TRIGGER schema_meta_insert_guard
BEFORE INSERT ON schema_meta
BEGIN
    SELECT RAISE(ABORT,'schema_meta is read-only after schema bootstrap');
END;
CREATE TRIGGER schema_meta_update_guard
BEFORE UPDATE ON schema_meta
BEGIN
    SELECT RAISE(ABORT,'schema_meta is read-only');
END;
CREATE TRIGGER schema_meta_delete_guard
BEFORE DELETE ON schema_meta
BEGIN
    SELECT RAISE(ABORT,'schema_meta is read-only');
END;

-- -------------------------------------------------------------------------
-- Immutable batch configuration snapshot.
-- -------------------------------------------------------------------------
CREATE TRIGGER batch_config_snapshot_insert_guard
BEFORE INSERT ON batch
WHEN EXISTS (
        SELECT 1 FROM json_each(NEW.config_snapshot)
        WHERE key NOT IN ('audio','pipeline','review','delivery','resources','cache','capabilities','experimental')
           OR (key<>'experimental' AND json_type(value)<>'object'))
   OR EXISTS (
        SELECT 1 FROM json_tree(NEW.config_snapshot)
        WHERE key IS NOT NULL AND (
            lower(key) IN ('token','access_token','auth_token','hf_token','review_token','api_key','apikey',
                           'password','secret','client_secret','authorization','credential','credentials')
            OR lower(key) LIKE '%_token' OR lower(key) LIKE '%_secret'
            OR lower(key) LIKE '%_password' OR lower(key) LIKE '%_api_key'
            OR lower(key) LIKE '%_credential'))
   OR EXISTS (SELECT 1 FROM json_each(NEW.config_snapshot,'$.audio')
              WHERE key NOT IN ('sample_rate_hz','channels','sample_format','loudness_target_lufs','true_peak_dbfs')
                 OR (key='sample_rate_hz' AND (type<>'integer' OR value<8000))
                 OR (key='channels' AND (type<>'integer' OR value<1))
                 OR (key='sample_format' AND (type<>'text' OR length(value)=0))
                 OR (key IN ('loudness_target_lufs','true_peak_dbfs') AND type NOT IN ('integer','real')))
   OR EXISTS (SELECT 1 FROM json_each(NEW.config_snapshot,'$.pipeline')
              WHERE key NOT IN ('planner_version','hard_timeout_s')
                 OR (key='planner_version' AND (type<>'text' OR length(value)=0))
                 OR (key='hard_timeout_s' AND (type<>'integer' OR value<=0)))
   OR EXISTS (SELECT 1 FROM json_each(NEW.config_snapshot,'$.review')
              WHERE key NOT IN ('enabled','adapter','bind_host','audition_format','policy_resolution')
                 OR (key IN ('enabled','policy_resolution') AND type NOT IN ('true','false'))
                 OR (key IN ('adapter','bind_host','audition_format') AND (type<>'text' OR length(value)=0)))
   OR EXISTS (SELECT 1 FROM json_each(NEW.config_snapshot,'$.delivery')
              WHERE key NOT IN ('output_root','naming','overwrite')
                 OR (key IN ('output_root','naming') AND (type<>'text' OR length(value)=0))
                 OR (key='overwrite' AND type NOT IN ('true','false')))
   OR EXISTS (SELECT 1 FROM json_each(NEW.config_snapshot,'$.resources')
              WHERE key NOT IN ('cpu_workers','gpu','model_cache')
                 OR (key='cpu_workers' AND (type<>'integer' OR value<1))
                 OR (key='gpu' AND type NOT IN ('true','false'))
                 OR (key='model_cache' AND (type<>'text' OR length(value)=0)))
   OR EXISTS (SELECT 1 FROM json_each(NEW.config_snapshot,'$.cache')
              WHERE key NOT IN ('enabled','retention_days','max_bytes')
                 OR (key='enabled' AND type NOT IN ('true','false'))
                 OR (key IN ('retention_days','max_bytes') AND (type<>'integer' OR value<0)))
   OR EXISTS (SELECT 1 FROM json_each(NEW.config_snapshot,'$.capabilities')
              WHERE key NOT IN ('gpu','review') OR type NOT IN ('true','false'))
   OR (json_type(NEW.config_snapshot,'$.experimental') IS NOT NULL AND (
        json_type(NEW.config_snapshot,'$.experimental')<>'object'
        OR COALESCE(json_type(NEW.config_snapshot,'$.experimental.enabled'),'missing')<>'true'))
BEGIN
    SELECT RAISE(ABORT,'Batch config snapshot violates namespace key/value schema, contains a persisted secret, or has disabled experimental namespace');
END;

CREATE TRIGGER batch_core_immutable
BEFORE UPDATE OF batch_id,workflow_mode,input_folder,config_snapshot,created_at ON batch
BEGIN
    SELECT RAISE(ABORT,'Batch identity and resolved configuration snapshot are immutable');
END;

-- -------------------------------------------------------------------------
-- Immutable CAS and logical artifact identity.
-- -------------------------------------------------------------------------
CREATE TRIGGER blob_core_identity_immutable
BEFORE UPDATE OF blob_id,content_hash,path,size_bytes ON blob
BEGIN
    SELECT RAISE(ABORT,'blob CAS identity is immutable');
END;

CREATE TRIGGER blob_gc_transition_guard
BEFORE UPDATE OF gc_state ON blob
WHEN NEW.gc_state<>OLD.gc_state
BEGIN
    SELECT CASE WHEN NOT (
        (OLD.gc_state='LIVE' AND NEW.gc_state='TOMBSTONED') OR
        (OLD.gc_state='TOMBSTONED' AND NEW.gc_state='PURGING')
    ) THEN RAISE(ABORT,'illegal Blob GC transition; required LIVE -> TOMBSTONED -> PURGING') END;
    SELECT CASE WHEN NEW.gc_state IN ('TOMBSTONED','PURGING') AND EXISTS (
        SELECT 1 FROM artifact a
        JOIN artifact_reference r ON r.artifact_id=a.artifact_id
        WHERE a.blob_id=OLD.blob_id
    ) THEN RAISE(ABORT,'Blob with strong ArtifactReference cannot enter GC') END;
END;

CREATE TRIGGER artifact_core_identity_immutable
BEFORE UPDATE OF artifact_id,blob_id,artifact_type,artifact_role,producer_component,
                 producer_execution_id,output_name,ordinal ON artifact
BEGIN
    SELECT RAISE(ABORT,'artifact logical identity is immutable');
END;

CREATE TRIGGER blob_strong_refcount_insert_guard
BEFORE INSERT ON blob
WHEN NEW.strong_refcount<>0
BEGIN
    SELECT RAISE(ABORT,'Blob strong_refcount is derived from ArtifactReference');
END;

CREATE TRIGGER artifact_strong_refcount_insert_guard
BEFORE INSERT ON artifact
WHEN NEW.strong_refcount<>0
BEGIN
    SELECT RAISE(ABORT,'Artifact strong_refcount is derived from ArtifactReference');
END;

CREATE TRIGGER artifact_strong_refcount_derived_guard
BEFORE UPDATE OF strong_refcount ON artifact
WHEN NEW.strong_refcount<>(
    SELECT COUNT(*) FROM artifact_reference r WHERE r.artifact_id=OLD.artifact_id)
BEGIN
    SELECT RAISE(ABORT,'Artifact strong_refcount is derived from ArtifactReference');
END;

CREATE TRIGGER blob_strong_refcount_derived_guard
BEFORE UPDATE OF strong_refcount ON blob
WHEN NEW.strong_refcount<>(
    SELECT COUNT(*)
      FROM artifact a JOIN artifact_reference r ON r.artifact_id=a.artifact_id
     WHERE a.blob_id=OLD.blob_id)
BEGIN
    SELECT RAISE(ABORT,'Blob strong_refcount is derived from ArtifactReference');
END;

CREATE TRIGGER blob_delete_guard
BEFORE DELETE ON blob
WHEN OLD.strong_refcount > 0
  OR EXISTS (SELECT 1 FROM artifact a WHERE a.blob_id=OLD.blob_id)
BEGIN
    SELECT RAISE(ABORT,'blob is still owned or retained');
END;

CREATE TRIGGER artifact_delete_guard
BEFORE DELETE ON artifact
WHEN OLD.strong_refcount > 0 OR OLD.pinned=1
  OR OLD.retention_until > strftime('%Y-%m-%dT%H:%M:%fZ','now')
BEGIN
    SELECT RAISE(ABORT,'logical artifact is still owned or retained');
END;

-- -------------------------------------------------------------------------
-- Plan lifecycle and immutable seal.
-- -------------------------------------------------------------------------
CREATE TRIGGER pipeline_plan_insert_draft_only
BEFORE INSERT ON pipeline_plan
WHEN NEW.status <> 'DRAFT' OR NEW.plan_fingerprint IS NOT NULL OR NEW.sealed_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT,'pipeline plan must be inserted as unsealed DRAFT');
END;

CREATE TRIGGER pipeline_plan_job_liveness_insert
BEFORE INSERT ON pipeline_plan
WHEN COALESCE((SELECT status FROM job WHERE job_id=NEW.job_id),'MISSING') IN ('SUCCEEDED','FAILED','STOPPED')
BEGIN
    SELECT RAISE(ABORT,'terminal Job cannot accept new PipelinePlan');
END;

CREATE TRIGGER pipeline_plan_parent_guard
BEFORE INSERT ON pipeline_plan
WHEN NEW.parent_plan_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM pipeline_plan p
    WHERE p.plan_id=NEW.parent_plan_id AND p.job_id=NEW.job_id
      AND p.status IN ('SEALED','SUPERSEDED') AND p.revision<NEW.revision)
BEGIN
    SELECT RAISE(ABORT,'parent Plan must be an earlier sealed revision of the same Job');
END;

CREATE TRIGGER plan_validation_report_guard
BEFORE INSERT ON pipeline_plan_validation
WHEN COALESCE(json_type(NEW.report_json),'missing')<>'object'
  OR COALESCE(json_extract(NEW.report_json,'$.schema'),'')<>'audioprep.plan-validation-report.v1'
  OR COALESCE(json_type(NEW.report_json,'$.passed'),'missing')<>'true'
  OR COALESCE(json_type(NEW.report_json,'$.counts'),'missing')<>'object'
  OR COALESCE(json_type(NEW.report_json,'$.counts.nodes'),'missing')<>'integer'
  OR COALESCE(json_type(NEW.report_json,'$.counts.edges'),'missing')<>'integer'
  OR json_extract(NEW.report_json,'$.counts.nodes')<>(SELECT COUNT(*) FROM pipeline_plan_node WHERE plan_id=NEW.plan_id)
  OR json_extract(NEW.report_json,'$.counts.edges')<>(SELECT COUNT(*) FROM pipeline_plan_edge WHERE plan_id=NEW.plan_id)
  OR COALESCE(json_type(NEW.report_json,'$.cardinality'),'missing')<>'object'
  OR COALESCE(json_type(NEW.report_json,'$.cardinality.required-single'),'missing')<>'integer'
  OR COALESCE(json_type(NEW.report_json,'$.cardinality.optional-single'),'missing')<>'integer'
  OR COALESCE(json_type(NEW.report_json,'$.cardinality.variadic'),'missing')<>'integer'
  OR json_extract(NEW.report_json,'$.cardinality.required-single')<>(
        SELECT COUNT(*) FROM pipeline_plan_node n, json_each(n.input_contracts) p
         WHERE n.plan_id=NEW.plan_id AND COALESCE(json_extract(p.value,'$.cardinality'),'required-single')='required-single')
  OR json_extract(NEW.report_json,'$.cardinality.optional-single')<>(
        SELECT COUNT(*) FROM pipeline_plan_node n, json_each(n.input_contracts) p
         WHERE n.plan_id=NEW.plan_id AND json_extract(p.value,'$.cardinality')='optional-single')
  OR json_extract(NEW.report_json,'$.cardinality.variadic')<>(
        SELECT COUNT(*) FROM pipeline_plan_node n, json_each(n.input_contracts) p
         WHERE n.plan_id=NEW.plan_id AND json_extract(p.value,'$.cardinality')='variadic')
  OR COALESCE(json_type(NEW.report_json,'$.media_subsets'),'missing')<>'array'
  OR json_array_length(NEW.report_json,'$.media_subsets')<>(SELECT COUNT(*) FROM pipeline_plan_edge WHERE plan_id=NEW.plan_id)
  OR EXISTS (SELECT 1 FROM json_each(NEW.report_json,'$.media_subsets') r
             WHERE COALESCE(json_type(r.value,'$.compatible'),'missing')<>'true'
                OR COALESCE(json_type(r.value,'$.from'),'missing')<>'text'
                OR COALESCE(json_type(r.value,'$.to'),'missing')<>'text'
                OR COALESCE(json_type(r.value,'$.output'),'missing')<>'text'
                OR COALESCE(json_type(r.value,'$.input'),'missing')<>'text'
                OR NOT EXISTS (
                    SELECT 1 FROM pipeline_plan_edge e
                     WHERE e.plan_id=NEW.plan_id
                       AND e.from_plan_node_id=json_extract(r.value,'$.from')
                       AND e.to_plan_node_id=json_extract(r.value,'$.to')
                       AND e.output_name=json_extract(r.value,'$.output')
                       AND e.input_name=json_extract(r.value,'$.input')))
  OR EXISTS (SELECT 1 FROM pipeline_plan_edge e
             WHERE e.plan_id=NEW.plan_id AND NOT EXISTS (
                 SELECT 1 FROM json_each(NEW.report_json,'$.media_subsets') r
                  WHERE json_extract(r.value,'$.from')=e.from_plan_node_id
                    AND json_extract(r.value,'$.to')=e.to_plan_node_id
                    AND json_extract(r.value,'$.output')=e.output_name
                    AND json_extract(r.value,'$.input')=e.input_name
                    AND COALESCE(json_type(r.value,'$.compatible'),'missing')='true'))
  OR COALESCE(json_type(NEW.report_json,'$.reachability'),'missing')<>'object'
  OR COALESCE(json_type(NEW.report_json,'$.reachability.roots'),'missing')<>'array'
  OR COALESCE(json_type(NEW.report_json,'$.reachability.reachable'),'missing')<>'array'
  OR COALESCE(json_type(NEW.report_json,'$.reachability.unreachable'),'missing')<>'array'
  OR json_array_length(NEW.report_json,'$.reachability.unreachable')<>0
  OR json_array_length(NEW.report_json,'$.reachability.roots')<>(
        SELECT COUNT(*) FROM pipeline_plan_node n WHERE n.plan_id=NEW.plan_id AND json_array_length(n.input_roles)=0)
  OR json_array_length(NEW.report_json,'$.reachability.reachable')<>(SELECT COUNT(*) FROM pipeline_plan_node WHERE plan_id=NEW.plan_id)
  OR EXISTS (SELECT 1 FROM pipeline_plan_node n
             WHERE n.plan_id=NEW.plan_id AND NOT EXISTS (
                 SELECT 1 FROM json_each(NEW.report_json,'$.reachability.reachable') r WHERE r.value=n.plan_node_id))
  OR EXISTS (SELECT 1 FROM json_each(NEW.report_json,'$.reachability.reachable') r
             WHERE r.type<>'text' OR NOT EXISTS (
                 SELECT 1 FROM pipeline_plan_node n WHERE n.plan_id=NEW.plan_id AND n.plan_node_id=r.value))
  OR EXISTS (SELECT 1 FROM pipeline_plan_node n
             WHERE n.plan_id=NEW.plan_id AND json_array_length(n.input_roles)=0 AND NOT EXISTS (
                 SELECT 1 FROM json_each(NEW.report_json,'$.reachability.roots') r WHERE r.value=n.plan_node_id))
  OR EXISTS (SELECT 1 FROM json_each(NEW.report_json,'$.reachability.roots') r
             WHERE r.type<>'text' OR NOT EXISTS (
                 SELECT 1 FROM pipeline_plan_node n
                  WHERE n.plan_id=NEW.plan_id AND n.plan_node_id=r.value AND json_array_length(n.input_roles)=0))
  OR COALESCE(json_type(NEW.report_json,'$.checks'),'missing')<>'object'
  OR COALESCE(json_type(NEW.report_json,'$.checks.port_cardinality'),'missing')<>'true'
  OR COALESCE(json_type(NEW.report_json,'$.checks.media_subsets'),'missing')<>'true'
  OR COALESCE(json_type(NEW.report_json,'$.checks.reachability'),'missing')<>'true'
  OR COALESCE(json_type(NEW.report_json,'$.checks.predicate_validation'),'missing')<>'true'
  OR COALESCE(json_type(NEW.report_json,'$.checks.ordinal_acyclicity'),'missing')<>'true'
  OR COALESCE(json_type(NEW.report_json,'$.checks.delivery_render_quality_master'),'missing')<>'true'
BEGIN
    SELECT RAISE(ABORT,'Plan validation receipt must contain a passed structured PlanSealValidator report');
END;

CREATE TRIGGER plan_validation_insert_guard
BEFORE INSERT ON pipeline_plan_validation
WHEN COALESCE((SELECT status FROM pipeline_plan WHERE plan_id=NEW.plan_id),'MISSING')<>'DRAFT'
BEGIN
    SELECT RAISE(ABORT,'Plan validation receipt may only be created for DRAFT Plan');
END;

CREATE TRIGGER plan_validation_update_guard
BEFORE UPDATE ON pipeline_plan_validation
BEGIN
    SELECT RAISE(ABORT,'Plan validation receipt is immutable; delete and revalidate DRAFT Plan');
END;

CREATE TRIGGER plan_validation_delete_guard
BEFORE DELETE ON pipeline_plan_validation
WHEN (SELECT status FROM pipeline_plan WHERE plan_id=OLD.plan_id)<>'DRAFT'
BEGIN
    SELECT RAISE(ABORT,'sealed Plan validation receipt is immutable');
END;

CREATE TRIGGER plan_validation_freezes_plan_metadata
BEFORE UPDATE OF planner_version ON pipeline_plan
WHEN NEW.planner_version<>OLD.planner_version
 AND EXISTS (SELECT 1 FROM pipeline_plan_validation v WHERE v.plan_id=OLD.plan_id)
BEGIN
    SELECT RAISE(ABORT,'validated DRAFT is frozen; delete validation receipt before editing planner metadata');
END;

CREATE TRIGGER pipeline_plan_identity_immutable
BEFORE UPDATE OF plan_id,job_id,revision,parent_plan_id ON pipeline_plan
BEGIN
    SELECT RAISE(ABORT,'pipeline Plan identity is immutable');
END;

CREATE TRIGGER pipeline_plan_seal_guard
BEFORE UPDATE OF status ON pipeline_plan
WHEN OLD.status='DRAFT' AND NEW.status='SEALED'
BEGIN
    SELECT CASE WHEN NEW.plan_fingerprint IS NULL OR NEW.sealed_at IS NULL
        THEN RAISE(ABORT,'SEALED plan requires fingerprint and sealed_at') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM pipeline_plan_validation v
        WHERE v.plan_id=OLD.plan_id AND v.plan_fingerprint=NEW.plan_fingerprint)
        THEN RAISE(ABORT,'SEALED plan requires matching PlanSealValidator receipt') END;
END;

CREATE TRIGGER pipeline_plan_transition_guard
BEFORE UPDATE OF status ON pipeline_plan
WHEN NOT (
    (OLD.status='DRAFT' AND NEW.status IN ('DRAFT','SEALED')) OR
    (OLD.status='SEALED' AND NEW.status IN ('SEALED','SUPERSEDED')) OR
    (OLD.status='SUPERSEDED' AND NEW.status='SUPERSEDED'))
BEGIN
    SELECT RAISE(ABORT,'illegal pipeline plan status transition');
END;

CREATE TRIGGER pipeline_plan_delete_guard
BEFORE DELETE ON pipeline_plan
WHEN OLD.status<>'DRAFT'
BEGIN
    SELECT RAISE(ABORT,'sealed/superseded pipeline plan is immutable');
END;

CREATE TRIGGER pipeline_plan_immutable_after_seal
BEFORE UPDATE ON pipeline_plan
WHEN OLD.status IN ('SEALED','SUPERSEDED') AND (
    NEW.job_id<>OLD.job_id OR NEW.revision<>OLD.revision OR
    COALESCE(NEW.parent_plan_id,'')<>COALESCE(OLD.parent_plan_id,'') OR
    NEW.planner_version<>OLD.planner_version OR
    COALESCE(NEW.plan_fingerprint,'')<>COALESCE(OLD.plan_fingerprint,'') OR
    COALESCE(NEW.sealed_at,'')<>COALESCE(OLD.sealed_at,'') OR
    NEW.created_at IS NOT OLD.created_at)
BEGIN
    SELECT RAISE(ABORT,'sealed/superseded pipeline plan is immutable');
END;

CREATE TRIGGER plan_cannot_supersede_installed_current
BEFORE UPDATE OF status ON pipeline_plan
WHEN OLD.status='SEALED' AND NEW.status='SUPERSEDED'
 AND EXISTS (SELECT 1 FROM job j WHERE j.current_plan_id=OLD.plan_id)
BEGIN
    SELECT RAISE(ABORT,'uninstall current_plan_id before superseding the Plan');
END;

CREATE TRIGGER pipeline_plan_cannot_supersede_started
BEFORE UPDATE OF status ON pipeline_plan
WHEN OLD.status='SEALED' AND NEW.status='SUPERSEDED'
 AND EXISTS (SELECT 1 FROM job j WHERE j.job_id=OLD.job_id AND j.started_at IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT,'started SEALED plan cannot be superseded');
END;

CREATE TRIGGER plan_validation_freezes_draft_update
BEFORE UPDATE ON pipeline_plan_node
WHEN EXISTS (SELECT 1 FROM pipeline_plan_validation v WHERE v.plan_id=OLD.plan_id)
BEGIN
    SELECT RAISE(ABORT,'validated DRAFT is frozen; delete validation receipt before editing');
END;
CREATE TRIGGER plan_validation_freezes_draft_insert
BEFORE INSERT ON pipeline_plan_node
WHEN EXISTS (SELECT 1 FROM pipeline_plan_validation v WHERE v.plan_id=NEW.plan_id)
BEGIN
    SELECT RAISE(ABORT,'validated DRAFT is frozen; delete validation receipt before editing');
END;
CREATE TRIGGER plan_validation_freezes_draft_delete
BEFORE DELETE ON pipeline_plan_node
WHEN EXISTS (SELECT 1 FROM pipeline_plan p WHERE p.plan_id=OLD.plan_id)
 AND EXISTS (SELECT 1 FROM pipeline_plan_validation v WHERE v.plan_id=OLD.plan_id)
BEGIN
    SELECT RAISE(ABORT,'validated DRAFT is frozen; delete validation receipt before editing');
END;

CREATE TRIGGER plan_node_insert_guard
BEFORE INSERT ON pipeline_plan_node
WHEN COALESCE((SELECT status FROM pipeline_plan WHERE plan_id=NEW.plan_id),'MISSING') <> 'DRAFT'
BEGIN
    SELECT RAISE(ABORT,'sealed pipeline plan is immutable');
END;
CREATE TRIGGER plan_node_update_guard
BEFORE UPDATE ON pipeline_plan_node
WHEN COALESCE((SELECT status FROM pipeline_plan WHERE plan_id=OLD.plan_id),'MISSING') <> 'DRAFT'
BEGIN
    SELECT RAISE(ABORT,'sealed pipeline plan is immutable');
END;
CREATE TRIGGER plan_node_delete_guard
BEFORE DELETE ON pipeline_plan_node
WHEN EXISTS (SELECT 1 FROM pipeline_plan WHERE plan_id=OLD.plan_id AND status<>'DRAFT')
BEGIN
    SELECT RAISE(ABORT,'sealed pipeline plan is immutable');
END;
CREATE TRIGGER plan_node_plan_id_immutable
BEFORE UPDATE OF plan_node_id,plan_id ON pipeline_plan_node
WHEN NEW.plan_node_id IS NOT OLD.plan_node_id OR NEW.plan_id IS NOT OLD.plan_id
BEGIN
    SELECT RAISE(ABORT,'pipeline plan node identifier and plan_id are immutable');
END;

CREATE TRIGGER plan_edge_insert_guard
BEFORE INSERT ON pipeline_plan_edge
BEGIN
    SELECT CASE WHEN COALESCE((SELECT status FROM pipeline_plan WHERE plan_id=NEW.plan_id),'MISSING') <> 'DRAFT'
        THEN RAISE(ABORT,'sealed pipeline plan is immutable') END;
    SELECT CASE WHEN EXISTS (SELECT 1 FROM pipeline_plan_validation v WHERE v.plan_id=NEW.plan_id)
        THEN RAISE(ABORT,'validated DRAFT is frozen; delete validation receipt before editing') END;
    SELECT CASE WHEN COALESCE((SELECT ordinal FROM pipeline_plan_node WHERE plan_id=NEW.plan_id AND plan_node_id=NEW.from_plan_node_id),-1)
                       >= COALESCE((SELECT ordinal FROM pipeline_plan_node WHERE plan_id=NEW.plan_id AND plan_node_id=NEW.to_plan_node_id),-1)
        THEN RAISE(ABORT,'pipeline edge must move forward in ordinal order') END;
END;
CREATE TRIGGER plan_edge_update_guard
BEFORE UPDATE ON pipeline_plan_edge
BEGIN
    SELECT RAISE(ABORT,'pipeline Plan edges are immutable rows; delete and reinsert while DRAFT');
END;
CREATE TRIGGER plan_edge_delete_guard
BEFORE DELETE ON pipeline_plan_edge
BEGIN
    SELECT CASE WHEN EXISTS (SELECT 1 FROM pipeline_plan p WHERE p.plan_id=OLD.plan_id AND p.status<>'DRAFT')
        THEN RAISE(ABORT,'sealed pipeline plan is immutable') END;
    SELECT CASE WHEN EXISTS (SELECT 1 FROM pipeline_plan p WHERE p.plan_id=OLD.plan_id)
                      AND EXISTS (SELECT 1 FROM pipeline_plan_validation v WHERE v.plan_id=OLD.plan_id)
        THEN RAISE(ABORT,'validated DRAFT is frozen; delete validation receipt before editing') END;
END;

-- -------------------------------------------------------------------------
-- Job source identity, plan binding and state machine.
-- -------------------------------------------------------------------------
CREATE TRIGGER job_insert_initial_state_guard
BEFORE INSERT ON job
WHEN NEW.status<>'CREATED' OR NEW.source_identity_frozen_at IS NOT NULL
  OR NEW.source_size_bytes IS NOT NULL OR NEW.source_mtime_ns IS NOT NULL
  OR NEW.source_content_hash IS NOT NULL OR NEW.source_artifact_id IS NOT NULL
  OR NEW.dispatch_generation<>0 OR NEW.started_at IS NOT NULL OR NEW.finished_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT,'Job must be inserted as empty CREATED record');
END;

CREATE TRIGGER job_insert_current_plan_must_be_null
BEFORE INSERT ON job
WHEN NEW.current_plan_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT,'current_plan_id must be installed after Job creation');
END;

CREATE TRIGGER job_current_plan_guard
BEFORE UPDATE OF current_plan_id ON job
WHEN NEW.current_plan_id IS NOT OLD.current_plan_id
BEGIN
    SELECT CASE WHEN OLD.started_at IS NOT NULL
        THEN RAISE(ABORT,'current plan cannot change after execution start') END;
    SELECT CASE WHEN NEW.current_plan_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM pipeline_plan p
        WHERE p.plan_id=NEW.current_plan_id AND p.job_id=OLD.job_id AND p.status='SEALED')
        THEN RAISE(ABORT,'current_plan_id must reference a same-job SEALED plan') END;
END;

CREATE TRIGGER job_identity_immutable
BEFORE UPDATE OF job_id,batch_id,source_path ON job
BEGIN
    SELECT RAISE(ABORT,'Job batch and source_path identity are immutable');
END;

CREATE TRIGGER job_runtime_fence_guard
BEFORE UPDATE OF status,dispatch_generation,active_run_token,lease_expires_at,worker_id ON job
WHEN (NEW.dispatch_generation IS NOT OLD.dispatch_generation
   OR NEW.active_run_token IS NOT OLD.active_run_token
   OR NEW.lease_expires_at IS NOT OLD.lease_expires_at
   OR NEW.worker_id IS NOT OLD.worker_id)
 AND NOT (
    (OLD.status IN ('QUEUED','WAITING_DECISION') AND NEW.status='RUNNING'
     AND NEW.dispatch_generation=OLD.dispatch_generation+1
     AND OLD.active_run_token IS NULL AND OLD.lease_expires_at IS NULL AND OLD.worker_id IS NULL
     AND NEW.active_run_token IS NOT NULL AND NEW.lease_expires_at IS NOT NULL AND NEW.worker_id IS NOT NULL
     AND EXISTS (SELECT 1 FROM pipeline_plan p
                 WHERE p.plan_id=NEW.current_plan_id AND p.job_id=OLD.job_id AND p.status='SEALED'))
    OR
    (OLD.status='RUNNING' AND NEW.status IN ('WAITING_DECISION','SUCCEEDED','FAILED','STOPPED')
     AND NEW.dispatch_generation=OLD.dispatch_generation
     AND NEW.active_run_token IS NULL AND NEW.lease_expires_at IS NULL AND NEW.worker_id IS NULL)
 )
BEGIN
    SELECT RAISE(ABORT,'Job execution fence changes only as one atomic generation bundle on RUNNING entry/exit');
END;

CREATE TRIGGER job_started_at_write_guard
BEFORE UPDATE OF started_at ON job
WHEN NEW.started_at IS NOT OLD.started_at
 AND NOT (OLD.status='QUEUED' AND NEW.status='RUNNING'
          AND OLD.started_at IS NULL AND NEW.started_at IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT,'started_at is written only during QUEUED to RUNNING');
END;

CREATE TRIGGER job_source_identity_guard
BEFORE UPDATE OF source_size_bytes,source_mtime_ns,source_content_hash,
                 source_artifact_id,source_identity_frozen_at ON job
WHEN NEW.source_identity_frozen_at IS NOT NULL
BEGIN
    SELECT CASE WHEN NEW.source_size_bytes IS NULL OR NEW.source_mtime_ns IS NULL
                  OR NEW.source_content_hash IS NULL OR NEW.source_artifact_id IS NULL
        THEN RAISE(ABORT,'SourceIdentity fields must be complete') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM artifact a
        JOIN blob b ON b.blob_id=a.blob_id
        JOIN artifact_reference r ON r.artifact_id=a.artifact_id
        WHERE a.artifact_id=NEW.source_artifact_id
          AND a.artifact_role='SOURCE_MEDIA'
          AND r.owner_type='JOB' AND r.owner_id=OLD.job_id AND r.ref_kind='source'
          AND b.content_hash=NEW.source_content_hash
          AND b.size_bytes=NEW.source_size_bytes)
        THEN RAISE(ABORT,'SourceIdentity requires a matching Job-owned SOURCE_MEDIA artifact') END;
END;

CREATE TRIGGER job_frozen_source_immutable
BEFORE UPDATE OF source_size_bytes,source_mtime_ns,source_content_hash,
                 source_artifact_id,source_identity_frozen_at ON job
WHEN OLD.source_identity_frozen_at IS NOT NULL AND (
    NEW.source_size_bytes IS NOT OLD.source_size_bytes OR
    NEW.source_mtime_ns IS NOT OLD.source_mtime_ns OR
    NEW.source_content_hash IS NOT OLD.source_content_hash OR
    NEW.source_artifact_id IS NOT OLD.source_artifact_id OR
    NEW.source_identity_frozen_at IS NOT OLD.source_identity_frozen_at)
BEGIN
    SELECT RAISE(ABORT,'frozen source identity is immutable');
END;

CREATE TRIGGER job_waiting_requires_no_inflight_nodes
BEFORE UPDATE OF status ON job
WHEN OLD.status='RUNNING' AND NEW.status='WAITING_DECISION'
 AND EXISTS (SELECT 1 FROM node_execution e WHERE e.job_id=OLD.job_id AND e.status IN ('DISPATCHED','RUNNING'))
BEGIN
    SELECT RAISE(ABORT,'WAITING_DECISION requires all dispatched/running NodeExecution attempts to close');
END;

CREATE TRIGGER job_status_transition_guard
BEFORE UPDATE OF status ON job
WHEN NOT (
    (OLD.status='CREATED' AND NEW.status IN ('CREATED','QUEUED','FAILED','STOPPED')) OR
    (OLD.status='QUEUED' AND NEW.status IN ('QUEUED','RUNNING','FAILED','STOPPED')) OR
    (OLD.status='RUNNING' AND NEW.status IN ('RUNNING','WAITING_DECISION','SUCCEEDED','FAILED','STOPPED')) OR
    (OLD.status='WAITING_DECISION' AND NEW.status IN ('WAITING_DECISION','RUNNING','FAILED','STOPPED')) OR
    (OLD.status IN ('SUCCEEDED','FAILED','STOPPED') AND NEW.status=OLD.status))
BEGIN
    SELECT RAISE(ABORT,'illegal Job status transition');
END;

CREATE TRIGGER job_terminal_fields_immutable
BEFORE UPDATE ON job
WHEN OLD.status IN ('SUCCEEDED','FAILED','STOPPED') AND (
    NEW.status<>OLD.status OR NEW.finished_at IS NOT OLD.finished_at OR
    NEW.error_code IS NOT OLD.error_code OR NEW.error_type IS NOT OLD.error_type OR
    NEW.current_plan_id IS NOT OLD.current_plan_id OR
    NEW.source_artifact_id IS NOT OLD.source_artifact_id OR
    NEW.dispatch_generation IS NOT OLD.dispatch_generation OR
    NEW.started_at IS NOT OLD.started_at OR NEW.created_at IS NOT OLD.created_at)
BEGIN
    SELECT RAISE(ABORT,'terminal Job is immutable');
END;

CREATE TRIGGER job_terminal_delete_guard
BEFORE DELETE ON job
WHEN OLD.status IN ('SUCCEEDED','FAILED','STOPPED')
BEGIN
    SELECT RAISE(ABORT,'terminal Job is immutable');
END;

CREATE TRIGGER job_success_requires_no_active_nodes
BEFORE UPDATE OF status ON job
WHEN NEW.status='SUCCEEDED' AND OLD.status<>NEW.status
 AND EXISTS (SELECT 1 FROM node_execution e
             WHERE e.job_id=OLD.job_id AND e.status IN ('PENDING','DISPATCHED','RUNNING'))
BEGIN
    SELECT RAISE(ABORT,'SUCCEEDED Job cannot retain active NodeExecution rows');
END;

CREATE TRIGGER job_terminal_aborts_active_nodes
AFTER UPDATE OF status ON job
WHEN NEW.status IN ('FAILED','STOPPED') AND OLD.status<>NEW.status
BEGIN
    UPDATE node_execution
       SET status='ABORTED', completed_at=COALESCE(completed_at,NEW.finished_at),
           run_token=NULL, worker_id=NULL,
           error_detail=CASE NEW.status WHEN 'STOPPED' THEN 'Job stopped' ELSE 'Job failed' END
     WHERE job_id=NEW.job_id AND status IN ('PENDING','DISPATCHED','RUNNING');
END;

-- -------------------------------------------------------------------------
-- Node execution and checkpoint identity/lifecycle.
-- -------------------------------------------------------------------------
CREATE TRIGGER node_execution_insert_pending_only
BEFORE INSERT ON node_execution
WHEN NEW.status<>'PENDING' OR NEW.started_at IS NOT NULL OR NEW.completed_at IS NOT NULL
  OR NEW.run_token IS NOT NULL OR NEW.worker_id IS NOT NULL OR NEW.hard_deadline_at IS NOT NULL
  OR NEW.error_code IS NOT NULL OR NEW.error_detail IS NOT NULL
BEGIN
    SELECT RAISE(ABORT,'NodeExecution must be inserted as PENDING');
END;

CREATE TRIGGER node_execution_identity_guard_insert
BEFORE INSERT ON node_execution
WHEN NOT EXISTS (
    SELECT 1 FROM pipeline_plan_node n
    JOIN pipeline_plan p ON p.plan_id=n.plan_id
    JOIN job j ON j.job_id=p.job_id
    WHERE n.plan_node_id=NEW.plan_node_id AND n.plan_id=NEW.plan_id
      AND p.job_id=NEW.job_id AND p.status='SEALED'
      AND n.implementation_fingerprint=NEW.implementation_fingerprint
      AND j.status IN ('QUEUED','RUNNING','WAITING_DECISION')
      AND (j.current_plan_id IS NULL OR j.current_plan_id=NEW.plan_id)
      AND ((j.dispatch_generation=0 AND NEW.dispatch_generation=1)
           OR j.dispatch_generation=NEW.dispatch_generation))
BEGIN
    SELECT RAISE(ABORT,'node execution identity mismatch, stale plan/generation, or implementation fingerprint mismatch');
END;

CREATE TRIGGER node_execution_dispatch_identity_guard
BEFORE UPDATE OF status ON node_execution
WHEN OLD.status='PENDING' AND NEW.status='DISPATCHED' AND NOT EXISTS (
    SELECT 1 FROM job j
    WHERE j.job_id=OLD.job_id AND j.status='RUNNING'
      AND j.current_plan_id=OLD.plan_id
      AND j.dispatch_generation=OLD.dispatch_generation)
BEGIN
    SELECT RAISE(ABORT,'NodeExecution dispatch rejected for stale current plan or generation');
END;

CREATE TRIGGER node_execution_run_identity_guard
BEFORE UPDATE OF status ON node_execution
WHEN OLD.status='DISPATCHED' AND NEW.status='RUNNING' AND NOT EXISTS (
    SELECT 1 FROM job j
    JOIN pipeline_plan p ON p.plan_id=j.current_plan_id
    WHERE j.job_id=OLD.job_id AND j.status='RUNNING'
      AND p.status='SEALED' AND j.current_plan_id=OLD.plan_id
      AND j.dispatch_generation=OLD.dispatch_generation)
BEGIN
    SELECT RAISE(ABORT,'stale plan/generation at execution start');
END;

CREATE TRIGGER node_execution_identity_immutable
BEFORE UPDATE OF execution_id,job_id,plan_id,plan_node_id,execution_seq,dispatch_generation,
                 implementation_fingerprint ON node_execution
BEGIN
    SELECT RAISE(ABORT,'node execution identity is immutable');
END;

CREATE TRIGGER node_execution_transition_guard
BEFORE UPDATE OF status ON node_execution
WHEN NOT (
    (OLD.status='PENDING' AND NEW.status IN ('PENDING','DISPATCHED','SKIPPED','ABORTED')) OR
    (OLD.status='DISPATCHED' AND NEW.status IN ('DISPATCHED','RUNNING','FAILED','ABORTED')) OR
    (OLD.status='RUNNING' AND NEW.status IN ('RUNNING','SUCCEEDED','FAILED','ABORTED')) OR
    (OLD.status IN ('SUCCEEDED','FAILED','ABORTED','SKIPPED') AND NEW.status=OLD.status))
BEGIN
    SELECT RAISE(ABORT,'illegal NodeExecution status transition');
END;

CREATE TRIGGER node_execution_terminal_fence_guard
BEFORE UPDATE OF status ON node_execution
WHEN OLD.status IN ('DISPATCHED','RUNNING')
 AND NEW.status IN ('SUCCEEDED','FAILED','ABORTED')
 AND (NEW.run_token IS NOT NULL OR NEW.worker_id IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT,'terminal NodeExecution must clear run_token and worker_id');
END;

CREATE TRIGGER node_execution_runtime_fields_guard
BEFORE UPDATE OF run_token,worker_id,hard_deadline_at,started_at ON node_execution
WHEN (NEW.run_token IS NOT OLD.run_token OR NEW.worker_id IS NOT OLD.worker_id
   OR NEW.hard_deadline_at IS NOT OLD.hard_deadline_at OR NEW.started_at IS NOT OLD.started_at)
 AND NOT (
    (OLD.status='DISPATCHED' AND NEW.status='RUNNING'
     AND OLD.run_token IS NULL AND OLD.worker_id IS NULL AND OLD.started_at IS NULL
     AND NEW.run_token IS NOT NULL AND NEW.worker_id IS NOT NULL
     AND NEW.run_token=(SELECT active_run_token FROM job WHERE job_id=OLD.job_id)
     AND NEW.worker_id=(SELECT worker_id FROM job WHERE job_id=OLD.job_id)
     AND NEW.hard_deadline_at IS NOT NULL AND NEW.started_at IS NOT NULL)
    OR
    (OLD.status='RUNNING' AND NEW.status IN ('SUCCEEDED','FAILED','ABORTED')
     AND NEW.run_token IS NULL AND NEW.worker_id IS NULL
     AND NEW.hard_deadline_at IS OLD.hard_deadline_at AND NEW.started_at IS OLD.started_at)
 )
BEGIN
    SELECT RAISE(ABORT,'NodeExecution runtime fence fields change only on start or terminal close');
END;

CREATE TRIGGER node_execution_error_detail_guard
BEFORE UPDATE OF error_detail ON node_execution
WHEN NEW.error_detail IS NOT OLD.error_detail
 AND NOT (OLD.status IN ('PENDING','DISPATCHED','RUNNING')
          AND NEW.status IN ('FAILED','ABORTED')
          AND OLD.error_detail IS NULL)
BEGIN
    SELECT RAISE(ABORT,'NodeExecution error_detail may only be written during terminal close');
END;

CREATE TRIGGER node_execution_terminal_immutable
BEFORE UPDATE ON node_execution
WHEN OLD.status IN ('SUCCEEDED','FAILED','ABORTED','SKIPPED') AND (
    NEW.status<>OLD.status OR NEW.completed_at IS NOT OLD.completed_at OR
    NEW.error_code IS NOT OLD.error_code OR NEW.error_detail IS NOT OLD.error_detail OR
    NEW.run_token IS NOT OLD.run_token OR NEW.worker_id IS NOT OLD.worker_id OR
    NEW.started_at IS NOT OLD.started_at OR NEW.hard_deadline_at IS NOT OLD.hard_deadline_at OR
    NEW.created_at IS NOT OLD.created_at)
BEGIN
    SELECT RAISE(ABORT,'terminal node execution cannot transition');
END;

CREATE TRIGGER node_execution_terminal_delete_guard
BEFORE DELETE ON node_execution
WHEN OLD.status IN ('SUCCEEDED','FAILED','ABORTED','SKIPPED')
BEGIN
    SELECT RAISE(ABORT,'terminal NodeExecution is immutable');
END;

CREATE TRIGGER checkpoint_insert_open_only
BEFORE INSERT ON checkpoint
WHEN NEW.status<>'OPEN'
BEGIN
    SELECT RAISE(ABORT,'Checkpoint must be inserted OPEN');
END;

CREATE TRIGGER checkpoint_identity_guard
BEFORE INSERT ON checkpoint
WHEN NOT EXISTS (
    SELECT 1 FROM node_execution e JOIN job j ON j.job_id=e.job_id
    WHERE e.execution_id=NEW.execution_id AND e.job_id=NEW.job_id
      AND e.plan_id=NEW.plan_id AND e.plan_node_id=NEW.plan_node_id
      AND e.status='SUCCEEDED' AND j.status NOT IN ('SUCCEEDED','FAILED','STOPPED'))
BEGIN
    SELECT RAISE(ABORT,'checkpoint job/plan/node identity mismatch');
END;

CREATE TRIGGER checkpoint_identity_immutable
BEFORE UPDATE OF checkpoint_id,job_id,plan_id,plan_node_id,execution_id,created_at ON checkpoint
BEGIN
    SELECT RAISE(ABORT,'Checkpoint identity is immutable');
END;

CREATE TRIGGER checkpoint_transition_guard
BEFORE UPDATE OF status ON checkpoint
WHEN NOT (
    (OLD.status='OPEN' AND NEW.status IN ('OPEN','COMMITTED','RELEASED')) OR
    (OLD.status='COMMITTED' AND NEW.status IN ('COMMITTED','RELEASED')) OR
    (OLD.status='RELEASED' AND NEW.status='RELEASED'))
BEGIN
    SELECT RAISE(ABORT,'illegal Checkpoint status transition');
END;

CREATE TRIGGER checkpoint_terminal_immutable
BEFORE UPDATE ON checkpoint
WHEN OLD.status='RELEASED' AND NEW.status<>OLD.status
BEGIN
    SELECT RAISE(ABORT,'released Checkpoint is immutable');
END;

CREATE TRIGGER checkpoint_release_requires_refs_released
BEFORE UPDATE OF status ON checkpoint
WHEN OLD.status<>'RELEASED' AND NEW.status='RELEASED'
 AND EXISTS (SELECT 1 FROM artifact_reference r
             WHERE r.owner_type='CHECKPOINT' AND r.owner_id=OLD.checkpoint_id)
BEGIN
    SELECT RAISE(ABORT,'release checkpoint refs before releasing Checkpoint');
END;

-- -------------------------------------------------------------------------
-- Polymorphic ownership and reference counts.
-- -------------------------------------------------------------------------
CREATE TRIGGER artifact_reference_owner_guard
BEFORE INSERT ON artifact_reference
BEGIN
    SELECT CASE WHEN NEW.owner_type='JOB' AND NOT EXISTS (SELECT 1 FROM job WHERE job_id=NEW.owner_id)
        THEN RAISE(ABORT,'ArtifactReference requires a live owner') END;
    SELECT CASE WHEN NEW.owner_type='CHECKPOINT' AND NOT EXISTS (SELECT 1 FROM checkpoint WHERE checkpoint_id=NEW.owner_id AND status<>'RELEASED')
        THEN RAISE(ABORT,'ArtifactReference requires a live owner') END;
    SELECT CASE WHEN NEW.owner_type='DECISION' AND NOT EXISTS (SELECT 1 FROM decision WHERE decision_id=NEW.owner_id AND status IN ('PENDING','RESOLVED'))
        THEN RAISE(ABORT,'ArtifactReference requires a live owner') END;
    SELECT CASE WHEN NEW.owner_type='DELIVERABLE' AND NOT EXISTS (SELECT 1 FROM deliverable WHERE deliverable_id=NEW.owner_id AND status IN ('STAGING','PUBLISHED'))
        THEN RAISE(ABORT,'ArtifactReference requires a live owner') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM artifact a JOIN blob b ON b.blob_id=a.blob_id
        WHERE a.artifact_id=NEW.artifact_id AND b.gc_state<>'LIVE')
        THEN RAISE(ABORT,'blob is not LIVE; recompute/reacquire instead') END;
END;

CREATE TRIGGER artifact_reference_update_immutable
BEFORE UPDATE ON artifact_reference
BEGIN
    SELECT RAISE(ABORT,'ArtifactReference rows are immutable; delete and insert to transfer ownership');
END;

CREATE TRIGGER decision_candidate_reference_delete_guard
BEFORE DELETE ON artifact_reference
WHEN OLD.owner_type='DECISION' AND EXISTS (
    SELECT 1 FROM decision d
    WHERE d.decision_id=OLD.owner_id AND d.status IN ('PENDING','RESOLVED'))
BEGIN
    SELECT RAISE(ABORT,'Decision candidate refs are released only by the terminal Decision transition');
END;

CREATE TRIGGER artifact_reference_insert_counts
AFTER INSERT ON artifact_reference
BEGIN
    UPDATE artifact SET strong_refcount=strong_refcount+1 WHERE artifact_id=NEW.artifact_id;
    UPDATE blob SET strong_refcount=strong_refcount+1
     WHERE blob_id=(SELECT blob_id FROM artifact WHERE artifact_id=NEW.artifact_id);
END;
CREATE TRIGGER artifact_reference_delete_counts
AFTER DELETE ON artifact_reference
BEGIN
    UPDATE artifact SET strong_refcount=strong_refcount-1 WHERE artifact_id=OLD.artifact_id;
    UPDATE blob SET strong_refcount=strong_refcount-1
     WHERE blob_id=(SELECT blob_id FROM artifact WHERE artifact_id=OLD.artifact_id);
END;

CREATE TRIGGER frozen_source_reference_delete_guard
BEFORE DELETE ON artifact_reference
WHEN OLD.owner_type='JOB' AND OLD.ref_kind='source'
 AND EXISTS (SELECT 1 FROM job j WHERE j.job_id=OLD.owner_id
             AND j.source_identity_frozen_at IS NOT NULL
             AND j.source_artifact_id=OLD.artifact_id)
BEGIN
    SELECT RAISE(ABORT,'frozen Job cannot release SOURCE_MEDIA ownership');
END;

CREATE TRIGGER job_delete_reference_guard
BEFORE DELETE ON job
WHEN EXISTS (SELECT 1 FROM artifact_reference WHERE owner_type='JOB' AND owner_id=OLD.job_id)
BEGIN
    SELECT RAISE(ABORT,'release JOB artifact refs before deleting owner');
END;
CREATE TRIGGER checkpoint_delete_reference_guard
BEFORE DELETE ON checkpoint
WHEN EXISTS (SELECT 1 FROM artifact_reference WHERE owner_type='CHECKPOINT' AND owner_id=OLD.checkpoint_id)
BEGIN
    SELECT RAISE(ABORT,'release CHECKPOINT artifact refs before deleting owner');
END;
CREATE TRIGGER decision_delete_reference_guard
BEFORE DELETE ON decision
WHEN EXISTS (SELECT 1 FROM artifact_reference WHERE owner_type='DECISION' AND owner_id=OLD.decision_id)
BEGIN
    SELECT RAISE(ABORT,'release DECISION artifact refs before deleting owner');
END;
CREATE TRIGGER deliverable_delete_reference_guard
BEFORE DELETE ON deliverable
WHEN EXISTS (SELECT 1 FROM artifact_reference WHERE owner_type='DELIVERABLE' AND owner_id=OLD.deliverable_id)
BEGIN
    SELECT RAISE(ABORT,'release DELIVERABLE artifact refs before deleting owner');
END;

CREATE TRIGGER execution_cache_output_immutable
BEFORE UPDATE ON execution_cache_output
BEGIN
    SELECT RAISE(ABORT,'execution_cache_output rows are immutable; delete and reinsert to rebind cache output');
END;

-- -------------------------------------------------------------------------
-- Decision identity and lifecycle.
-- -------------------------------------------------------------------------
CREATE TRIGGER decision_insert_pending_only
BEFORE INSERT ON decision
WHEN NEW.status<>'PENDING' OR NEW.resolution_action IS NOT NULL OR NEW.resolved_at IS NOT NULL
  OR NEW.resolver_type IS NOT NULL OR NEW.applied_at IS NOT NULL OR NEW.confidence IS NOT NULL
BEGIN
    SELECT RAISE(ABORT,'Decision must be inserted PENDING and unresolved');
END;

CREATE TRIGGER decision_identity_guard_insert
BEFORE INSERT ON decision
WHEN NOT EXISTS (
    SELECT 1 FROM job j
    JOIN pipeline_plan_node n ON n.plan_node_id=NEW.plan_node_id
    JOIN pipeline_plan p ON p.plan_id=n.plan_id
    WHERE j.job_id=NEW.origin_job_id AND j.batch_id=NEW.batch_id
      AND j.status NOT IN ('SUCCEEDED','FAILED','STOPPED')
      AND p.job_id=j.job_id)
BEGIN
    SELECT RAISE(ABORT,'decision job/batch/plan identity mismatch');
END;

CREATE TRIGGER decision_identity_immutable
BEFORE UPDATE OF decision_id,origin_job_id,batch_id,plan_node_id,decision_type,
                 join_signature,join_signature_components,
                 policy_signature,policy_signature_components,expires_at,created_at ON decision
BEGIN
    SELECT RAISE(ABORT,'Decision origin and policy identity are immutable');
END;

CREATE TRIGGER decision_resolution_selector_guard
BEFORE UPDATE OF status,resolution_action ON decision
WHEN OLD.status='PENDING' AND NEW.status='RESOLVED' AND NOT EXISTS (
    SELECT 1 FROM decision_candidate c
    WHERE c.decision_id=OLD.decision_id
      AND c.selector_key=json_extract(NEW.resolution_action,'$.selector_key'))
BEGIN
    SELECT RAISE(ABORT,'Decision resolution selector must identify an existing candidate');
END;

CREATE TRIGGER decision_transition_guard
BEFORE UPDATE OF status ON decision
WHEN NOT (
    (OLD.status='PENDING' AND NEW.status IN ('PENDING','RESOLVED','EXPIRED','CANCELLED')) OR
    (OLD.status='RESOLVED' AND NEW.status IN ('RESOLVED','APPLIED','CANCELLED')) OR
    (OLD.status IN ('APPLIED','EXPIRED','CANCELLED') AND NEW.status=OLD.status))
BEGIN
    SELECT RAISE(ABORT,'illegal Decision status transition');
END;

CREATE TRIGGER decision_resolution_write_guard
BEFORE UPDATE OF resolution_action,confidence,resolver_type,resolved_at ON decision
WHEN NOT (OLD.status='PENDING' AND NEW.status='RESOLVED')
 AND (NEW.resolution_action IS NOT OLD.resolution_action
   OR NEW.confidence IS NOT OLD.confidence
   OR NEW.resolver_type IS NOT OLD.resolver_type
   OR NEW.resolved_at IS NOT OLD.resolved_at)
BEGIN
    SELECT RAISE(ABORT,'Decision resolution is written exactly once during PENDING to RESOLVED');
END;

CREATE TRIGGER decision_applied_at_guard
BEFORE UPDATE OF applied_at ON decision
WHEN NOT (OLD.status='RESOLVED' AND NEW.status='APPLIED')
 AND NEW.applied_at IS NOT OLD.applied_at
BEGIN
    SELECT RAISE(ABORT,'Decision applied_at is written only during RESOLVED to APPLIED');
END;

CREATE TRIGGER decision_terminal_immutable
BEFORE UPDATE ON decision
WHEN OLD.status IN ('APPLIED','EXPIRED','CANCELLED') AND (
    NEW.status<>OLD.status OR NEW.resolution_action IS NOT OLD.resolution_action OR
    NEW.confidence IS NOT OLD.confidence OR NEW.resolver_type IS NOT OLD.resolver_type OR
    NEW.resolved_at IS NOT OLD.resolved_at OR NEW.applied_at IS NOT OLD.applied_at)
BEGIN
    SELECT RAISE(ABORT,'terminal Decision is immutable');
END;

CREATE TRIGGER decision_terminal_delete_guard
BEFORE DELETE ON decision
WHEN OLD.status IN ('APPLIED','EXPIRED','CANCELLED')
BEGIN
    SELECT RAISE(ABORT,'terminal Decision is immutable');
END;

CREATE TRIGGER decision_candidate_reference_guard
BEFORE INSERT ON decision_candidate
WHEN NOT EXISTS (
    SELECT 1 FROM artifact_reference r
    WHERE r.artifact_id=NEW.artifact_id AND r.owner_type='DECISION'
      AND r.owner_id=NEW.decision_id AND r.ref_kind='candidate')
BEGIN
    SELECT RAISE(ABORT,'Decision candidate requires matching strong ArtifactReference');
END;

CREATE TRIGGER decision_candidate_job_guard
BEFORE INSERT ON decision_candidate
WHEN NOT EXISTS (
    SELECT 1 FROM decision d
    JOIN artifact a ON a.artifact_id=NEW.artifact_id
    JOIN node_execution e ON e.execution_id=a.producer_execution_id
    WHERE d.decision_id=NEW.decision_id AND e.job_id=d.origin_job_id)
BEGIN
    SELECT RAISE(ABORT,'Decision candidate Artifact must be produced by the origin Job');
END;

CREATE TRIGGER decision_candidate_guard
BEFORE INSERT ON decision_candidate
WHEN NOT EXISTS (SELECT 1 FROM decision d WHERE d.decision_id=NEW.decision_id AND d.status='PENDING')
BEGIN
    SELECT RAISE(ABORT,'candidates may only be attached to PENDING Decision');
END;

CREATE TRIGGER decision_candidate_immutable
BEFORE UPDATE ON decision_candidate
BEGIN
    SELECT RAISE(ABORT,'Decision candidate identity is immutable');
END;

CREATE TRIGGER decision_candidate_delete_immutable
BEFORE DELETE ON decision_candidate
BEGIN
    SELECT RAISE(ABORT,'Decision candidates are append-only audit records');
END;

CREATE TRIGGER decision_job_identity_guard
BEFORE INSERT ON decision_job
WHEN NOT EXISTS (
    SELECT 1 FROM decision d WHERE d.decision_id=NEW.decision_id AND d.origin_job_id=NEW.job_id)
 OR (NEW.execution_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM node_execution e WHERE e.execution_id=NEW.execution_id AND e.job_id=NEW.job_id))
BEGIN
    SELECT RAISE(ABORT,'decision_job identity mismatch');
END;

CREATE TRIGGER decision_job_immutable
BEFORE UPDATE ON decision_job
BEGIN
    SELECT RAISE(ABORT,'decision_job identity is immutable');
END;

CREATE TRIGGER decision_job_delete_immutable
BEFORE DELETE ON decision_job
BEGIN
    SELECT RAISE(ABORT,'decision_job links are append-only audit records');
END;

CREATE TRIGGER decision_apply_guard
BEFORE UPDATE OF status ON decision
WHEN NEW.status='APPLIED' AND OLD.status='RESOLVED' AND (
    NOT EXISTS (SELECT 1 FROM boundary_fact f
                WHERE f.source_decision_id=OLD.decision_id AND f.job_id=OLD.origin_job_id
                  AND f.fact_key='decision.'||OLD.decision_id||'.selector'
                  AND f.value_json=json_quote(json_extract(OLD.resolution_action,'$.selector_key')))
    OR NOT EXISTS (
        SELECT 1
        FROM decision_candidate c
        WHERE c.decision_id=OLD.decision_id
          AND c.selector_key=json_extract(OLD.resolution_action,'$.selector_key')
          AND EXISTS (
              SELECT 1 FROM artifact_reference r
              WHERE r.artifact_id=c.artifact_id AND r.ref_kind='selected' AND (
                  (r.owner_type='CHECKPOINT' AND EXISTS (
                      SELECT 1 FROM checkpoint cp
                      WHERE cp.checkpoint_id=r.owner_id AND cp.job_id=OLD.origin_job_id
                        AND cp.status<>'RELEASED'))
                  OR (r.owner_type='DELIVERABLE' AND EXISTS (
                      SELECT 1 FROM deliverable dv
                      WHERE dv.deliverable_id=r.owner_id AND dv.job_id=OLD.origin_job_id
                        AND dv.status IN ('STAGING','PUBLISHED')))
              )
          )
    ))
BEGIN
    SELECT RAISE(ABORT,'Decision apply requires transferred ownership for selected candidate and Boundary fact');
END;

CREATE TRIGGER decision_terminal_releases_refs
AFTER UPDATE OF status ON decision
WHEN NEW.status IN ('APPLIED','EXPIRED','CANCELLED') AND NEW.status<>OLD.status
BEGIN
    DELETE FROM artifact_reference
     WHERE owner_type='DECISION' AND owner_id=NEW.decision_id;
END;

CREATE TRIGGER boundary_fact_source_guard
BEFORE INSERT ON boundary_fact
WHEN NEW.source_decision_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM decision d WHERE d.decision_id=NEW.source_decision_id
      AND d.origin_job_id=NEW.job_id AND d.status IN ('RESOLVED','APPLIED'))
BEGIN
    SELECT RAISE(ABORT,'Boundary fact source Decision must be RESOLVED/APPLIED for the same Job');
END;

CREATE TRIGGER boundary_fact_immutable_update
BEFORE UPDATE ON boundary_fact
BEGIN
    SELECT RAISE(ABORT,'boundary facts are append-only and immutable');
END;
CREATE TRIGGER boundary_fact_immutable_delete
BEFORE DELETE ON boundary_fact
BEGIN
    SELECT RAISE(ABORT,'boundary facts are append-only and immutable');
END;

-- -------------------------------------------------------------------------
-- Timeline identity, ordered contiguous spans and seal completeness.
-- -------------------------------------------------------------------------
CREATE TRIGGER timeline_mapping_insert_draft_only
BEFORE INSERT ON timeline_mapping
WHEN NEW.status<>'DRAFT' OR NEW.sealed_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT,'Timeline mapping must be inserted DRAFT');
END;

CREATE TRIGGER timeline_mapping_artifact_job_guard
BEFORE INSERT ON timeline_mapping
WHEN NOT EXISTS (
    SELECT 1 FROM artifact a
    JOIN node_execution e ON e.execution_id=a.producer_execution_id
    WHERE a.artifact_id=NEW.artifact_id AND e.job_id=NEW.job_id AND a.artifact_role='ASR_SEGMENT')
BEGIN
    SELECT RAISE(ABORT,'timeline artifact must be produced by the same job');
END;

CREATE TRIGGER timeline_mapping_identity_immutable
BEFORE UPDATE OF job_id,segment_id,artifact_id,created_at ON timeline_mapping
BEGIN
    SELECT RAISE(ABORT,'Timeline mapping identity is immutable; rebuild a DRAFT mapping instead');
END;

CREATE TRIGGER timeline_span_draft_only
BEFORE INSERT ON timeline_span
WHEN COALESCE((SELECT status FROM timeline_mapping
               WHERE job_id=NEW.job_id AND segment_id=NEW.segment_id),'MISSING') <> 'DRAFT'
BEGIN
    SELECT RAISE(ABORT,'sealed timeline is immutable');
END;

CREATE TRIGGER timeline_span_order_guard
BEFORE INSERT ON timeline_span
BEGIN
    SELECT CASE WHEN NEW.span_index=0 AND NEW.dst_start_tick<>0
        THEN RAISE(ABORT,'first timeline span must start at destination tick zero') END;
    SELECT CASE WHEN NEW.span_index>0 AND NOT EXISTS (
        SELECT 1 FROM timeline_span p
        WHERE p.job_id=NEW.job_id AND p.segment_id=NEW.segment_id
          AND p.span_index=NEW.span_index-1 AND p.dst_end_tick=NEW.dst_start_tick)
        THEN RAISE(ABORT,'timeline spans must be inserted in contiguous destination order') END;
    SELECT CASE WHEN NEW.span_index <> (
        SELECT COUNT(*) FROM timeline_span s
        WHERE s.job_id=NEW.job_id AND s.segment_id=NEW.segment_id)
        THEN RAISE(ABORT,'timeline span_index must be contiguous') END;
    SELECT CASE WHEN NEW.op='MAP' AND EXISTS (
        SELECT 1 FROM timeline_span p
        WHERE p.job_id=NEW.job_id AND p.segment_id=NEW.segment_id AND p.op='MAP'
          AND p.src_end_tick > NEW.src_start_tick)
        THEN RAISE(ABORT,'mapped source spans must be ordered and non-overlapping') END;
    SELECT CASE WHEN NEW.dst_end_tick > (
        SELECT dst_end_tick FROM timeline_mapping m
        WHERE m.job_id=NEW.job_id AND m.segment_id=NEW.segment_id)
        THEN RAISE(ABORT,'timeline span exceeds mapping destination end') END;
END;

CREATE TRIGGER timeline_span_update_immutable
BEFORE UPDATE ON timeline_span
BEGIN
    SELECT RAISE(ABORT,'timeline spans are append-only; rebuild DRAFT mapping instead');
END;
CREATE TRIGGER timeline_mapping_delete_guard
BEFORE DELETE ON timeline_mapping
WHEN OLD.status='SEALED'
BEGIN
    SELECT RAISE(ABORT,'sealed timeline is immutable');
END;

CREATE TRIGGER timeline_span_delete_guard
BEFORE DELETE ON timeline_span
WHEN (SELECT status FROM timeline_mapping WHERE job_id=OLD.job_id AND segment_id=OLD.segment_id)<>'DRAFT'
BEGIN
    SELECT RAISE(ABORT,'sealed timeline is immutable');
END;

CREATE TRIGGER timeline_mapping_seal_guard
BEFORE UPDATE OF status ON timeline_mapping
WHEN OLD.status='DRAFT' AND NEW.status='SEALED'
BEGIN
    SELECT CASE WHEN NEW.sealed_at IS NULL
        THEN RAISE(ABORT,'sealed timeline requires sealed_at') END;
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM timeline_span s
        WHERE s.job_id=OLD.job_id AND s.segment_id=OLD.segment_id AND s.span_index=0)
        THEN RAISE(ABORT,'timeline must contain at least one span') END;
    SELECT CASE WHEN (
        SELECT MIN(dst_start_tick) FROM timeline_span s
        WHERE s.job_id=OLD.job_id AND s.segment_id=OLD.segment_id) <> 0
        THEN RAISE(ABORT,'timeline spans must start at destination tick zero') END;
    SELECT CASE WHEN (
        SELECT COUNT(*) FROM timeline_span s
        WHERE s.job_id=OLD.job_id AND s.segment_id=OLD.segment_id) <> 1 + (
        SELECT MAX(span_index) FROM timeline_span s
        WHERE s.job_id=OLD.job_id AND s.segment_id=OLD.segment_id)
        THEN RAISE(ABORT,'timeline span_index must be contiguous at seal') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM timeline_span s
        LEFT JOIN timeline_span p ON p.job_id=s.job_id AND p.segment_id=s.segment_id
          AND p.span_index=s.span_index-1
        WHERE s.job_id=OLD.job_id AND s.segment_id=OLD.segment_id AND s.span_index>0
          AND (p.span_index IS NULL OR p.dst_end_tick<>s.dst_start_tick))
        THEN RAISE(ABORT,'timeline destination spans must remain contiguous at seal') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM timeline_span s
        JOIN timeline_span p ON p.job_id=s.job_id AND p.segment_id=s.segment_id
          AND p.span_index<s.span_index AND p.op='MAP'
        WHERE s.job_id=OLD.job_id AND s.segment_id=OLD.segment_id AND s.op='MAP'
          AND p.src_end_tick>s.src_start_tick)
        THEN RAISE(ABORT,'timeline mapped source spans overlap at seal') END;
    SELECT CASE WHEN COALESCE((
        SELECT MAX(dst_end_tick) FROM timeline_span s
        WHERE s.job_id=OLD.job_id AND s.segment_id=OLD.segment_id),-1) <> NEW.dst_end_tick
        THEN RAISE(ABORT,'timeline spans must completely cover destination interval') END;
    SELECT CASE WHEN NEW.mapping_kind='IDENTITY_SLICE' AND (
        (SELECT COUNT(*) FROM timeline_span s WHERE s.job_id=OLD.job_id AND s.segment_id=OLD.segment_id)<>1 OR
        (SELECT op FROM timeline_span s WHERE s.job_id=OLD.job_id AND s.segment_id=OLD.segment_id AND span_index=0)<>'MAP' OR
        NEW.src_timebase_num<>NEW.dst_timebase_num OR NEW.src_timebase_den<>NEW.dst_timebase_den OR
        (SELECT src_end_tick-src_start_tick FROM timeline_span s
          WHERE s.job_id=OLD.job_id AND s.segment_id=OLD.segment_id AND span_index=0) <>
        (SELECT dst_end_tick-dst_start_tick FROM timeline_span s
          WHERE s.job_id=OLD.job_id AND s.segment_id=OLD.segment_id AND span_index=0))
        THEN RAISE(ABORT,'IDENTITY_SLICE requires one MAP span, equal timebases and equal tick duration') END;
END;

CREATE TRIGGER timeline_mapping_terminal_immutable
BEFORE UPDATE ON timeline_mapping
WHEN OLD.status='SEALED' AND (
    NEW.job_id<>OLD.job_id OR NEW.segment_id<>OLD.segment_id OR NEW.artifact_id<>OLD.artifact_id OR
    NEW.mapping_kind<>OLD.mapping_kind OR NEW.src_timebase_num<>OLD.src_timebase_num OR
    NEW.src_timebase_den<>OLD.src_timebase_den OR NEW.dst_timebase_num<>OLD.dst_timebase_num OR
    NEW.dst_timebase_den<>OLD.dst_timebase_den OR NEW.dst_end_tick<>OLD.dst_end_tick OR
    NEW.sealed_at IS NOT OLD.sealed_at)
BEGIN
    SELECT RAISE(ABORT,'sealed timeline is immutable');
END;

-- -------------------------------------------------------------------------
-- Deliverable publication lifecycle.
-- -------------------------------------------------------------------------
CREATE TRIGGER deliverable_insert_staging_only
BEFORE INSERT ON deliverable
WHEN NEW.status<>'STAGING' OR NEW.published_path IS NOT NULL OR NEW.manifest_hash IS NOT NULL
  OR NEW.published_at IS NOT NULL OR NEW.closed_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT,'Deliverable must be inserted STAGING');
END;

CREATE TRIGGER deliverable_identity_immutable
BEFORE UPDATE OF deliverable_id,job_id,materialization_mode,staging_path,created_at ON deliverable
BEGIN
    SELECT RAISE(ABORT,'Deliverable Job and staging identity are immutable');
END;

CREATE TRIGGER deliverable_published_identity_immutable
BEFORE UPDATE ON deliverable
WHEN OLD.status IN ('PUBLISHED','DELETED') AND (
    NEW.job_id<>OLD.job_id OR NEW.materialization_mode<>OLD.materialization_mode OR
    NEW.staging_path<>OLD.staging_path OR NEW.published_path IS NOT OLD.published_path OR
    NEW.manifest_hash IS NOT OLD.manifest_hash OR NEW.published_at IS NOT OLD.published_at)
BEGIN
    SELECT RAISE(ABORT,'published Deliverable identity is immutable');
END;

CREATE TRIGGER deliverable_deleted_terminal_immutable
BEFORE UPDATE ON deliverable
WHEN OLD.status='DELETED' AND (
    NEW.status<>OLD.status OR NEW.closed_at IS NOT OLD.closed_at OR
    NEW.published_path IS NOT OLD.published_path OR NEW.manifest_hash IS NOT OLD.manifest_hash OR
    NEW.published_at IS NOT OLD.published_at OR NEW.created_at IS NOT OLD.created_at)
BEGIN
    SELECT RAISE(ABORT,'deleted Deliverable publication identity is immutable');
END;

CREATE TRIGGER deliverable_transition_guard
BEFORE UPDATE OF status ON deliverable
WHEN NOT (
    (OLD.status='STAGING' AND NEW.status IN ('STAGING','PUBLISHED','FAILED')) OR
    (OLD.status='PUBLISHED' AND NEW.status IN ('PUBLISHED','DELETED')) OR
    (OLD.status IN ('DELETED','FAILED') AND NEW.status=OLD.status))
BEGIN
    SELECT RAISE(ABORT,'illegal Deliverable status transition');
END;

CREATE TRIGGER deliverable_publish_requires_segments
BEFORE UPDATE OF status ON deliverable
WHEN OLD.status='STAGING' AND NEW.status='PUBLISHED'
 AND NOT EXISTS (SELECT 1 FROM deliverable_segment s WHERE s.deliverable_id=OLD.deliverable_id)
BEGIN
    SELECT RAISE(ABORT,'deliverable cannot publish without segments');
END;

CREATE TRIGGER deliverable_publish_contiguous_ordinals
BEFORE UPDATE OF status ON deliverable
WHEN OLD.status='STAGING' AND NEW.status='PUBLISHED' AND (
    (SELECT MIN(ordinal) FROM deliverable_segment WHERE deliverable_id=OLD.deliverable_id)<>0
    OR (SELECT MAX(ordinal)+1 FROM deliverable_segment WHERE deliverable_id=OLD.deliverable_id)<>
       (SELECT COUNT(*) FROM deliverable_segment WHERE deliverable_id=OLD.deliverable_id))
BEGIN
    SELECT RAISE(ABORT,'Deliverable segment ordinals must be contiguous from zero at publish');
END;

CREATE TRIGGER deliverable_close_requires_refs_released
BEFORE UPDATE OF status ON deliverable
WHEN NEW.status IN ('DELETED','FAILED')
 AND EXISTS (SELECT 1 FROM artifact_reference r
             WHERE r.owner_type='DELIVERABLE' AND r.owner_id=OLD.deliverable_id)
BEGIN
    SELECT RAISE(ABORT,'release deliverable refs before closing deliverable');
END;

CREATE TRIGGER deliverable_segment_path_identity_guard
BEFORE INSERT ON deliverable_segment
WHEN NEW.relative_path <> 'segments/' || NEW.segment_id || '.wav'
BEGIN
    SELECT RAISE(ABORT,'Deliverable segment_id must equal the lowercase .wav filename stem');
END;

CREATE TRIGGER deliverable_segment_staging_insert_guard
BEFORE INSERT ON deliverable_segment
WHEN COALESCE((SELECT status FROM deliverable WHERE deliverable_id=NEW.deliverable_id),'MISSING')<>'STAGING'
BEGIN
    SELECT RAISE(ABORT,'Deliverable segments may only be inserted while STAGING');
END;
CREATE TRIGGER deliverable_segment_staging_update_guard
BEFORE UPDATE ON deliverable_segment
BEGIN
    SELECT RAISE(ABORT,'Deliverable segment rows are immutable; delete and reinsert while STAGING');
END;
CREATE TRIGGER deliverable_segment_staging_delete_guard
BEFORE DELETE ON deliverable_segment
WHEN COALESCE((SELECT status FROM deliverable WHERE deliverable_id=OLD.deliverable_id),'MISSING')<>'STAGING'
BEGIN
    SELECT RAISE(ABORT,'published Deliverable segments are immutable');
END;

CREATE TRIGGER deliverable_publish_reference_guard
BEFORE UPDATE OF status ON deliverable
WHEN OLD.status='STAGING' AND NEW.status='PUBLISHED' AND EXISTS (
    SELECT 1 FROM deliverable_segment s
    WHERE s.deliverable_id=OLD.deliverable_id AND NOT EXISTS (
        SELECT 1 FROM artifact_reference r WHERE r.artifact_id=s.artifact_id
          AND r.owner_type='DELIVERABLE' AND r.owner_id=OLD.deliverable_id AND r.ref_kind='segment'))
BEGIN
    SELECT RAISE(ABORT,'every Deliverable segment requires matching strong ArtifactReference');
END;

CREATE TRIGGER deliverable_segment_job_guard
BEFORE INSERT ON deliverable_segment
WHEN NOT EXISTS (
    SELECT 1 FROM deliverable d
    JOIN artifact a ON a.artifact_id=NEW.artifact_id
    JOIN node_execution e ON e.execution_id=a.producer_execution_id
    WHERE d.deliverable_id=NEW.deliverable_id AND d.job_id=e.job_id AND d.status='STAGING'
      AND a.artifact_role='ASR_SEGMENT')
BEGIN
    SELECT RAISE(ABORT,'deliverable segment artifact must belong to same Job and STAGING deliverable');
END;

-- -------------------------------------------------------------------------
-- Resource lease ownership and identity.
-- -------------------------------------------------------------------------
CREATE TRIGGER resource_lease_identity_guard
BEFORE INSERT ON resource_lease
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM job j WHERE j.job_id=NEW.job_id AND j.status NOT IN ('SUCCEEDED','FAILED','STOPPED'))
        THEN RAISE(ABORT,'terminal or missing Job cannot accept new ResourceLease') END;
    SELECT CASE WHEN NEW.execution_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM node_execution e WHERE e.execution_id=NEW.execution_id AND e.job_id=NEW.job_id)
        THEN RAISE(ABORT,'Resource lease execution must belong to the same Job') END;
    SELECT CASE WHEN NEW.expires_at<=strftime('%Y-%m-%dT%H:%M:%fZ','now')
        THEN RAISE(ABORT,'Resource lease expires_at must be in the future') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM resource_lease l WHERE l.resource_kind=NEW.resource_kind AND l.resource_key=NEW.resource_key
          AND l.expires_at>strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        THEN RAISE(ABORT,'resource is already leased') END;
    DELETE FROM resource_lease
     WHERE resource_kind=NEW.resource_kind AND resource_key=NEW.resource_key
       AND expires_at<=strftime('%Y-%m-%dT%H:%M:%fZ','now');
END;

CREATE TRIGGER resource_lease_identity_immutable
BEFORE UPDATE OF lease_id,resource_kind,resource_key,job_id,execution_id,token,created_at ON resource_lease
BEGIN
    SELECT RAISE(ABORT,'Resource lease identity and token are immutable');
END;

CREATE TRIGGER event_immutable_update
BEFORE UPDATE ON event
BEGIN
    SELECT RAISE(ABORT,'events are append-only');
END;
CREATE TRIGGER event_immutable_delete
BEFORE DELETE ON event
BEGIN
    SELECT RAISE(ABORT,'events are append-only');
END;

CREATE INDEX idx_job_batch_status ON job(batch_id,status);
CREATE INDEX idx_plan_job_status ON pipeline_plan(job_id,status);
CREATE INDEX idx_node_plan_ordinal ON pipeline_plan_node(plan_id,ordinal);
CREATE INDEX idx_execution_job_status ON node_execution(job_id,status);
CREATE INDEX idx_artifact_blob ON artifact(blob_id);
CREATE INDEX idx_artifact_ref_owner ON artifact_reference(owner_type,owner_id);
CREATE INDEX idx_decision_status_expiry ON decision(status,expires_at);
CREATE INDEX idx_event_job_id ON event(job_id,event_id);
CREATE INDEX idx_lease_expiry ON resource_lease(expires_at);
