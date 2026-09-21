"""PostgreSQL Knowledge Governance Registry — Phase 24A.

The authoritative persistence for knowledge governance metadata in
strict modes (CONTROLLED_PILOT / PRODUCTION). The in-process
SourceRegistry remains the READ MODEL; this store owns registration
state and canonical chunk contents.

Layering: this module NEVER imports runtime.* — the connection
factory is INJECTED (production wiring passes
runtime.state.pg.PostgresStore().connect). Tests inject fakes; the
state machine below is fully deterministic without a database.

Lifecycle (Phase 24 spec §14/§15/§18):

    DISCOVERED → INGESTED → REGISTERED → VALIDATED → ACTIVE

Anomalous/terminal states: REJECTED, EXPIRED, SUPERSEDED, INVALID,
RETIRED. An uploaded document is NEVER automatically ACTIVE: activation
is an explicit guarded transition that requires both sides (WeKnora
retrieval + this registry) verified. WeKnora and PostgreSQL are not a
distributed transaction — the state machine makes every intermediate
crash state fail closed (nothing between DISCOVERED and ACTIVE can
ground evidence; governance R2 denies SOURCE_NOT_ACTIVE:<state>).

Hash discipline (spec §12): three DISTINCT anchors, never mixed —
  chunk hash    sha256(chunk content)           evidence unit
  version hash  sha256(ordered chunk hashes)    registration integrity
  document hash sha256(source document bytes)   ingestion anchor (recorded)
"""
from __future__ import annotations

import hashlib
import json
from typing import Callable, Optional

from .registry import SourceRegistry
from .model import RegistryError, REGISTRATION_STATES

# ---- lifecycle ------------------------------------------------------------ #
ACTIVE = "ACTIVE"
LIFECYCLE_STATES = REGISTRATION_STATES
ELIGIBLE_STATE = "ACTIVE"          # the ONLY state that can ground evidence
_TERMINAL = ("REJECTED", "EXPIRED", "SUPERSEDED", "INVALID", "RETIRED")

# Guarded transitions: from -> {allowed to}. No path skips verification,
# no path leaves terminal states, and nothing reaches ACTIVE except
# through VALIDATED.
TRANSITIONS = {
    "DISCOVERED": {"INGESTED", "REJECTED"},
    "INGESTED": {"REGISTERED", "REJECTED"},
    "REGISTERED": {"VALIDATED", "REJECTED"},
    "VALIDATED": {"ACTIVE", "REJECTED"},
    "ACTIVE": {"RETIRED", "EXPIRED", "SUPERSEDED"},
}
for _t in _TERMINAL:
    TRANSITIONS[_t] = set()

SCOPES = ("GLOBAL", "TENANT", "PRIVATE")   # §43: explicit, no fake tenancy

# Idempotent DDL for the knowledge registry tables (extends the Phase
# 22A set; sources/versions gain governance-lifecycle columns, chunks
# are NEW and hold the canonical contents used for F-24 re-anchoring).
KNOWLEDGE_DDL = """
CREATE TABLE IF NOT EXISTS knowledge_sources (
    source_id       VARCHAR(100) PRIMARY KEY,
    source_name     VARCHAR(200),
    source_type     VARCHAR(50) NOT NULL,
    publisher       VARCHAR(200),
    authority_level CHAR(1) NOT NULL,
    jurisdiction    VARCHAR(10) NOT NULL,
    license_status  VARCHAR(20) NOT NULL,
    canonical_uri   VARCHAR(500),
    scope           VARCHAR(20) NOT NULL DEFAULT 'GLOBAL',
    document_hash   VARCHAR(64),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge_versions (
    version_id      VARCHAR(200) PRIMARY KEY,
    source_id       VARCHAR(100) NOT NULL
                    REFERENCES knowledge_sources(source_id),
    document_id     VARCHAR(200) NOT NULL,
    version         VARCHAR(50) NOT NULL,
    effective_from  DATE NOT NULL,
    effective_to    DATE,
    status          VARCHAR(20) NOT NULL DEFAULT 'DISCOVERED',
    license_status  VARCHAR(20) NOT NULL,
    superseded_by   VARCHAR(200),
    version_hash    VARCHAR(64),
    content_hashes  JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kv_source ON knowledge_versions(source_id);
CREATE INDEX IF NOT EXISTS idx_kv_document ON knowledge_versions(document_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_kv_document_active
    ON knowledge_versions(document_id)
    WHERE status = 'ACTIVE';

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    chunk_id        VARCHAR(100) PRIMARY KEY,
    version_id      VARCHAR(200) NOT NULL
                    REFERENCES knowledge_versions(version_id),
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    content_hash    VARCHAR(64) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kc_version
    ON knowledge_chunks(version_id, chunk_index);

CREATE TABLE IF NOT EXISTS knowledge_registry_events (
    event_id    BIGSERIAL PRIMARY KEY,
    version_id  VARCHAR(200),
    event_type  VARCHAR(50) NOT NULL,
    payload     JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kre_version
    ON knowledge_registry_events(version_id, created_at);
"""

