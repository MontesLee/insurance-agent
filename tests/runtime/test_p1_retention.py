"""Phase 13 P1 Stage 1 / Item 2 — Retention / sweep / erasure-audit tests.

Covers: policy loading (valid / malformed fail-closed / absent = inert),
positive sweep (aged terminal + verified backup → swept + audited; younger
kept; dry-run plans but deletes nothing), terminality gates (non-terminal
task statuses and protected project statuses never swept, with AND without
a valid backup), backup-first rule (no / tampered / wrong-project backup →
REFUSED + audited; policy opt-out), audit-log discipline (append-only,
ids/counts only, survives sweeps, logs dry-run decisions), recovery
(re-run, concurrent saves, unknown-mode refusal) and runtime neutrality.
"""
from __future__ import annotations

import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from runtime.harness import LongRunningHarness  # noqa: E402
from runtime.state import backup as bk  # noqa: E402
from runtime.state import retention as rt  # noqa: E402

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_dir():
    return tempfile.mkdtemp(prefix="ret_", dir=os.path.join(REPO, "tmp"))


_TS = "%Y-%m-%dT%H:%M:%SZ"


def days_ago(n: float) -> str:
    return time.strftime(_TS, time.gmtime(time.time() - n * 86400))


def make_project(root, *, statuses=("PASSED", "PASSED"),
                 status="ready_for_delivery", age_days=40.0):
    """A project whose on-disk shape the sweep reads: task statuses,
    project status, aged updated_at. Retention only READS these files,
    so shaping them directly (then _save) is the right unit seam."""
    h = LongRunningHarness(root)
    n = max(1, len(statuses))
    p = h.create_project("p", task_graph={"tasks": [
        {"task_id": "t%d" % i, "task_type": "client_profile"}
        for i in range(n)]})
    for t, st in zip(p.tasks, statuses):
        t["status"] = st
    p.status = status
    p.updated_at = days_ago(age_days)
    p._save()
    return p


def write_policy(root, **kw):
    doc = {"schema_version": "1.0", "max_age_days": 30,
           "require_verified_backup": True,
           "backup_root": kw.pop("backup_root", "backups")}
    doc.update(kw)
    with open(os.path.join(root, rt.POLICY_NAME), "w",
              encoding="utf-8") as f:
        json.dump(doc, f)


def write_raw_policy(root, text):
    with open(os.path.join(root, rt.POLICY_NAME), "w",
              encoding="utf-8") as f:
        f.write(text)


def backup_of(root, pid, name="backups"):
    dest = os.path.join(root, name)
    out = bk.backup_project(root, pid, dest)
    assert out["status"] == "BACKUP_CREATED", out
    return out["backup_dir"]


def idx(root):
    from runtime.harness.harness import _index_read
    return _index_read(root)


def log_lines(root):
    return rt.read_erasure_log(root)


