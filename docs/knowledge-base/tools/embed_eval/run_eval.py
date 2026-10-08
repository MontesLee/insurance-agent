# -*- coding: utf-8 -*-
"""KB-V1 Embedding A/B evaluation core.

Frozen inputs (never modified here):
  - corpus chunks: evidence/eval/chunks_791.json (live 791, read-only)
  - benchmark: retrieval-benchmark-v1.yaml (57 cases)
Per model:
  1. embed all 791 chunks (index vectors)
  2. embed the 57 benchmark queries
  3. cosine ranking (vectors are unit-norm) -> full ranking per query
  4. metrics: Recall@1/5/10, MRR (50 positive), qualification/50,
     claim-support (verbatim containment ground truth, HIGH-risk only),
     negative pass/FPR
  5. self-retrieval over a seeded 50-chunk sample:
     a. identical-text (expected degenerate in direct mode -> documented)
     b. prefix-64 (query = first 64 chars; realistic partial quote)
  6. failure matrix for every failed positive case
  7. term-ladder discrimination (§15)

Usage: python run_eval.py <model_tag> <ollama_model_name>
"""
from __future__ import annotations

import json
import math
import random
import re
import sys
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[3]))  # repo root for runtime imports
sys.path.insert(0, str(HERE.parents[1] / "tools"))

from embed_driver import embed  # noqa: E402

KB = HERE.parents[1]
EVID = KB / "evidence" / "eval"

SELF_SAMPLE_N = 50
SELF_SEED = 42
PREFIX_LEN = 64

LAYER_MAP = {
    "L1-01": "法律法规",
    "L1-25": "政策意见",
    "L2-01": "疾病定义", "L2-02": "疾病定义",
    "L2-03": "监管通知", "L2-05": "监管通知",
}
DOC_TYPE_MAP = {
    "L1-01": "法律", "L1-25": "国务院意见",
    "L2-01": "行业规范", "L2-02": "行业规范",
}


def doc_layer(doc_id: str) -> str:
    if doc_id in ("L2-01", "L2-02"):
        return "行业规范-疾病定义"
    if doc_id in ("L2-03", "L2-05"):
        return "监管通知"
    if doc_id == "L1-01":
        return "法律"
    if doc_id == "L1-25":
        return "政策意见"
    return "监管规章"


def cosine_rank(qv: list[float], index: list[list[float]]) -> list[int]:
    sims = [sum(a * b for a, b in zip(qv, cv)) for cv in index]
    return sorted(range(len(sims)), key=lambda i: -sims[i]), sims


def compact(s: str) -> str:
    return "".join(str(s or "").split())


def qualify_hits(query: str, hits: list[dict]) -> list[dict]:
    from runtime.grounding import gate as ggate
    from runtime.qa_agent.agent import _qualified_evidence

    rules = ggate.load_rules()
    items = [
        {"content": h["content"], "source_name": h["doc_id"], "document_name": h["doc_id"]}
        for h in hits
    ]
    kept = _qualified_evidence(items, query, rules)
    ids = {it["source_name"] for it in kept}
    return [h for h in hits if h["doc_id"] in ids]


def claim_verdict(fact: str, chunks: list[str]) -> dict:
    from runtime.grounding import claim_support as cs

    verdict = cs.check(fact + "。", [{"content": c} for c in chunks],
                       rules={"claim_support": {"enabled": True}})
    contained = any(compact(fact) in compact(c) for c in chunks)
    return {"module_ok": verdict.get("ok"), "contained": contained,
            "ok": bool(verdict.get("ok")) or contained}


def embed_all(model: str, texts: list[str], tag: str, kind: str) -> list[list[float]]:
    cache = EVID / f"emb_{tag}_{kind}.json"
    if cache.exists():
        d = json.loads(cache.read_text())
        if d.get("n") == len(texts) and d.get("model") == model:
            return d["vectors"]
    res = embed(model, texts)
    EVID.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({**res, "model": model, "texts_sha": hash(tuple(texts))}))
    return res["vectors"]


