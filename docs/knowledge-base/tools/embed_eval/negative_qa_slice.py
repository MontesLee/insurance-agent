# -*- coding: utf-8 -*-
"""BGE-M3 Negative Retrieval -> Full QA Slice experiment.

Drives the 5 pipeline-FAILED frozen negative cases (RB-N-001/002/003/004/006
from retrieval-benchmark-v1.yaml — the bge-m3 negatives that retrieved AND
qualified insurance evidence in the A/B pipeline benchmark) through the REAL
production QA chain, in-process, zero production change:

    Intent (real classifier) -> BGE-M3 Retrieval (real WeKnora vector_search
    on eval KB insurance-kb-v1-eval-bge-m3) -> C2 Qualification (real
    _qualified_evidence, frozen rules) -> LLM Answer (real gateway,
    glm-5.3-flash via .env) -> Citation Gate + Claim Support (real
    generate_grounded _full_gate, CLAIM_SUPPORT_ENABLED=1 = production gray
    toggle) -> Final Answer.

Governed-registry note: the Owner's experiment chain (task section 3) is
Intent->Retrieval->C2->LLM->Gates; the PG document registry holds the
pilot-2 corpus only (KB-V1 docs are not registered), so the governed
build_evidence layer is intentionally out of scope here exactly as in the
A/B benchmark — the boundary under test is C2 + citation gate + claim
support, which are the layers the embedding switch gate depends on.

The shadow_observer seam (loop.py, designed no-op observation hook)
captures the RAW generated answer of the final gate call so refused cases
still show what the LLM attempted (task section 7 Q3).

Usage: python negative_qa_slice.py
Output: evidence/eval/negative_qa_slice.json (incremental per case)
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

KB = HERE.parents[1]
EVID = KB / "evidence" / "eval"

BASE = "http://127.0.0.1:8080"
TENANT = "10001"
EVAL_KB_NAME = "insurance-kb-v1-eval-bge-m3"

# The 5 frozen negative cases that FAILED under bge-m3 pipeline retrieval
# (evidence/eval/pipeline_bgem3-pipeline.json: neg_pass 2/7 -> these 5).
CASE_IDS = ["RB-N-001", "RB-N-002", "RB-N-003", "RB-N-004", "RB-N-006"]

import os  # noqa: E402

# Production gray toggle (env wins by design — claim_support.py enabled()).
os.environ["CLAIM_SUPPORT_ENABLED"] = "1"


def H(jwt):
    return {"Authorization": "Bearer " + jwt, "X-Tenant-ID": TENANT,
            "Content-Type": "application/json"}


def get_kbid(jwt, name):
    req = urllib.request.Request(
        BASE + "/api/v1/knowledge-bases?page=1&limit=50", headers=H(jwt))
    with urllib.request.urlopen(req, timeout=30) as r:
        doc = json.loads(r.read().decode("utf-8"))
    for kb in doc.get("data") or []:
        if kb.get("name") == name:
            return kb["id"]
    raise SystemExit("KB not found: " + name)


def search(jwt, kbid, query):
    body = json.dumps({"query": query, "knowledge_base_id": kbid,
                       "search_method": "vector_search"},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + "/api/v1/knowledge-search",
                                 data=body, headers=H(jwt), method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        doc = json.loads(r.read().decode("utf-8"))
    if doc.get("success") is not True:
        raise RuntimeError("search failed: " + str(doc.get("error"))[:120])
    out = []
    for src in doc.get("data") or []:
        fname = src.get("knowledge_filename") or src.get(
            "knowledge_title") or ""
        out.append({
            "doc_id": str(fname).rsplit(".", 1)[0],
            "content": src.get("content") or src.get("matched_content") or "",
            "score": src.get("score"),
        })
    return out


# ---------------------------------------------------------------- scan
_NUM = re.compile(r"\d+(?:\.\d+)?")
_CN_NUM = re.compile(
    r"[一二三四五六七八九十百千万亿]+(?:元|倍|年|日|天|个月|%)")
_LAWNAME = re.compile(r"《[^》]{2,40}》")


def wrong_fact_scan(answer: str, evidence: list) -> dict:
    """Automated first-pass flagging (task section 9): numbers / Chinese
    amounts / law titles in the DELIVERED answer that do NOT appear in the
    qualified evidence. Manual review follows in the report."""
    ev_text = "".join(e.get("content", "") for e in evidence)
    ev_norm = re.sub(r"\s+", "", ev_text)
    flagged = []
    for m in _NUM.findall(answer or ""):
        # [E1]-style labels and bare small ordinals are not facts
        if m in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0"):
            continue
        if m not in ev_norm:
            flagged.append({"kind": "number", "value": m})
    for m in _CN_NUM.findall(answer or ""):
        if re.sub(r"\s+", "", m) not in ev_norm:
            flagged.append({"kind": "cn_amount", "value": m})
    for m in _LAWNAME.findall(answer or ""):
        if m not in ev_norm:
            flagged.append({"kind": "law_name", "value": m})
    return {"flagged": flagged,
            "counts": {"numbers": len(set(_NUM.findall(answer or ""))),
                       "cn_amounts": len(set(_CN_NUM.findall(answer or ""))),
                       "law_names": len(set(_LAWNAME.findall(answer or "")))}}


def classify_claims(text: str, evidence: list, rules: dict) -> list:
    """Per-claim classification rows for the delivered text (real module,
    read-only call — same deterministic typing the gate used)."""
    from runtime.grounding import claim_support as csupp
    rows = []
    try:
        for c in csupp.split_claims(text or "", rules):
            v = csupp.check(c["claim_text"] + "。", evidence, rules=rules)
            state = "SUPPORTED" if v.get("ok") else (
                ";".join(v.get("violations") or [])[:80] or "GATE_FAIL")
            rows.append({"claim": c["claim_text"][:120],
                         "claim_type": c.get("claim_type", ""),
                         "support_state": state})
    except Exception as exc:  # noqa: BLE001 — diagnostics only
        rows.append({"claim": "<classification error: %s>" % exc,
                     "claim_type": "", "support_state": "UNKNOWN"})
    return rows


# ---------------------------------------------------------------- main
def main() -> int:
    import yaml
    from runtime.grounding import context as gctx
    from runtime.grounding import gate as ggate
    from runtime.grounding import loop as gloop
    from runtime.intent.classifier import classify
    from runtime.qa_agent.agent import _qualified_evidence, system_prompt
    from runtime.agent.config import load_llm_config

    jwt = (REPO / "tmp" / "weknora-admin.jwt").read_text(
        encoding="utf-8").strip()
    kbid = get_kbid(jwt, EVAL_KB_NAME)
    rules = ggate.load_rules()
    top_k = int((rules.get("retrieval") or {}).get("top_k", 8))

    bench = yaml.safe_load(
        (KB / "retrieval-benchmark-v1.yaml").read_text(encoding="utf-8"))

    provider = load_llm_config().to_provider(qa=True)
    print("LLM provider:", provider.name, provider.model, flush=True)

    # designed observation seam (loop.shadow_observer, no-op unless set)
    shadow_log = []

    def observer(event, data):
        try:
            shadow_log.append({"event": event,
                               "answer": (data.get("answer") or "")[:4000],
                               "ok": data.get("ok"),
                               "violations": (data.get("violations")
                                              or [])[:10]})
        except Exception:  # noqa: BLE001
            pass
    gloop.shadow_observer = observer

    out_path = EVID / "negative_qa_slice.json"
    record = {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "kb": EVAL_KB_NAME, "kb_id": kbid,
              "claim_support": "enabled via env CLAIM_SUPPORT_ENABLED=1 "
                               "(production gray toggle; env wins by design)",
              "generation_model": provider.model,
              "rules_top_k": top_k, "cases": []}

    for cid in CASE_IDS:
        q = bench[cid]["query"]
        print("=" * 60, flush=True)
        print(cid, q, flush=True)
        trace = {"case_id": cid, "query": q}

        # 1. Intent (real, deterministic)
        ir = classify(q)
        governed_unknown_qa = (ir["intent_id"] == "unknown_insurance_intent"
                               and "domain:insurance_anchor"
                               in (ir.get("reason_codes") or []))
        trace["intent"] = {
            "intent_id": ir["intent_id"], "confidence": ir["confidence"],
            "clarification_required": ir["clarification_required"],
            "reason_codes": ir["reason_codes"][:5],
            "production_route": ("knowledge-qa slice (governed unknown "
                                 "w/ insurance anchor — K.28.7 seam)"
                                 if governed_unknown_qa else
                                 "clarify/unknown path (QA slice would NOT "
                                 "fire in production)"),
        }
        # generate_grounded input contract: insurance_qa or governed unknown
        if governed_unknown_qa:
            qa_intent = ir            # the REAL production intent record
            trace["intent"]["qa_input"] = "real intent_result (as production)"
        else:
            qa_intent = {              # synthetic, DISCLOSED — QA chain probe
                "intent_id": "insurance_qa", "confidence": 1.0,
                "confidence_source": "probe",
                "context_refs": {}, "clarification_required": False,
                "reason_codes": ["probe:synthetic_qa_intent_for_slice"],
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            trace["intent"]["qa_input"] = (
                "synthetic insurance_qa (intent layer would divert; QA chain "
                "force-driven to test the embedding-variable layers)")

        # 2. Retrieval (real WeKnora vector_search on eval KB)
        hits = search(jwt, kbid, q)
        trace["retrieved_documents"] = [
            {"document_id": h["doc_id"], "chunk_id": "(window over doc)",
             "score": h["score"], "rank": i + 1,
             "chars": len(h["content"])}
            for i, h in enumerate(hits)]
        print("  retrieval:", len(hits), "hits ->",
              [h["doc_id"] for h in hits[:6]], flush=True)

        # 3. C2 Qualification (real module, frozen rules)
        items = [{"content": h["content"], "source_name": h["doc_id"],
                  "document_name": h["doc_id"]} for h in hits]
        qualified = _qualified_evidence(items, q, rules)
        qset = {id(it) for it in qualified}
        trace["qualified_evidence"] = [
            {"chunk_id": "(window over doc)",
             "document_id": it["source_name"],
             "qualified": id(it) in qset,
             "reason": ("bigram floor pass" if id(it) in qset
                        else "below min_query_bigram_overlap")}
            for it in items]
        print("  qualified:", len(qualified), flush=True)

        if not qualified:
            trace["final_answer"] = "(refusal template: insufficient_evidence)"
            trace["final_decision"] = "REFUSAL"
            trace["pollution"] = "SAFE_FALSE_RETRIEVAL (no qualified evidence)"
            record["cases"].append(trace)
            out_path.write_text(json.dumps(record, ensure_ascii=False,
                                           indent=1), encoding="utf-8")
            continue

        # 4. Evidence assembly (production shape: top_k cap)
        evidence = [("E%d" % (i + 1),
                     {"content": it["content"],
                      "header": gloop.kb_header(it),
                      "anchor": gctx.anchor(it)})
                    for i, it in enumerate(qualified[:top_k])]
        retrieval_rec = gctx.retrieval(
            q, top_k, "weknora-eval-bge-m3", "success",
            len(items), 0, False)

        # 5+6+7. LLM -> Citation Gate -> Claim Support -> Final
        shadow_log.clear()
        gateway = gloop.build_gateway(provider, rules)
        t0 = time.time()
        result = gloop.generate_grounded(
            q, evidence, qa_intent, retrieval_rec, gateway, rules,
            system_prompt(rules))
        dt = time.time() - t0
        answer = result.get("answer", "")
        status = result.get("grounding_status", "")
        reason = result.get("failure_reason", "")

        gen = result.get("generation_provenance", {}) or {}
        trace["generation"] = {
            "model": gen.get("model", ""), "provider": gen.get("provider",
                                                               ""),
            "prompt_version": gen.get("prompt_version", ""),
            "attempts": gen.get("attempts", 0),
            "elapsed_s": round(dt, 1)}
        trace["shadow_final_gate"] = (shadow_log[-1] if shadow_log
                                      else None)
        if shadow_log:
            trace["raw_generated_answer"] = shadow_log[-1].get(
                "answer", "")[:4000]
            trace["raw_gate_ok"] = shadow_log[-1].get("ok")
            trace["raw_gate_violations"] = shadow_log[-1].get(
                "violations", [])

        # claim classification on the DELIVERED text
        trace["generated_claims"] = classify_claims(answer, evidence, rules)
        trace["citation_gate"] = {
            "result": ("PASS" if status in ("grounded",
                                            "partial_grounding")
                       else "REJECT (%s)" % reason)}
        trace["claim_support"] = {
            "result": ("PASS" if status in ("grounded",
                                            "partial_grounding")
                       else ("REJECT" if "claim" in " ".join(
                           trace["raw_gate_violations"]
                           if trace.get("raw_gate_violations") else [])
                           or any("claim" in str(v) for v in
                                  (gen.get("gate_violations") or []))
                           else "not the blocking layer (see violations)"))}
        trace["final_answer"] = answer
        trace["final_decision"] = ("ANSWER" if status == "grounded"
                                   else "PARTIAL"
                                   if status == "partial_grounding"
                                   else "REFUSAL")
        trace["failure_reason"] = reason
        trace["wrong_fact_scan"] = wrong_fact_scan(answer, [
            {"content": e["content"]} for _, e in evidence])
        print("  final:", trace["final_decision"], reason, "| %.1fs" % dt,
              flush=True)

        record["cases"].append(trace)
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=1),
                            encoding="utf-8")
        time.sleep(1.0)

    gloop.shadow_observer = None
    print("\nsaved ->", out_path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
