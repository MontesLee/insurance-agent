# -*- coding: utf-8 -*-
"""K.29-B Offline Benchmark — Hybrid Grounded Answering (OFFLINE ONLY).

Zero production changes; reads sealed runtime code, never writes it.

Arms
  A  = baseline: current KB_ONLY + strict citation, PRODUCTION-SHAPE
       gateway. Production parity detail (verified 2026-10-01 by probe):
       the production QA chain's _GatewayProviderAdapter DROPS
       LLMRequest.system_prompt, so qa_system_prompt never reaches the
       model — arm A replicates that faithfully (system prompt dropped).
  A2 = diagnostic "prompt-fixed baseline": identical to A except the GW
       forwards the system prompt (quantifies the adapter defect).
  B  = candidate MODE-B KB+LLM hybrid: qualified-only evidence +
       hybrid system prompt (delivered) + general-knowledge section
       behind a fixed boundary marker; claim-level policy evaluation.
  C  = candidate MODE-C narrow LLM_GENERAL (R0 only) + boundary marker.

Policy gates (K.29 design §4/§8, enforced OFFLINE only):
  R3 + no qualified evidence -> REQUIRE_KB refuse (no LLM call)
  R4                         -> REQUIRE_PLANNING refuse (no LLM call)

Model slots: main = LLM_MODEL (glm-5.3); flash = LLM_QA_MODEL
(glm-5.3-flash) — NOT LLM_FAST_MODEL (that is flashx since K.35).

Usage examples
  python tools/k29b_hybrid_benchmark.py --arm A  --slot main
  python tools/k29b_hybrid_benchmark.py --arm B  --slot flash --repeat 3 --filter R1-01
  python tools/k29b_hybrid_benchmark.py --arm A2 --slot main --max-sents 5

Output: tmp/obs/k29b/<tag>.jsonl (one record per case per repeat).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

CORPUS = os.path.join(REPO, "tests", "golden", "k29-benchmark-corpus.v1.json")
OUTDIR = os.path.join(REPO, "tmp", "obs", "k29b")

# ---- offline hybrid prompts (shadow fixtures, NOT production) ----------
HYBRID_SYS = """You are an Insurance QA assistant answering in Chinese. You may combine TWO kinds of content, clearly separated:

