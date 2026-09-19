"""Retention — Phase 13 P1 Stage 1 / Item 2.

An operator capability, NOT a runtime capability: the sweep only ever
acts on TERMINAL projects between runs — it never runs inside run(),
never touches the scheduler, and never deletes anything the harness
would still execute. Deletion itself is the EXISTING R-04
`delete_project` (files + index entry under the R-01 lock).

Design contract (stage1-plan §Item 2):

  * Inert by default — no `retention_policy.json` in the harness root
    means the sweep is a no-op with ZERO side effects (no erasure.log
    is created; existing suites are unaffected).

  * Fail-closed on malformed policy — a policy file that does not
    parse/validate refuses the whole sweep (logged as POLICY_INVALID)
    rather than guessing a window.

  * Terminal-only — a project is sweepable only if its status is not
    one of the protected lifecycle states (pending/running/paused/
    waiting_review/waiting_approval — in-flight, review- and
    approval-gated projects are NEVER swept) AND every task is in a
    terminal state {PASSED, PASS, COMPLETED, NEEDS_REVIEW, BLOCKED,
    SKIPPED}. Any RUNNING/PENDING/FAILED/unknown task keeps the
    project (FAILED keeps it because repair/replan may still revive
    it). Unknown task statuses keep the project — never guess.

  * Backup-first — when the policy requires a verified backup, a
    sweep may only delete a project for which Item 1a's
    `verify_backup` currently passes on at least one backup under the
    policy's backup_root (manifest + size + sha256 + magic; no key
    involved). Otherwise the deletion is REFUSED and audited.

  * Dry-run by default — `sweep_expired(..., execute=False)` records
    SWEEP_PLANNED decisions and deletes nothing; actual deletion
    needs the explicit execute flag (CLI: --execute).

  * Audited — every decision lands in the append-only
    `<root>/erasure.log` (JSONL: sweep id, timestamp, acting mode,
    project_id, decision, reason, deleted file count, backup
    reference, dry_run flag) — ids/counts/reasons only, never case
    content. The log and the policy file are root sidecars: the sweep
    never sweeps them.

Statuses: SWEEP / SWEEP_PLANNED / REFUSED / KEEP per project;
SWEEP_RUN / NO_POLICY / POLICY_INVALID / SWEEP_REFUSED per run.
"""
from __future__ import annotations

import calendar
import json
import os
import time
import uuid

from runtime.state.durable import FileLock, read_json_retry

POLICY_NAME = "retention_policy.json"
POLICY_SCHEMA_VERSION = "1.0"
ERASURE_LOG_NAME = "erasure.log"

# A task in any OTHER state (PENDING/RUNNING/FAILED/FAIL/REPAIRING/
# unknown/missing) keeps the project — fail-closed, never guess.
TERMINAL_TASK_STATUSES = frozenset({
    "PASSED", "PASS", "COMPLETED", "NEEDS_REVIEW", "BLOCKED", "SKIPPED",
})
# Project lifecycle states that must NEVER be swept: in-flight, paused,
# review-gated (final-review protection) and approval-gated projects.
PROTECTED_PROJECT_STATUSES = frozenset({
    "pending", "running", "paused", "waiting_review", "waiting_approval",
})

_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _now_str() -> str:
    return time.strftime(_TS_FORMAT, time.gmtime())


def _parse_ts(value) -> float:
    """Epoch seconds (UTC — timestamps carry the Z suffix), or None when
    unparsable (caller keeps the project)."""
    try:
        return float(calendar.timegm(time.strptime(str(value), _TS_FORMAT)))
    except (ValueError, TypeError, OverflowError):
        return None


def _index_path(harness_root: str) -> str:
    from runtime.harness.harness import _index_path as p
    return p(harness_root)


# ---- policy ---------------------------------------------------------------- #
def load_policy(harness_root: str):
    """(policy, error). (None, None) = no policy file → INERT sweep.
    (None, reason) = malformed policy → fail-closed refusal."""
    path = os.path.join(harness_root, POLICY_NAME)
    if not os.path.isfile(path):
        return None, None
    try:
        doc = read_json_retry(path)
    except (json.JSONDecodeError, OSError, ValueError) as e:
        # a corrupt policy must REFUSE the sweep, never crash it into a
        # half-run and never fall through to guessing a window
        return None, "policy unreadable: %s" % str(e)[:120]
    if not isinstance(doc, dict):
        return None, "policy is not a JSON object"
    if doc.get("schema_version") != POLICY_SCHEMA_VERSION:
        return None, ("unsupported schema_version %r (expected %s)"
                      % (doc.get("schema_version"), POLICY_SCHEMA_VERSION))
    age = doc.get("max_age_days")
    if not isinstance(age, (int, float)) or isinstance(age, bool) \
            or age < 0:
        return None, "max_age_days must be a number >= 0"
    require_backup = doc.get("require_verified_backup", True)
    if not isinstance(require_backup, bool):
        return None, "require_verified_backup must be a boolean"
    backup_root = doc.get("backup_root")
    if require_backup and not (isinstance(backup_root, str) and backup_root):
        return None, ("backup_root is required when "
                      "require_verified_backup is true")
    return {
        "max_age_days": float(age),
        "require_verified_backup": require_backup,
        "backup_root": (os.path.abspath(os.path.join(harness_root,
                                                    backup_root))
                        if backup_root else None),
    }, None


