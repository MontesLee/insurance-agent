# -*- coding: utf-8 -*-
"""D-04 replay arm SD: verified-subset delivery simulation (deterministic,
zero LLM) — mirrors loop.py's AUTHORITY_VERIFIED_SUBSET_DELIVERY block:
on whole-answer gate failure, keep sentences that individually pass the
SAME full gate (citation + claim support), re-gate the join, deliver if
non-empty and passing. Applied to (a) the 13 original P0 drafts and
(b) the 13 Candidate-B answers (CB+SD combo = armed production + prompt
candidate)."""
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


def main() -> int:
    from runtime.grounding import gate as ggate
    from runtime.grounding import loop as gloop
    from runtime.grounding import context as gctx
    from runtime.grounding import claim_support as csupp
    from runtime.qa_agent.agent import _qualified_evidence

    rules = ggate.load_rules()
    top_k = int((rules.get("retrieval") or {}).get("top_k", 8))
    jwt = (REPO / "tmp" / "weknora-admin.jwt").read_text(
        encoding="utf-8").strip()

    def H():
        return {"Authorization": "Bearer " + jwt, "X-Tenant-ID": "10001",
                "Content-Type": "application/json"}

    def evidence_for(q):
        body = json.dumps({"query": q, "knowledge_base_id": KBID,
                           "search_method": "vector_search"},
                          ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(BASE + "/api/v1/knowledge-search",
                                     data=body, headers=H(), method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            doc = json.loads(r.read().decode("utf-8"))
        items = [{"content": s.get("content") or "",
                  "source_name": str(s.get("knowledge_filename")
                                     or "").rsplit(".", 1)[0],
                  "document_name": str(s.get("knowledge_filename")
                                       or "").rsplit(".", 1)[0]}
                 for s in doc.get("data") or []]
        qualified = _qualified_evidence(items, q, rules)
        ev = [("E%d" % (i + 1),
               {"content": it["content"], "header": gloop.kb_header(it),
                "anchor": gctx.anchor(it)})
              for i, it in enumerate(qualified[:top_k])]
        return ev, {l: e["anchor"] for l, e in ev}

    def full_gate(text, evidence, emap):
        v = ggate.check(text, emap, rules)
        if v.get("ok"):
            v = csupp.merge_verdict(
                v, csupp.check(text, evidence, rules=rules))
        return v

    def subset_deliver(answer, evidence, emap):
        sents = [s for s in ggate.split_sentences(answer, rules)
                 if s.strip()]
        keep = [s for s in sents if full_gate(s, evidence, emap).get("ok")]
        if not keep:
            return False, "", 0
        joined = "\n".join(
            s if s.endswith(("。", "！", "？", "!", "?", "；", ";"))
            else s + "。" for s in keep).strip()
        ok = bool(full_gate(joined, evidence, emap).get("ok"))
        return ok, joined, len(keep)

    sl = json.loads((EVID / "qa_slice_bgem3-migration.json")
                    .read_text(encoding="utf-8"))["cases"]
    cb = {c["case_id"]: c for c in json.loads(
        (EVID / "d04_replay_cb.json").read_text(encoding="utf-8"))["cases"]}

    out = {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "arm": "SD verified-subset simulation (deterministic)",
           "cases": []}
    for c in sl:
        if c.get("failure_reason") != "citation_gate_rejected" \
                or c["case_id"].startswith("RB-N"):
            continue
        cid, q = c["case_id"], c["query"]
        ev, emap = evidence_for(q)
        draft = c.get("raw_answer") or ""
        ok0, sub0, k0 = subset_deliver(draft, ev, emap)
        row = {"case_id": cid,
               "sd_original_draft": {"delivered": ok0, "kept": k0,
                                     "subset": sub0[:220]}}
        cbrow = cb.get(cid)
        if cbrow and cbrow.get("answer"):
            ok1, sub1, k1 = subset_deliver(cbrow["answer"], ev, emap)
            row["sd_cb_answer"] = {"delivered": ok1, "kept": k1,
                                   "subset": sub1[:220]}
        out["cases"].append(row)
        (EVID / "d04_replay_sd.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1),
            encoding="utf-8")
        print("%-14s SD(draft)=%s kept=%d | SD(CB)=%s kept=%s"
              % (cid, ok0, k0,
                 row.get("sd_cb_answer", {}).get("delivered"),
                 row.get("sd_cb_answer", {}).get("kept")), flush=True)
        time.sleep(0.5)
    n0 = sum(1 for r in out["cases"]
             if r["sd_original_draft"]["delivered"])
    n1 = sum(1 for r in out["cases"]
             if r.get("sd_cb_answer", {}).get("delivered"))
    print("SD on original drafts: %d/%d | SD on CB answers: %d/%d"
          % (n0, len(out["cases"]), n1, len(out["cases"])), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
