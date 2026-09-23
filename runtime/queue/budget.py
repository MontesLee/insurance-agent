"""Run budget & bounded execution — Phase 26C-3.

A budget is RUN-SCOPED, ABSOLUTE and PostgreSQL-authoritative. It is
a CONTROL BOUNDARY beside the 26C-2 run lifecycle — NOT a second
state machine, and it adds NO run states: exhaustion terminalises
the run FAILED with a structured reason (budget_exceeded:<type>) and
the task CANCELLED with the same reason (the 26C-2 expiry pattern).

Ownership: budget binds to run_id (never worker/task/agent) because
task retries, worker recovery and HITL resumes all belong to ONE
run — none of them reset anything (limits are write-once; retry,
replan, resume and crash recovery keep counters and deadline
bit-identical).

Dimensions (V0.1) — NULL limit = UNMETERED for that dimension:
    max_llm_calls · max_input_tokens · max_output_tokens ·
    max_estimated_cost · max_task_attempts · max_repair_attempts ·
    max_replans
plus used-counters, an llm-call RESERVATION counter (§13
race-safe: check+increment is ONE CAS statement), and
usage_unknown / cost_unknown flags.

NO FAKE ACCOUNTING (hard rule):
  * tokens come from real provider usage passed to settle(); a
    missing value is UNKNOWN — recorded as a flag, NEVER added as 0.
  * cost comes from a config-supplied pricing table (model -> in/out
    price per 1K tokens); unknown pricing -> UNKNOWN cost.
  * UNKNOWN under a HARD limit for that dimension means compliance
    CANNOT be proven -> the next control point STOPS the run
    (fail-closed). UNKNOWN never counts as zero.

Enforcement points (all inside runtime.queue.run_control — the
existing control points, no daemon): before start, before
settle-success, before retry, before HITL approval-resume.
Reservation semantics (strictest simple rule, §15/§16): a reserved
call counts against the limit immediately; a provider failure
settles the attempt (call consumed, tokens UNKNOWN) — budget never
inflates from failures, and an abandoned reservation simply remains
counted (fail-closed direction) until the run ends.

Settlement idempotency + auditability: every reserve/settle/
release emits one row in agent_run_budget_events with a UNIQUE
event_key — replays are no-ops, and "why did this run stop?" is
answerable from the ledger (type/limit/used/reserved/remaining).
Exactly-once execution is NOT claimed.
"""
from __future__ import annotations

import json
from typing import Optional

UNKNOWN = "UNKNOWN"          # sentinel — NEVER a numeric 0 stand-in

