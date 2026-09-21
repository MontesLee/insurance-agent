# Database Schema — Phase 22A

PostgreSQL 16.4 · Designed per CURRENT_PERSISTENCE_MAP.md + Phase 21
DATA_ARCHITECTURE.md. Schema-first: reviewed before any runtime code
touches the database.

## Connection

```text
Host:     127.0.0.1
Port:     5433 (separate from WeKnora's 5432)
Database: agent_runtime
User:     agent
Password: env AGENT_PG_PASSWORD (never committed)
```

## Tables

### projects (from projects.json)

```sql
CREATE TABLE projects (
    project_id  VARCHAR(50) PRIMARY KEY,
    org_id      UUID NOT NULL DEFAULT gen_random_uuid(),
    name        VARCHAR(200) NOT NULL,
    case_id     VARCHAR(50),
    status      VARCHAR(30) NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    extra       JSONB DEFAULT '{}'
);
```

### case_states (from case_state.json)

```sql
CREATE TABLE case_states (
    case_id         VARCHAR(50) PRIMARY KEY,
    project_id      VARCHAR(50) NOT NULL REFERENCES projects(project_id),
    org_id          UUID NOT NULL,
    state_version   INTEGER NOT NULL DEFAULT 0,
    -- Full CaseState JSON (tasks, stages, artifacts, workflow)
    state           JSONB NOT NULL,
    state_hash      VARCHAR(64) NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Org isolation enforced at query level
CREATE INDEX idx_case_states_org ON case_states(org_id);
CREATE INDEX idx_case_states_project ON case_states(project_id);
```

### artifacts (from artifacts/*.json, metadata only)

```sql
CREATE TABLE artifacts (
    artifact_id     VARCHAR(100) PRIMARY KEY, -- "{case_id}/{artifact_type}"
    case_id         VARCHAR(50) NOT NULL REFERENCES case_states(case_id),
    org_id          UUID NOT NULL,
    artifact_type   VARCHAR(50) NOT NULL,
    skill           VARCHAR(50),
    content         JSONB, -- content stored inline (pilot; Object Storage later)
    content_hash    VARCHAR(64) NOT NULL,
    schema_version  VARCHAR(10) DEFAULT '1.0',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX idx_artifact_case_type ON artifacts(case_id, artifact_type);
CREATE INDEX idx_artifact_org ON artifacts(org_id);
```

### events (from events.jsonl)

```sql
CREATE TABLE events (
    event_id    BIGSERIAL PRIMARY KEY,
    org_id      UUID NOT NULL,
    project_id  VARCHAR(50),
    case_id     VARCHAR(50),
    event_type  VARCHAR(50) NOT NULL,
    payload     JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_events_case_time ON events(case_id, created_at);
CREATE INDEX idx_events_org ON events(org_id);
CREATE INDEX idx_events_project ON events(project_id);
```

### checkpoints (from checkpoints.jsonl)

```sql
CREATE TABLE checkpoints (
    checkpoint_id   BIGSERIAL PRIMARY KEY,
    case_id         VARCHAR(50) NOT NULL,
    org_id          UUID NOT NULL,
    task_id         VARCHAR(100),
    state           JSONB NOT NULL,
    state_hash      VARCHAR(64) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_checkpoints_case ON checkpoints(case_id, created_at DESC);
CREATE INDEX idx_checkpoints_org ON checkpoints(org_id);
```

### approvals (from approvals.jsonl)

```sql
CREATE TABLE approvals (
    approval_id     VARCHAR(50) PRIMARY KEY,
    case_id         VARCHAR(50) NOT NULL,
    org_id          UUID NOT NULL,
    project_id      VARCHAR(50),
    request_type    VARCHAR(50) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    payload         JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_approvals_case ON approvals(case_id);
CREATE INDEX idx_approvals_org ON approvals(org_id);
CREATE INDEX idx_approvals_status ON approvals(status);
```

### knowledge_sources (from JSON registry files)

```sql
CREATE TABLE knowledge_sources (
    source_id       VARCHAR(100) PRIMARY KEY,
    source_name     VARCHAR(200),
    source_type     VARCHAR(50) NOT NULL,
    publisher       VARCHAR(200),
    authority_level CHAR(1) NOT NULL,
    jurisdiction    VARCHAR(10) NOT NULL,
    license_status  VARCHAR(20) NOT NULL,
    canonical_uri   VARCHAR(500),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE knowledge_versions (
    version_id      VARCHAR(200) PRIMARY KEY, -- "{source_id}@{version}"
    source_id       VARCHAR(100) NOT NULL REFERENCES knowledge_sources(source_id),
    document_id     VARCHAR(200) NOT NULL,
    version         VARCHAR(50) NOT NULL,
    effective_from  DATE NOT NULL,
    effective_to    DATE,
    status          VARCHAR(20) DEFAULT 'ACTIVE',
    license_status  VARCHAR(20) NOT NULL,
    content_hashes  JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## Schema Design Principles

1. **org_id on every customer-owned table** — cross-tenant isolation
   enforced at query level (WHERE org_id = current_org).
2. **JSONB for state** — CaseState is a rich JSON structure; normalizing
   every field into separate tables would be premature and fragile.
3. **content_hash on state/artifacts/checkpoints** — preserves the
   existing fingerprint-based tamper detection.
4. **No triggers or stored procedures** — all logic in the Python
   repository layer. PostgreSQL is persistence, not business logic.
5. **BIGSERIAL for events** — global ordering preserved.
6. **UUID for org_id** — multi-tenant ready from day one.

## Transaction Boundaries

| Transaction | Tables touched | Atomicity |
|---|---|---|
| Case save | case_states + artifacts | Must be atomic (state and artifacts together) |
| Approval decision | approvals | Atomic status transition |
| Event append | events | Single insert (autonomous) |
| Checkpoint write | checkpoints | Single insert (autonomous) |
| Project create | projects + case_states | Atomic (project + initial state) |
| Project delete | projects + case_states + artifacts + events + checkpoints + approvals | Atomic cascade |
