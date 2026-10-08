"""28.K.27-RV4-C2 — RetrievedEvidence → QualifiedEvidence (P1-B Phase 1).

The relevance qualification floor between governance-allowed retrieval
and the [E#] evidence set. All evidence content in these tests comes
from the REAL governed pilot corpus (knowledge/pilot/documents/) —
no fabricated insurance facts. Offline: stub service + recording
gateway; the REAL rules file (threshold + generic-bigram stoplist) is
exercised.
"""
from __future__ import annotations

import os
import re
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Checks, run_sections  # noqa: E402

from runtime.grounding import gate as ggate  # noqa: E402
from runtime.qa_agent import run_qa_turn  # noqa: E402
from runtime.qa_agent.agent import _bigrams, _qualified_evidence  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
DOCS = os.path.join(REPO, "knowledge", "pilot", "documents")

RV4_Q = ("200万重疾险是我的，我和配偶都有百万医疗险，孩子没有保险。"
         "房贷还剩100万。配偶35岁，有100万重疾险，家庭主要收入是我一个人")
WT_Q = "重疾险的等待期是什么"


def _doc_chunk(fname, needle=None):
    """A REAL corpus chunk (first section containing needle, else the
    longest section) — governed pilot corpus text, never invented."""
    text = open(os.path.join(DOCS, fname), encoding="utf-8").read()
    secs = re.split(r"\n#+ ", text)
    body = secs[1:] if len(secs) > 1 else secs
    if needle:
        hit = [s for s in body if needle in s]
        if hit:
            return hit[0][:400]
    return max(body, key=len)[:400]


def _item(content, source):
    return {"content": content, "source_name": source,
            "document_name": source, "version": "2019",
            "effective_from": "2019-01-01", "effective_to": None,
            "authority_level": "regulation",
            "source_url": "http://example.invalid/x",
            "chunk_id": "c1"}


def _svc(items):
    """Stub KnowledgeService: returns the given RETRIEVED items through
    the real build_evidence contract shape."""
    gov = SimpleNamespace(
        status="success",
        conflict=False,
        retrieval_metadata={"governance": {"allowed": len(items),
                                           "rejected": 0}})

    class _S:
        name = "stub"
        provider = SimpleNamespace(name="stub")

        def build_evidence(self, query, top_k=None, **kw):
            return list(items), gov, [], None

    return _S()


class _RecGateway:
    """Records the evidence labels each generation attempt received and
    returns scripted answers (one per call); never touches the network."""

    name = "rec"
    provider = SimpleNamespace(name="rec")

    def __init__(self, answer="[E1] 依据内容。", answers=None):
        self.answers = list(answers) if answers else [answer]
        self.seen_labels = []

    def generate(self, request):
        # the single evidence-bearing message content, as a string
        ev = [m.get("content", "") for m in request.messages
              if "Evidence" in str(m.get("content", ""))]
        self.seen_labels.append(ev[0] if ev else "")
        from runtime.llm.types import LLMResponse, LLMUsage
        ans = self.answers.pop(0) if self.answers else "[E1] 依据内容。"
        return LLMResponse(request_id=request.request_id, provider="rec",
                           model="stub", content=ans,
                           finish_reason="stop",
                           usage=LLMUsage(1, 1, 2), latency_ms=1.0)


def _ir(q):
    """A REAL classifier result (schema-valid IntentResult)."""
    from runtime.intent.classifier import classify
    ir = classify(q)
    assert ir["intent_id"] == "insurance_qa", ir["intent_id"]
    return ir


def section(fn):
    SECTIONS.append(fn)
    return fn


SECTIONS = []


@section
def test_r1_rv4_irrelevant_agri_reg_filtered(c: Checks):
    """The RV4-A real case: agri-reg penalty chunk (governance-allowed
    RETRIEVED hit) must NOT become QualifiedEvidence -> existing
    insufficient_evidence honest refusal, no E1, no grounded."""
    rules = ggate.load_rules()
    chunk = _doc_chunk("pilot_law_agri_2012.md", needle="保险机构经营")
    c.chk("agri chunk retrieved from real corpus", bool(chunk))
    items = [_item(chunk, "农业保险条例")]
    kept = _qualified_evidence(items, RV4_Q, rules)
    c.chk("R1 agri NOT qualified", kept == [])
    gw = _RecGateway()          # would produce a cited answer — must
    ctx = run_qa_turn(          # never be called
        RV4_Q, _ir(RV4_Q), service=_svc(items), gateway=gw, rules=rules)
    c.chk("R1 refusal=insufficient_evidence",
          ctx["grounding_status"] == "refused"
          and ctx["failure_reason"] == "insufficient_evidence")
    c.chk("R1 no generation attempted (gateway untouched)",
          gw.seen_labels == [])
    c.chk("R1 no E1 in evidence_refs",
          not (ctx.get("evidence_refs") or []))


@section
def test_r2_relevant_evidence_qualifies(c: Checks):
    """Real governed health-ins chunk for a waiting-period question
    keeps the grounded path working (no over-filter)."""
    rules = ggate.load_rules()
    chunk = _doc_chunk("pilot_reg_health_ins_2019.md", needle="等待")
    items = [_item(chunk, "健康保险管理办法")]
    c.chk("R2 chunk qualifies",
          bool(_qualified_evidence(items, WT_Q, rules)))
    gw = _RecGateway(answer="短期健康保险等待期由合同约定[E1]。")
    ctx = run_qa_turn(WT_Q, _ir(WT_Q), service=_svc(items), gateway=gw,
                      rules=rules)
    c.chk("R2 grounded preserved",
          ctx["grounding_status"] == "grounded")
    c.chk("R2 evidence_refs non-empty",
          bool(ctx.get("evidence_refs")))


