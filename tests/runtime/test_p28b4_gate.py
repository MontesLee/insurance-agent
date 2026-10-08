"""Phase 28.B4 — B4 equivalence gate + golden framework + gray observation.

Covers: golden-case schema contract, the full gate run (every case must
PASS — this IS the versioned capture, kept green in CI), and the M2
gray-observation semantics (slice_decision reasons, slice-error
fallback annotation, flag isolation). Authority is NEVER enabled: the
gate compares flag-off vs flag-on runs of the same real server.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from _common import make_client, wait_terminal  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

from runtime.agent import FakeLLMProvider  # noqa: E402
from runtime.evaluation.router_equivalence.models import load_cases  # noqa: E402
from runtime.evaluation.router_equivalence.runner import run_gate  # noqa: E402

CASES_PATH = os.path.join(REPO, "tests", "golden", "router_cases.json")
SCHEMA_PATH = os.path.join(REPO, "schema", "router-golden-case.schema.json")


# --------------------------------------------------------------------------
# golden framework: schema contract + coverage
# --------------------------------------------------------------------------

def test_golden_cases_validate_against_schema():
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        validator = Draft7Validator(json.load(fh))
    with open(CASES_PATH, encoding="utf-8") as fh:
        doc = json.load(fh)
    errs = [e.message for e in validator.iter_errors(doc)]
    assert not errs, errs[:5]


def test_golden_coverage_mandated_sets():
    cases = {c.case_id: c for c in load_cases()}
    by_type = {}
    for c in cases.values():
        by_type.setdefault(c.equivalence_type, []).append(c.case_id)
    for t in ("grounded_answer", "insufficient_evidence", "kb_unavailable",
              "llm_unavailable", "hallucinated_citation"):
        assert by_type.get(t), t
    for t in ("product_existing", "product_missing", "d6_missing_fact",
              "context_reference", "forbidden_recommendation"):
        assert by_type.get(t), t
    assert by_type.get("plan_artifact_equality") and \
        by_type.get("plan_preserve")
    assert by_type.get("clarification") and by_type.get("safe_fallback")
    assert len(cases) >= 14


# --------------------------------------------------------------------------
# THE GATE — every golden case must PASS (versioned capture in CI)
# --------------------------------------------------------------------------

def test_b4_gate_all_cases_pass():
    report = run_gate()
    reds = [r for r in report.results if r.verdict == "RED"]
    detail = "\n".join("%s: %s" % (r.case_id, r.mismatches)
                       for r in reds)
    assert not reds, "B4 gate RED cases:\n%s" % detail
    assert report.passed == len(report.results) >= 14


def test_b4_gate_e1_annotation_honesty():
    # since M3 (Phase 28.D) the planning E1 is REAL: the candidate side
    # executes as insurance-planning-agent (same spine, mounted
    # identity) — the trivial "no candidate path yet" note must be GONE
    # and every E1 case must PASS on genuine equivalence
    report = run_gate()
    e1 = [r for r in report.results if r.case_id.startswith("GC-PL")]
    assert e1 and all(r.verdict == "PASS" for r in e1)
    assert all(not any("no candidate path yet" in n for n in r.notes)
               for r in e1)


# --------------------------------------------------------------------------
# M2 gray observation (Phase 3)
# --------------------------------------------------------------------------

def _shadow_for(rid):
    from runtime.intent import shadow as sh
    recs = [r for r in sh.iter_records() if r.get("run_id") == rid]
    assert recs, "no shadow record for %s" % rid
    return recs[0]


def test_gray_flag_off_records_fallback_reason():
    # K.28-II-DP-P2-1 (owner-directed hardening): default OFF no longer
    # falls back to the ungoverned legacy agent — the turn FAILS CLOSED
    # (run_failed / PRODUCT_QA_UNAVAILABLE, fixed consumer copy). The
    # 28.B4 observation contract (shadow records the flag_off reason)
    # is unchanged.
    client, mgr, _bus = make_client()
    mgr.agent_provider = FakeLLMProvider(["这款产品信息请稍等。"])
    rid = client.post("/api/chats/chat_gray_off/messages",
                      json={"text": "P001是什么产品"}).json()["run_id"]
    run = wait_terminal(client, rid)
    assert run["status"] == "failed"
    assert run["result_status"] == "PRODUCT_QA_UNAVAILABLE"
    # the legacy provider must never have produced the answer
    chat = client.get("/api/chats/chat_gray_off").json()
    answers = [m["content"] for m in chat["messages"]
               if m["role"] == "assistant"]
    assert answers == ["该功能暂时不可用，暂时无法回答产品相关的问题。"
                       "您可以咨询保险知识类问题，或稍后再试。"]
    rec = _shadow_for(rid)
    assert rec["slice_decision"] == {"slice": "product-qa", "fired": False,
                                     "reason": "flag_off"}


def test_gray_flag_on_fires_only_product_qa():
    os.environ["INSURANCE_AGENT_PRODUCT_QA_SLICE"] = "1"
    try:
        # product_qa -> product slice, reason fired
        c1, m1, _b = make_client()
        m1.agent_provider = FakeLLMProvider([
            "目录未列出该产品专项等待期[E1]。关联资料显示百万医疗险常见"
            "等待期为30天[E2]。"])
        r1 = c1.post("/api/chats/chat_gray_pq/messages",
                     json={"text": "demo-百万医疗险A的等待期多久"}
                     ).json()["run_id"]
        run1 = wait_terminal(c1, r1)
        assert run1["result_status"] == "QA_ANSWERED", run1
        rec1 = _shadow_for(r1)
        assert rec1["slice_decision"] == {"slice": "product-qa",
                                          "fired": True, "reason": "fired"}

        # insurance_qa -> knowledge-QA slice UNAFFECTED by the product flag
        c2, m2, _b2 = make_client()
        m2.agent_provider = FakeLLMProvider([
            "重大疾病保险常见等待期为90天[E1]。"])
        r2 = c2.post("/api/chats/chat_gray_qa/messages",
                     json={"text": "重疾险的等待期是什么"}).json()["run_id"]
        run2 = wait_terminal(c2, r2)
        assert run2["result_status"] == "QA_ANSWERED", run2
        rec2 = _shadow_for(r2)
        assert rec2["slice_decision"]["slice"] == "knowledge-qa"
        assert rec2["slice_decision"]["fired"] is True

        # insurance_plan -> legacy path UNAFFECTED by the PRODUCT flag
        # (M3 made PLAN_SLICE real but it stays default OFF — so a plan
        # turn here runs legacy with reason flag_off on the plan slice)
        c3, m3, _b3 = make_client()
        m3.agent_provider = FakeLLMProvider([
            ("agent_decide", {"action": "finish",
                              "message": "分析完成。"})])
        r3 = c3.post("/api/chats/chat_gray_plan/messages",
                     json={"text": "帮我规划保险"}).json()["run_id"]
        run3 = wait_terminal(c3, r3)
        assert run3["result_status"] != "QA_ANSWERED"
        rec3 = _shadow_for(r3)
        assert rec3["actual_execution"] == "existing-agent"
        assert rec3["slice_decision"] == {"slice": "plan", "fired": False,
                                          "reason": "flag_off"}
    finally:
        del os.environ["INSURANCE_AGENT_PRODUCT_QA_SLICE"]


def test_gray_slice_error_annotates_and_falls_back():
    # a crashing slice must fall back to the legacy path AND record the
    # error on the shadow record (the turn never dies)
    import runtime.qa_agent as qa_mod
    os.environ["INSURANCE_AGENT_QA_SLICE"] = "1"
    orig = qa_mod.run_qa_turn

    def _boom(**kw):
        raise RuntimeError("golden: slice crash")

    qa_mod.run_qa_turn = _boom
    try:
        client, mgr, _bus = make_client()
        mgr.agent_provider = FakeLLMProvider(["备用路径回答完毕。"])
        rid = client.post("/api/chats/chat_gray_err/messages",
                          json={"text": "重疾险的等待期是什么"}
                          ).json()["run_id"]
        run = wait_terminal(client, rid)
        assert run["status"] == "completed"
        assert run["result_status"] != "QA_ANSWERED"   # legacy finished it
        rec = _shadow_for(rid)
        assert rec["actual_execution"] == "insurance-qa-agent"  # as routed
        assert "slice_error" in rec and "golden: slice crash" in \
            rec["slice_error"]
        view = client.get("/api/chats/chat_gray_err").json()
        assert view["messages"][-1]["content"] == "备用路径回答完毕。"
    finally:
        qa_mod.run_qa_turn = orig
        del os.environ["INSURANCE_AGENT_QA_SLICE"]


if __name__ == "__main__":
    failures = 0
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        try:
            fn()
            print("PASS %s" % fn.__name__)
        except AssertionError as exc:
            failures += 1
            print("FAIL %s :: %s" % (fn.__name__, exc))
    print("\n%d test(s), %d failure(s)" % (len(fns), failures))
    sys.exit(1 if failures else 0)
