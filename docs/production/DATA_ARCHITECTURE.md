# Data Architecture — Phase 21

PostgreSQL target data model. DESIGN ONLY — no schema created,
no migration written, no ORM introduced.

## 1. Data Ownership Matrix

| Data | PostgreSQL | Object Storage | WeKnora | Redis | Memory |
|---|---|---|---|---|---|
| Client facts | ✅ (primary) | No | No | No | Runtime projection |
| CaseState | ✅ (primary) | No | No | No | Runtime projection |
| Task state | ✅ (primary) | No | No | No | Runtime projection |
| Task dependencies | ✅ (primary) | No | No | No | Runtime projection |
| Checkpoints | ✅ (primary) | Snapshot blob | No | No | No |
| Artifacts (metadata) | ✅ (index) | No | No | No | No |
| Artifacts (content) | metadata only | ✅ (primary) | No | No | No |
| Reports | ✅ (metadata) | ✅ (content) | No | No | No |
| Evidence items | ✅ (primary) | No | No | No | No |
| Approval requests | ✅ (primary) | No | No | No | No |
| Approval decisions | ✅ (primary) | No | No | No | No |
| Knowledge registry | ✅ (primary) | No | No | No | Cache |
| Knowledge chunks | No | No | ✅ (primary) | No | Cache |
| Product catalog | ✅ (primary) | No | No | No | Cache |
| Audit events | ✅ (primary) | No | No | No | No |
| Evaluation results | ✅ (primary) | No | No | No | No |
| User identity | ✅ (primary) | No | No | No | No |
| LLM call logs | ✅ (primary) | No | No | No | No |

**Design rationale**: PostgreSQL owns all structured state that needs
transactions, querying, and referential integrity. Object Storage owns
large binary/text content that would bloat the database. WeKnora owns
the full-text index and embeddings (its own storage). Redis owns
nothing in this design (see ADR-010).

## 2. PostgreSQL Target Schema (DESIGN ONLY)

### Identity & Multi-tenancy

```sql
-- Why: multi-tenant production requires user/org separation.
-- Current: single-user, API-key based (runtime/auth.py).
CREATE TABLE users (
    user_id       UUID PRIMARY KEY,
    email         VARCHAR(255) UNIQUE NOT NULL,
    display_name  VARCHAR(100),
    is_active     BOOLEAN DEFAULT true,
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

-- Why: organization boundary for tenant isolation.
CREATE TABLE organizations (
    org_id         UUID PRIMARY KEY,
    name           VARCHAR(200) NOT NULL,
    data_retention_days INTEGER,  -- per-tenant retention policy
    created_at     TIMESTAMPTZ DEFAULT now()
);

-- Why: user ↔ org with role. Maps to existing OWNER/REVIEWER/OPERATOR.
CREATE TABLE memberships (
    user_id  UUID REFERENCES users,
    org_id   UUID REFERENCES organizations,
    role     VARCHAR(20) NOT NULL,  -- OWNER/REVIEWER/OPERATOR
    PRIMARY KEY (user_id, org_id)
);
```

### Project / Case

```sql
-- Why: a "case" is the unit of client work. Maps to current
-- project_id in harness. Currently in projects.json.
CREATE TABLE projects (
    project_id  VARCHAR(50) PRIMARY KEY,
    org_id      UUID REFERENCES organizations,
    name        VARCHAR(200),
    case_id     VARCHAR(50),
    status      VARCHAR(30) NOT NULL, -- running/completed/needs_review/etc
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Why: per-project metadata for audit and isolation.
CREATE TABLE case_metadata (
    project_id  VARCHAR(50) REFERENCES projects,
    key         VARCHAR(100),
    value       JSONB,
    PRIMARY KEY (project_id, key)
);
```

### Agent Runtime (Tasks)

