# -*- coding: utf-8 -*-
"""D-04 audit step 1: build the unified refusal corpus from existing
bge-era evidence (kb-v1), attribute each case to D04-R1..R8, build the
sufficiency matrix, and run the minimal-answer gate test (offline,
read-only runtime modules; zero production contact).

Sources (all kb-v1 + bge-m3, 2026-10-05):
  qa_slice_bgem3-migration.json  19 cases, FULL chain (drafts + violations)
  prod_shadow_kb1.json           30 cases, governed chain (no drafts)
Labels: REAL=0 (window has zero real traffic); all PRODUCTION-LIKE.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

KB = HERE.parents[1]
EVID = KB / "evidence" / "eval"
OUT = EVID / "d04_corpus.json"

import yaml  # noqa: E402
from runtime.grounding import gate as ggate  # noqa: E402
from runtime.grounding import claim_support as csupp  # noqa: E402

RULES = ggate.load_rules()


def compact(s):
    return "".join(str(s or "").split())


def load(name):
    return json.loads((EVID / name).read_text(encoding="utf-8"))


def main() -> int:
    bench = yaml.safe_load(
        (KB / "retrieval-benchmark-v1.yaml").read_text(encoding="utf-8"))
    slice_cases = {c["case_id"]: c
                   for c in load("qa_slice_bgem3-migration.json")["cases"]}
    nomic = {c["case_id"]: c
             for c in load("qa_slice_nomic-migration.json")["cases"]}
    shadow = load("prod_shadow_kb1.json")["cases"]

    rows = []

    # ---- population 1: migration slice (full chain, bge) ----
    for cid, c in slice_cases.items():
        q = c["query"]
        neg = cid.startswith("RB-N")
        bench_case = bench.get(cid) if cid.startswith("RB-") else None
        exp_doc = (bench_case or {}).get("expected_document_id")
        exp_fact = (bench_case or {}).get("expected_fact") or ""
        retrieved = [r["doc"] for r in c.get("retrieved", [])]
        qual_n = c.get("qualified_n", 0)
        reason = c.get("failure_reason") or ("ANSWERED"
                                             if c.get("final_decision")
                                             == "ANSWER" else "?")
        viol_kinds = set(c.get("raw_viol_kinds") or [])
        draft = c.get("raw_answer") or ""
        n_qual = (nomic.get(cid) or {}).get("qualified_n")
        n_ret = [r["doc"] for r in (nomic.get(cid) or {}).get("retrieved",
                                                              [])]
        n_fin = (nomic.get(cid) or {}).get("final_decision")

        # ---- attribution (ordered) ----
        if c.get("final_decision") == "ANSWER":
            rclass, root = "-", "answered (not a D-04 case)"
        elif neg:
            rclass, root = "R7", "negative query — correct refusal"
        elif reason == "insufficient_evidence":
            if exp_doc and exp_doc not in retrieved:
                rclass, root = "R1", "expected doc not retrieved"
            elif qual_n == 0:
                rclass, root = "R2", "retrieved but C2 qualified 0"
            else:
                rclass, root = "R2", "insufficient_evidence at governed path"
        elif reason == "llm_unavailable":
            rclass, root = "R8", "provider transient (excluded from D-04 base)"
        else:
            # citation_gate_rejected — classify with draft + expected fact
            ev_texts = []
            # rebuild evidence contents from the slice's stored retrieval?
            # drafts + violations are authoritative; expected-fact presence
            # is tested against the corpus via the benchmark fact anchor
            if "fact_sentence" in viol_kinds and "claim_support" \
                    not in viol_kinds:
                rclass, root = "R3", "citation presence failure only"
            elif "claim_support" in viol_kinds:
                # did the draft assert the expected fact (cited) and fail?
                if exp_fact and compact(exp_fact)[:20] in compact(draft):
                    rclass, root = "R4", "draft asserts the fact; lexical " \
                                        "support rejects (paraphrase ceiling)"
                elif exp_doc and exp_doc in retrieved and qual_n > 0:
                    # model had the right doc; did it avoid asserting?
                    if re.search(r"证据(中)?(未|不包含|没有)|无法.*(回答|依据)",
                                 draft):
                        rclass, root = "R6", "model hedged/meta-described " \
                                            "instead of asserting (evidence " \
                                            "was qualified)"
                    else:
                        rclass, root = "R4", "claim-support rejection on " \
                                            "generated claims"
                else:
                    rclass, root = "R4", "claim-support rejection"
            else:
                rclass, root = "R8", "unclassified gate rejection"

        # ---- minimal-answer gate test (benchmark positives only) ----
        minans = None
        if bench_case and exp_fact and c.get("final_decision") == "REFUSAL" \
                and exp_doc in retrieved:
            # evidence contents from the case's stored retrieval (top hits)
            hits = c.get("retrieved", [])
            # reconstruct items list shape used by the slice harness
            # content not stored per-hit in the slice json; use the
            # benchmark fact against the corpus chunk file instead:
            # the minimal answer is tested against a synthetic single
            # evidence = the expected fact itself (upper bound check)
            ev = [("E1", {"content": exp_fact, "header": "test",
                          "anchor": {}})]
            text = "%s[E1]。" % exp_fact
            v1 = ggate.check(text, {"E1": {}}, RULES)
            v2 = csupp.check(text, ev, rules=RULES)
            minans = {"citation_ok": bool(v1.get("ok")),
                      "support_ok": bool(v2.get("ok")),
                      "support_violations": (v2.get("violations")
                                             or [])[:3]}
        rows.append({
            "case_id": cid, "population": "PRODUCTION-LIKE",
            "source": "qa_slice_bgem3(kb-v1)",
            "query": q,
            "category": "NEGATIVE" if neg else (
                bench_case.get("risk_level", "GEN")
                if bench_case else "GENERAL"),
            "retrieved_docs": retrieved[:6], "qualified_n": qual_n,
            "final": c.get("final_decision"), "reason": reason,
            "viol_kinds": sorted(viol_kinds),
            "r_class": rclass, "root": root,
            "minimal_answer_test": minans,
            "nomic": {"qualified_n": n_qual,
                      "exp_doc_rank": (n_ret.index(exp_doc) + 1
                                       if exp_doc and exp_doc in n_ret
                                       else None),
                      "final": n_fin},
            "bge_exp_doc_rank": (retrieved.index(exp_doc) + 1
                                 if exp_doc and exp_doc in retrieved
                                 else None),
            "draft_head": draft[:160],
        })

    # ---- population 2: governed shadow ----
    slice_queries = {c["query"] for c in rows}
    for c in shadow:
        if c["query"] in slice_queries:
            continue                       # dedupe (same query traced fully)
        neg = c["category"] == "negative"
        ret = c.get("retrieval", {})
        reason = c.get("reason") or ("ANSWERED" if c.get("final")
                                     == "ANSWER" else "?")
        viol = set(c.get("viol_kinds") or [])
        if c.get("final") == "ANSWER":
            rclass, root = "-", "answered"
        elif neg:
            rclass, root = "R7", "negative query — correct refusal"
        elif reason == "llm_unavailable":
            rclass, root = "R8", "provider transient"
        elif reason == "insufficient_evidence":
            rclass, root = ("R2" if (ret.get("allowed") or 0) > 0 else "R1"),\
                "governed path: allowed=%s qual=%s" % (
                    ret.get("allowed"), c.get("qualified_n"))
        elif "claim_support" in viol:
            rclass, root = "R4", "claim-support rejection (no draft kept)"
        elif viol:
            rclass, root = "R3", "citation presence failure"
        else:
            rclass, root = "R8", "unclassified"
        rows.append({
            "case_id": c["case_id"], "population": "PRODUCTION-LIKE",
            "source": "prod_shadow(kb-v1,governed)",
            "query": c["query"], "category": c["category"],
            "retrieved_docs": (ret.get("docs") or [])[:6],
            "qualified_n": c.get("qualified_n"),
            "final": c.get("final"), "reason": reason,
            "viol_kinds": sorted(viol), "r_class": rclass, "root": root,
            "minimal_answer_test": None, "nomic": None,
            "bge_exp_doc_rank": None, "draft_head": (c.get("answer")
                                                     or "")[:120],
        })

    (EVID / "d04_corpus.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- summary ----
    from collections import Counter
    refusals = [r for r in rows if r["final"] == "REFUSAL"]
    cnt = Counter(r["r_class"] for r in refusals)
    print("corpus:", len(rows), "cases | refusals:", len(refusals))
    for k in ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"):
        n = cnt.get(k, 0)
        print("  %s: %d (%.0f%%)" % (k, n, n / len(refusals) * 100))
    mat = Counter()
    for r in refusals:
        mat[(("ret+" if (r["qualified_n"] or 0) > 0 else "ret-"),
             ("cit+" if "claim_support" in r["viol_kinds"] else "cit-"),
             r["r_class"])] += 1
    print("matrix:", dict(mat))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