# ---- audit ------------------------------------------------------------------ #
def _audit(harness_root: str, record: dict) -> None:
    """Append one JSONL record to <root>/erasure.log. Ids/counts/reasons
    only — never case content, never key material. Best-effort on OSError
    (a broken audit sink must not half-execute a sweep's bookkeeping)."""
    rec = dict(record)
    rec.setdefault("timestamp", _now_str())
    try:
        os.makedirs(harness_root, exist_ok=True)
        with open(os.path.join(harness_root, ERASURE_LOG_NAME), "a",
                  encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


def read_erasure_log(harness_root: str) -> list:
    path = os.path.join(harness_root, ERASURE_LOG_NAME)
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    out.append({"decision": "AUDIT_CORRUPT_LINE"})
    return out


# ---- eligibility ------------------------------------------------------------ #
def _terminal_reason(project) -> str:
    """'' when the project is terminal (sweepable), else a KEEP reason."""
    status = (project.status or "").lower()
    if status in PROTECTED_PROJECT_STATUSES:
        return "project status %r is protected" % project.status
    for t in (project.tasks or []):
        ts = t.get("status")
        if ts not in TERMINAL_TASK_STATUSES:
            return ("task %s not terminal (status %r)"
                    % (t.get("task_id", "?"), ts))
    return ""


def _find_verified_backup(backup_root: str, project_id: str):
    """Newest VALID Item-1a backup for project_id under backup_root:
    {"backup_id", "backup_dir", "created_at"} or None. Tampered /
    incomplete backups verify False and are skipped (never trusted)."""
    from runtime.state import backup as bk
    if not backup_root or not os.path.isdir(backup_root):
        return None
    best = None
    try:
        names = sorted(os.listdir(backup_root))
    except OSError:
        return None
    for name in names:
        bdir = os.path.join(backup_root, name)
        manifest = read_json_retry(
            os.path.join(bdir, bk.MANIFEST_NAME))
        if not isinstance(manifest, dict) \
                or manifest.get("project_id") != project_id:
            continue
        v = bk.verify_backup(bdir)
        if not v.get("valid"):
            continue
        cand = {"backup_id": manifest.get("backup_id", name),
                "backup_dir": bdir,
                "created_at": manifest.get("created_at", "")}
        if best is None or cand["created_at"] > best["created_at"]:
            best = cand
    return best


# ---- sweep ------------------------------------------------------------------ #
def sweep_expired(harness_root: str, now: float = None, *,
                  execute: bool = False, emit=None) -> dict:
    """Apply the retention policy to every project in the root. Dry-run
    unless execute=True (deletion needs the explicit flag; the CLI maps
    --execute). Per project the decision AND the deletion happen under
    one hold of the R-01 index lock (re-entrant since Item 1b), so a
    concurrent save either lands before the age check (visible to it)
    or after the delete (existing delete_project semantics). Returns:
      {"status": "SWEEP_RUN"|"NO_POLICY"|"POLICY_INVALID"|"SWEEP_REFUSED",
       "dry_run": bool, "swept"/"planned"/"kept"/"refused": [...] }
    """
    emit = emit or (lambda m: None)
    from runtime.harness.harness import list_projects, load_project
    from runtime.state.dataprotection import delete_project
    from runtime import mode as rt_mode

    harness_root = os.path.abspath(harness_root)
    sweep_id = "swp_%s" % uuid.uuid4().hex[:10]
    now = time.time() if now is None else now

    # acting mode — an unknown INSURANCE_AGENT_MODE must BLOCK the sweep
    # (mode.py: never fall back to permissive defaults on a typo)
    try:
        actor_mode = rt_mode.mode()
    except RuntimeError as e:
        _audit(harness_root, {"sweep_id": sweep_id, "project_id": None,
                              "decision": "SWEEP_REFUSED",
                              "reason": str(e)[:200], "dry_run":
                              not execute})
        return {"status": "SWEEP_REFUSED", "reason": str(e)[:300],
                "swept": [], "planned": [], "kept": [], "refused": []}

    policy, err = load_policy(harness_root)
    if err is not None:                      # malformed → refuse to sweep
        _audit(harness_root, {"sweep_id": sweep_id, "project_id": None,
                              "decision": "POLICY_INVALID",
                              "reason": err[:200], "mode": actor_mode,
                              "dry_run": not execute})
        emit("POLICY_INVALID: %s" % err)
        return {"status": "POLICY_INVALID", "reason": err[:300],
                "swept": [], "planned": [], "kept": [], "refused": []}
    if policy is None:                       # no policy → inert no-op
        return {"status": "NO_POLICY", "dry_run": not execute,
                "swept": [], "planned": [], "kept": [], "refused": []}

    window = policy["max_age_days"] * 86400.0
    swept, planned, kept, refused = [], [], [], []

    for entry in list_projects(harness_root):
        pid = entry.get("project_id")
        if not pid:
            continue
        with FileLock(_index_path(harness_root)):
            project = load_project(harness_root, pid)
            reason = ("project not loadable" if project is None
                      else _terminal_reason(project))
            age = None
            if project is not None and not reason:
                ts = _parse_ts(project.updated_at)
                if ts is None:
                    reason = "updated_at unreadable: %r" % project.updated_at
                else:
                    age = now - ts
                    if age < window:
                        reason = ("age %.1fd < window %.1fd"
                                  % (age / 86400.0,
                                     policy["max_age_days"]))
            if reason:                        # KEEP — audited, never deleted
                _audit(harness_root, {
                    "sweep_id": sweep_id, "project_id": pid,
                    "decision": "KEEP", "reason": reason[:200],
                    "mode": actor_mode, "dry_run": not execute})
                kept.append(pid)
                continue
            backup = None
            if policy["require_verified_backup"]:
                backup = _find_verified_backup(policy["backup_root"], pid)
                if backup is None:
                    # backup-first rule: deletion REFUSED + audited
                    _audit(harness_root, {
                        "sweep_id": sweep_id, "project_id": pid,
                        "decision": "REFUSED",
                        "reason": "no verified backup under %s"
                                  % policy["backup_root"],
                        "mode": actor_mode, "dry_run": not execute})
                    refused.append(pid)
                    emit("REFUSED %s: no verified backup" % pid)
                    continue
            if not execute:                   # dry-run: plan, delete nothing
                _audit(harness_root, {
                    "sweep_id": sweep_id, "project_id": pid,
                    "decision": "SWEEP_PLANNED",
                    "reason": "aged terminal project, verified backup %s"
                              % backup["backup_id"],
                    "backup_id": backup["backup_id"] if backup else None,
                    "mode": actor_mode, "dry_run": True})
                planned.append(pid)
                emit("SWEEP_PLANNED %s" % pid)
                continue

            # execute: the EXISTING R-04 erasure primitive (rmtree +
            # index removal under the same re-entrant R-01 lock)
            out = delete_project(harness_root, pid)
            _audit(harness_root, {
                "sweep_id": sweep_id, "project_id": pid,
                "decision": "SWEEP",
                "reason": "aged terminal project (%.1fd), verified backup %s"
                          % ((age or 0) / 86400.0,
                             backup["backup_id"] if backup else "none"),
                "files_deleted": out.get("files_deleted", 0),
                "backup_id": backup["backup_id"] if backup else None,
                "mode": actor_mode, "dry_run": False})
            swept.append(pid)
            emit("SWEEP %s (%d files)" % (pid, out.get("files_deleted", 0)))

    return {"status": "SWEEP_RUN", "dry_run": not execute,
            "swept": swept, "planned": planned, "kept": kept,
            "refused": refused}


if __name__ == "__main__":  # pragma: no cover — operator CLI
    import argparse
    ap = argparse.ArgumentParser(
        description="Item 2 retention sweep (single node, operator-run). "
                    "DRY-RUN by default; --execute is required to delete.")
    ap.add_argument("harness_root")
    ap.add_argument("--execute", action="store_true",
                    help="actually delete aged terminal projects "
                         "(without it: dry-run, nothing is deleted)")
    args = ap.parse_args()
    logs = []
    out = sweep_expired(args.harness_root, execute=args.execute,
                        emit=logs.append)
    for line in logs:
        print(line)
    print("%s dry_run=%s swept=%d planned=%d kept=%d"
          % (out["status"], out.get("dry_run", True),
             len(out.get("swept", [])), len(out.get("planned", [])),
             len(out.get("kept", []))))
    if out["status"] in ("POLICY_INVALID", "SWEEP_REFUSED"):
        print(out.get("reason", ""))
    raise SystemExit(0 if out["status"] in ("SWEEP_RUN", "NO_POLICY") else 1)