# ------------------------------------------------------------------ #
# S1 — policy loading: inert default, fail-closed malformed
# ------------------------------------------------------------------ #
@section
def test_s1_policy_loading(c: Checks):
    d = fresh_dir()
    try:
        p = make_project(d)
        pid = p.project_id
        # no policy → INERT even with execute=True: nothing deleted,
        # and not even an erasure.log is created
        out = rt.sweep_expired(d, execute=True)
        c.chk("S1: no policy → NO_POLICY", out["status"] == "NO_POLICY")
        c.chk("S1: inert — project dir survives",
              os.path.isdir(os.path.join(d, pid)))
        c.chk("S1: inert — index entry survives",
              any(e["project_id"] == pid for e in idx(d)))
        c.chk("S1: inert — no erasure.log created",
              not os.path.exists(os.path.join(d, rt.ERASURE_LOG_NAME)))

        # malformed policies → POLICY_INVALID, nothing swept, one audit
        bad = {
            "not json": "{oops",
            "not an object": "[1,2]",
            "bad schema_version": json.dumps(
                {"schema_version": "2.0", "max_age_days": 30}),
            "missing max_age_days": json.dumps(
                {"schema_version": "1.0"}),
            "negative age": json.dumps(
                {"schema_version": "1.0", "max_age_days": -5}),
            "string age": json.dumps(
                {"schema_version": "1.0", "max_age_days": "30"}),
            "string require flag": json.dumps(
                {"schema_version": "1.0", "max_age_days": 30,
                 "require_verified_backup": "yes"}),
            "backup required but no backup_root": json.dumps(
                {"schema_version": "1.0", "max_age_days": 30,
                 "require_verified_backup": True}),
        }
        for name, text in bad.items():
            write_raw_policy(d, text)
            out = rt.sweep_expired(d)
            c.chk("S1: malformed (%s) → POLICY_INVALID" % name,
                  out["status"] == "POLICY_INVALID", out)
            c.chk("S1: malformed (%s) → nothing swept",
                  os.path.isdir(os.path.join(d, pid)))
        entries = log_lines(d)
        c.chk("S1: malformed refusals audited",
              sum(1 for e in entries if e["decision"] == "POLICY_INVALID")
              == len(bad), len(entries))
        c.chk("S1: audit names the reason",
              all(e.get("reason") for e in entries
                  if e["decision"] == "POLICY_INVALID"))

        # valid minimal policy parses with the safe default (backup
        # required unless explicitly opted out)
        write_raw_policy(d, json.dumps(
            {"schema_version": "1.0", "max_age_days": 7,
             "require_verified_backup": False}))
        pol, err = rt.load_policy(d)
        c.chk("S1: valid minimal policy loads", err is None
              and pol is not None and pol["max_age_days"] == 7.0)
        c.chk("S1: default max_age_days is days-scale", isinstance(
            pol["max_age_days"], float))
        pol2, _ = rt.load_policy(d)
        c.chk("S1: backup not required → backup_root None",
              pol2["require_verified_backup"] is False
              and pol2["backup_root"] is None)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ #
# S2 — positive sweep: dry-run plans, execute sweeps, age window
# ------------------------------------------------------------------ #
@section
def test_s2_positive_sweep(c: Checks):
    d = fresh_dir()
    try:
        old = make_project(d, age_days=40)          # past the 30d window
        young = make_project(d, age_days=5)         # inside it
        pid_old, pid_young = old.project_id, young.project_id
        backup_of(d, pid_old)
        backup_of(d, pid_young)
        write_policy(d)

        out = rt.sweep_expired(d)                   # DRY-RUN (default)
        c.chk("S2: dry-run → SWEEP_RUN", out["status"] == "SWEEP_RUN")
        c.chk("S2: dry-run flag reported", out["dry_run"] is True)
        c.chk("S2: aged project planned, young kept",
              out["planned"] == [pid_old] and out["kept"] == [pid_young],
              out)
        c.chk("S2: dry-run deleted nothing",
              os.path.isdir(os.path.join(d, pid_old))
              and len(idx(d)) == 2)
        ent = [e for e in log_lines(d) if e["project_id"] == pid_old]
        c.chk("S2: SWEEP_PLANNED audited with backup ref",
              any(e["decision"] == "SWEEP_PLANNED" and e.get("backup_id")
              for e in ent), ent)
        c.chk("S2: KEEP (young) audited with window reason",
              any(e["decision"] == "KEEP" and "window" in e["reason"]
              for e in log_lines(d)))

        out = rt.sweep_expired(d, execute=True)     # EXECUTE
        c.chk("S2: execute sweeps exactly the aged one",
              out["swept"] == [pid_old], out)
        c.chk("S2: swept dir gone",
              not os.path.exists(os.path.join(d, pid_old)))
        c.chk("S2: index entry removed",
              [e["project_id"] for e in idx(d)] == [pid_young])
        c.chk("S2: young project intact",
              os.path.isdir(os.path.join(d, pid_young)))
        sw = [e for e in log_lines(d)
              if e["decision"] == "SWEEP" and e["project_id"] == pid_old]
        from runtime import mode as rt_mode
        c.chk("S2: SWEEP audited with file count + mode",
              len(sw) == 1 and sw[0].get("files_deleted", 0) > 0
              and sw[0].get("mode") == rt_mode.mode(), sw)
        c.chk("S2: dry-run entries survive the execute run (append-only)",
              any(e["decision"] == "SWEEP_PLANNED" for e in log_lines(d)))
        c.chk("S2: backup itself untouched by the sweep",
              os.path.isdir(os.path.join(d, "backups")))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ #
