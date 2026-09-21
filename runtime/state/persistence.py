"""Production persistence selector — Phase 22B.

Enforces the architecture rule: in STRICT modes (CONTROLLED_PILOT,
PRODUCTION), PostgreSQL is the ONLY authoritative persistence layer.
JSON/file is legacy/migration only. No silent fallback exist — the
fallback path is architecturally absent from this module.

Rules (P22B fail-closed matrix):

  | Mode             | JSON  | PostgreSQL | Unavailable PG | startup |
  |------------------|-------|------------|----------------|--------|
  | DEMO             | ✅    | optional   | N/A            | PASS   |
  | EVALUATION       | ✅    | optional   | N/A            | PASS   |
  | CONTROLLED_PILOT | ❌    | REQUIRED   | FAIL           | FAIL   |
  | PRODUCTION       | ❌    | REQUIRED   | FAIL           | FAIL   |

Selected via INSURANCE_AGENT_STATE_BACKEND=json|postgres.
Default in non-strict modes: json (backward compatible).
In strict modes: postgres (REQUIRED, not configurable to json).
"""
from __future__ import annotations

import os
from typing import Optional

BACKEND_ENV = "INSURANCE_AGENT_STATE_BACKEND"
BACKEND_JSON = "json"
BACKEND_POSTGRES = "postgres"
_VALID_BACKENDS = (BACKEND_JSON, BACKEND_POSTGRES)

PG_DSN_ENV = "AGENT_PG_DSN"
PG_PASSWORD_ENV = "AGENT_PG_PASSWORD"

# Tables required at startup (schema validation).
REQUIRED_TABLES = (
    "projects", "case_states", "artifacts", "events", "checkpoints",
    "approvals", "knowledge_sources", "knowledge_versions",
)


class PersistenceConfigError(RuntimeError):
    """Startup-time persistence configuration failure — fail closed.
    The caller MUST NOT continue; there is no fallback."""


def resolve_backend() -> str:
    """Determine the persistence backend from mode + env. In strict
    modes PostgreSQL is REQUIRED and JSON is REJECTED. In non-strict
    modes the default is JSON (backward compatible)."""
    from runtime import mode as rt_mode
    m = rt_mode.mode()  # may raise for unknown mode (fail closed)
    explicit = os.environ.get(BACKEND_ENV, "").strip().lower()
    if explicit and explicit not in _VALID_BACKENDS:
        raise PersistenceConfigError(
            "P-DB-07: unsupported INSURANCE_AGENT_STATE_BACKEND=%r "
            "(supported: %s)" % (explicit, "/".join(_VALID_BACKENDS)))

    if m in rt_mode.STRICT_MODES:
        if explicit == BACKEND_JSON:
            raise PersistenceConfigError(
                "P-DB-08: runtime mode %s requires PostgreSQL; "
                "INSURANCE_STATE_BACKEND=json is FORBIDDEN (JSON is "
                "legacy/migration only in strict modes)" % m)
        return BACKEND_POSTGRES
    return explicit or BACKEND_JSON


def validate_startup(backend: Optional[str] = None) -> dict:
    """Full startup validation. Returns info on success. Raises
    PersistenceConfigError on ANY failure. No fallback path — the
    caller must abort the process on this exception."""
    from runtime import mode as rt_mode
    backend = backend or resolve_backend()
    info = {
        "runtime_mode": rt_mode.mode(),
        "persistence_backend": backend,
        "database_identity": "none",
        "schema_version": "none",
        "migration_valid": False,
    }

    if backend == BACKEND_JSON:
        if info["runtime_mode"] in rt_mode.STRICT_MODES:
            # unreachable (resolve_backend prevents it), but fail
            # closed anyway — defense in depth
            raise PersistenceConfigError(
                "P-DB-08: JSON backend in %s (defensive check)"
                % info["runtime_mode"])
        info["migration_valid"] = True
        return info

    # backend == postgres: validate everything
    dsn = os.environ.get(PG_DSN_ENV, "")
    password = os.environ.get(PG_PASSWORD_ENV, "")
    if not dsn and not password:
        raise PersistenceConfigError(
            "P-DB-01: PostgreSQL required but no %s or %s configured"
            % (PG_DSN_ENV, PG_PASSWORD_ENV))

    try:
        from runtime.state.pg import PostgresStore
        store = PostgresStore()
    except Exception as e:  # noqa: BLE001 — import/driver failure
        raise PersistenceConfigError(
            "P-DB-06: PostgreSQL driver failure: %s" % str(e)[:120])

    # P-DB-02: connectivity
    if not store.health():
        raise PersistenceConfigError(
            "P-DB-02: PostgreSQL unavailable (health check failed)")

    # P-DB-03/05: schema + required tables
    import psycopg2
    try:
        with store.connect() as conn:
            with conn.cursor() as cur:
                for table in REQUIRED_TABLES:
                    cur.execute(
                        "SELECT EXISTS (SELECT 1 FROM information_schema"
                        ".tables WHERE table_name = %s)", (table,))
                    if not cur.fetchone()["exists"]:
                        raise PersistenceConfigError(
                            "P-DB-05: required table %r missing" % table)
                cur.execute("SELECT current_database() AS db")
                info["database_identity"] = cur.fetchone()["db"]
    except PersistenceConfigError:
        raise
    except psycopg2.OperationalError as e:
        raise PersistenceConfigError(
            "P-DB-02: PostgreSQL connection failed: %s" % str(e)[:120])

    info["schema_version"] = "1.0"
    info["migration_valid"] = True
    return info


def get_store():
    """Return the active persistence store. In strict modes this is
    ALWAYS a PostgresStore (or startup fails). In non-strict modes
    this returns None (caller uses the existing JSON/file path —
    the PostgresStore is available for migration/testing but is
    NOT the runtime path)."""
    backend = resolve_backend()
    if backend == BACKEND_POSTGRES:
        validate_startup(backend)
        from runtime.state.pg import PostgresStore
        return PostgresStore()
    return None  # caller uses existing JSON/file persistence


def redact_dsn(dsn: str) -> str:
    """For logging: strip password from any connection string."""
    import re
    return re.sub(r"password=[^ ]+", "password=***", dsn)