def main() -> int:
    tag = sys.argv[1]  # nomic | bge-m3
    model = sys.argv[2]  # ollama model name
    chunks = json.loads((EVID / "chunks_791.json").read_text(encoding="utf-8"))
    n = len(chunks)
    docs = [str(c["doc_file"]).rsplit(".", 1)[0] for c in chunks]
    contents = [c["content"] for c in chunks]

    bench = yaml.safe_load((KB / "retrieval-benchmark-v1.yaml").read_text(encoding="utf-8"))
    cases = [(cid, c) for cid, c in bench.items() if isinstance(c, dict)]
    positives = [(cid, c) for cid, c in cases if c.get("expected_layer") != "NEGATIVE"]
    negatives = [(cid, c) for cid, c in cases if c.get("expected_layer") == "NEGATIVE"]

    t0 = time.time()
    index_vecs = embed_all(model, contents, tag, "index")
    index_time = time.time() - t0
    queries = [c["query"] for _, c in cases]
    query_vecs = embed_all(model, queries, tag, "queries")

    dim = len(index_vecs[0])
    out: dict = {
        "tag": tag, "model": model, "dim": dim, "chunks": n,
        "index_embed_seconds": round(index_time, 1),
        "metrics": {}, "cases": [], "self_retrieval": {}, "failure_matrix": {},
        "ladders": {},
    }

    # ---------- benchmark ----------
    recalls = {1: 0, 5: 0, 10: 0}
    mrr_sum = 0.0
    qual_pass = 0
    claim_pass = 0
    claim_module_pass = 0
    claim_total = 0
    for (cid, c), qv in zip(cases, query_vecs):
        order, _ = cosine_rank(qv, index_vecs)
        hits = [
            {"doc_id": docs[i], "content": contents[i], "score": None}
            for i in order[:10]
        ]
        rec = {"case_id": cid, "query": c["query"], "top10": [docs[i] for i in order[:10]]}
        if c.get("expected_layer") == "NEGATIVE":
            qhits = qualify_hits(c["query"], hits)
            rec["qualified"] = [h["doc_id"] for h in qhits]
            rec["pass"] = not qhits
        else:
            exp = c["expected_document_id"]
            ranks = [i + 1 for i, d in enumerate([docs[j] for j in order]) if d == exp]
            first = ranks[0] if ranks else None
            rec["expected_rank_full"] = first
            for k in (1, 5, 10):
                if first is not None and first <= k:
                    recalls[k] += 1
            if first:
                mrr_sum += 1.0 / first
            top_hits = hits[:10]
            qhits = qualify_hits(c["query"], top_hits)
            q_exp = [h for h in qhits if h["doc_id"] == exp]
            rec["qualified_expected"] = bool(q_exp)
            if q_exp:
                qual_pass += 1
            ok = first is not None and first <= 10 and bool(q_exp)
            if ok and c.get("claim_support_required"):
                claim_total += 1
                v = claim_verdict(c["expected_fact"], [h["content"] for h in q_exp][:5])
                rec["claim"] = v
                claim_module_pass += int(bool(v["module_ok"]))
                ok = v["ok"]
                if v["ok"]:
                    claim_pass += 1
            rec["pass"] = ok
        out["cases"].append(rec)

    npos = len(positives)
    neg_pass = sum(1 for r in out["cases"] if r["case_id"].startswith("RB-N") and r["pass"])
    out["metrics"] = {
        "Recall@1": recalls[1] / npos,
        "Recall@5": recalls[5] / npos,
        "Recall@10": recalls[10] / npos,
        "MRR": mrr_sum / npos,
        "QualifiedEvidence": f"{qual_pass}/50",
        "QualificationRate": qual_pass / 50,
        "ClaimSupport": f"{claim_pass}/{claim_total}",
        "ClaimModuleOnly": f"{claim_module_pass}/{claim_total}",
        "NegativePass": f"{neg_pass}/{len(negatives)}",
        "NegativeFPR": (len(negatives) - neg_pass) / len(negatives),
    }

    # ---------- self-retrieval ----------
    rng = random.Random(SELF_SEED)
    sample_idx = sorted(rng.sample(range(n), SELF_SAMPLE_N))
    ident_at = {1: 0, 5: 0, 10: 0}
    prefix_at = {1: 0, 5: 0, 10: 0}
    sr_rows = []
    prefix_texts = [contents[i][:PREFIX_LEN] for i in sample_idx]
    prefix_vecs = embed_all(model, prefix_texts, tag, "selfprefix")
    for row_i, i in enumerate(sample_idx):
        qv = index_vecs[i]  # identical text -> identical vector
        order, _ = cosine_rank(qv, index_vecs)
        rank_ident = order.index(i) + 1
        qv2 = prefix_vecs[row_i]
        order2, _ = cosine_rank(qv2, index_vecs)
        rank_prefix = order2.index(i) + 1
        for k in (1, 5, 10):
            ident_at[k] += int(rank_ident <= k)
            prefix_at[k] += int(rank_prefix <= k)
        sr_rows.append({
            "chunk_id": chunks[i]["chunk_id"], "doc": docs[i],
            "layer": doc_layer(docs[i]), "chunk_index": chunks[i]["chunk_index"],
            "chars": chunks[i]["chars"],
            "identical_rank": rank_ident, "prefix64_rank": rank_prefix,
            "prefix_query": prefix_texts[row_i],
        })
    by_layer: dict = {}
    for r in sr_rows:
        by_layer.setdefault(r["layer"], []).append(r)
    layer_stats = {}
    for layer, rows in by_layer.items():
        layer_stats[layer] = {
            "n": len(rows),
            "prefix64@1": sum(1 for r in rows if r["prefix64_rank"] <= 1) / len(rows),
            "prefix64@10": sum(1 for r in rows if r["prefix64_rank"] <= 10) / len(rows),
        }
    out["self_retrieval"] = {
        "sample": {"n": SELF_SAMPLE_N, "seed": SELF_SEED, "prefix_len": PREFIX_LEN},
        "identical@1/5/10": [ident_at[k] / SELF_SAMPLE_N for k in (1, 5, 10)],
        "prefix64@1/5/10": [prefix_at[k] / SELF_SAMPLE_N for k in (1, 5, 10)],
        "prefix64_by_layer": layer_stats,
        "rows": sr_rows,
    }

    # ---------- failure matrix ----------
    matrix: dict = {k: [] for k in
                    ("DATA_MISSING", "CHUNKING", "EMBEDDING", "RANKING",
                     "QUALIFICATION", "NEGATIVE_NOISE", "UNKNOWN")}
    corpus_compact = [compact(c) for c in contents]
    # adjacency map for boundary check
    by_doc_chunks: dict = {}
    for i, c in enumerate(chunks):
        by_doc_chunks.setdefault(docs[i], []).append((c["chunk_index"], i))
    for rec in out["cases"]:
        if rec["pass"]:
            continue
        cid = rec["case_id"]
        case = bench[cid]
        if cid.startswith("RB-N"):
            matrix["NEGATIVE_NOISE"].append({"case": cid, "qualified": rec.get("qualified", [])})
            continue
        fact = compact(case["expected_fact"])
        exp = case["expected_document_id"]
        holders = [i for i in range(n) if docs[i] == exp and fact in corpus_compact[i]]
        if not holders:
            # boundary check: consecutive chunk concat (same doc, adjacent index)
            found_boundary = False
            for idx_pair in by_doc_chunks.get(exp, []):
                pass
            seq = sorted(by_doc_chunks.get(exp, []))
            for (i1, a), (i2, b) in zip(seq, seq[1:]):
                if i2 == i1 + 1 and fact in compact(contents[a] + contents[b]):
                    found_boundary = True
                    break
            if found_boundary:
                matrix["CHUNKING"].append({"case": cid, "reason": "fact spans chunk boundary"})
            else:
                matrix["DATA_MISSING"].append({"case": cid, "reason": "fact not found verbatim"})
            continue
        h = holders[0]
        # query ranking of holder
        qi = [c["query"] for _, c in cases].index(case["query"])
        order, _ = cosine_rank(query_vecs[qi], index_vecs)
        qrank = order.index(h) + 1
        # self ranking of holder (identical text; meaningful via prefix)
        pv = embed_all(model, [contents[h][:PREFIX_LEN]], tag, "tmp_holder") \
            if False else None
        if rec.get("qualified_expected") is False and qrank <= 10:
            matrix["QUALIFICATION"].append({"case": cid, "holder_query_rank": qrank})
        elif qrank > 10:
            # holder not retrieved by the case query: is the embedding able
            # to find the chunk from its own prefix?
            # use cached prefix vectors when holder is in the sample
            sr_map = {r["chunk_id"]: r for r in sr_rows}
            hrow = sr_map.get(chunks[h]["chunk_id"])
            if hrow and hrow["prefix64_rank"] > 10:
                matrix["EMBEDDING"].append(
                    {"case": cid, "holder_query_rank": qrank,
                     "holder_prefix64_rank": hrow["prefix64_rank"]})
            else:
                matrix["RANKING"].append(
                    {"case": cid, "holder_query_rank": qrank,
                     "note": "chunk findable by own prefix but not by case query"})
        else:
            matrix["UNKNOWN"].append({"case": cid, "holder_query_rank": qrank})
    out["failure_matrix"] = {k: v for k, v in matrix.items() if v}
    out["failure_matrix_counts"] = {k: len(v) for k, v in matrix.items()}

    # ---------- term ladders (§15) ----------
    ladders = {
        "销售阶梯": ["保险销售", "保险销售行为", "保险销售行为管理", "保险销售行为管理办法"],
        "重疾阶梯": ["重大疾病", "重大疾病保险", "重大疾病保险的疾病定义", "重大疾病保险的疾病定义使用规范"],
    }
    ladder_out = {}
    for name, terms in ladders.items():
        tvecs = embed_all(model, terms, tag, f"ladder_{name}")
        # nearest doc for each term (max cosine over chunks, aggregated to doc)
        nearest = {}
        for t, tv in zip(terms, tvecs):
            order, sims = cosine_rank(tv, index_vecs)
            doc_scores: dict = {}
            for i in order:
                d = docs[i]
                if d not in doc_scores:
                    doc_scores[d] = sims[i]
            top_docs = sorted(doc_scores.items(), key=lambda kv: -kv[1])[:3]
            nearest[t] = [[d, round(s, 4)] for d, s in top_docs]
        # adjacent-term separation: sim(term, chunks of its OWN most-specific doc)
        ladder_out[name] = {"nearest_docs": nearest}
    # pair similarity matrix within each ladder
    for name, terms in ladders.items():
        tvecs = embed_all(model, terms, tag, f"ladder_{name}")
        sims = [[round(sum(a * b for a, b in zip(x, y)), 4) for y in tvecs] for x in tvecs]
        ladder_out[name]["pair_sims"] = sims
        ladder_out[name]["terms"] = terms
    out["ladders"] = ladder_out

    dest = EVID / f"eval_{tag}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved ->", dest)
    print(json.dumps(out["metrics"], ensure_ascii=False, indent=1))
    print("self-retrieval identical@1 (expect 1.0, degenerate):", out["self_retrieval"]["identical@1/5/10"][0])
    print("self-retrieval prefix64@1/5/10:", out["self_retrieval"]["prefix64@1/5/10"])
    print("failure matrix:", out["failure_matrix_counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
