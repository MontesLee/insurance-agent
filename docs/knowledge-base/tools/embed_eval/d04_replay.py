# -*- coding: utf-8 -*-
"""D-04 offline replay (D04-EVAL) — isolated from production AND from the
Phase16 authority runtime (own ledger paths; zero :8123 contact).

Arms:
  P0  current policy (citation gate + lexical claim support) on the
      REFUSED drafts from qa_slice_bgem3-migration — must reproduce
      refusals (control).
  CA  Candidate A = Phase16 authority chain (v2 semantics: hard-class
      prefilter -> sentence-granularity citation -> semantic judge ->
      independent post-gate) applied OFFLINE to the same drafts.
  CB  Candidate B = prompt-only regeneration (candidate v5 guidance:
      assert the fact using evidence-original phrasing, cite every
      sentence) through the UNCHANGED P0 gates.

Outputs: evidence/eval/d04_replay.json (+ d04_replay_ledger.jsonl)
"""
from __future__ import annotations

import json
import os
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
KBID = "44af9ff2-ecef-445e-87c6-cb1458cd4d44"

os.environ["CLAIM_SUPPORT_ENABLED"] = "1"   # offline process (not :8123)

# v2 authority semantics (mirror of tools/k29c_fix3_phase13_authority.py,
# OFFLINE ledger; production authority untouched)
HARD = re.compile(
    r"\d|P0\d{2}|demo-|该产品|这款|某产品|保险法|管理办法|监管|银保监|"
    r"令第|施行|保证.{0,6}(续保|赔付|返还)|承诺|"
    r"所有|全部|一律|任何|都.{0,3}(能|可|会|是|有)|必然|一定会|"
    r"每个人|所有人群|所有情况|所有产品|"
    r"您|你家|您家|你的")
CIT = re.compile(r"\[E\d+\]")

CANDIDATE_B_PROMPT = (
    "You are the Insurance QA Agent. Answer using ONLY the numbered "
    "evidence provided. RULES: (1) Keep every fact sentence SHORT and "
    "close to the evidence wording — reuse the evidence's own key "
    "phrases verbatim instead of paraphrasing; (2) cite [E1]-style "
    "immediately after EVERY fact sentence; (3) answer ONLY the part "
    "of the question the evidence directly states — if the evidence "
    "gives a partial answer, state that part and stop; (4) never add "
    "conclusions, summaries or advice beyond the evidence text.")


def H(jwt):
    return {"Authorization": "Bearer " + jwt, "X-Tenant-ID": TENANT,
            "Content-Type": "application/json"}