BUDGET_DDL = """
CREATE TABLE IF NOT EXISTS agent_run_budgets (
    run_id               VARCHAR(120) PRIMARY KEY,
    max_llm_calls        BIGINT,
    max_input_tokens     BIGINT,
    max_output_tokens    BIGINT,
    max_estimated_cost   NUMERIC(18,6),
    max_task_attempts    BIGINT,
    max_repair_attempts  BIGINT,
    max_replans          BIGINT,
    llm_calls_used       BIGINT NOT NULL DEFAULT 0,
    input_tokens_used    BIGINT NOT NULL DEFAULT 0,
    output_tokens_used   BIGINT NOT NULL DEFAULT 0,
    estimated_cost_used  NUMERIC(18,6) NOT NULL DEFAULT 0,
    task_attempts_used   BIGINT NOT NULL DEFAULT 0,
    repair_attempts_used BIGINT NOT NULL DEFAULT 0,
    replans_used         BIGINT NOT NULL DEFAULT 0,
    llm_calls_reserved   BIGINT NOT NULL DEFAULT 0,
    usage_unknown        BOOLEAN NOT NULL DEFAULT FALSE,
    cost_unknown         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS agent_run_budget_events (
    event_id    BIGSERIAL PRIMARY KEY,
    event_key   VARCHAR(160) UNIQUE NOT NULL,
    run_id      VARCHAR(120) NOT NULL,
    kind        VARCHAR(40) NOT NULL,
    detail      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# dimension -> (limit column, used column)
DIMS = {
    "llm_calls": ("max_llm_calls", "llm_calls_used"),
    "input_tokens": ("max_input_tokens", "input_tokens_used"),
    "output_tokens": ("max_output_tokens", "output_tokens_used"),
    "estimated_cost": ("max_estimated_cost", "estimated_cost_used"),
    "task_attempts": ("max_task_attempts", "task_attempts_used"),
    "repair_attempts": ("max_repair_attempts",
                        "repair_attempts_used"),
    "replans": ("max_replans", "replans_used"),
}


class BudgetExceeded(RuntimeError):
    """Hard budget stop — fail closed. `.detail` carries the full
    audit answer (type / limit / used / reserved / remaining)."""

    def __init__(self, detail: dict):
        self.detail = dict(detail)
        super().__init__(
            "budget exceeded: %s (limit=%s used=%s reserved=%s "
            "remaining=%s run=%s)"
            % (detail.get("type"), detail.get("limit"),
               detail.get("used"), detail.get("reserved"),
               detail.get("remaining"), detail.get("run_id")))


class RunBudget:
    """PG-authoritative run budget. Wraps (never changes) the 26A/26B
    task semantics; co-enforced with the 26C-2 deadline at the same
    control points."""

    def __init__(self, connect, pricing: Optional[dict] = None):
        self._connect = connect
        # pricing: {model: {"input_per_1k": float,
        #                   "output_per_1k": float}} — explicit config
        # only; a model absent here has UNKNOWN cost (never 0).
        self.pricing = pricing or {}
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(BUDGET_DDL)

    # ---- configure (write-once, absolute) ------------------------------ #
    def configure(self, run_id: str, **limits) -> dict:
        """Create the budget row. Idempotent AND immutable: an
        existing row is returned as-is — retry/replan/resume/crash
        can never raise or reset a limit (INV-26C3)."""
        cols = {k: v for k, v in limits.items()
                if k in {c for c, _ in DIMS.values()}}
        if not cols:
            cols = {}
        names = ["run_id"] + list(cols)
        vals = [run_id] + list(cols.values())
        ph = ",".join(["%s"] * len(names))
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO agent_run_budgets (%s) VALUES (%s) "
                    "ON CONFLICT (run_id) DO NOTHING"
                    % (",".join(names), ph), vals)
                return self._row(cur, run_id)

    # ---- reads ----------------------------------------------------------- #
    def snapshot(self, run_id: str) -> Optional[dict]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                return self._row(cur, run_id)

    def _row(self, cur, run_id):
        cur.execute("SELECT * FROM agent_run_budgets WHERE "
                    "run_id=%s", (run_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    # ---- reservation (race-safe: ONE CAS statement) ---------------------- #
    def reserve_llm_call(self, run_id: str, n: int = 1,
                         event_key: str = "") -> dict:
        """Reserve n call slots BEFORE the LLM call (§13). One
        UPDATE with the capacity check inside — concurrent workers
        can never oversubscribe max_llm_calls."""
        ek = event_key or _auto_key(run_id, "reserve")
        with self._connect() as conn:
            with conn.cursor() as cur:
                if not self._event(cur, run_id, ek, "RESERVE",
                                   {"n": n}):
                    return {"outcome": "DUPLICATE", "changed": False,
                            "snapshot": self._row(cur, run_id)}
                cur.execute("""
                    UPDATE agent_run_budgets SET
                        llm_calls_reserved = llm_calls_reserved + %s,
                        updated_at = now()
                    WHERE run_id=%s AND (max_llm_calls IS NULL OR
                        llm_calls_reserved + %s <= max_llm_calls)
                """, (n, run_id, n))
                if cur.rowcount != 1:
                    snap = self._row(cur, run_id)
                    raise BudgetExceeded(_detail(
                        "llm_calls", snap, reserved=True))
                return {"outcome": "RESERVED", "changed": True,
                        "snapshot": self._row(cur, run_id)}

    def release_reservation(self, run_id: str, n: int = 1,
                            event_key: str = "") -> dict:
        ek = event_key or _auto_key(run_id, "release")
        with self._connect() as conn:
            with conn.cursor() as cur:
                if not self._event(cur, run_id, ek, "RELEASE",
                                   {"n": n}):
                    return {"outcome": "DUPLICATE", "changed": False,
                            "snapshot": self._row(cur, run_id)}
                cur.execute("""
                    UPDATE agent_run_budgets SET
                        llm_calls_reserved =
                            GREATEST(llm_calls_reserved - %s, 0),
                        updated_at = now()
                    WHERE run_id=%s
                """, (n, run_id))
                return {"outcome": "RELEASED", "changed": True,
                        "snapshot": self._row(cur, run_id)}

    # ---- settlement (idempotent via event_key; UNKNOWN never 0) ---------- #
    def settle(self, run_id: str, event_key: str, *,
               llm_calls: int = 0,
               input_tokens=UNKNOWN, output_tokens=UNKNOWN,
               cost=UNKNOWN,
               task_attempts: int = 0, repair_attempts: int = 0,
               replans: int = 0) -> dict:
        """Record ACTUAL usage. ONE transaction: the ledger INSERT
        (UNIQUE event_key) gates every delta — a replayed settle is
        a visible NO-OP. Token/cost values equal to the UNKNOWN
        sentinel set the unknown-flags instead of adding 0."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                if not self._event(cur, run_id, event_key, "SETTLE", {
                        "llm_calls": llm_calls,
                        "input_tokens": _v(input_tokens),
                        "output_tokens": _v(output_tokens),
                        "cost": _v(cost),
                        "task_attempts": task_attempts,
                        "repair_attempts": repair_attempts,
                        "replans": replans}):
                    return {"outcome": "DUPLICATE", "changed": False,
                            "snapshot": self._row(cur, run_id)}
                in_t = _num(input_tokens)
                out_t = _num(output_tokens)
                cost_v = _num(cost)
                cur.execute("""
                    UPDATE agent_run_budgets SET
                        llm_calls_used = llm_calls_used + %s,
                        llm_calls_reserved =
                            GREATEST(llm_calls_reserved - %s, 0),
                        input_tokens_used = input_tokens_used
                            + COALESCE(%s, 0),
                        output_tokens_used = output_tokens_used
                            + COALESCE(%s, 0),
                        estimated_cost_used = estimated_cost_used
                            + COALESCE(%s, 0),
                        task_attempts_used = task_attempts_used + %s,
                        repair_attempts_used =
                            repair_attempts_used + %s,
                        replans_used = replans_used + %s,
                        usage_unknown = usage_unknown OR %s,
                        cost_unknown = cost_unknown OR %s,
                        updated_at = now()
                    WHERE run_id=%s
                """, (llm_calls, llm_calls,
                      in_t, out_t, cost_v,
                      task_attempts, repair_attempts, replans,
                      in_t is None, cost_v is None, run_id))
                return {"outcome": "SETTLED", "changed": True,
                        "snapshot": self._row(cur, run_id)}

    def estimate_cost(self, model: str, input_tokens, output_tokens):
        """Config-driven cost (§9). Unknown model/prices -> UNKNOWN
        (the sentinel, never 0)."""
        p = self.pricing.get(model)
        if not p or _num(input_tokens) is None \
                or _num(output_tokens) is None:
            return UNKNOWN
        return round(_num(input_tokens) / 1000.0
                     * float(p["input_per_1k"])
                     + _num(output_tokens) / 1000.0
                     * float(p["output_per_1k"]), 6)

    # ---- gate (control points) -------------------------------------------- #
    def check(self, run_id: str, *, extra_task_attempts: int = 0,
              soft_threshold: float = 0.8) -> dict:
        """Raise BudgetExceeded when any HARD limit is violated, an
        UNKNOWN flags a hard-limited token/cost dimension (compliance
        unprovable -> fail closed), or usage + extra would exceed.
        Soft threshold crossings only emit a ledger event (audit),
        never change behavior."""
        snap = self.snapshot(run_id)
        if snap is None:
            return snap or {}
        for dim, (lim_c, used_c) in DIMS.items():
            lim = snap.get(lim_c)
            if lim is None:
                continue
            lim = float(lim)          # NUMERIC columns arrive as
                                      # Decimal — coerce once
            used = float(snap.get(used_c) or 0)
            extra = extra_task_attempts if dim == "task_attempts" \
                else 0
            reserved = (snap.get("llm_calls_reserved") or 0) \
                if dim == "llm_calls" else 0
            if dim == "llm_calls":
                used = used + reserved
            if used + extra > lim:
                raise BudgetExceeded(_detail(dim, snap))
            if used + extra >= soft_threshold * lim:
                self._soft_event(run_id, dim, used + extra, lim)
        # UNKNOWN under a hard limit: cannot prove compliance
        if snap.get("usage_unknown"):
            if snap.get("max_input_tokens") is not None \
                    or snap.get("max_output_tokens") is not None:
                raise BudgetExceeded(_detail(
                    "usage_unknown_under_hard_token_budget", snap))
        if snap.get("cost_unknown") \
                and snap.get("max_estimated_cost") is not None:
            raise BudgetExceeded(_detail(
                "cost_unknown_under_hard_cost_budget", snap))
        return snap

    # ---- internals ---------------------------------------------------------- #
    def _event(self, cur, run_id, key, kind, detail) -> bool:
        """Append-once ledger row. False = duplicate (idempotent)."""
        cur.execute("""
            INSERT INTO agent_run_budget_events
                (event_key, run_id, kind, detail)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (event_key) DO NOTHING
        """, (key[:160], run_id, kind,
              json.dumps(detail or {}, ensure_ascii=False)))
        return cur.rowcount == 1

    def _soft_event(self, run_id, dim, used, limit):
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    # deterministic key per (dim, used): repeated
                    # checks at the same crossing record ONE event
                    self._event(cur, run_id,
                                "%s:soft:%s:%s" % (run_id, dim, used),
                                "SOFT_WARNING",
                                {"type": dim, "used": used,
                                 "limit": limit})
        except Exception:  # noqa: BLE001 — observation only
            pass


def _num(v):
    """Numeric value, or None when UNKNOWN/absent (NEVER 0)."""
    if v is None or v == UNKNOWN:
        return None
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return None


def _v(v):
    return UNKNOWN if _num(v) is None else _num(v)


def _auto_key(run_id, tag):
    import time
    return "%s:%s:%d" % (run_id, tag, int(time.time() * 1000))


def _detail(dim, snap, reserved=False):
    lim_c, used_c = DIMS.get(dim, (dim, dim))
    lim = snap.get(lim_c) if snap else None
    used = snap.get(used_c) if snap else None
    res = (snap.get("llm_calls_reserved") or 0) if snap else 0
    if dim == "llm_calls":
        used = (used or 0) + res
    rem = None
    if isinstance(lim, (int, float)) and isinstance(used,
                                                    (int, float)):
        rem = max(0, lim - used)
    return {"type": "MAX_%s" % dim.upper(), "limit": lim,
            "used": used, "reserved": res if reserved else None,
            "remaining": rem, "run_id": snap.get("run_id") if snap
            else None}
