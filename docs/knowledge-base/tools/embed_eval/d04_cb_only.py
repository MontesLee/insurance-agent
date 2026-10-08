# -*- coding: utf-8 -*-
"""D-04 Candidate B replay-only pass (prompt regeneration through the
UNCHANGED P0 gates). Reuses the evidence rebuild from d04_replay."""
from __future__ import annotations

import json
import os
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
KBID = "44af9ff2-ecef-445e-87c6-cb1458cd4d44"
os.environ["CLAIM_SUPPORT_ENABLED"] = "1"

CANDIDATE_B_PROMPT = (
    "You are the Insurance QA Agent. Answer using ONLY the numbered "
    "evidence provided. RULES: (1) Keep every fact sentence SHORT and "
    "close to the evidence wording — reuse the evidence's own key "
    "phrases verbatim instead of paraphrasing; (2) cite [E1]-style "
    "immediately after EVERY fact sentence; (3) answer ONLY the part "
    "of the question the evidence directly states — if the evidence "
    "gives a partial answer, state that part and stop; (4) never add "
    "conclusions, summaries or advice beyond the evidence text.")


def main() -> int:
    from runtime.grounding import gate as ggate
    from runtime.grounding import loop as gloop
    from runtime.grounding import context as gctx
    from runtime.grounding import claim_support as csupp
    from runtime.qa_agent.agent import _qualified_evidence
    from runtime.agent.config import load_llm_config
    from runtime.llm.types import LLMRequest

    rules = ggate.load_rules()
    top_k = int((rules.get("retrieval") or {}).get("top_k", 8))
    jwt = (REPO / "tmp" / "weknora-admin.jwt").read_text(
        encoding="utf-8").strip()
    provider = load_llm_config().to_provider(qa=True)
    gateway = gloop.build_gateway(provider, rules)

    def H():
        return {"Authorization": "Bearer " + jwt, "X-Tenant-ID": "10001",
                "Content-Type": "application/json"}

    def search(query):
        body = json.dumps({"query": query, "knowledge_base_id": KBID,
                           "search_method": "vector_search"},
                          ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(BASE + "/api/v1/knowledge-search",
                                     data=body, headers=H(), method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            doc = json.loads(r.read().decode("utf-8"))
        return [{"content": s.get("content") or "",
                 "source_name": str(s.get("knowledge_filename")
                                    or "").rsplit(".", 1)[0],
                 "document_name": str(s.get("knowledge_filename")
                                      or "").rsplit(".", 1)[0]}
                for s in doc.get("data") or []]

    replay = json.loads((EVID / "d04_replay.json").read_text(
        encoding="utf-8"))
    sl = json.loads((EVID / "qa_slice_bgem3-migration.json")
                    .read_text(encoding="utf-8"))["cases"]
    drafts = {c["case_id"]: c for c in sl}

    out = {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "arm": "CB prompt-regeneration (P0 gates unchanged)",
           "cases": []}
    (EVID / "d04_replay_cb.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8")

    for rec in replay["cases"]:
        cid, q = rec["case_id"], rec["query"]
        hits = search(q)
        qualified = _qualified_evidence(hits, q, rules)
        evidence = [("E%d" % (i + 1),
                     {"content": it["content"],
                      "header": gloop.kb_header(it),
                      "anchor": gctx.anchor(it)})
                    for i, it in enumerate(qualified[:top_k])]
        emap = {l: e["anchor"] for l, e in evidence}
        user = "User question: %s\n\n%s" % (
            q, gloop.evidence_block([(l, e) for l, e in evidence]))
        row = {"case_id": cid, "query": q}
        delivered = False
        answer = ""
        for attempt in range(2):            # 1 regen like production
            req = LLMRequest(
                messages=[{"role": "user", "content": user}],
                system_prompt=CANDIDATE_B_PROMPT, max_tokens=1024,
                timeout_s=90.0,
                metadata={"purpose": "d04-cb", "attempt": attempt})
            try:
                resp = gateway.generate(req)
            except Exception as exc:  # noqa: BLE001
                row["error"] = repr(exc)[:100]
                break
            answer = (resp.content or "").strip()
            cit = ggate.check(answer, emap, rules)
            sup = csupp.check(answer, evidence, rules=rules) \
                if cit.get("ok") else {"ok": False}
            delivered = bool(cit.get("ok") and sup.get("ok"))
            if delivered:
                break
        row.update({"delivered": delivered, "answer": answer[:350],
                    "chars": len(answer)})
        out["cases"].append(row)
        (EVID / "d04_replay_cb.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1),
            encoding="utf-8")
        print("%-14s CB delivered=%s chars=%d" % (cid, delivered,
                                                  len(answer)), flush=True)
        time.sleep(1.0)
    n = sum(1 for c in out["cases"] if c.get("delivered"))
    print("CB delivered: %d/%d" % (n, len(out["cases"])), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
