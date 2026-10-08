# -*- coding: utf-8 -*-
"""Pipeline-level benchmark through the REAL WeKnora search path
(vector_search), against a given KB — for the embedding A/B.

Frozen: 57 cases, qualification floor, claim-support rule, top-10.
Usage: python pipeline_bench.py <kb_name> <tag>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3]))  # repo root
sys.path.insert(0, str(HERE.parents[1] / "tools"))

KB = HERE.parents[1]
EVID = KB / "evidence" / "eval"
BASE = "http://127.0.0.1:8080"
TENANT = "10001"
TOP_K = 10


def H(jwt):
    return {"Authorization": f"Bearer {jwt}", "X-Tenant-ID": TENANT,
            "Content-Type": "application/json"}


def get_kbid(jwt, name):
    r = requests.get(f"{BASE}/api/v1/knowledge-bases", headers=H(jwt), timeout=30)
    r.raise_for_status()
    for kb in r.json()["data"]:
        if kb["name"] == name:
            return kb["id"]
    raise SystemExit(f"KB {name} not found")


def search(jwt, kbid, query):
    r = requests.post(f"{BASE}/api/v1/knowledge-search", headers=H(jwt),
                      json={"query": query, "knowledge_base_id": kbid,
                            "search_method": "vector_search"}, timeout=60)
    r.raise_for_status()
    doc = r.json()
    if doc.get("success") is not True:
        return []
    out = []
    for src in doc.get("data") or []:
        fname = src.get("knowledge_filename") or src.get("knowledge_title") or ""
        out.append({"doc_id": str(fname).rsplit(".", 1)[0],
                    "content": src.get("content") or src.get("matched_content") or "",
                    "score": src.get("score")})
    return out


def qualify(query, hits):
    from runtime.grounding import gate as ggate
    from runtime.qa_agent.agent import _qualified_evidence

    rules = ggate.load_rules()
    items = [{"content": h["content"], "source_name": h["doc_id"],
              "document_name": h["doc_id"]} for h in hits]
    kept = _qualified_evidence(items, query, rules)
    ids = {it["source_name"] for it in kept}
    return [h for h in hits if h["doc_id"] in ids]


def compact(s):
    return "".join(str(s or "").split())


def claim_ok(fact, chunks):
    from runtime.grounding import claim_support as cs

    v = cs.check(fact + "。", [{"content": c} for c in chunks],
                 rules={"claim_support": {"enabled": True}})
    contained = any(compact(fact) in compact(c) for c in chunks)
    return {"module_ok": v.get("ok"), "contained": contained,
            "ok": bool(v.get("ok")) or contained}


def main() -> int:
    kb_name, tag = sys.argv[1], sys.argv[2]
    jwt = (HERE.parents[3] / "tmp" / "weknora-admin.jwt").read_text(encoding="utf-8").strip()
    kbid = get_kbid(jwt, kb_name)
    print(f"KB {kb_name}: {kbid}")
    bench = yaml.safe_load((KB / "retrieval-benchmark-v1.yaml").read_text(encoding="utf-8"))
    cases = [(cid, c) for cid, c in bench.items() if isinstance(c, dict)]
    results = []
    counts = {"total": 0, "PASS": 0, "FAIL": 0, "recall1": 0, "recall5": 0,
              "recall10": 0, "mrr": 0.0, "qualified": 0, "claim_pass": 0,
              "claim_total": 0, "neg_pass": 0, "neg_total": 0, "npos": 0}
    for cid, c in cases:
        rec = {"case_id": cid, "query": c["query"]}
        try:
            hits = search(jwt, kbid, c["query"])
        except Exception as exc:  # noqa: BLE001
            rec.update({"status": "ERROR", "error": str(exc)[:150]})
            results.append(rec)
            counts["total"] += 1
            counts["FAIL"] += 1
            continue
        rec["top10"] = [h["doc_id"] for h in hits[:TOP_K]]
        if c.get("expected_layer") == "NEGATIVE":
            counts["neg_total"] += 1
            qh = qualify(c["query"], hits)
            rec["qualified"] = [h["doc_id"] for h in qh]
            ok = not qh
            counts["neg_pass"] += int(ok)
        else:
            counts["npos"] += 1
            exp = c["expected_document_id"]
            rank = next((i + 1 for i, h in enumerate(hits) if h["doc_id"] == exp), None)
            rec["expected_rank"] = rank
            counts["recall1"] += int(rank == 1)
            counts["recall5"] += int(rank is not None and rank <= 5)
            counts["recall10"] += int(rank is not None and rank <= 10)
            counts["mrr"] += (1.0 / rank) if rank else 0.0
            qh = qualify(c["query"], hits)
            q_exp = [h for h in qh if h["doc_id"] == exp]
            rec["qualified_expected"] = bool(q_exp)
            counts["qualified"] += int(bool(q_exp))
            ok = rank is not None and rank <= TOP_K and bool(q_exp)
            if ok and c.get("claim_support_required"):
                counts["claim_total"] += 1
                v = claim_ok(c["expected_fact"], [h["content"] for h in q_exp][:5])
                rec["claim"] = v
                ok = v["ok"]
                counts["claim_pass"] += int(ok)
        rec["status"] = "PASS" if ok else "FAIL"
        counts["total"] += 1
        counts[rec["status"]] += 1
        results.append(rec)
        print(f"{cid}: {rec['status']}" + (f" rank={rec.get('expected_rank')}" if rec.get("expected_rank") else ""))
        time.sleep(0.3)
    summary = {"kb": kb_name, "kb_id": kbid, "tag": tag,
               "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "counts": counts,
               "results": results}
    (EVID / f"pipeline_{tag}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False))
    print("saved ->", EVID / f"pipeline_{tag}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
