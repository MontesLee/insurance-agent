# -*- coding: utf-8 -*-
"""K.29-B aggregation — compute §14 metrics from k29b jsonl records.

No composite score, no ranking (task §10): only objective per-metric
numbers, with INSUFFICIENT_SAMPLE labeling when n < 3.

Usage:
  python tools/k29b_aggregate.py                 # all tmp/obs/k29b/*.jsonl
  python tools/k29b_aggregate.py A_main A_flash  # specific runs only
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(REPO, "tmp", "obs", "k29b")

# Uniform post-hoc refinement: evidence-meta/hedge variants that the
# narrow in-run EV_META_RE (pre-patch arms) missed. Idempotent for
# arms that already ran the broad regex in-run.
META2_RE = re.compile(
    r"证据|资料|未提及|未载明|未给出|未提供|没有|无法|不代表|不在|"
    r"以.{0,20}(为准|确认|核对)|建议.{0,12}(查阅|阅读|咨询|确认|查询)|"
    r"以具体产品|咨询保险公司")
LABEL_RE = re.compile(r"\[E\d+\]")


def refined_genuine(recs):
    """genuine entries after uniform broad-meta filtering; split by
    cited (label present in the claim text) vs uncited."""
    n = uncited = 0
    samples = []
    for r in recs:
        ev = r.get("eval") or {}
        for t in (ev.get("genuine_bad_list") or []):
            if META2_RE.search(t):
                continue
            n += 1
            if not LABEL_RE.search(t):
                uncited += 1
            elif len(samples) < 12:
                samples.append((r["case_id"], t))
    return n, uncited, samples


def sent_level_citation(recs):
    """Sentence-level citation completeness over stored answers (B/C
    arms) — the granularity the PRODUCTION citation gate enforces
    (clause-level claim split over-penalizes mid-sentence fragments
    whose sentence DOES end with [E#]). Caveat: answers stored
    truncated to 600 chars."""
    import sys
    sys.path.insert(0, REPO)
    from runtime.grounding import gate as ggate
    from runtime.grounding import claim_support as cs
    rules = ggate.load_rules()
    pat = rules["citation"]["pattern"]
    tot_f = tot_c = 0
    for r in recs:
        ans = r.get("answer") or ""
        if r.get("grounding") != "generated" or not ans:
            continue
        for s in ggate.split_sentences(ans, rules):
            if not s.strip():
                continue
            if cs.classify_claim(cs._CITATION_RE.sub("", s)) == "C-FACT":
                tot_f += 1
                if re.findall(pat, s):
                    tot_c += 1
    return tot_c, tot_f


def load(tags):
    runs = {}
    if tags:
        paths = [os.path.join(OUTDIR, t + ".jsonl") for t in tags]
    else:
        paths = sorted(glob.glob(os.path.join(OUTDIR, "*.jsonl")))
    for p in paths:
        tag = os.path.splitext(os.path.basename(p))[0]
        if tag.startswith(("SMOKE", "log")):
            continue
        recs = []
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    recs.append(json.loads(line))
        if recs:
            runs[tag] = recs
    return runs


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def agg_arm(recs):
    """Aggregate one (arm, slot) run: n cases, quality, grounding,
    safety, stability surfaces."""
    n = len(recs)
    out = {"n": n}
    llm_recs = [r for r in recs if r.get("grounding") in
                ("generated",) or (r.get("grounding") in
                                   ("grounded", "partial_grounding",
                                    "refused")
                                   and not r.get("refused_pre_llm")
                                   and r.get("grounding") != "not_qa_path"
                                   and r.get("final_policy_decision")
                                   != "BASELINE_ROUTE_product_qa_slice_"
                                      "off_refuse"
                                   and r.get("final_policy_decision")
                                   != "BASELINE_ROUTE_planning_path")]
    gen_recs = [r for r in recs if r.get("grounding") == "generated"]

    # ---- quality (baseline arms) ----
    gr = [r for r in recs if r.get("grounding") in
          ("grounded", "partial_grounding")]
    out["grounded"] = len(gr)
    out["partial_grounding"] = sum(
        1 for r in recs if r.get("grounding") == "partial_grounding")
    ref = [r for r in recs if r.get("grounding") == "refused"]
    out["refused"] = len(ref)
    out["refused_pre_llm"] = sum(1 for r in recs if r.get("refused_pre_llm"))
    reasons = defaultdict(int)
    for r in ref:
        reasons[r.get("failure_reason") or "?"] += 1
    out["refusal_reasons"] = dict(reasons)
    # harness/provider errors
    out["errors"] = sum(1 for r in recs
                        if r.get("grounding") in ("error", "harness_error"))
    out["not_qa_path"] = sum(1 for r in recs
                             if r.get("grounding") == "not_qa_path")

    # ---- candidate decision distribution ----
    dec = defaultdict(int)
    for r in recs:
        d = r.get("final_policy_decision")
        if d:
            dec[d] += 1
    out["decisions"] = dict(dec)

    # ---- grounding metrics over records WITH claim eval ----
    ev = [r for r in recs if r.get("eval")]
    cit = [r for r in recs if r.get("citation_final_attempt")]
    out["n_with_eval"] = len(ev)
    if ev:
        tot_out = sum(r["eval"]["n_fact_outside"] for r in ev)
        tot_sup = sum(r["eval"]["fact_outside_supported"] for r in ev)
        tot_cit = sum(r["eval"]["fact_outside_cited"] for r in ev)
        tot_hard = sum(r["eval"]["n_hard_inside_boundary"] for r in ev)
        tot_contra = sum(len(r["eval"]["contradicted_list"]) for r in ev)
        tot_inv = sum(len(r["eval"]["invented_labels"]) for r in ev)
        out["claim_support_rate"] = pct(tot_sup, tot_out)
        out["citation_rate_outside_facts"] = pct(tot_cit, tot_out)
        out["hard_inside_boundary_count"] = tot_hard
        out["contradicted_count"] = tot_contra
        out["invented_label_count"] = tot_inv
        out["risk_escape_recs"] = sum(
            1 for r in ev if r["eval"]["n_genuine_bad_facts"] > 0)
        g, gu, gs = refined_genuine(recs)
        out["genuine_bad_refined"] = g
        out["genuine_uncited_refined"] = gu
        if "fact_outside_supported_ws" in ev[0]["eval"]:
            tot_ws = sum(r["eval"]["fact_outside_supported_ws"]
                         for r in ev)
            out["claim_support_rate_ws_lenient"] = pct(tot_ws, tot_out)
    if cit:
        vals = [r["citation_final_attempt"]["completeness"]
                for r in cit
                if r["citation_final_attempt"]["completeness"] is not None]
        out["citation_completeness_mean"] = (
            round(sum(vals) / len(vals), 3) if vals else None)
        out["n_citation_measured"] = len(vals)
    gen_ans = [r for r in recs if r.get("grounding") == "generated"
               and (r.get("answer") or "")]
    if gen_ans:
        c, f = sent_level_citation(gen_ans)
        out["citation_sent_level"] = pct(c, f)
        out["citation_sent_level_c/f"] = "%d/%d" % (c, f)

    # ---- safety scans ----
    sc = [r for r in recs if r.get("safety")]
    if sc:
        out["safety_promise"] = sum(1 for r in sc if r["safety"]["promise"])
        out["safety_recommend_amount"] = sum(
            1 for r in sc if r["safety"]["recommend_amount"])
        out["safety_reg_uncited"] = sum(
            1 for r in sc if r["safety"]["reg_uncited"])

    # ---- R4 recommendation escape (QA answering personalized) ----
    r4 = [r for r in recs if r.get("risk") == "R4"]
    if r4:
        esc = [r for r in r4 if r.get("grounding") in
               ("grounded", "partial_grounding", "generated")]
        out["r4_answered_by_qa"] = len(esc)
        out["r4_total"] = len(r4)
        amt = [r for r in esc if (r.get("safety") or {})
               .get("recommend_amount")]
        out["r4_with_amount"] = len(amt)

    # ---- risk-class breakdown (valid/refuse/violation) ----
    by_risk = defaultdict(lambda: defaultdict(int))
    for r in recs:
        by_risk[r.get("risk")][
            r.get("final_policy_decision") or r.get("grounding")] += 1
    out["by_risk"] = {k: dict(v) for k, v in by_risk.items()}
    return out


def stability(recs, key):
    """Per-case repeat consistency for N>=3 runs (task §16)."""
    per = defaultdict(list)
    for r in recs:
        per[r["case_id"]].append(
            r.get("final_policy_decision") or r.get("grounding"))
    rows = {}
    stable = 0
    tot = 0
    for cid, ds in per.items():
        if len(ds) >= 3:
            tot += 1
            consistent = len(set(ds)) == 1
            stable += int(consistent)
            rows[cid] = {"n": len(ds), "consistent": consistent,
                         "decisions": ds}
    return {"per_case": rows,
            "consistent_rate": pct(stable, tot) if tot else None,
            "n_cases_ge3": tot}


def main():
    tags = sys.argv[1:]
    runs = load(tags)
    summary = {}
    for tag, recs in runs.items():
        summary[tag] = {"aggregate": agg_arm(recs)}
        n_rep = max((r.get("run_ix") or 1) for r in recs)
        if n_rep >= 3:
            summary[tag]["stability"] = stability(recs, tag)
    outp = os.path.join(OUTDIR, "summary.json")
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print("wrote %s (%d runs)" % (outp, len(summary)))
    for tag, s in summary.items():
        a = s["aggregate"]
        print("\n== %s ==" % tag)
        for k in ("n", "grounded", "partial_grounding", "refused",
                  "refused_pre_llm", "refusal_reasons", "errors",
                  "decisions"):
            if k in a:
                print("  %-28s %s" % (k, a[k]))
        for k in ("claim_support_rate", "citation_rate_outside_facts",
                  "citation_completeness_mean", "genuine_bad_fact_count",
                  "hard_inside_boundary_count", "contradicted_count",
                  "invented_label_count", "risk_escape_recs"):
            if k in a:
                print("  %-28s %s" % (k, a[k]))
        if "stability" in s:
            print("  stability_consistent_rate   %s (%d cases n>=3)" % (
                s["stability"]["consistent_rate"],
                s["stability"]["n_cases_ge3"]))


if __name__ == "__main__":
    main()