@section
def test_r3_mixed_only_qualified_enters(c: Checks):
    rules = ggate.load_rules()
    agri = _item(_doc_chunk("pilot_law_agri_2012.md",
                            needle="保险机构经营"), "农业保险条例")
    good = _item(_doc_chunk("pilot_reg_health_ins_2019.md",
                            needle="等待"), "健康保险管理办法")
    kept = _qualified_evidence([agri, good], WT_Q, rules)
    c.chk("R3 only relevant kept",
          [k["source_name"] for k in kept] == ["健康保险管理办法"])


@section
def test_r4_zero_retrieval_unchanged(c: Checks):
    rules = ggate.load_rules()
    ctx = run_qa_turn(WT_Q, _ir(WT_Q), service=_svc([]), gateway=_RecGateway(),
                      rules=rules)
    c.chk("R4 empty retrieval still refuses insufficient_evidence",
          ctx["failure_reason"] == "insufficient_evidence")


@section
def test_r5_retry_cannot_bypass_qualification(c: Checks):
    """Attempt 1 fails at the LLM -> attempt 2 receives the SAME
    (already filtered) evidence set; unqualified retrieval can never
    re-enter evidence_refs through the retry path."""
    rules = ggate.load_rules()
    agri = _item(_doc_chunk("pilot_law_agri_2012.md",
                            needle="保险机构经营"), "农业保险条例")
    ctx = run_qa_turn(RV4_Q, _ir(RV4_Q), service=_svc([agri]),
                      gateway=_RecGateway(), rules=rules)
    c.chk("R5 filtered-out evidence -> refusal BEFORE any generation",
          ctx["failure_reason"] == "insufficient_evidence")
    # REGENERATION path (the actual retry in generate_grounded):
    # attempt 1 fails the CITATION GATE, attempt 2 receives the SAME
    # already-filtered evidence set (never re-expanded to raw retrieval)
    good = _item(_doc_chunk("pilot_reg_health_ins_2019.md",
                            needle="等待"), "健康保险管理办法")
    gw = _RecGateway(answers=[
        "短期健康保险等待期由合同约定。",              # gate-fail: no [E1]
        "短期健康保险等待期由合同约定[E1]。"])         # regen: cited
    ctx2 = run_qa_turn(WT_Q, _ir(WT_Q), service=_svc([good]), gateway=gw,
                       rules=rules)
    c.chk("R5 regeneration ran twice", len(gw.seen_labels) == 2)

    def _ev_part(s):
        # attempt 2 legitimately appends gate feedback AFTER the
        # evidence block — the EVIDENCE SET is the prefix
        return str(s).split("\n\nYour previous attempt")[0]

    c.chk("R5 both attempts saw the IDENTICAL filtered evidence set",
          _ev_part(gw.seen_labels[0]) == _ev_part(gw.seen_labels[1])
          and "[E1]" in str(gw.seen_labels[0]))
    c.chk("R5 grounded after regen", ctx2["grounding_status"] == "grounded")


@section
def test_r6_user_facts_get_no_external_citation(c: Checks):
    """A user self-report (配偶35岁/房贷100万…) in the refusal path is
    never decorated with an unrelated [E#]: with only irrelevant
    evidence the answer is the honest template (claim-level citation
    semantics stay Phase 2 — here we only assert no citation appears)."""
    rules = ggate.load_rules()
    agri = _item(_doc_chunk("pilot_law_agri_2012.md",
                            needle="保险机构经营"), "农业保险条例")
    ctx = run_qa_turn(RV4_Q, _ir(RV4_Q), service=_svc([agri]),
                      gateway=_RecGateway(), rules=rules)
    c.chk("R6 refusal text carries no [E citation",
          "[E" not in (ctx.get("answer") or ""))


@section
def test_knobs_threshold_zero_disables(c: Checks):
    """Rollback knob: min_query_bigram_overlap=0 restores the pre-C2
    direct pass-through (retrieved == evidence)."""
    rules = ggate.load_rules()
    agri = [_item(_doc_chunk("pilot_law_agri_2012.md",
                             needle="保险机构经营"), "农业保险条例")]
    off = dict(rules)
    off["retrieval"] = dict(rules.get("retrieval") or {},
                            qualification={
                                "min_query_bigram_overlap": 0})
    c.chk("threshold 0 -> passthrough (rollback)",
          _qualified_evidence(agri, RV4_Q, off) == agri)
    c.chk("threshold live -> filtered",
          _qualified_evidence(agri, RV4_Q, rules) == [])


@section
def test_bigram_unit_contract(c: Checks):
    """CJK-only, punctuation/digit-free bigrams; stoplist removes
    保险/个人-class noise from the overlap COUNT."""
    b = _bigrams("百万医疗险，200万！ABC")
    c.chk("digits/latin/punct excluded (stripped text = 百万医疗险万)",
          b == {"百万", "万医", "医疗", "疗险", "险万"})
    qb = _bigrams(RV4_Q)
    agri = _bigrams(_doc_chunk("pilot_law_agri_2012.md",
                               needle="保险机构经营"))
    generic = set((ggate.load_rules().get("retrieval") or {})
                  .get("qualification", {}).get("generic_bigrams") or [])
    c.chk("RV4∩agri non-generic overlap < threshold",
          len((qb & agri) - generic) < 2)


def main():
    return run_sections(
        SECTIONS, "webui_test_k27rv4c2_evidence_qualification.txt",
        "K.27-RV4-C2 EVIDENCE QUALIFICATION")


if __name__ == "__main__":
    sys.exit(main())
