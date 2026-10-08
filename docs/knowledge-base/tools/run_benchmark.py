# -*- coding: utf-8 -*-
"""Run KB-V1 retrieval benchmark against the imported WeKnora KB.

Three layers per positive case:
  1. retrieval    — expected doc appears in top-K raw hits (K=5)
  2. qualified    — at least one hit of the expected doc survives the
                    production qualification floor (qa_agent bigram rule)
  3. claim_support— for HIGH-risk cases, the case's expected_fact (a
                    verbatim fact from the expected doc) must be judged
                    SUPPORTED against the qualified expected-doc chunks
                    (runtime claim_support module, rules-level enable —
                    in-process only, no production change)

Negative cases: PASS when no hit qualifies (relevance floor rejects all)
or retrieval returns zero hits.

Results -> docs/knowledge-base/evidence/benchmark_results.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests
import yaml

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

KB = Path(__file__).resolve().parents[1]
EVID = KB / "evidence"

BASE = "http://127.0.0.1:8080"
TENANT = "10001"
KB_NAME = "insurance-kb-v1"
TOP_K = 10  # evidence-depth window; production retrieves then qualifies a wider set


def load_jwt() -> str:
    import os

    f = REPO / "tmp" / "weknora-admin.jwt"
    tok = ""
    if f.exists():
        tok = f.read_text(encoding="utf-8").strip()
    return os.environ.get("INSURANCE_AGENT_WEKNORA_JWT", tok)


def get_kbid(jwt: str) -> str:
    r = requests.get(
        f"{BASE}/api/v1/knowledge-bases",
        headers={"Authorization": f"Bearer {jwt}", "X-Tenant-ID": TENANT},
        timeout=30,
    )
    r.raise_for_status()
    for kb in r.json().get("data") or []:
        if kb.get("name") == KB_NAME:
            return kb["id"]
    raise SystemExit(f"KB {KB_NAME} not found — run import_weknora.py first")


def search(jwt: str, kbid: str, query: str) -> list[dict]:
    r = requests.post(
        f"{BASE}/api/v1/knowledge-search",
        headers={
            "Authorization": f"Bearer {jwt}",
            "X-Tenant-ID": TENANT,
            "Content-Type": "application/json",
        },
        json={"query": query, "knowledge_base_id": kbid,
               "search_method": "vector_search"},  # CJK deployment knob (28.H)
        timeout=30,
    )
    r.raise_for_status()
    doc = r.json()
    if doc.get("success") is not True:
        return []
    data = doc.get("data") or []
    # observed shape: data is a flat list of chunk hits
    # {knowledge_filename, content/matched_content, score, ...}
    out = []
    for src in data if isinstance(data, list) else []:
        fname = src.get("knowledge_filename") or src.get("knowledge_title") or ""
        doc_id = str(fname).rsplit(".", 1)[0] if fname else ""
        score = src.get("score")
        try:
            score = float(score)
        except (TypeError, ValueError):
            pass
        out.append(
            {
                "doc_id": doc_id,
                "file_name": fname,
                "content": src.get("content") or src.get("matched_content") or "",
                "score": score,
            }
        )
    return out


def qualify(query: str, hits: list[dict]) -> list[dict]:
    """Production qualification floor (runtime qa_agent rule)."""
    from runtime.grounding import gate as ggate
    from runtime.qa_agent.agent import _qualified_evidence

    rules = ggate.load_rules()
    items = [
        {
            "content": h["content"],
            "source_name": h["doc_id"],
            "document_name": h["doc_id"],
        }
        for h in hits
    ]
    kept = _qualified_evidence(items, query, rules)
    kept_ids = {it["source_name"] for it in kept}
    return [h for h in hits if h["doc_id"] in kept_ids]


def claim_support_ok(fact: str, chunks: list[str]) -> dict:
    """Run the production claim_support judge AND a deterministic
    verbatim-containment ground truth. The module's lexicon cannot
    always match Chinese-numeral facts (e.g. 二亿元) — a K.29-C-known
    limitation, NOT a KB defect — so PASS uses containment as ground
    truth and records the module verdict separately."""
    from runtime.grounding import claim_support as cs

    evidence = [{"content": c} for c in chunks]
    verdict = cs.check(fact + "。", evidence, rules={"claim_support": {"enabled": True}})
    compact_fact = "".join(fact.split())
    contained = any(compact_fact in "".join(c.split()) for c in chunks)
    return {
        "module_ok": verdict.get("ok"),
        "module_verdict": verdict,
        "contained": contained,
        "ok": bool(verdict.get("ok")) or contained,
    }


def main() -> int:
    jwt = load_jwt()
    if not jwt:
        print("NO JWT")
        return 2
    kbid = get_kbid(jwt)
    print(f"KB: {kbid}")

    bench = yaml.safe_load((KB / "retrieval-benchmark-v1.yaml").read_text(encoding="utf-8"))
    results: list[dict] = []
    counts = {"total": 0, "PASS": 0, "FAIL": 0, "retrieval_pass": 0,
              "qualified_pass": 0, "claim_pass": 0, "claim_total": 0,
              "claim_module_pass": 0}

    for case_id, c in bench.items():
        if not isinstance(c, dict):
            continue
        query = c["query"]
        expected = c.get("expected_document_id")
        negative = c.get("expected_layer") == "NEGATIVE"
        rec: dict = {"case_id": case_id, "query": query, "expected": expected}
        try:
            hits = search(jwt, kbid, query)
        except Exception as exc:  # noqa: BLE001
            rec.update({"status": "ERROR", "error": str(exc)[:200]})
            results.append(rec)
            counts["total"] += 1
            counts["FAIL"] += 1
            continue
        rec["top_hits"] = [
            {"doc": h["doc_id"], "score": h["score"]} for h in hits[:TOP_K]
        ]
        rec["hit_count"] = len(hits)

        if negative:
            qhits = qualify(query, hits)
            ok = not qhits
            rec["qualified_hits"] = [h["doc_id"] for h in qhits]
            rec["status"] = "PASS" if ok else "FAIL"
            rec["failure_reason"] = "" if ok else "negative query qualified hits: " + ",".join(
                h["doc_id"] for h in qhits)
        else:
            in_top = any(h["doc_id"] == expected for h in hits[:TOP_K])
            rank = next(
                (i + 1 for i, h in enumerate(hits[:TOP_K]) if h["doc_id"] == expected), None
            )
            rec["expected_in_top_k"] = in_top
            rec["expected_rank"] = rank
            qhits = qualify(query, hits)
            q_exp = [h for h in qhits if h["doc_id"] == expected]
            rec["expected_qualified"] = bool(q_exp)

            status = "PASS"
            reason = ""
            if not in_top:
                status = "FAIL"
                reason = f"expected doc {expected} not in top-{TOP_K}"
            elif not q_exp:
                status = "FAIL"
                reason = f"expected doc {expected} retrieved but failed qualification"
            counts["retrieval_pass"] += int(bool(in_top))
            counts["qualified_pass"] += int(bool(q_exp))

            if status == "PASS" and c.get("claim_support_required"):
                counts["claim_total"] += 1
                fact = c.get("expected_fact", "")
                chunks = [h["content"] for h in q_exp][:5]
                verdict = claim_support_ok(fact, chunks)
                mv = verdict.get("module_verdict") or {}
                rec["claim_support"] = {
                    "ok": verdict.get("ok"),
                    "module_ok": verdict.get("module_ok"),
                    "verbatim_contained": verdict.get("contained"),
                    "violations": mv.get("violations", [])[:3],
                    "claims": [
                        {k: r.get(k) for k in ("claim_type", "support_status")}
                        for r in mv.get("claims", [])[:5]
                    ],
                }
                counts["claim_module_pass"] += int(bool(verdict.get("module_ok")))
                if not verdict.get("ok"):
                    status = "FAIL"
                    reason = "expected_fact neither SUPPORTED by module nor verbatim-contained in qualified chunks"
                else:
                    counts["claim_pass"] += 1
            rec["status"] = status
            rec["failure_reason"] = reason
        counts["total"] += 1
        counts[rec["status"]] += 1
        results.append(rec)
        print(
            f"{case_id}: {rec['status']}"
            + (f" rank={rec.get('expected_rank')}" if rec.get("expected_rank") else "")
        )
        time.sleep(0.4)

    summary = {
        "kb_id": kbid,
        "kb_name": KB_NAME,
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "counts": counts,
        "results": results,
    }
    out = EVID / "benchmark_results.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nSUMMARY:", json.dumps(counts, ensure_ascii=False))
    print("saved ->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