```sql
-- Why: task = one stage of the workflow. Currently in CaseState
-- tasks[] (in-memory + case_state.json).
-- This is the table that enables multi-worker task claiming.
CREATE TABLE tasks (
    task_id         UUID PRIMARY KEY,
    project_id      VARCHAR(50) REFERENCES projects,
    task_type       VARCHAR(50) NOT NULL,  -- maps to skill name
    status          VARCHAR(30) NOT NULL,  -- PENDING/RUNNING/etc
    -- Idempotency: prevents duplicate execution across workers
    idempotency_key VARCHAR(200) UNIQUE,
    -- Concurrency: worker claims a task by setting this + lease_expires
    claimed_by      VARCHAR(100),
    lease_expires   TIMESTAMPTZ,
    -- Ordering: DAG dependencies
    depends_on      UUID[],
    -- Retry
    attempt_count   INTEGER DEFAULT 0,
    max_attempts    INTEGER DEFAULT 3,
    -- Content
    input           JSONB,
    output          JSONB,
    failure_reason  TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_tasks_status ON tasks(status) WHERE status IN ('PENDING','QUEUED');
CREATE INDEX idx_tasks_project ON tasks(project_id);

-- Why: per-attempt records for observability and debugging.
-- Currently "attempts" field in CaseState stage records.
CREATE TABLE task_attempts (
    attempt_id  UUID PRIMARY KEY,
    task_id     UUID REFERENCES tasks,
    attempt_no  INTEGER NOT NULL,
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    outcome     VARCHAR(20),  -- SUCCESS/FAILED/TIMEOUT/CANCELLED
    error_detail TEXT,
    worker_id   VARCHAR(100)
);
```

### Checkpoints

```sql
-- Why: crash recovery. Currently checkpoints.jsonl per project.
-- DB enables: atomic checkpoint + task status update in one
-- transaction.
CREATE TABLE checkpoints (
    checkpoint_id   UUID PRIMARY KEY,
    project_id      VARCHAR(50) REFERENCES projects,
    task_id         UUID REFERENCES tasks,
    -- Artifact fingerprints for tamper detection (existing logic)
    fingerprints    JSONB NOT NULL,
    state_snapshot  JSONB,
    -- Snapshot blob for large state → Object Storage
    snapshot_ref    VARCHAR(500),
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_checkpoint_project ON checkpoints(project_id, created_at DESC);
```

### Artifacts

```sql
-- Why: metadata index for artifacts. Content in Object Storage.
-- Currently artifacts/*.json per project directory.
CREATE TABLE artifacts (
    artifact_id     UUID PRIMARY KEY,
    project_id      VARCHAR(50) REFERENCES projects,
    artifact_type   VARCHAR(50) NOT NULL,  -- maps to skill output type
    skill           VARCHAR(50),
    -- Hash for tamper detection (existing fingerprint logic)
    content_hash    VARCHAR(64) NOT NULL,
    -- Object Storage reference
    storage_uri     VARCHAR(500),
    -- Schema version for contract evolution
    schema_version  VARCHAR(10) DEFAULT '1.0',
    -- Lineage
    input_artifact_ids UUID[],
    evidence_refs   JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_artifact_project_type ON artifacts(project_id, artifact_type);
```

### Approvals

```sql
-- Why: HITL approval state machine. Currently approvals.jsonl.
-- DB enables: atomic status transition + audit trail.
CREATE TABLE approval_requests (
    approval_id     VARCHAR(50) PRIMARY KEY,
    project_id      VARCHAR(50) REFERENCES projects,
    request_type    VARCHAR(50) NOT NULL, -- TASK/FINAL_REVIEW/etc
    status          VARCHAR(20) NOT NULL, -- PENDING/WAITING_HUMAN/
                                          -- APPROVED/REJECTED/EXPIRED
    -- Human-only resolution (existing policy)
    requested_by    VARCHAR(100),
    resolved_by     VARCHAR(100),  -- must be "human:*" actor
    resolved_at     TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    context         JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE approval_decisions (
    decision_id  UUID PRIMARY KEY,
    approval_id  VARCHAR(50) REFERENCES approval_requests,
    actor        VARCHAR(100) NOT NULL,
    decision     VARCHAR(10) NOT NULL, -- APPROVE/REJECT
    reason       TEXT,
    decided_at   TIMESTAMPTZ DEFAULT now()
);
```

### Knowledge Registry