# Column migration for databases created by the Phase 22A DDL (the
# tables exist without the Phase 24 governance columns). Idempotent.
KNOWLEDGE_MIGRATION = """
ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS scope VARCHAR(20) NOT NULL DEFAULT 'GLOBAL';
ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS document_hash VARCHAR(64);
ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE knowledge_versions
    ADD COLUMN IF NOT EXISTS superseded_by VARCHAR(200);
ALTER TABLE knowledge_versions
    ADD COLUMN IF NOT EXISTS version_hash VARCHAR(64);
ALTER TABLE knowledge_versions
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
"""


def chunk_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def version_integrity_hash(chunk_hashes_in_order: list) -> str:
    """Version-level anchor: sha256 over the ordered chunk hashes."""
    h = hashlib.sha256()
    for ch in chunk_hashes_in_order:
        h.update((ch or "").encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


class KnowledgeRegistryStore:
    """Authoritative knowledge-registry persistence (fail-closed).

    All state-changing methods validate transitions and refuse to
    weaken an ACTIVE registration; nothing here is best-effort.
    """

    def __init__(self, connect: Callable):
        self._connect = connect

    # ---- schema -------------------------------------------------------- #
    def init_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(KNOWLEDGE_DDL)
                cur.execute(KNOWLEDGE_MIGRATION)

    # ---- sources -------------------------------------------------------- #
    def upsert_source(self, entry: dict) -> None:
        scope = entry.get("scope", "GLOBAL")
        if scope not in SCOPES:
            raise RegistryError("bad scope %r" % scope)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO knowledge_sources
                        (source_id, source_name, source_type, publisher,
                         authority_level, jurisdiction, license_status,
                         canonical_uri, scope, document_hash, updated_at)
                    VALUES (%(source_id)s, %(source_name)s,
                            %(source_type)s, %(publisher)s,
                            %(authority_level)s, %(jurisdiction)s,
                            %(license_status)s, %(canonical_uri)s,
                            %(scope)s, %(document_hash)s, now())
                    ON CONFLICT (source_id) DO UPDATE SET
                        source_name = EXCLUDED.source_name,
                        publisher = EXCLUDED.publisher,
                        authority_level = EXCLUDED.authority_level,
                        jurisdiction = EXCLUDED.jurisdiction,
                        license_status = EXCLUDED.license_status,
                        canonical_uri = EXCLUDED.canonical_uri,
                        scope = EXCLUDED.scope,
                        document_hash = COALESCE(EXCLUDED.document_hash,
                                                 knowledge_sources
                                                 .document_hash),
                        updated_at = now()
                """, {
                    "source_id": entry["source_id"],
                    "source_name": entry.get("source_name", ""),
                    "source_type": entry.get("source_type", "regulation"),
                    "publisher": entry.get("publisher", ""),
                    "authority_level": entry["authority_level"],
                    "jurisdiction": entry["jurisdiction"],
                    "license_status": entry["license_status"],
                    "canonical_uri": entry.get("canonical_uri", ""),
                    "scope": scope,
                    "document_hash": entry.get("document_hash"),
                })

    def get_source(self, source_id: str) -> Optional[dict]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM knowledge_sources "
                            "WHERE source_id = %s", (source_id,))
                r = cur.fetchone()
                return dict(r) if r else None

    # ---- versions -------------------------------------------------------- #
    def upsert_version(self, entry: dict,
                       state: str = "DISCOVERED") -> dict:
        """Idempotent registration of (document, version). Pipeline
        preflight passes content_hashes={} (anchors are written by
        upsert_chunks afterwards); an existing row keeps its stored
        hashes in that case. Non-empty hashes that DIFFER from an
        ACTIVE registration are refused — drift on ACTIVE must go
        through explicit retire/supersede."""
        if state not in LIFECYCLE_STATES:
            raise RegistryError("bad lifecycle state %r" % state)
        version_id = "%s@%s" % (entry["source_id"], entry["version"])
        hashes = entry.get("content_hashes") or {}
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status, content_hashes, version_hash "
                            "FROM knowledge_versions WHERE version_id = %s",
                            (version_id,))
                row = cur.fetchone()
                if row:
                    if row["status"] == "ACTIVE" and hashes and \
                            json.dumps(row["content_hashes"],
                                       sort_keys=True) != json.dumps(
                                           hashes, sort_keys=True):
                        raise RegistryError(
                            "ACTIVE version %s re-registered with "
                            "different hashes — retire/supersede "
                            "explicitly (fail closed)" % version_id)
                    if row["status"] == "ACTIVE":
                        return {"version_id": version_id,
                                "state": row["status"], "noop": True}
                    cur.execute("""
                        UPDATE knowledge_versions SET
                            document_id=%s, effective_from=%s,
                            effective_to=%s, license_status=%s,
                            content_hashes=%s, updated_at=now()
                        WHERE version_id=%s
                    """, (entry["document_id"], entry["effective_from"],
                          entry.get("effective_to"),
                          entry["license_status"],
                          json.dumps(hashes), version_id))
                    return {"version_id": version_id, "state": row["status"],
                            "noop": False}
                cur.execute("""
                    INSERT INTO knowledge_versions
                        (version_id, source_id, document_id, version,
                         effective_from, effective_to, status,
                         license_status, content_hashes, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                """, (version_id, entry["source_id"], entry["document_id"],
                      entry["version"], entry["effective_from"],
                      entry.get("effective_to"), state,
                      entry["license_status"], json.dumps(hashes)))
                return {"version_id": version_id, "state": state,
                        "noop": False}

    def get_version(self, version_id: str) -> Optional[dict]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM knowledge_versions "
                            "WHERE version_id = %s", (version_id,))
                r = cur.fetchone()
                return dict(r) if r else None

    def versions_of_source(self, source_id: str) -> list:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM knowledge_versions "
                            "WHERE source_id = %s "
                            "ORDER BY effective_from", (source_id,))
                return [dict(r) for r in cur.fetchall()]

    # ---- chunks (canonical contents) ------------------------------------- #
    def upsert_chunks(self, version_id: str, chunks: list) -> str:
        """Atomically replace a version's chunk set and re-anchor the
        version integrity hash. chunks: [{chunk_id, chunk_index,
        content}] in document order; content_hash is COMPUTED here —
        caller-provided hashes are never trusted. On an ACTIVE version
        the recomputed set must MATCH the registered anchors (true
        idempotency); a different set is registration drift and is
        REFUSED (supersede explicitly)."""
        rows = sorted(chunks, key=lambda c: c["chunk_index"])
        hashes = {c["chunk_id"]: chunk_hash(c["content"]) for c in rows}
        integ = version_integrity_hash(
            [hashes[c["chunk_id"]] for c in rows])
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status, content_hashes FROM "
                            "knowledge_versions WHERE version_id = %s",
                            (version_id,))
                row = cur.fetchone()
                if not row:
                    raise RegistryError("version %s not registered"
                                        % version_id)
                if row["status"] == "ACTIVE" and json.dumps(
                        row["content_hashes"], sort_keys=True) != \
                        json.dumps(hashes, sort_keys=True):
                    raise RegistryError(
                        "ACTIVE version %s chunk set drifted — supersede/"
                        "retire explicitly (fail closed)" % version_id)
                cur.execute("DELETE FROM knowledge_chunks "
                            "WHERE version_id = %s", (version_id,))
                for c in rows:
                    cur.execute("""
                        INSERT INTO knowledge_chunks
                            (chunk_id, version_id, chunk_index, content,
                             content_hash)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            version_id = EXCLUDED.version_id,
                            chunk_index = EXCLUDED.chunk_index,
                            content = EXCLUDED.content,
                            content_hash = EXCLUDED.content_hash
                    """, (c["chunk_id"], version_id, c["chunk_index"],
                          c["content"], hashes[c["chunk_id"]]))
                cur.execute("""
                    UPDATE knowledge_versions SET
                        content_hashes = %s, version_hash = %s,
                        updated_at = now()
                    WHERE version_id = %s
                """, (json.dumps(hashes), integ, version_id))
        return integ

    def chunks_of(self, version_id: str) -> list:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM knowledge_chunks "
                            "WHERE version_id = %s ORDER BY chunk_index",
                            (version_id,))
                return [dict(r) for r in cur.fetchall()]

    def content_map(self, only_active: bool = True,
                    scope: str = "GLOBAL") -> dict:
        """{document_id: {chunk_id: canonical content}} — the F-24
        re-anchoring data (canonical chunk contents, ACTIVE versions,
        scope-filtered like the read model)."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT v.document_id AS doc, c.chunk_id AS cid,
                           c.content AS content
                    FROM knowledge_chunks c
                    JOIN knowledge_versions v ON v.version_id =
                        c.version_id
                    JOIN knowledge_sources s ON s.source_id =
                        v.source_id
                    WHERE (%s = false OR v.status = 'ACTIVE')
                      AND s.scope = %s
                    ORDER BY c.chunk_index
                """, (only_active, scope))
                out: dict = {}
                for r in cur.fetchall():
                    out.setdefault(r["doc"], {})[r["cid"]] = r["content"]
                return out

    # ---- guarded state machine ------------------------------------------- #
    def transition(self, version_id: str, to_state: str,
                   expected_from: Optional[str] = None) -> dict:
        """Guarded lifecycle transition. Refuses illegal jumps, skips
        over verification steps, or transitions out of terminal states.
        `expected_from` adds an idempotence guard for pipeline reruns."""
        if to_state not in LIFECYCLE_STATES:
            raise RegistryError("bad lifecycle state %r" % to_state)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM knowledge_versions "
                            "WHERE version_id = %s", (version_id,))
                row = cur.fetchone()
                if not row:
                    raise RegistryError("version %s not registered"
                                        % version_id)
                cur_state = row["status"]
                if cur_state == to_state:
                    return {"version_id": version_id, "state": cur_state,
                            "noop": True}
                if expected_from is not None and cur_state != expected_from:
                    raise RegistryError(
                        "transition %s->%s refused: current state is %s "
                        "(expected %s)" % (cur_state, to_state,
                                           cur_state, expected_from))
                if to_state not in TRANSITIONS.get(cur_state, set()):
                    raise RegistryError(
                        "illegal transition %s -> %s (fail closed)"
                        % (cur_state, to_state))
                if to_state == "ACTIVE":
                    self._activation_guards(cur, version_id)
                cur.execute("UPDATE knowledge_versions SET status=%s, "
                            "updated_at=now() WHERE version_id=%s",
                            (to_state, version_id))
                return {"version_id": version_id, "state": to_state,
                        "noop": False}

    def supersede(self, version_id: str, superseded_by: str) -> None:
        """Explicit operator supersession: ACTIVE → SUPERSEDED with the
        replacing version recorded. Required before a newer version of
        the same source can activate over an overlapping window (the
        activation guard refuses ambiguity — Phase 24 §21)."""
        self.transition(version_id, "SUPERSEDED")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE knowledge_versions SET "
                            "superseded_by=%s, updated_at=now() "
                            "WHERE version_id=%s",
                            (superseded_by, version_id))

    def _activation_guards(self, cur, version_id: str) -> None:
        """ACTIVE only when: chunks registered & integrity-anchored, and
        no OTHER active version of the same source has an overlapping
        effective window (ambiguity refuses activation — §21)."""
        cur.execute("SELECT source_id, effective_from, effective_to, "
                    "version_hash, content_hashes FROM knowledge_versions "
                    "WHERE version_id = %s", (version_id,))
        me = cur.fetchone()
        if not me["version_hash"]:
            raise RegistryError(
                "activation refused: %s has no version_hash (chunks not "
                "registered)" % version_id)
        if not me["content_hashes"]:
            raise RegistryError(
                "activation refused: %s has no chunk anchors" % version_id)
        cur.execute("SELECT version_id, effective_from, effective_to "
                    "FROM knowledge_versions WHERE source_id = %s "
                    "AND status = 'ACTIVE' AND version_id != %s",
                    (me["source_id"], version_id))

        def _iso(d):
            return d.isoformat() if hasattr(d, "isoformat") else str(d)

        for other in cur.fetchall():
            a_from, a_to = _iso(me["effective_from"]), \
                _iso(me["effective_to"] or "9999-12-31")
            b_from, b_to = _iso(other["effective_from"]), \
                _iso(other["effective_to"] or "9999-12-31")
            if a_from <= b_to and b_from <= a_to:   # windows overlap
                raise RegistryError(
                    "activation refused: %s window overlaps ACTIVE %s "
                    "(AMBIGUOUS — supersede explicitly)" % (
                        version_id, other["version_id"]))

    # ---- read model -------------------------------------------------------- #
    def entries(self, scope: str = "GLOBAL",
                include_inactive: bool = False) -> list:
        """Registry-entry dicts (SourceRegistry shape). Governance
        metadata is the AGENT registry's truth; scope filters knowledge
        visibility (GLOBAL_ONLY today — §43).

        Pre-chunking versions (DISCOVERED/INGESTED, empty content_hashes)
        are NOT loaded: they have no registered chunk identity, so a hit
        from them is an honest REGISTRY_MISS in governance. Versions from
        REGISTERED on carry anchors and load with their lifecycle status
        (R2 denies SOURCE_NOT_ACTIVE:<state>).
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT v.*, s.source_name, s.source_type, s.publisher,
                           s.jurisdiction AS source_jurisdiction,
                           s.authority_level AS source_authority,
                           s.canonical_uri, s.scope
                    FROM knowledge_versions v
                    JOIN knowledge_sources s USING (source_id)
                    WHERE (%s = true OR v.status = 'ACTIVE')
                      AND s.scope = %s
                      AND v.content_hashes::text != '{}'
                """, (include_inactive, scope))
                rows = [dict(r) for r in cur.fetchall()]
        out = []
        for r in rows:
            out.append({
                "document_id": r["document_id"],
                "source_id": r["source_id"],
                "source_name": r["source_name"] or "",
                "source_type": r["source_type"],
                "publisher": r.get("publisher") or "",
                "authority_level": r["source_authority"],
                "jurisdiction": r["source_jurisdiction"],
                "canonical_uri": r.get("canonical_uri") or "",
                "version": r["version"],
                "effective_from": str(r["effective_from"]),
                "effective_to": (str(r["effective_to"])
                                 if r["effective_to"] else None),
                "status": r["status"],
                "license_status": r["license_status"],
                "content_hashes": r["content_hashes"],
                "version_hash": r.get("version_hash") or "",
            })
        return out

    def load_registry(self, scope: str = "GLOBAL") -> SourceRegistry:
        """Build the governance READ MODEL. Non-ACTIVE versions are
        included with their lifecycle status so governance can deny
        them with an explicit reason (SOURCE_NOT_ACTIVE:<state>) —
        only SourceRegistry validates the same rules as JSON files."""
        return SourceRegistry(self.entries(scope=scope,
                                           include_inactive=True))

    # ---- audit -------------------------------------------------------- #
    def audit(self, event_type: str, payload: dict,
              version_id: str = "") -> None:
        """Append-only registry lifecycle event (operator domain —
        deliberately a SEPARATE table from the runtime's case events:
        ingestion is not an agent-runtime concern, Phase 24 §15)."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO knowledge_registry_events
                        (version_id, event_type, payload)
                    VALUES (%s, %s, %s)
                """, (version_id, event_type,
                      json.dumps(payload, ensure_ascii=False,
                                 default=str)))

    def load_audit(self, version_id: Optional[str] = None) -> list:
        with self._connect() as conn:
            with conn.cursor() as cur:
                if version_id:
                    cur.execute("SELECT * FROM knowledge_registry_events"
                                " WHERE version_id = %s ORDER BY "
                                "event_id", (version_id,))
                else:
                    cur.execute("SELECT * FROM knowledge_registry_events"
                                " ORDER BY event_id")
                return [dict(r) for r in cur.fetchall()]

    # ---- integrity -------------------------------------------------------- #
    def selfcheck(self, version_id: str) -> dict:
        """At-rest tamper detection (§12/§40): stored chunk contents
        must hash to the stored chunk hashes, the ordered chunk hashes
        must reproduce the stored version_hash, and both must match the
        version row's content_hashes projection."""
        chunks = self.chunks_of(version_id)
        v = self.get_version(version_id)
        if not v:
            raise RegistryError("version %s not registered" % version_id)
        problems = []
        for c in chunks:
            if chunk_hash(c["content"]) != c["content_hash"]:
                problems.append("CHUNK_TAMPERED:%s" % c["chunk_id"])
        ordered = [c["content_hash"] for c in chunks]
        if version_integrity_hash(ordered) != (v.get("version_hash") or ""):
            problems.append("VERSION_HASH_MISMATCH")
        reg_hashes = v.get("content_hashes") or {}
        for c in chunks:
            if reg_hashes.get(c["chunk_id"]) != c["content_hash"]:
                problems.append("PROJECTION_DRIFT:%s" % c["chunk_id"])
        return {"version_id": version_id, "ok": not problems,
                "problems": problems}
