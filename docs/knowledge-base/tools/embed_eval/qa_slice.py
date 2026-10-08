# -*- coding: utf-8 -*-
"""Generalized full-QA-slice harness (migration edition).

Runs a case list through the REAL production QA chain, in-process:
intent (real classifier) -> WeKnora vector_search on the named KB ->
C2 qualification (frozen rules) -> LLM (real gateway, .env QA tier) ->
citation gate + claim support (generate_grounded; CLAIM_SUPPORT_ENABLED=1
in-process = production gray toggle) -> final answer.

Identical engine to negative_qa_slice.py (same evidence-trace shape);
cases supplied via a JSON list so positive/negative/general sets and both
embedding arms run the exact same code path.

Usage: python qa_slice.py <kb_name> <arm_tag> <cases.json>
  cases.json: [{"case_id","query","intent_mode":"auto"|"force_qa"}, ...]
Output: evidence/eval/qa_slice_<arm_tag>.json (incremental)
"""
from __future__ import annotations

import json
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

import os  # noqa: E402

os.environ["CLAIM_SUPPORT_ENABLED"] = "1"   # production gray toggle (env wins)


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
        raise RuntimeError("search failed")
    out = []
    for src in doc.get("data") or []:
        fname = src.get("knowledge_filename") or src.get(
            "knowledge_title") or ""
        out.append({"doc_id": str(fname).rsplit(".", 1)[0],
                    "content": src.get("content")
                    or src.get("matched_content") or "",
                    "score": src.get("score")})
    return out


def classify_claims(text, evidence, rules):
    from runtime.grounding import claim_support as csupp
    rows = []
    for c in csupp.split_claims(text or "", rules):
        v = csupp.check(c["claim_text"] + "。", evidence, rules=rules)
        rows.append({"claim": c["claim_text"][:110],
                     "claim_type": c.get("claim_type", ""),
                     "support": "SUPPORTED" if v.get("ok")
                     else "REJECTED"})
    return rows


def main() -> int:
    from runtime.grounding import context as gctx
    from runtime.grounding import gate as ggate
    from runtime.grounding import loop as gloop
    from runtime.intent.classifier import classify
    from runtime.qa_agent.agent import _qualified_evidence, system_prompt
    from runtime.agent.config import load_llm_config

    kb_name, arm, cases_path = sys.argv[1], sys.argv[2], sys.argv[3]
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))

    jwt = (REPO / "tmp" / "weknora-admin.jwt").read_text(
        encoding="utf-8").strip()
    kbid = get_kbid(jwt, kb_name)
    rules = ggate.load_rules()
    top_k = int((rules.get("retrieval") or {}).get("top_k", 8))
    provider = load_llm_config().to_provider(qa=True)
    print("KB %s (%s) | arm=%s | %d cases | model=%s"
          % (kb_name, kbid, arm, len(cases), provider.model), flush=True)

    shadow_log = []

    def observer(event, data):
        try:
            shadow_log.append({"answer": (data.get("answer") or "")[:4000],
                               "ok": data.get("ok"),
                               "violations": (data.get("violations")
                                              or [])[:10]})
        except Exception:  # noqa: BLE001
            pass
    gloop.shadow_observer = observer

    out_path = EVID / ("qa_slice_%s.json" % arm)
    record = {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kb": kb_name,
              "kb_id": kbid, "arm": arm, "model": provider.model,
              "cases": []}

    for case in cases:
        cid, q = case["case_id"], case["query"]
        print("=" * 60, flush=True)
        print(cid, q, flush=True)
        trace = {"case_id": cid, "query": q}

        ir = classify(q)
        governed = (ir["intent_id"] == "unknown_insurance_intent"
                    and "domain:insurance_anchor"
                    in (ir.get("reason_codes") or []))
        qa_intent_route = (ir["intent_id"] == "insurance_qa") or governed
        trace["intent"] = {"intent_id": ir["intent_id"],
                           "confidence": ir["confidence"],
                           "clarify": ir["clarification_required"],
                           "reasons": ir["reason_codes"][:4],
                           "qa_route": qa_intent_route}
        if qa_intent_route:
            qa_intent = ir
        else:
            qa_intent = {"intent_id": "insurance_qa", "confidence": 1.0,
                         "confidence_source": "probe",
                         "context_refs": {},
                         "clarification_required": False,
                         "reason_codes": ["probe:synthetic_qa_intent"],
                         "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")}

        t0 = time.time()
        hits = search(jwt, kbid, q)
        t_ret = time.time() - t0
        trace["retrieved"] = [{"doc": h["doc_id"], "rank": i + 1,
                               "score": round(h["score"] or 0, 5)}
                              for i, h in enumerate(hits)]
        trace["retrieval_ms"] = int(t_ret * 1000)

        items = [{"content": h["content"], "source_name": h["doc_id"],
                  "document_name": h["doc_id"]} for h in hits]
        qualified = _qualified_evidence(items, q, rules)
        qids = {it["source_name"] for it in qualified}
        trace["qualified"] = sorted(qids)
        trace["qualified_n"] = len(qualified)

        if not qualified:
            trace["final_decision"] = "REFUSAL"
            trace["failure_reason"] = "insufficient_evidence"
            trace["final_answer"] = "(template: insufficient_evidence)"
            record["cases"].append(trace)
            out_path.write_text(json.dumps(record, ensure_ascii=False,
                                           indent=1), encoding="utf-8")
            print("  -> REFUSAL insufficient_evidence (no qualified)",
                  flush=True)
            continue

        evidence = [("E%d" % (i + 1),
                     {"content": it["content"],
                      "header": gloop.kb_header(it),
                      "anchor": gctx.anchor(it)})
                    for i, it in enumerate(qualified[:top_k])]
        retrieval_rec = gctx.retrieval(q, top_k, kb_name, "success",
                                       len(items), 0, False)
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

        trace["generation"] = {"attempts": gen.get("attempts", 0),
                               "elapsed_s": round(dt, 1)}
        trace["raw_answer"] = (shadow_log[-1].get("answer", "")
                               if shadow_log else "")
        trace["raw_viol_kinds"] = sorted(set(
            str(v).split(":")[0] for v in
            (shadow_log[-1].get("violations") if shadow_log else [])))
        trace["raw_violations"] = ((shadow_log[-1].get("violations"))
                                   if shadow_log else [])[:10]
        trace["cited"] = result.get("evidence_refs", [])
        trace["claims"] = classify_claims(answer, evidence, rules)
        trace["final_answer"] = answer
        trace["final_decision"] = ("ANSWER" if status == "grounded"
                                   else "PARTIAL"
                                   if status == "partial_grounding"
                                   else "REFUSAL")
        trace["failure_reason"] = reason
        print("  -> %s (%s) | %.1fs" % (trace["final_decision"], reason, dt),
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