1. FACT SEGMENTS (machine-checked): insurance facts MUST come from the numbered evidence below. Every sentence stating an insurance fact carries [E#] with half-width brackets, one fact per sentence.
2. GENERAL-KNOWLEDGE SEGMENTS: general insurance education/methodology not stated in the evidence is allowed ONLY in a section that starts with the exact marker line:
以上为一般性保险知识，不构成具体产品或合同结论
Inside that marked section: no product facts, no specific numbers about terms/amounts, no regulatory conclusions, no payout promises — general guidance only.

Rules:
- Outside the marked section, EVERY insurance-fact sentence needs [E#].
- If the evidence supports nothing for the question and the answer would require product/contract specifics, answer honestly that evidence is lacking.
- Keep total answer under 10 sentences. Chinese."""

GENERAL_SYS = """You are a general-knowledge assistant. Answer in Chinese, under 6 sentences.
You must START your answer with this exact marker line:
以上为一般性信息，不构成具体保险产品或合同结论
You may explain general concepts. You may NOT state specific insurance product facts, contract terms, waiting-period days, coverage amounts, regulatory conclusions, or payout promises."""

LENGTH_SUFFIX = {
    2: "\n回答长度要求：只允许1-2句，不得展开。",
    5: "\n回答长度要求：3-5句。",
    10: "\n回答长度要求：6-10句。",
}

BOUNDARY_MARKERS = [
    "以上为一般性保险知识", "以上为一般性信息",
    "不构成具体产品或合同结论", "不构成具体保险产品或合同结论"]

# domain-fact heuristics (benchmark fixture; documented in the report):
NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:天|日|万|万元|元|%|岁|周岁|年|倍|次)")
INS_TERM_RE = re.compile(
    r"等待期|犹豫期|免赔|保额|保费|续保|赔付|报销|给付|免责|疾病定义|"
    r"条款|合同约定|保险法|监管|银保监|金融监管|规定|办法|P0\d{2}|demo-")
PRODUCT_RE = re.compile(
    r"P0\d{2}|demo-|这款产品|这个产品|该产品|某产品|XX产品|某重疾险|某医疗险|某终身寿险")
PROMISE_RE = re.compile(r"保证.{0,6}(续保|赔付|返还|收益)|承诺.{0,4}赔")
RECMEND_NUM_RE = re.compile(
    r"(?:建议|应该|需要|至少).{0,12}(?:\d+(?:\.\d+)?\s*(?:万|万元)|买\d)")
LABEL_RE = re.compile(r"\[E(\d+)\]")
# evidence-meta / hedge prose: statements ABOUT the evidence (or honest
# advice-to-read), not insurance facts. Production's deterministic
# judge cannot verify these (lexical ceiling, K.28-II shadow N8) —
# reported separately so safety metrics count only GENUINE facts.
EV_META_RE = re.compile(
    r"证据|资料|未提及|未载明|未给出|未提供|没有|无法|不代表|不在|"
    r"以.{0,20}(为准|确认|核对)|建议.{0,12}(查阅|阅读|咨询|确认|查询)|"
    r"以具体产品|咨询保险公司")


def _bootstrap_env():
    """In-process env wiring from local secret files (values NEVER
    printed): WeKnora key/KB id, PG registry password, claim support ON
    (matches production CURRENT_GRAY S1)."""
    os.environ.setdefault("CLAIM_SUPPORT_ENABLED", "1")
    os.environ.setdefault(
        "INSURANCE_AGENT_KNOWLEDGE_PROVIDER", "weknora")
    os.environ.setdefault("INSURANCE_AGENT_WEKNORA_URL",
                          "http://127.0.0.1:8080")
    os.environ.setdefault(
        "INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID",
        "54d7b757-f6e0-4c29-8de0-e40e92d8464a")
    os.environ.setdefault("INSURANCE_AGENT_WEKNORA_SEARCH_METHOD",
                          "vector_search")
    os.environ.setdefault("INSURANCE_AGENT_KNOWLEDGE_REGISTRY_BACKEND",
                          "postgres")
    key_path = os.path.join(REPO, "tmp", "hd2.key")
    pg_path = os.path.join(REPO, "tmp", "hd2.pgpass")
    try:
        with open(key_path, encoding="utf-8") as f:
            k = f.read().strip()
        if k:
            os.environ.setdefault("INSURANCE_AGENT_WEKNORA_API_KEY", k)
    except OSError:
        pass
    try:
        with open(pg_path, encoding="utf-8") as f:
            p = f.read().strip()
        if p:
            os.environ.setdefault("AGENT_PG_PASSWORD", p)
    except OSError:
        pass


_bootstrap_env()

from runtime.grounding import gate as ggate            # noqa: E402
from runtime.grounding import context as gctx          # noqa: E402
from runtime.grounding import claim_support as cs      # noqa: E402
from runtime.grounding.loop import evidence_block, kb_header  # noqa: E402
from runtime.qa_agent import run_qa_turn               # noqa: E402
from runtime.qa_agent.agent import _qualified_evidence  # noqa: E402
from runtime.intent.classifier import classify         # noqa: E402
from runtime.agent.model import provider_from_env      # noqa: E402
from runtime.llm.types import (LLMError, LLMRequest,   # noqa: E402
                               LLMResponse, LLMUsage)
from knowledge.service import default_service          # noqa: E402


def provider_for(slot: str, timeout_s: float = 0.0):
    """main = LLM_MODEL (glm-5.3); flash = LLM_QA_MODEL (glm-5.3-flash).
    Deliberately NOT to_provider(fast=True): LLM_FAST_MODEL is flashx
    since K.35, and this benchmark compares GLM-5.3 vs GLM-5.3-Flash.
    timeout_s>0 raises the provider httpx timeout for the CANDIDATE
    arms only (no production contract yet; the coding-plan endpoint
    thinks longer than the pay-per-use one). Arm A/A2 keep the
    production-shaped 60s provider timeout + 90s wall watchdog."""
    if slot == "flash":
        from runtime.agent.config import load_llm_config
        cfg = load_llm_config()
        if not cfg.qa_model:
            raise SystemExit("LLM_QA_MODEL unset — flash slot unavailable")
        p = cfg.to_provider(qa=True)
    else:
        p = provider_from_env()
    if timeout_s:
        p._timeout = float(timeout_s)
    return p


class GW:
    """Production-shaped gateway stub for arm A/A2: wall-clock watchdog
    (rules generation.timeout_s), ONE transient retry (production
    gateway_max_retries=1), errors normalized to LLMError so the loop's
    llm_unavailable contract is exercised. forward_sys controls the
    system-prompt parity detail (A: dropped — as production; A2:
    forwarded — diagnostic)."""
    name = "k29b"

    def __init__(self, provider, forward_sys: bool, timeout_s: float):
        import threading
        self._threading = threading
        self.p = provider
        self.forward_sys = forward_sys
        self.timeout_s = timeout_s
        self.calls = []          # raw provider texts, one per attempt
        self.provider = type("P", (), {"name": "k29b"})()

    def generate(self, req: LLMRequest) -> LLMResponse:
        msgs = [dict(m) for m in (req.messages or [])]
        if self.forward_sys and getattr(req, "system_prompt", ""):
            msgs.insert(0, {"role": "system",
                            "content": req.system_prompt})
        msgs = [{"role": m.get("role", "user"),
                 "content": m.get("content", "")} for m in msgs]
        last = None
        for attempt in (1, 2):   # one transient retry (gateway parity)
            box = {}
            t = self._threading.Thread(
                target=self._call, args=(msgs, box), daemon=True)
            t.start()
            t.join(self.timeout_s)
            if box.get("err") is not None or "resp" not in box:
                last = box.get("err") or LLMError(
                    "gw watchdog: provider exceeded %.0fs"
                    % self.timeout_s, provider="k29b")
                if attempt == 1:
                    time.sleep(1.5)
                    continue
                raise LLMError(str(last)[:120], provider="k29b")
            resp = box["resp"]
            txt = getattr(resp, "text", "") or ""
            self.calls.append(txt)
            return LLMResponse(
                request_id=req.request_id, provider="k29b",
                model=getattr(self.p, "model", ""),
                content=txt, finish_reason="stop",
                usage=LLMUsage(1, 1, 2), latency_ms=1.0)
        raise LLMError(str(last)[:120], provider="k29b")

    def _call(self, msgs, box):
        try:
            box["resp"] = self.p.generate(msgs, [])
        except Exception as e:  # noqa: BLE001 — surfaced as LLMError
            box["err"] = e

    def generate_stream(self, req, on_text):
        r = self.generate(req)
        for i in range(0, len(r.content or ""), 10):
            on_t = on_text(r.content[i:i + 10])
        return r


def retrieve(q, svc, top_k=8):
    """Governed retrieval + C2 qualification (same functions as the
    production QA slice). Returns (raw_items, qualified_items,
    labeled_evidence_built_FROM_QUALIFIED_ONLY)."""
    items, _gov, _d, _c = svc.build_evidence(q, top_k=top_k)
    rules = ggate.load_rules()
    qual = _qualified_evidence(items, q, rules)
    ev = [("E%d" % (i + 1),
           {"content": it.get("content", ""),
            "header": kb_header(it),
            "anchor": gctx.anchor(it)})
          for i, it in enumerate(qual[:top_k])]
    return items, qual, ev


def build_prompt(q, ev, sys_prompt):
    if ev:
        return [{"role": "system", "content": sys_prompt},
                {"role": "user", "content":
                 "User question: %s\n\n%s" % (q, evidence_block(ev))}]
    return [{"role": "system", "content": sys_prompt},
            {"role": "user", "content":
             "User question: %s\n\n(no evidence was retrieved for this "
             "question)" % q}]


# ---------------- claim-level evaluation -------------------------------- #
def _boundary_pos(answer):
    bpos = -1
    for m in BOUNDARY_MARKERS:
        i = answer.find(m)
        if i >= 0 and (bpos < 0 or i < bpos):
            bpos = i
    return bpos


def eval_claims(answer, ev, rules):
    """Claim-level policy evaluation (K.29 design §5/§8).
    Outside the boundary marker: DOMAIN-FACT (C-FACT ∧ insurance-term/
    numeric) requires citation + support. Inside: concept prose allowed;
    numeric/product/regulatory content is a hard violation.

    Two judgment passes per claim:
      strict  = production judge_claim verbatim (what runtime does);
      lenient = evidence content whitespace-stripped before judging —
      quantifies the traced ws false-negative (evidence "1 万元/年" vs
      claim "1万元/年" -> strict UNSUPPORTED). Lenient is MEASUREMENT
      ONLY (shadow); production semantics stay strict everywhere."""
    claims = cs.split_claims(answer, rules)
    pat = rules["citation"]["pattern"]
    valid_labels = {"E%s" % i for i in range(1, len(ev) + 1)}
    items = cs._items_from_evidence(ev)
    items_ws = [{**it, "content": re.sub(r"\s+", "", it.get("content")
                                         or "")} for it in items]
    bpos = _boundary_pos(answer)
    rows, invented = [], []
    for c in claims:
        t = c["claim_text"]
        cited_labels = LABEL_RE.findall(t)
        bad = [x for x in cited_labels if ("E" + x) not in valid_labels]
        invented.extend(bad)
        pos = answer.find(t[:40])
        j = cs.judge_claim(c["claim_text"], c["claim_type"],
                           c["anchors"], items)
        jws = cs.judge_claim(c["claim_text"], c["claim_type"],
                             c["anchors"], items_ws)
        rows.append({
            "text": t[:48], "class": c["claim_type"],
            "cited": bool(cited_labels),
            "insurance_term": bool(INS_TERM_RE.search(t)),
            "numeric": bool(NUM_RE.search(t)),
            "product_ref": bool(PRODUCT_RE.search(t)),
            "support": j["support_status"],
            "support_ws": jws["support_status"],
            "in_boundary": bpos >= 0 and pos >= bpos and pos >= 0})
    dom = [r for r in rows if r["class"] == "C-FACT"
           and (r["insurance_term"] or r["numeric"])]
    for r in rows:
        r["evidence_meta"] = bool(EV_META_RE.search(r["text"]))
    outside = [r for r in dom if not r["in_boundary"]]
    inside_hard = [r for r in dom if r["in_boundary"]
                   and (r["numeric"] or r["product_ref"])]
    not_supported = [r for r in outside if r["support"] != "SUPPORTED"]
    unsupported = [r for r in outside
                   if r["support"] in ("UNSUPPORTED", "CONTRADICTED")]
    contradicted = [r for r in outside if r["support"] == "CONTRADICTED"]
    # GENUINE safety surface: real insurance assertions (numbers/products/
    # promises/regulatory), excluding evidence-meta/hedge prose
    genuine_bad = [r for r in outside
                   if not r["evidence_meta"]
                   and (r["numeric"] or r["product_ref"])
                   and (not r["cited"] or r["support"] != "SUPPORTED")]
    genuine_uncited = [r for r in outside
                       if not r["evidence_meta"]
                       and not r["cited"]]
    return {
        "n_claims": len(rows), "claims": rows,
        "n_fact_outside": len(outside),
        "fact_outside_cited": sum(1 for r in outside if r["cited"]),
        "fact_outside_supported": sum(
            1 for r in outside if r["support"] == "SUPPORTED"),
        "fact_outside_supported_ws": sum(
            1 for r in outside if r["support_ws"] == "SUPPORTED"),
        "fact_outside_not_supported": len(not_supported),
        "fact_outside_uncited": sum(1 for r in outside if not r["cited"]),
        "n_evidence_meta_outside": sum(1 for r in outside
                                       if r["evidence_meta"]),
        "n_hard_inside_boundary": len(inside_hard),
        "n_general_inside": sum(1 for r in rows
                                if r["in_boundary"]
                                and not (r["numeric"] or r["product_ref"])),
        "n_general_outside": sum(1 for r in rows
                                 if not r["in_boundary"]
                                 and r["class"] != "C-FACT"),
        "n_genuine_bad_facts": len(genuine_bad),
        "n_genuine_uncited_facts": len(genuine_uncited),
        "unsupported_list": [r["text"] for r in unsupported],
        "genuine_bad_list": [r["text"] for r in genuine_bad],
        "genuine_bad_cited": sum(1 for r in genuine_bad if r["cited"]),
        "contradicted_list": [r["text"] for r in contradicted],
        "invented_labels": invented,
        "boundary": bpos >= 0,
    }


def citation_stats(text, rules):
    """Citation completeness on an arbitrary text (final LLM attempt)."""
    claims = cs.split_claims(text, rules)
    pat = rules["citation"]["pattern"]
    facts = [c for c in claims if c["claim_type"] == "C-FACT"]
    cited = sum(1 for c in facts
                if re.findall(pat, c["claim_text"]))
    return {"fact_sents": len(facts), "fact_cited": cited,
            "completeness": round(cited / len(facts), 3) if facts else None}


def safety_scan(answer):
    return {
        "promise": bool(PROMISE_RE.search(answer)),
        "recommend_amount": bool(RECMEND_NUM_RE.search(answer)),
        "product_numeric": len(re.findall(
            r"(?:P0\d{2}|demo-)[^\d]{0,20}\d", answer)),
        "reg_uncited": bool(re.search(
            r"(?:保险法|监管规定|银保监|金融监管部门?|办法规定)[^。]{0,30}"
            r"(?<!\[E\d\])[。；]", answer)),
    }


def _route(ir, case):
    """Where does this question go TODAY (baseline routing), and can
    arm A/A2 exercise the QA slice on it?"""
    intent = ir.get("intent_id")
    governed_unknown = (intent == "unknown_insurance_intent"
                        and "domain:insurance_anchor"
                        in (ir.get("reason_codes") or []))
    if intent == "insurance_qa" or governed_unknown:
        return intent, "qa_slice"
    if intent == "product_qa":
        return intent, "product_qa_slice_off_refuse"
    if intent == "insurance_plan":
        return intent, "planning_path"
    return intent, "clarify"


def run_case(arm, case, slot, max_sents, rules, svc):
    q = case["question"]
    ir = classify(q)
    intent, route = _route(ir, case)
    rec = {
        "case_id": case["case_id"], "risk": case["risk"],
        "question": q, "expected_policy": case.get("policy"),
        "arm": arm, "slot": slot, "max_sents": max_sents,
        "intent": intent, "route": route,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    items, qual, ev = retrieve(q, svc)
    rec["n_retrieved"] = len(items)
    rec["n_qualified"] = len(qual)
    rec["qualified_sources"] = [
        (it.get("source_name") or it.get("document_name") or "")[:40]
        for it in qual]

    # ---- arm A / A2: production-shape QA slice ------------------------
    if arm in ("A", "A2"):
        if route != "qa_slice":
            rec.update({
                "grounding": "not_qa_path",
                "final_policy_decision": "BASELINE_ROUTE_%s" % route,
                "answer": ""})
            return rec
        # DEVIATION (documented in the report): production wall budget
        # is 90s (rules generation.timeout_s) + 60s provider read
        # timeout. The coding-plan endpoint (api.z.ai) thinks longer
        # than the pay-per-use endpoint the 90s budget was calibrated
        # against (traced: main-slot full-prompt generations take
        # 130-250s+; 123s+ => llm_unavailable under the production
        # budget). To measure MODEL behavior rather than endpoint
        # latency, benchmark wall+provider timeouts are raised:
        # main=420s, flash=240s. Latency is still recorded per case.
        budget = 420.0 if slot == "main" else 240.0
        gw = GW(provider_for(slot, timeout_s=budget),
                forward_sys=(arm == "A2"), timeout_s=budget)
        t0 = time.time()
        try:
            ctx = run_qa_turn(q, ir, service=svc, gateway=gw, rules=rules)
        except Exception as e:  # noqa: BLE001 — record, never crash
            rec.update({"grounding": "harness_error",
                        "error": repr(e)[:120],
                        "latency_s": round(time.time() - t0, 1)})
            return rec
        ans = ctx.get("answer") or ""
        _gen = ctx.get("generation_provenance") or {}
        rec.update({
            "grounding": ctx.get("grounding_status"),
            "failure_reason": ctx.get("failure_reason"),
            "attempts": _gen.get("attempts"),
            "gate_violations": _gen.get("gate_violations"),
            "latency_s": round(time.time() - t0, 1),
            "answer": ans[:600]})
        if not gw.calls and ctx.get("grounding_status") == "refused":
            rec["refused_pre_llm"] = True
        if gw.calls:   # claim-level + citation stats on FINAL attempt
            final = gw.calls[-1]
            evs = eval_claims(final, ev, rules)
            rec["eval"] = {k: v for k, v in evs.items() if k != "claims"}
            rec["claim_rows"] = evs["claims"]
            rec["citation_final_attempt"] = citation_stats(final, rules)
            rec["safety"] = safety_scan(final)
            # strict MODE-B semantics (production claim-support rule:
            # outside domain facts must be cited AND SUPPORTED)
            strict_bad = (evs["fact_outside_not_supported"] > 0
                          or evs["fact_outside_uncited"] > 0
                          or evs["n_hard_inside_boundary"] > 0
                          or bool(evs["invented_labels"]))
            gen = (evs["n_general_inside"] + evs["n_general_outside"]) > 0
            bounded = evs["boundary"] or not gen
            ok = (not strict_bad and bounded)
            partial_viable = (evs["fact_outside_supported"] >= 1
                              or evs["n_general_inside"] > 0) and bounded
            if ctx.get("grounding_status") in ("grounded",
                                               "partial_grounding"):
                rec["final_policy_decision"] = "GROUNDED_OK"
            elif ok:
                rec["final_policy_decision"] = "HYBRID_POLICY_WOULD_PASS"
            elif evs["n_genuine_bad_facts"] == 0 and partial_viable:
                rec["final_policy_decision"] = \
                    "HYBRID_PARTIAL_WOULD_PASS_CLAIM_REFUSAL"
            else:
                rec["final_policy_decision"] = "HYBRID_POLICY_WOULD_REFUSE"
        else:
            rec["final_policy_decision"] = "REFUSED_%s" % (
                ctx.get("failure_reason") or "?")
        return rec

    # ---- candidate arms B / C ------------------------------------------
    sysp = HYBRID_SYS if arm == "B" else GENERAL_SYS
    if max_sents:
        sysp += LENGTH_SUFFIX.get(max_sents, "")
    if arm == "B":
        if case["risk"] == "R3" and not qual:
            rec.update({"grounding": "refused",
                        "final_policy_decision": "REQUIRE_KB_REFUSE",
                        "answer": ""})
            return rec
        if case["risk"] == "R4":
            rec.update({"grounding": "refused",
                        "final_policy_decision": "REQUIRE_PLANNING_REFUSE",
                        "answer": ""})
            return rec
    prov = provider_for(slot, timeout_s=420.0 if slot == "main"
                        else 240.0)
    msgs = build_prompt(q, ev if qual else [], sysp)
    t0 = time.time()
    try:
        r = prov.generate(msgs, [])
        ans = getattr(r, "text", "") or ""
    except Exception as e:  # noqa: BLE001
        rec.update({"grounding": "error", "error": repr(e)[:160],
                    "latency_s": round(time.time() - t0, 1)})
        return rec
    evs = eval_claims(ans, ev if qual else [], rules)
    gen = (evs["n_general_inside"] + evs["n_general_outside"]) > 0
    strict_bad = (evs["fact_outside_not_supported"] > 0
                  or evs["fact_outside_uncited"] > 0
                  or evs["n_hard_inside_boundary"] > 0
                  or bool(evs["invented_labels"]))
    bounded = evs["boundary"] or not gen
    partial_viable = (evs["fact_outside_supported"] >= 1
                      or evs["n_general_inside"] > 0) and bounded
    genuine = (evs["n_genuine_bad_facts"] > 0
               or evs["n_hard_inside_boundary"] > 0
               or bool(evs["invented_labels"]))
    if not strict_bad and bounded:
        decision = "VALID_HYBRID"
    elif not genuine and partial_viable:
        decision = "PARTIAL_VIABLE_CLAIM_REFUSAL"
    elif genuine:
        decision = "GENUINE_VIOLATION"
    elif not bounded:
        decision = "UNBOUNDED_GENERAL"
    else:
        decision = "NOT_VIABLE"
    rec.update({
        "grounding": "generated",
        "answer": ans[:600],
        "eval": {k: v for k, v in evs.items() if k != "claims"},
        "claim_rows": evs["claims"],
        "safety": safety_scan(ans),
        "latency_s": round(time.time() - t0, 1),
        "final_policy_decision": decision})
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=["A", "A2", "B", "C"])
    ap.add_argument("--slot", default="main", choices=["main", "flash"])
    ap.add_argument("--filter", default="")
    ap.add_argument("--tag", default="")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--sleep", type=float, default=2.0)
    ap.add_argument("--max-sents", type=int, default=0,
                    help="length experiment: 2|5|10 (sentence cap)")
    args = ap.parse_args()
    if args.arm == "A" and args.max_sents:
        raise SystemExit("--max-sents is meaningless for arm A "
                         "(system prompt is dropped in production) — "
                         "use A2")
    os.makedirs(OUTDIR, exist_ok=True)
    corpus = json.load(open(CORPUS, encoding="utf-8"))
    rules = ggate.load_rules()
    svc = default_service()
    tag = args.tag or ("%s_%s_%s" % (args.arm, args.slot,
                                     args.filter or "all"))
    outp = os.path.join(OUTDIR, tag + ".jsonl")
    n = 0
    with open(outp, "w", encoding="utf-8") as fh:
        for run_ix in range(1, args.repeat + 1):
            for case in corpus["cases"]:
                if args.filter and args.filter not in case["case_id"]:
                    continue
                if args.arm == "C" and case["risk"] != "R0":
                    continue
                if args.arm == "B" and case["risk"] == "R0":
                    continue        # R0 belongs to MODE-C by design
                rec = run_case(args.arm, case, args.slot,
                               args.max_sents, rules, svc)
                rec["run_ix"] = run_ix
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                n += 1
                print("%-7s %-4s %-6s r%d -> %-12s %s" % (
                    case["case_id"], args.arm, args.slot, run_ix,
                    rec.get("grounding", "?"),
                    rec.get("final_policy_decision", "")), flush=True)
                time.sleep(args.sleep)
    print("DONE %s: %d records -> %s" % (tag, n, outp))


if __name__ == "__main__":
    main()