```sql
-- Why: the governance truth source. Currently JSON files
-- (pilot_sources.json, weknora_*_registry.json).
-- DB enables: transactional updates, versioned history, querying.
CREATE TABLE knowledge_sources (
    source_id       VARCHAR(100) PRIMARY KEY,
    source_name     VARCHAR(200),
    source_type     VARCHAR(50) NOT NULL,
    publisher       VARCHAR(200),
    authority_level CHAR(1) NOT NULL,  -- S/A/B/C/D
    jurisdiction    VARCHAR(10) NOT NULL,
    license_status  VARCHAR(20) NOT NULL, -- ALLOWED/RESTRICTED/UNKNOWN
    canonical_uri   VARCHAR(500),
    created_at      TIMESTAMESTZ DEFAULT now()
);

CREATE TABLE knowledge_versions (
    version_id      VARCHAR(100) PRIMARY KEY, -- source_id@version
    source_id       VARCHAR(100) REFERENCES knowledge_sources,
    document_id     VARCHAR(200), -- WeKnora knowledge_filename stem
    version         VARCHAR(50),
    effective_from  DATE NOT NULL,
    effective_to    DATE,
    status          VARCHAR(20) DEFAULT 'ACTIVE',
    -- Chunk hashes for provenance verification (existing logic)
    content_hashes  JSONB NOT NULL,
    weknora_kb_id   VARCHAR(100),
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

### Audit Events

```sql
-- Why: audit trail for compliance. Currently events.jsonl.
-- DB enables: querying, indexing, retention policies.
CREATE TABLE audit_events (
    event_id    BIGSERIAL PRIMARY KEY,
    project_id  VARCHAR(50),
    task_id     UUID,
    event_type  VARCHAR(50) NOT NULL,
    actor       VARCHAR(100),
    payload     JSONB,  -- PII-redacted (existing redact() logic)
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_events_project_time ON audit_events(project_id, created_at);
```

### Evaluation

```sql
-- Why: track evaluation runs and results for regression detection.
-- Currently offline-only eval suites.
CREATE TABLE evaluation_runs (
    eval_id     UUID PRIMARY KEY,
    suite       VARCHAR(100) NOT NULL,
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    overall     VARCHAR(20),  -- PASS/FAIL/BLOCKED
    metadata    JSONB
);

CREATE TABLE evaluation_results (
    result_id   BIGSERIAL PRIMARY KEY,
    eval_id     UUID REFERENCES evaluation_runs,
    case_id     VARCHAR(100),
    status      VARCHAR(10),  -- PASS/FAIL/SKIP
    details     JSONB
);
```

## 3. What Does NOT Go Into PostgreSQL

| Data | Where | Why |
|---|---|---|
| Artifact content (JSON blobs) | Object Storage | Size; PostgreSQL stores metadata + hash only |
| Report rendered content | Object Storage | Large, read-heavy, immutable |
| WeKnora chunks/embeddings | WeKnora's internal storage | WeKnora manages its own index |
| BM25 index (mock engine) | Memory (in-process) | Rebuilt per instance; WeKnora replaces this in production |
| LLM raw prompts/responses | Object Storage (if needed) | Size + PII concerns; only after redaction |
| Snapshot blobs (large state) | Object Storage | Checkpoint stores reference, not content |

## 4. Consistency Model

| Data | Consistency | Why |
|---|---|---|
| Task status transitions | STRONG (DB transaction) | Duplicate execution is a correctness issue |
| Approval status | STRONG (DB transaction) | Double-approval is a compliance violation |
| Artifact creation | STRONG (DB + Object Storage) | Artifact must be fully written before indexed |
| Event log | EVENTUAL (append-only) | Events can lag slightly; audit not real-time |
| Knowledge registry | STRONG (DB transaction) | Governance decisions must be consistent |
| BM25/vector cache | EVENTUAL (in-memory) | Stale cache degrades quality but not correctness |
| Checkpoint snapshots | STRONG (atomic write) | Crash recovery requires consistency |

## 5. Migration Requirements Summary

The key principle: **Skill contracts are UNCHANGED**. The database
is a persistence backend, not business logic. Skills still produce
schema-validated artifacts; the orchestrator still enforces the data
chain. Only the storage layer changes.

```text
Current: Skill → Artifact dict → case_state.json (file)
Target:  Skill → Artifact dict → PostgreSQL + Object Storage
```

The `runtime/state/` module is the seam: it already abstracts
persistence operations (save/load/put_artifact/get_artifact).
A future PostgreSQL implementation would swap this module without
touching the business logic above it.