# S3 — terminality gates: nothing in-flight / gated is ever swept
# ------------------------------------------------------------------ #
@section
def test_s3_terminality_gates(c: Checks):
    d = fresh_dir()
    try:
        write_policy(d, require_verified_backup=False)
        cases = [
            ("RUNNING task", {"statuses": ("PASSED", "RUNNING")}),
            ("PENDING task", {"statuses": ("PENDING", "PASSED")}),
            ("FAILED task", {"statuses": ("FAILED",)}),
            ("REPAIRING task", {"statuses": ("REPAIRING",)}),
            ("unknown task status", {"statuses": ("WEIRD",)}),
            ("waiting_review project", {"status": "waiting_review"}),
            ("waiting_approval project", {"status": "waiting_approval"}),
            ("paused project", {"status": "paused"}),
            ("pending project", {"status": "pending"}),
            ("running project", {"status": "running"}),
        ]
        pids = {}
        for name, kw in cases:
            p = make_project(d, **kw)
            pids[p.project_id] = name
        out = rt.sweep_expired(d, execute=True)
        c.chk("S3: no protected project swept", out["swept"] == [], out)
        c.chk("S3: all protected projects kept",
              set(out["kept"]) == set(pids), out)
        for pid, name in pids.items():
            c.chk("S3: %s dir survives" % name,
                  os.path.isdir(os.path.join(d, pid)))
        reasons = {e["project_id"]: e["reason"] for e in log_lines(d)
                   if e["decision"] == "KEEP"}
        c.chk("S3: KEEP reasons name the protection",
              any("protected" in r for r in reasons.values())
              and any("not terminal" in r for r in reasons.values()))

        # even WITH a valid backup, a non-terminal project stays:
        # back up while quiescent, THEN flip a task to RUNNING
        p = make_project(d, statuses=("PASSED", "PASSED"))
        backup_of(d, p.project_id)
        p.tasks[1]["status"] = "RUNNING"
        p._save()                       # updated_at stays aged (set above)
        out = rt.sweep_expired(d, execute=True)
        c.chk("S3: aged+backed-up but RUNNING task → still kept",
              p.project_id in out["kept"] and p.project_id not in out["swept"])

        # genuinely terminal variants ARE sweepable
        for st in ("ready_for_delivery", "cancelled"):
            p = make_project(d, status=st)
            out = rt.sweep_expired(d, execute=True)
            c.chk("S3: %s project swept" % st,
                  p.project_id in out["swept"], out)

        # index entry whose dir vanished → KEEP, not a crash
        p = make_project(d)
        shutil.rmtree(os.path.join(d, p.project_id))
        out = rt.sweep_expired(d, execute=True)
        c.chk("S3: un-loadable project kept (fail-closed)",
              p.project_id in out["kept"])
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ #
# S4 — backup-first rule
# ------------------------------------------------------------------ #
@section
def test_s4_backup_first(c: Checks):
    d = fresh_dir()
    try:
        write_policy(d)                      # require_verified_backup=True
        p = make_project(d)
        pid = p.project_id
        os.makedirs(os.path.join(d, "backups"), exist_ok=True)
        out = rt.sweep_expired(d, execute=True)
        c.chk("S4: empty backup root → REFUSED",
              out["refused"] == [pid] and out["swept"] == [], out)
        c.chk("S4: refused project NOT deleted",
              os.path.isdir(os.path.join(d, pid)))
        c.chk("S4: REFUSED audited",
              any(e["decision"] == "REFUSED" and "no verified backup"
              in e["reason"] for e in log_lines(d)))
        # dry-run reports the refusal too (what execute would do)
        c.chk("S4: dry-run also refuses (decision visible before delete)",
              rt.sweep_expired(d)["refused"] == [pid])

        # tampered backup verifies False → REFUSED
        bdir = backup_of(d, pid)
        target = os.path.join(bdir, "project.json")
        with open(target, "ab") as f:
            f.write(b"x")                    # size+hash now mismatch
        c.chk("S4: tampered backup fails verify_backup",
              not bk.verify_backup(bdir)["valid"])
        out = rt.sweep_expired(d, execute=True)
        c.chk("S4: tampered backup → REFUSED, project survives",
              out["refused"] == [pid]
              and os.path.isdir(os.path.join(d, pid)))

        # a backup of a DIFFERENT project does not authorize this one
        shutil.rmtree(bdir, ignore_errors=True)
        other = make_project(d, statuses=("PASSED",), age_days=40)
        backup_of(d, other.project_id)
        out = rt.sweep_expired(d, execute=True)
        c.chk("S4: other project's backup does not authorize",
              pid in out["refused"] and other.project_id in out["swept"],
              out)

        # newest VALID backup is the recorded reference
        p2 = make_project(d)
        b_old = backup_of(d, p2.project_id)
        with open(os.path.join(b_old, bk.MANIFEST_NAME),
                  encoding="utf-8") as f:
            m = json.load(f)
        m["created_at"] = "2020-01-01T00:00:00Z"   # manifest is not hashed
        with open(os.path.join(b_old, bk.MANIFEST_NAME), "w",
                  encoding="utf-8") as f:
            json.dump(m, f)
        b_new = backup_of(d, p2.project_id)
        new_id = json.load(open(os.path.join(b_new, bk.MANIFEST_NAME),
                                encoding="utf-8"))["backup_id"]
        out = rt.sweep_expired(d, execute=True)
        sw = [e for e in log_lines(d) if e["decision"] == "SWEEP"
              and e["project_id"] == p2.project_id]
        c.chk("S4: swept with the newest valid backup recorded",
              p2.project_id in out["swept"] and sw
              and sw[-1].get("backup_id") == new_id, sw)

        # explicit policy opt-out: no backup required → sweeps anyway
        p3 = make_project(d)
        write_policy(d, require_verified_backup=False)
        out = rt.sweep_expired(d, execute=True)
        c.chk("S4: policy opt-out sweeps without any backup",
              p3.project_id in out["swept"], out)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ #
# S5 — audit-log discipline
# ------------------------------------------------------------------ #
@section
def test_s5_audit_discipline(c: Checks):
    d = fresh_dir()
    try:
        p = make_project(d)
        backup_of(d, p.project_id)
        write_policy(d)
        rt.sweep_expired(d)                  # dry-run first
        rt.sweep_expired(d, execute=True)
        lines = log_lines(d)
        c.chk("S5: log is parseable JSONL with required fields",
              all({"sweep_id", "timestamp", "decision", "mode"}
              <= set(e) for e in lines), lines[:2])
        c.chk("S5: dry-run decision logged", any(
            e["decision"] == "SWEEP_PLANNED" and e["dry_run"] is True
            for e in lines))
        c.chk("S5: execute decision logged as dry_run=false", any(
            e["decision"] == "SWEEP" and e["dry_run"] is False
            for e in lines))
        raw = open(os.path.join(d, rt.ERASURE_LOG_NAME),
                   encoding="utf-8").read()
        c.chk("S5: no case_id (content) in the audit log",
              p.case_id not in raw)
        c.chk("S5: no ciphertext/key material in the audit log",
              "IA1:" not in raw and "Fernet" not in raw)
        # the sweep never deletes its own audit trail or the policy
        c.chk("S5: erasure.log + policy survive the sweep",
              os.path.exists(os.path.join(d, rt.ERASURE_LOG_NAME))
              and os.path.exists(os.path.join(d, rt.POLICY_NAME)))
        # re-run after everything is swept: no error, log intact
        out = rt.sweep_expired(d, execute=True)
        c.chk("S5: re-run on empty root is a clean no-op sweep",
              out["status"] == "SWEEP_RUN" and out["swept"] == []
              and out["planned"] == [] and out["kept"] == [])
        c.chk("S5: audit log preserved across the re-run",
              len(log_lines(d)) >= len(lines))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ #
