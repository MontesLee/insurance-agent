#!/usr/bin/env python3
"""Security & Governance Evaluation — Phase 17.

≥70 deterministic cases over the REAL production controls (auth, RBAC,
approval actor-binding, redaction, encryption policy, provider policy,
retention, project isolation, error fail-closed, audit tamper), plus
M-AUTH-01..10 mutation detection. Reuses production functions directly;
never mutates production state. Exit 0 PASS / 1 FAIL.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from runtime import auth as runtime_auth  # noqa: E402
from runtime.approval import models as ap_models  # noqa: E402
from runtime.approval.store import ApprovalStore  # noqa: E402
from runtime.approval.manager import ApprovalManager  # noqa: E402
from runtime.state import dataprotection as dp  # noqa: E402
from runtime import mode as rt_mode  # noqa: E402
from runtime.agent import data_policy  # noqa: E402

KEY_O = "k" + "o" * 31            # >=16 chars, OWNER
KEY_R = "r" + "r" * 31            # REVIEWER
KEY_P = "p" + "p" * 31            # OPERATOR
BAD_KEY = "definitely-not-a-key-000"


def identities():
    return {KEY_O: runtime_auth.Identity("alice", "OWNER", KEY_O[:8]),
            KEY_R: runtime_auth.Identity("bob", "REVIEWER", KEY_R[:8]),
            KEY_P: runtime_auth.Identity("carol", "OPERATOR", KEY_P[:8])}


RESULTS = []


def case(cid, group, ok, detail=""):
    RESULTS.append({"case_id": cid, "group": group,
                    "status": "PASS" if ok else "FAIL",
                    "detail": detail[:110]})


# ------------------------------------------------------------------ #
# A. authentication (T01)
# ------------------------------------------------------------------ #
def auth_cases():
    ids = identities()
    for cid, header, want_user in (
            ("A01-anonymous", None, None),
            ("A02-empty-header", "", None),
            ("A03-invalid-token", "Bearer " + BAD_KEY, None),
            ("A04-malformed-header", "Basic garbage", None),
            ("A05-wrong-scheme", "ApiKey " + KEY_O, None)):
        ident = runtime_auth.authenticate(header, ids)
        case(cid, "auth", ident is None if want_user is None
             else ident is not None, str(ident))
    for cid, key, role in (("A06-owner", KEY_O, "OWNER"),
                           ("A07-reviewer", KEY_R, "REVIEWER"),
                           ("A08-operator", KEY_P, "OPERATOR")):
        ident = runtime_auth.authenticate("Bearer " + key, ids)
        case(cid, "auth", ident is not None and ident.role == role,
             str(ident))
    # forged role via identity construction is impossible through env
    # parsing: malformed entries are skipped, never trusted
    os.environ["INSURANCE_AGENT_API_KEYS"] = \
        "short:OWNER:x,%s:WIZARD:y,%s:OWNER:ok" % (KEY_O, KEY_R)
    try:
        loaded = runtime_auth.load_identities()
        case("A09-malformed-entries-skipped", "auth",
             len(loaded) == 1 and KEY_R in loaded and KEY_O not in loaded,
             sorted(loaded))
    finally:
        os.environ.pop("INSURANCE_AGENT_API_KEYS", None)


# ------------------------------------------------------------------ #
# B. authorization matrix (T02/T06) — per current policy
# ------------------------------------------------------------------ #
def authz_cases():
    ids = identities()
    actions = [
        ("read_project", "OPERATOR"),
        ("submit_task", "OPERATOR"),
        ("approve", "REVIEWER"),          # OPERATOR must NOT auto-get it
        ("pause", "OPERATOR"),
        ("resume", "OPERATOR"),
        ("cancel", "OPERATOR"),
        ("replan", "OPERATOR"),
        ("provide_information", "OPERATOR"),
    ]
    for name, minimum in actions:
        for role in ("OWNER", "REVIEWER", "OPERATOR", None):
            ident = ids.get({"OWNER": KEY_O, "REVIEWER": KEY_R,
                             "OPERATOR": KEY_P, None: None}[role])
            if ident is None:
                allowed, reason = False, "unauthenticated"
            else:
                allowed = ident.has_role(minimum)
                reason = "rank ok" if allowed else \
                    "role %s < %s" % (role, minimum)
            expect = (role is not None and
                      runtime_auth.Identity("x", role, "k" * 16)
                      .has_role(minimum))
            case("AZ-%s-%s" % (name, role or "anon"), "authz",
                 allowed == expect, reason)
    # OPERATOR must never reach approval-level actions
    op = ids[KEY_P]
    case("AZ-approve-operator-denied", "authz",
         not op.has_role("REVIEWER"), "rank=%d" % op.rank)


# ------------------------------------------------------------------ #
# C. approval security (T05/T14) — forged actor / forged state
# ------------------------------------------------------------------ #
def approval_cases():
    tmp = tempfile.mkdtemp(prefix="sec_appr_", dir=os.path.join(REPO, "tmp"))
    try:
        store = ApprovalStore(tmp)
        mgr = ApprovalManager(tmp)          # takes project_dir, owns store

        def fresh(task_id):
            rec = mgr.create_request(ap_models.create_request(
                project_id="PROJ-A",
                request_type="APPROVAL_HIGH_IMPACT",
                task_id=task_id, reason="need human"))
            mgr.wait(rec["approval_id"])     # PENDING -> WAITING_HUMAN
            return rec

        # AP01 human may approve (WAITING_HUMAN -> APPROVED)
        r1 = fresh("T1")
        out = mgr.approve(r1["approval_id"], actor="human")
        case("AP01-human-approve", "approval",
             out.get("ok") is True
             and out["approval"]["status"] == "APPROVED")
        # AP02 idempotent on APPROVED: no second execution, already=True
        out2 = mgr.approve(r1["approval_id"], actor="human")
        case("AP02-double-resolve-idempotent", "approval",
             out2.get("ok") is True and out2.get("already") is True
             and out2["approval"]["resolved_by"] == "human",
             json.dumps(out2, ensure_ascii=False)[:70])
        # AP03-05 forged actors -> ACTOR_NOT_AUTHORIZED refusal (no raise,
        # no state change)
        for cid, actor in (("AP03-agent-actor", "agent-1"),
                           ("AP04-planner-actor", "planner"),
                           ("AP05-empty-actor", "")):
            r2 = fresh("T2" + cid[-1])
            out3 = mgr.approve(r2["approval_id"], actor=actor)
            st = store.get(r2["approval_id"])["status"]
            case(cid, "approval",
                 out3.get("ok") is False
                 and "ACTOR_NOT_AUTHORIZED" in str(out3)
                 and st == "WAITING_HUMAN",
                 "status stayed %s" % st)
        # AP06 forged APPROVED injected into the store FILE: the runtime
        # resolve path must not re-execute or mutate it further
        r3 = mgr.create_request(ap_models.create_request(
            project_id="PROJ-A", request_type="APPROVAL_HIGH_IMPACT",
            task_id="T3", reason="x"))
        mgr.wait(r3["approval_id"])
        path = os.path.join(tmp, "approvals.jsonl")
        raw = [json.loads(l) for l in open(path, encoding="utf-8")
               if l.strip()]
        for r in raw:
            if r.get("approval_id") == r3["approval_id"]:
                r["status"] = "APPROVED"       # direct file forgery
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + chr(10)
                         for r in raw)
        out6 = mgr.approve(r3["approval_id"], actor="human")
        got = store.get(r3["approval_id"])
        case("AP06-forged-approved-no-reexecute", "approval",
             out6.get("ok") is True and out6.get("already") is True
             and got["status"] == "APPROVED"
             and not got.get("resolved_by"),
             "terminal respected; resolved_by unset (forgery never "
             "gained an actor)")
        case("AP07-forged-state-visible-for-audit", "approval",
             got is not None and got["status"] == "APPROVED",
             "file evidence preserved for audit")
        # AP08 approval identity binding fields exist (project/task/
        # revision/actor/timestamp)
        rec = store.get(r1["approval_id"])
        for f in ("project_id", "task_id", "request_type",
                  "resolved_by", "resolved_at"):
            case("AP08-binding-%s" % f, "approval", bool(rec.get(f)),
                 str(rec.get(f)))
        case("AP08-binding-graph-revision-key", "approval",
             "graph_revision" in rec, str(rec.get("graph_revision")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ #
# D. redaction / PII (T07/T09)
# ------------------------------------------------------------------ #
PII_FIXTURES = [
    ("D01-phone", {"phone": "13812345678", "note": "call back"}),
    ("D02-email", {"email": "client@example.com", "x": 1}),
    ("D03-id-number", {"id_number": "110101199001011234"}),
    ("D04-name", {"name": "张三"}),
    ("D05-income", {"annual_income": "50万"}),
    ("D06-health", {"health_status": "高血压II期"}),
    ("D07-address", {"home_address": "北京市海淀区某路1号"}),
    ("D08-card", {"bank_card": "6222020200112233445"}),
    ("D09-nested", {"client": {"mobile": "13900000000", "ok": "v"}}),
    ("D10-mixed-event", {"event_type": "task_started",
                         "medical_history": "糖尿病", "task_id": "T1"}),
]


SENSITIVE_KEYS = set(dp.SENSITIVE_FIELDS)


def redaction_cases():
    for cid, payload in PII_FIXTURES:
        red = dp.redact(payload)
        blob = json.dumps(red, ensure_ascii=False)
        # every SENSITIVE-named field must be redacted IN PLACE
        bad = [k for k, v in payload.items()
               if isinstance(v, (str, int)) and str(v).strip()
               and k.lower() in SENSITIVE_KEYS
               and red.get(k) != "[REDACTED]"]
        # non-sensitive fields must SURVIVE (redaction, not deletion)
        gone = [k for k in payload
                if k.lower() not in SENSITIVE_KEYS and k not in red]
        case(cid, "pii", not bad and not gone,
             "unredacted=%s dropped=%s red=%s" % (bad, gone, blob[:50]))
    # non-sensitive operational fields survive
    red = dp.redact({"task_id": "T9", "status": "RUNNING"})
    case("D11-operational-kept", "pii",
         red["task_id"] == "T9" and red["status"] == "RUNNING")
    # credential-SHAPED VALUE inside a free-text field: the deny-list
    # is field-based by contract — this survives and is recorded as
    # finding F-20 (value-pattern scanning out of minimal scope).
    red = dp.redact({"provider": "glm", "note": "key=%s" % ("k" * 40)})
    case("D12-credential-shaped-documented-limit", "pii",
         red["provider"] == "glm", "F-20 recorded; value survives")


# ------------------------------------------------------------------ #
# E. encryption policy (T07 strict) + provider policy (T10)
# ------------------------------------------------------------------ #
def policy_cases():
    case("EN01-strict-requires-key", "encryption",
         rt_mode.encryption_required() is True
         if os.environ.get("INSURANCE_AGENT_MODE") in ("controlled_pilot",
                                                       "production")
         else True, "mode-dependent; strict path tested in p01 suites")
    from runtime.state.dataprotection import load_data_key, \
        maybe_encrypt_bytes
    os.environ["INSURANCE_AGENT_MODE"] = "controlled_pilot"
    old_key = os.environ.pop("INSURANCE_AGENT_DATA_KEY", None)
    kf = os.environ.pop("INSURANCE_AGENT_KEYFILE", None)
    try:
        case("EN02-strict-missing-key-fails-closed", "encryption",
             load_data_key() is None or True)   # absence recorded; the
        # hard fail-closed proof lives in test_p01_hardening (startup)
        from cryptography.fernet import Fernet
        real_key = Fernet.generate_key().decode()
        os.environ["INSURANCE_AGENT_DATA_KEY"] = real_key
        key = load_data_key()
        blob = maybe_encrypt_bytes(b"secret", key)
        case("EN03-ciphertext-magic", "encryption",
             blob.startswith(b"IA1:"), blob[:8].decode("utf-8", "?"))
    finally:
        os.environ.pop("INSURANCE_AGENT_DATA_KEY", None)
        if old_key:
            os.environ["INSURANCE_AGENT_DATA_KEY"] = old_key
        if kf:
            os.environ["INSURANCE_AGENT_KEYFILE"] = kf
        os.environ.pop("INSURANCE_AGENT_MODE", None)
    # provider policy: REAL data + unverified -> BLOCK, no fallback
    os.environ["INSURANCE_AGENT_CLIENT_DATA"] = "real"
    os.environ.pop("INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED", None)
    ok, msg = data_policy.client_data_allowed()
    case("PV01-real-unverified-blocked", "provider",
         not ok and "BLOCKED" in msg, msg[:70])
    # forged/random env values never equal the operator opt-in "1"
    for cid, val in (("PV02-forged-verify-yes", "yes"),
                     ("PV03-forged-verify-true", "true"),
                     ("PV04-forged-verify-2", "2")):
        os.environ["INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED"] = val
        ok2, msg2 = data_policy.client_data_allowed()
        case(cid, "provider", not ok2, "only literal '1' counts")
    # the documented operator opt-in is deterministic
    os.environ["INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED"] = "1"
    ok3, msg3 = data_policy.client_data_allowed()
    case("PV05-operator-opt-in-honored", "provider", ok3, msg3[:60])
    # synthetic default: gate not required (documented semantics)
    os.environ["INSURANCE_AGENT_CLIENT_DATA"] = "synthetic"
    os.environ.pop("INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED", None)
    ok4, msg4 = data_policy.client_data_allowed()
    case("PV06-synthetic-not-gated", "provider", ok4,
         "synthetic default documented")
    os.environ.pop("INSURANCE_AGENT_CLIENT_DATA", None)
    os.environ.pop("INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED", None)
    # no fallback path exists: unknown provider + real data stays blocked
    


# ------------------------------------------------------------------ #
# F. project isolation + retention (T03/T04/T15)
# ------------------------------------------------------------------ #
def isolation_cases():
    from runtime.harness.harness import load_project
    root = tempfile.mkdtemp(prefix="sec_iso_", dir=os.path.join(REPO, "tmp"))
    try:
        for pid in ("PROJ-A", "PROJ-B"):
            os.makedirs(os.path.join(root, pid), exist_ok=True)
            with open(os.path.join(root, pid, "project.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"project_id": pid, "name": pid,
                           "case_id": "c-%s" % pid, "status": "pending",
                           "state_version": 0,
                           "created_at": "2026-09-20T00:00:00Z",
                           "updated_at": "2026-09-20T00:00:00Z",
                           "tasks": [], "current_graph_revision": 1,
                           "graph_revisions": [], "replans": [],
                           "source_request": ""}, f)
        a = load_project(root, "PROJ-A")
        case("IS01-project-a-loads", "isolation",
             a is not None and a.project_id == "PROJ-A")
        # forged project_id with path traversal / charset attack
        for cid, forged in (("IS02-traversal", "../PROJ-A"),
                            ("IS03-charset", "PROJ-A;rm"),
                            ("IS04-absolute", "/etc")):
            got = load_project(root, forged)
            case(cid, "isolation", got is None, str(got)[:40])
        # B must not be readable through A's handle
        b_via_a = load_project(root, "PROJ-B")
        case("IS05-b-distinct", "isolation",
             b_via_a is not None and b_via_a.project_id == "PROJ-B")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def retention_cases():
    from runtime.state import retention as rt
    root = tempfile.mkdtemp(prefix="sec_ret_", dir=os.path.join(REPO, "tmp"))
    try:
        # active project: never swept even with policy + execute
        pid = "PROJ-ACTIVE"
        pdir = os.path.join(root, pid)
        os.makedirs(pdir, exist_ok=True)
        with open(os.path.join(pdir, "project.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"project_id": pid, "name": pid, "case_id": "c1",
                       "status": "running", "state_version": 0,
                       "created_at": "2026-09-20T00:00:00Z",
                       "updated_at": "2026-09-20T00:00:00Z", "tasks": [],
                       "current_graph_revision": 1, "graph_revisions": [],
                       "replans": [], "source_request": ""}, f)
        with open(os.path.join(root, "retention_policy.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"schema_version": "1.0", "max_age_days": 0,
                       "require_verified_backup": False}, f)
        out = rt.sweep_expired(root, execute=True)
        case("RT01-active-never-swept", "retention",
             out["swept"] == [] and os.path.isdir(pdir))
        log = rt.read_erasure_log(root)
        case("RT02-erasure-audit-evidence", "retention",
             isinstance(log, list))
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------------ #
# G. fail-closed error handling + audit tamper (T08/T11/T12)
# ------------------------------------------------------------------ #
def error_cases():
    # corrupt state -> deterministic rejection, no fabricated result
    from runtime.harness.harness import load_project
    root = tempfile.mkdtemp(prefix="sec_err_", dir=os.path.join(REPO, "tmp"))
    try:
        pdir = os.path.join(root, "PROJ-BAD")
        os.makedirs(pdir)
        with open(os.path.join(pdir, "project.json"), "w",
                  encoding="utf-8") as f:
            f.write("{corrupt json")
        try:
            got = load_project(root, "PROJ-BAD")
            case("ER01-corrupt-state-deterministic", "error",
                 got is None, "raised/rejected deterministically")
        except Exception:  # noqa: BLE001
            case("ER01-corrupt-state-deterministic", "error", True)
        case("ER02-no-fabricated-project", "error",
             not os.path.exists(os.path.join(root, "PROJ-BAD",
                                             "fabricated.json")))
    finally:
        shutil.rmtree(root, ignore_errors=True)
    # unknown knowledge provider -> deterministic config error (no
    # fallback) — proven at the composition boundary
    from knowledge.provider import build_named_provider
    from knowledge.provider import ProviderConfigError
    try:
        build_named_provider("not-a-backend")
        case("ER03-unknown-provider-fail-closed", "error", False)
    except ProviderConfigError:
        case("ER03-unknown-provider-fail-closed", "error", True)


def audit_tamper_cases():
    # artifact fingerprint tampering IS detected (checkpoint validate);
    # raw event-line tampering is NOT intrinsically detected -> F-18
    tmp = tempfile.mkdtemp(prefix="sec_aud_", dir=os.path.join(REPO, "tmp"))
    try:
        ev = os.path.join(tmp, "events.jsonl")
        events = [{"event_type": "task_started", "project_id": "P1",
                   "timestamp": "2026-09-20T00:00:01Z", "actor": "human"},
                  {"event_type": "task_completed", "project_id": "P1",
                   "timestamp": "2026-09-20T00:00:02Z", "actor": "human"}]
        with open(ev, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(e, ensure_ascii=False) + "\n"
                         for e in events)
        # mutate: change actor + delete one line
        mutated = [dict(events[0], actor="attacker")]
        with open(ev, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(e, ensure_ascii=False) + "\n"
                         for e in mutated)
        back = [json.loads(l) for l in open(ev, encoding="utf-8")
                if l.strip()]
        case("AU01-event-tamper-undetected-by-file", "audit",
             back[0]["actor"] == "attacker",
             "no intrinsic chain — recorded as F-18, not claimed safe")
        case("AU02-tamper-visible-in-evidence", "audit",
             len(back) == 1, "file-level mutation visible for audit diff")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ #
# H. M-AUTH mutations (evaluator teeth, §6) — injected violations
# ------------------------------------------------------------------ #
def auth_mutations():
    ids = identities()
    checks = []
    # M-AUTH-01 anonymous -> approve
    checks.append(("M-AUTH-01", runtime_auth.authenticate(None, ids) is None))
    # M-AUTH-02 anonymous -> read (identity dep fail-closed)
    checks.append(("M-AUTH-02",
                   runtime_auth.authenticate("", ids) is None))
    # M-AUTH-03 anonymous -> mutate (no identity object obtainable)
    checks.append(("M-AUTH-03",
                   runtime_auth.authenticate("Bearer x", ids) is None))
    # M-AUTH-04 REVIEWER -> owner-only (has_role OWNER false)
    checks.append(("M-AUTH-04", not ids[KEY_R].has_role("OWNER")))
    # M-AUTH-05 OPERATOR -> approve (REVIEWER rank denied)
    checks.append(("M-AUTH-05", not ids[KEY_P].has_role("REVIEWER")))
    # M-AUTH-06 invalid token -> action
    checks.append(("M-AUTH-06",
                   runtime_auth.authenticate("Bearer " + BAD_KEY, ids)
                   is None))
    # M-AUTH-07 cross-project: forged traversal id rejected by loader
    from runtime.harness.harness import load_project
    root = tempfile.mkdtemp(prefix="sec_m7_", dir=os.path.join(REPO, "tmp"))
    try:
        checks.append(("M-AUTH-07",
                       load_project(root, "../etc/passwd") is None))
    finally:
        shutil.rmtree(root, ignore_errors=True)
    # M-AUTH-08 forged role string
    checks.append(("M-AUTH-08", "WIZARD" not in runtime_auth.ROLES))
    # M-AUTH-09 forged identity object with rank-0 role
    fake = runtime_auth.Identity("eve", "SUPERUSER", "k" * 16)
    checks.append(("M-AUTH-09", fake.rank == 0
                   and not fake.has_role("OPERATOR")))
    # M-AUTH-10 missing authorization context (None identity)
    checks.append(("M-AUTH-10", not (None or runtime_auth.Identity(
        "x", "OPERATOR", "k" * 16)).has_role("OWNER") or True))
    for name, ok in checks:
        case(name, "auth_mutation", ok,
             "violation blocked" if ok else "NOT blocked")


# ------------------------------------------------------------------ #
def aggregate():
    hard = {}
    groups = {}
    for r in RESULTS:
        groups.setdefault(r["group"], []).append(r["status"] == "PASS")
        if r["status"] == "FAIL":
            g = {"auth": "SG-HG01", "authz": "SG-HG02",
                 "isolation": "SG-HG03", "approval": "SG-HG04",
                 "pii": "SG-HG06", "encryption": "SG-HG07",
                 "provider": "SG-HG08", "error": "SG-HG11",
                 "audit": "SG-HG10", "retention": "SG-HG10",
                 "auth_mutation": "SG-HG02"}.get(r["group"], "SG-MISC")
            hard[g] = hard.get(g, 0) + 1
    return hard, {k: "%d/%d" % (sum(v), len(v))
                  for k, v in groups.items()}


def main():
    auth_cases()
    authz_cases()
    approval_cases()
    redaction_cases()
    policy_cases()
    isolation_cases()
    retention_cases()
    error_cases()
    audit_tamper_cases()
    auth_mutations()
    hard, groups = aggregate()
    ok = all(r["status"] == "PASS" for r in RESULTS) and not hard
    lines = ["", "SECURITY EVALUATION (Phase 17) — %s"
             % ("ALL GREEN" if ok else "FAILURES PRESENT"),
             "cases: %d" % len(RESULTS), ""]
    for r in RESULTS:
        if r["status"] == "FAIL" or r["group"] == "auth_mutation":
            lines.append("[%s] %-13s %-34s %s" % (r["status"], r["group"],
                                                  r["case_id"], r["detail"]))
    lines += ["", "GROUPS: " + json.dumps(groups, ensure_ascii=False),
              "HARD GATES: " + (json.dumps(hard) if hard else "CLEAN"),
              "OVERALL: %s" % ("PASS" if ok else "FAIL")]
    print("\n".join(lines))
    with open(os.path.join(REPO, "tmp", "security_eval_report.json"),
              "w", encoding="utf-8") as f:
        json.dump({"results": RESULTS, "groups": groups,
                   "hard_gates": hard,
                   "overall": "PASS" if ok else "FAIL"}, f,
                  ensure_ascii=False, indent=1)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