def search(jwt, query):
    body = json.dumps({"query": query, "knowledge_base_id": KBID,
                       "search_method": "vector_search"},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + "/api/v1/knowledge-search",
                                 data=body, headers=H(jwt), method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        doc = json.loads(r.read().decode("utf-8"))
    out = []
    for src in doc.get("data") or []:
        fname = str(src.get("knowledge_filename") or "").rsplit(".", 1)[0]
        out.append({"content": src.get("content") or "", "source_name":
                    fname, "document_name": fname})
    return out


def main() -> int:
    import yaml
    from runtime.grounding import gate as ggate
    from runtime.grounding import loop as gloop
    from runtime.grounding import context as gctx
    from runtime.grounding import claim_support as csupp
    from runtime.grounding.shadow_judge import SemanticJudgeClient
    from runtime.qa_agent.agent import _qualified_evidence, system_prompt
    from runtime.agent.config import load_llm_config
    from knowledge.pilot.ingest_registry_pg import _pg_store
    sys.path.insert(0, str(REPO / "tools"))
    from k29c_fix3_independent_postgate import IndependentPostGate

    rules = ggate.load_rules()
    top_k = int((rules.get("retrieval") or {}).get("top_k", 8))
    jwt = (REPO / "tmp" / "weknora-admin.jwt").read_text(
        encoding="utf-8").strip()
    provider = load_llm_config().to_provider(qa=True)
    judge = SemanticJudgeClient(load_llm_config().to_provider(qa=True),
                                tau=0.7)
    judge._provider._timeout = 25.0
    pg = IndependentPostGate()

    sl = json.loads((EVID / "qa_slice_bgem3-migration.json")
                    .read_text(encoding="utf-8"))["cases"]
    cases = [c for c in sl
             if c.get("failure_reason") == "citation_gate_rejected"
             and not c["case_id"].startswith("RB-N")]      # 13 D-04 cases
    print("D04-EVAL cases:", len(cases), flush=True)

    ledger = open(REPO / "tmp" / "obs" / "d04_replay_ledger.jsonl", "a",
                  encoding="utf-8")
    out = {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "cases": []}

    n_judge = 0

    def ca_decision(sentence, evidence):
        """Candidate A: authority chain, offline. True=upgrade."""
        nonlocal n_judge
        bare = CIT.sub("", sentence)
        if HARD.search(bare):
            return False, "hard-class"
        if not CIT.search(sentence) or not evidence:
            return False, "no-citation"
        n_judge += 1
        t0 = time.time()
        try:
            jr = judge.judge_claim(bare, [evidence[0][1].get("content", "")
                                          [:1500]])
        except Exception as exc:  # noqa: BLE001 — fail closed
            jr = {"decision": "KEEP_BASELINE", "reason": repr(exc)[:60]}
        rec = {"arm": "CA", "sentence": sentence[:90],
               "judge": jr.get("decision"), "s": round(time.time() - t0, 1)}
        if jr.get("decision") != "ALLOW_UPGRADE":
            ledger.write(json.dumps(rec, ensure_ascii=False) + "\n")
            return False, "judge:" + str(jr.get("decision"))
        raw_ev = [{"content": e.get("content", ""),
                   "source_name": e.get("header", ""),
                   "product_id": (e.get("anchor") or {}).get("document_id")}
                  for _, e in evidence]
        ok, reasons = pg.check(sentence, raw_ev)
        rec["postgate"] = ok
        ledger.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return (ok, "postgate:" + ("pass" if ok else str(reasons)[:40]))

    for c in cases:
        cid, q, draft = c["case_id"], c["query"], c.get("raw_answer") or ""
        print("=" * 56, flush=True)
        print(cid, q, flush=True)
        # rebuild the deterministic evidence set for this query
        hits = search(jwt, q)
        qualified = _qualified_evidence(hits, q, rules)
        evidence = [("E%d" % (i + 1),
                     {"content": it["content"],
                      "header": gloop.kb_header(it),
                      "anchor": gctx.anchor(it)})
                    for i, it in enumerate(qualified[:top_k])]
        emap = {l: e["anchor"] for l, e in evidence}

        # ---- P0 control: gates on the original draft ----
        p0_cit = ggate.check(draft, emap, rules)
        p0_sup = csupp.check(draft, evidence, rules=rules) \
            if p0_cit.get("ok") else {"ok": False}
        p0_refused = not (p0_cit.get("ok") and p0_sup.get("ok"))
        partial_rows = [r for r in (p0_sup.get("claims") or [])
                        if r.get("support_status") == "PARTIAL"]
        unsup_rows = [r for r in (p0_sup.get("claims") or [])
                      if r.get("support_status") in ("UNSUPPORTED",
                                                     "CONTRADICTED")]

        # ---- Candidate A: authority chain on failing sentences ----
        sentences = [s for s in ggate.split_sentences(draft, rules)
                     if s.strip()]
        ca_upgraded, ca_blocked = [], []
        for s in sentences:
            v = ggate.check(s, emap, rules)
            if v.get("ok"):
                sv = csupp.check(s, evidence, rules=rules)
                if sv.get("ok"):
                    continue                      # passes already
            up, why = ca_decision(s, evidence)
            (ca_upgraded if up else ca_blocked).append(
                {"s": s[:60], "why": why})
        ca_deliver = bool(ca_upgraded) and not any(
            b["why"] == "no-citation" for b in ca_blocked) and \
            not any(b["why"].startswith("judge") for b in ca_blocked)
        # deliver only if EVERY failing sentence upgraded (v2 semantics)

        # ---- Candidate B: regeneration with candidate prompt ----
        cb = {"status": "not-run"}
        try:
            user = "User question: %s\n\n%s" % (
                q, gloop.evidence_block([(l, e) for l, e in evidence]))
            from runtime.agent.model import LLMRequest
            gw = gloop.build_gateway(provider, rules)
            req = LLMRequest(
                messages=[{"role": "user", "content": user}],
                system_prompt=CANDIDATE_B_PROMPT, max_tokens=1024,
                timeout_s=90.0,
                metadata={"purpose": "d04-candidate-b"})
            resp = gw.generate(req)
            ans = (resp.content or "").strip()
            b_cit = ggate.check(ans, emap, rules)
            b_sup = csupp.check(ans, evidence, rules=rules) \
                if b_cit.get("ok") else {"ok": False}
            cb = {"status": "ok",
                  "delivered": bool(b_cit.get("ok") and b_sup.get("ok")),
                  "cit_ok": bool(b_cit.get("ok")),
                  "sup_ok": bool(b_sup.get("ok")),
                  "answer": ans[:400],
                  "partial_rows": len([r for r in (b_sup.get("claims")
                                                   or []) if r.get(
                                                       "support_status")
                                       == "PARTIAL"]),
                  "unsup_rows": len([r for r in (b_sup.get("claims") or [])
                                     if r.get("support_status") in
                                     ("UNSUPPORTED", "CONTRADICTED")])}
        except Exception as exc:  # noqa: BLE001
            cb = {"status": "error", "error": repr(exc)[:120]}

        rec = {"case_id": cid, "query": q,
               "p0": {"refused": p0_refused,
                      "partial_rows": len(partial_rows),
                      "unsupported_rows": len(unsup_rows)},
               "ca": {"failing_sentences": len(ca_upgraded)
                      + len(ca_blocked),
                      "upgraded": len(ca_upgraded),
                      "blocked": ca_blocked[:4],
                      "delivered": ca_deliver},
               "cb": cb}
        out["cases"].append(rec)
        (EVID / "d04_replay.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1),
            encoding="utf-8")
        print("  P0 refused=%s (partial %d/unsup %d) | CA upgraded %d/%d "
              "deliver=%s | CB delivered=%s"
              % (p0_refused, len(partial_rows), len(unsup_rows),
                 len(ca_upgraded), len(ca_upgraded) + len(ca_blocked),
                 ca_deliver, cb.get("delivered")), flush=True)
        time.sleep(1.0)

    out["judge_calls_total"] = n_judge
    (EVID / "d04_replay.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    ledger.close()
    print("judge calls:", n_judge, "->", EVID / "d04_replay.json",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
