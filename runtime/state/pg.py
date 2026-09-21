"""PostgreSQL persistence layer — Phase 22A.

Implements the SAME persistence interface as the JSON/file backend
(runtime/state/store.py + runtime/harness/harness.py persistence
methods) against PostgreSQL 16.4.

Selected via INSURANCE_AGENT_STATE_BACKEND=postgres.
Default (unset) = the unchanged JSON/file backend.

Contract: business skills NEVER import this module directly. They use
the existing runtime state interfaces (case_state.put_artifact,
store.save, harness._save). This module is the PostgreSQL
implementation behind the persistence seam.

Schema: docs/production/DATABASE_SCHEMA.md
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from typing import Optional

import psycopg2
import psycopg2.extras

# Schema DDL — idempotent (IF NOT EXISTS)
DDL = """
CREATE TABLE IF NOT EXISTS projects (
    project_id  VARCHAR(50) PRIMARY KEY,
    org_id      UUID NOT NULL DEFAULT gen_random_uuid(),
    name        VARCHAR(200) NOT NULL,
    case_id     VARCHAR(50),
    status      VARCHAR(30) NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    extra       JSONB DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS case_states (
    case_id         VARCHAR(50) PRIMARY KEY,
    project_id      VARCHAR(50) NOT NULL REFERENCES projects(project_id),
    org_id          UUID NOT NULL,
    state_version   INTEGER NOT NULL DEFAULT 0,
    state           JSONB NOT NULL,
    state_hash      VARCHAR(64) NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_case_states_org ON case_states(org_id);
CREATE INDEX IF NOT EXISTS idx_case_states_project ON case_states(project_id);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id     VARCHAR(200) PRIMARY KEY,
    case_id         VARCHAR(50) NOT NULL REFERENCES case_states(case_id),
    org_id          UUID NOT NULL,
    artifact_type   VARCHAR(50) NOT NULL,
    skill           VARCHAR(50),
    content         JSONB,
    content_hash    VARCHAR(64) NOT NULL,
    schema_version  VARCHAR(10) DEFAULT '1.0',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_artifact_case_type
    ON artifacts(case_id, artifact_type);
CREATE INDEX IF NOT EXISTS idx_artifact_org ON artifacts(org_id);

CREATE TABLE IF NOT EXISTS events (
    event_id    BIGSERIAL PRIMARY KEY,
    org_id      UUID NOT NULL,
    project_id  VARCHAR(50),
    case_id     VARCHAR(50),
    event_type  VARCHAR(50) NOT NULL,
    payload     JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_events_case_time ON events(case_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_org ON events(org_id);
CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id);

CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id   BIGSERIAL PRIMARY KEY,
    case_id         VARCHAR(50) NOT NULL,
    org_id          UUID NOT NULL,
    task_id         VARCHAR(100),
    state           JSONB NOT NULL,
    state_hash      VARCHAR(64) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_checkpoints_case
    ON checkpoints(case_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_checkpoints_org ON checkpoints(org_id);

CREATE TABLE IF NOT EXISTS approvals (
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
CREATE INDEX IF NOT EXISTS idx_approvals_case ON approvals(case_id);
CREATE INDEX IF NOT EXISTS idx_approvals_org ON approvals(org_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);

CREATE TABLE IF NOT EXISTS knowledge_sources (
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

CREATE TABLE IF NOT EXISTS knowledge_versions (
    version_id      VARCHAR(200) PRIMARY KEY,
    source_id       VARCHAR(100) NOT NULL
                    REFERENCES knowledge_sources(source_id),
    document_id     VARCHAR(200) NOT NULL,
    version         VARCHAR(50) NOT NULL,
    effective_from  DATE NOT NULL,
    effective_to    DATE,
    status          VARCHAR(20) DEFAULT 'ACTIVE',
    license_status  VARCHAR(20) NOT NULL,
    content_hashes  JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _sha256(data) -> str:
    if isinstance(data, str):
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False)
        .encode("utf-8")).hexdigest()


class PostgresStore:
    """PostgreSQL implementation of the persistence seam.

    Maintains the same save/load semantics as the JSON backend:
    - save(state) writes case_state + all artifacts atomically
    - load(case_id) returns the full state dict or None
    - project index upsert is transactional
    """

    def __init__(self, dsn: Optional[str] = None):
        self._dsn = dsn or os.environ.get(
            "AGENT_PG_DSN",
            "host=127.0.0.1 port=5433 dbname=agent_runtime user=agent "
            "password=%s" % os.environ.get("AGENT_PG_PASSWORD", ""))
        self._org_id = str(uuid.UUID(
            os.environ.get("AGENT_ORG_ID",
                           "00000000-0000-0000-0000-000000000001")))

    def connect(self):
        return psycopg2.connect(self._dsn,
                                cursor_factory=psycopg2.extras
                                .RealDictCursor)

    def init_schema(self):
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(DDL)

    # ---- projects --------------------------------------------------- #
    def upsert_project(self, entry: dict) -> None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO projects (project_id, name, case_id, status,
                                          created_at, updated_at, extra)
                    VALUES (%(project_id)s, %(name)s, %(case_id)s,
                            %(status)s, now(), now(), '{}')
                    ON CONFLICT (project_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        case_id = EXCLUDED.case_id,
                        status = EXCLUDED.status,
                        updated_at = now()
                """, {"project_id": entry.get("project_id"),
                      "name": entry.get("name", ""),
                      "case_id": entry.get("case_id"),
                      "status": entry.get("status", "pending")})

    def list_projects(self) -> list:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM projects ORDER BY updated_at DESC")
                rows = cur.fetchall()
                out = []
                for r in rows:
                    out.append({
                        "project_id": r["project_id"],
                        "name": r["name"],
                        "case_id": r["case_id"],
                        "status": r["status"],
                        "created_at": str(r["created_at"]),
                        "updated_at": str(r["updated_at"]),
                    })
                return out

    def get_project(self, project_id: str) -> Optional[dict]:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM projects WHERE project_id = %s",
                    (project_id,))
                r = cur.fetchone()
                if not r:
                    return None
                return dict(r)

    def delete_project(self, project_id: str) -> int:
        """Cascading delete: all related rows removed atomically."""
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM artifacts WHERE case_id IN
                        (SELECT case_id FROM case_states
                         WHERE project_id = %s)
                """, (project_id,))
                cur.execute("""
                    DELETE FROM events WHERE project_id = %s
                        OR case_id IN (SELECT case_id FROM case_states
                                       WHERE project_id = %s)
                """, (project_id, project_id))
                cur.execute("""
                    DELETE FROM checkpoints WHERE case_id IN
                        (SELECT case_id FROM case_states
                         WHERE project_id = %s)
                """, (project_id,))
                cur.execute("""
                    DELETE FROM approvals WHERE project_id = %s
                        OR case_id IN (SELECT case_id FROM case_states
                                       WHERE project_id = %s)
                """, (project_id, project_id))
                cur.execute("DELETE FROM case_states WHERE project_id = %s",
                            (project_id,))
                cur.execute("DELETE FROM projects WHERE project_id = %s",
                            (project_id,))
                return cur.rowcount

    # ---- case states + artifacts (atomic) ----------------------------- #
    def save_state(self, state: dict) -> None:
        """Atomic write: case_state + all new artifacts in one
        transaction. Mirrors store.save() semantics."""
        case_id = state.get("case_id", "")
        state_json = json.dumps(state, ensure_ascii=False,
                                default=str)
        state_hash = _sha256(state_json)
        project_id = state.get("project_id", case_id)
        # ensure project exists
        self.upsert_project({
            "project_id": project_id, "name": project_id,
            "case_id": case_id, "status": "active"})
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO case_states
                        (case_id, project_id, org_id, state_version,
                         state, state_hash, updated_at)
                    VALUES (%s, %s, %s, 1, %s, %s, now())
                    ON CONFLICT (case_id) DO UPDATE SET
                        state_version = case_states.state_version + 1,
                        state = EXCLUDED.state,
                        state_hash = EXCLUDED.state_hash,
                        updated_at = now()
                """, (case_id, project_id, self._org_id,
                      state_json, state_hash))
                # upsert artifacts (from state.artifacts)
                artifacts = state.get("artifacts", {})
                for art_type, art_data in artifacts.items():
                    if not isinstance(art_data, dict):
                        continue
                    art_json = json.dumps(art_data, ensure_ascii=False,
                                           default=str)
                    cur.execute("""
                        INSERT INTO artifacts
                            (artifact_id, case_id, org_id, artifact_type,
                             content, content_hash, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, now())
                        ON CONFLICT (case_id, artifact_type) DO UPDATE SET
                            content = EXCLUDED.content,
                            content_hash = EXCLUDED.content_hash
                    """, ("%s/%s" % (case_id, art_type), case_id,
                          self._org_id, art_type, art_json,
                          _sha256(art_json)))

    def load_state(self, case_id: str) -> Optional[dict]:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT state FROM case_states WHERE case_id = %s",
                    (case_id,))
                r = cur.fetchone()
                if not r:
                    return None
                st = r["state"]
                return st if isinstance(st, dict) else json.loads(st)

    # ---- events ------------------------------------------------------ #
    def append_event(self, case_id: str, project_id: str,
                     event_type: str, payload: dict) -> None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO events (org_id, project_id, case_id,
                                        event_type, payload)
                    VALUES (%s, %s, %s, %s, %s)
                """, (self._org_id, project_id, case_id, event_type,
                      json.dumps(payload, ensure_ascii=False,
                                 default=str)))

    def load_events(self, case_id: str) -> list:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM events WHERE case_id = %s "
                    "ORDER BY event_id", (case_id,))
                return [dict(r) for r in cur.fetchall()]

    # ---- approvals ---------------------------------------------------- #
    def upsert_approval(self, record: dict) -> None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO approvals
                        (approval_id, case_id, org_id, project_id,
                         request_type, status, payload, created_at,
                         updated_at)
                    VALUES (%(approval_id)s, %(case_id)s, %(org_id)s,
                            %(project_id)s, %(request_type)s, %(status)s,
                            %(payload)s, now(), now())
                    ON CONFLICT (approval_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        payload = EXCLUDED.payload,
                        updated_at = now()
                """, {
                    "approval_id": record.get("approval_id", ""),
                    "case_id": record.get("case_id",
                                          record.get("project_id", "")),
                    "org_id": self._org_id,
                    "project_id": record.get("project_id"),
                    "request_type": record.get("request_type", ""),
                    "status": record.get("status", "PENDING"),
                    "payload": json.dumps(record, ensure_ascii=False,
                                          default=str),
                })

    def load_approvals(self, case_id: str) -> list:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT payload FROM approvals "
                    "WHERE case_id = %s ORDER BY created_at",
                    (case_id,))
                out = []
                for r in cur.fetchall():
                    p = r["payload"]
                    out.append(p if isinstance(p, dict)
                              else json.loads(p))
                return out

    # ---- knowledge registry ------------------------------------------- #
    def load_knowledge_sources(self) -> list:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM knowledge_sources ORDER BY source_id")
                return [dict(r) for r in cur.fetchall()]

    def upsert_knowledge_source(self, entry: dict) -> None:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO knowledge_sources
                        (source_id, source_name, source_type, publisher,
                         authority_level, jurisdiction, license_status,
                         canonical_uri)
                    VALUES (%(source_id)s, %(source_name)s,
                            %(source_type)s, %(publisher)s,
                            %(authority_level)s, %(jurisdiction)s,
                            %(license_status)s, %(canonical_uri)s)
                    ON CONFLICT (source_id) DO UPDATE SET
                        source_name = EXCLUDED.source_name,
                        authority_level = EXCLUDED.authority_level,
                        license_status = EXCLUDED.license_status
                """, entry)

    # ---- migration helpers -------------------------------------------- #
    def count(self, table: str) -> int:
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM %s" % table)
                return cur.fetchone()["n"]

    def health(self) -> bool:
        try:
            with self.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return cur.fetchone() is not None
        except Exception:  # noqa: BLE001
            return False