# S6 — recovery, concurrency, mode fail-closed, CLI
# ------------------------------------------------------------------ #
@section
def test_s6_recovery_concurrency_mode_cli(c: Checks):
    d = fresh_dir()
    env_saved = {"INSURANCE_AGENT_MODE": os.environ.get(
        "INSURANCE_AGENT_MODE")}
    try:
        # unknown INSURANCE_AGENT_MODE must BLOCK the sweep (mode.py
        # philosophy: never fall back to permissive defaults)
        p = make_project(d)
        backup_of(d, p.project_id)
        write_policy(d)
        os.environ["INSURANCE_AGENT_MODE"] = "bogus_mode"
        out = rt.sweep_expired(d, execute=True)
        c.chk("S6: unknown mode → SWEEP_REFUSED",
              out["status"] == "SWEEP_REFUSED", out)
        c.chk("S6: unknown mode → nothing deleted",
              os.path.isdir(os.path.join(d, p.project_id)))
        c.chk("S6: refusal audited",
              any(e["decision"] == "SWEEP_REFUSED" for e in log_lines(d)))
        os.environ.pop("INSURANCE_AGENT_MODE")

        # concurrent saves on another project while the sweep executes
        live = make_project(d, age_days=0.0001)   # young → must survive
        stop = threading.Event()
        errs = []

        def _saver():
            try:
                while not stop.is_set():
                    live.updated_at = days_ago(0)
                    live._save()
            except Exception as e:  # noqa: BLE001
                errs.append(e)
        th = threading.Thread(target=_saver)
        th.start()
        try:
            out = rt.sweep_expired(d, execute=True)
        finally:
            stop.set()
            th.join(timeout=5)
        c.chk("S6: saver thread had no errors", not errs, errs)
        c.chk("S6: aged project swept under concurrent saves",
              out["swept"] == [p.project_id], out)
        c.chk("S6: concurrently-saved project survives",
              os.path.isdir(os.path.join(d, live.project_id)))
        c.chk("S6: index stays valid JSON with the survivor",
              [e["project_id"] for e in idx(d)] == [live.project_id])

        # CLI: dry-run default, --execute required to delete
        p2 = make_project(d)
        backup_of(d, p2.project_id)
        env = dict(os.environ)
        env.pop("INSURANCE_AGENT_MODE", None)
        env["INSURANCE_AGENT_NO_DOTENV"] = "1"
        r = subprocess.run(
            [sys.executable, "-m", "runtime.state.retention", d],
            cwd=REPO, env=env, capture_output=True, text=True,
            timeout=120)
        c.chk("S6: CLI dry-run exits 0",
              r.returncode == 0 and "NO_POLICY" not in r.stdout, r.stdout)
        c.chk("S6: CLI dry-run deleted nothing",
              os.path.isdir(os.path.join(d, p2.project_id)))
        r = subprocess.run(
            [sys.executable, "-m", "runtime.state.retention", d,
             "--execute"],
            cwd=REPO, env=env, capture_output=True, text=True,
            timeout=120)
        c.chk("S6: CLI --execute sweeps the aged project",
              r.returncode == 0
              and not os.path.exists(os.path.join(d, p2.project_id)),
              r.stdout + r.stderr)
        os.remove(os.path.join(d, rt.POLICY_NAME))   # root is policy-less
        r = subprocess.run(
            [sys.executable, "-m", "runtime.state.retention", d],
            cwd=REPO, env=env, capture_output=True, text=True,
            timeout=120)
        c.chk("S6: CLI on policy-less root reports inert NO_POLICY",
              r.returncode == 0 and "NO_POLICY" in r.stdout, r.stdout)
    finally:
        for k, v in env_saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ #
# S7 — runtime neutrality (structural)
# ------------------------------------------------------------------ #
@section
def test_s7_runtime_neutrality(c: Checks):
    src = inspect.getsource(rt)
    for banned in ("_run_parallel", "_execute_stage", "_run_eval_and_repair",
                   "SpecialistAgentExecutor", "ApprovalManager",
                   "create_request"):
        c.chk("S7: retention never references %s" % banned,
              banned not in src)
    for needed in ("delete_project", "verify_backup", "FileLock"):
        c.chk("S7: retention builds on %s" % needed, needed in src)
    # nothing in the runtime wires the sweep into any execution path
    wired = []
    for root, _dirs, files in os.walk(os.path.join(REPO, "runtime")):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            if path.endswith(os.path.join("state", "retention.py")):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    body = f.read()
            except OSError:
                continue
            if "state.retention" in body or "state import retention" in body \
                    or "import retention" in body:
                wired.append(path)
    c.chk("S7: no runtime module imports the sweep", wired == [], wired)


def main():
    return run_sections(SECTIONS, "p1_item2_retention_log.txt",
                        "P1 ITEM 2 RETENTION")


if __name__ == "__main__":
    sys.exit(main())
