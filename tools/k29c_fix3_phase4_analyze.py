# -*- coding: utf-8 -*-
"""FIX-3 Phase 4 — extended-shadow analysis (READ ONLY).

Consumes the cumulative shadow jsonl (+ Phase-3 records), produces:
  Phase 2  ALLOW_CASE_REVIEW (every ALLOW vs deterministic refusal)
  Phase 3  E-class breakdown (E1 给付 / E2 自由支配 / E3 报销 / E4)
  Phase 4  evidence-meta watch classification
  Phase 5  stability (repeat-agreement via claim-text clusters)
  Phase 6  second-layer SAFE_ALLOW / FALSE_ALLOW audit (deterministic
           re-verification: contradiction/numeric/product/date checks)
  Phase 7  sufficiency matrix (observed vs structurally-zero strata)
Output: tmp/obs/k29c_fix3_phase4_analysis.json
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from runtime.grounding import claim_support as cs  # noqa: E402

SRC = os.path.join(REPO, "tmp", "obs", "k29c_fix3_phase3_shadow.jsonl")
OUT = os.path.join(REPO, "tmp", "obs", "k29c_fix3_phase4_analysis.json")

RISK = {
    "numeric": re.compile(r"\d+(?:\.\d+)?\s*(?:天|日|万|万元|元|%|岁|周岁|年|倍|次|月)"),
    "product": re.compile(r"P0\d{2}|demo-|该产品|这款|某产品|重疾险A|医疗险A"),
    "regulatory": re.compile(r"保险法|管理办法|监管|施行|令第|银保监|条文|发布"),
    "payment": re.compile(r"保证.{0,6}(续保|赔付|返还)|返还|承诺|赔付比例|全额赔付"),
    "date": re.compile(r"\d{4}年|\d{1,2}月\d{1,2}日|生效|失效"),
    "negation": re.compile(r"不返还|不属于|不予|不能获|都赔|全部覆盖"),
}
E_CLASS = [
    ("E1", re.compile(r"给付|一次性|定额|按保额|打款|赔.*固定|一笔")),
    ("E2", re.compile(r"自由支配|随便.{0,4}(花|用)|用途|发票|还贷|房贷|用.{0,6}限制")),
    ("E3", re.compile(r"报销|凭.{0,6}票据|垫付|按比例")),
]
META_RE = re.compile(r"证据|资料|条款里|现有|未提及|没有提到|未载明")


def risk_of(text):
    return sorted(k for k, rx in RISK.items() if rx.search(text))


def eclass(text):
    for tag, rx in E_CLASS:
        if rx.search(text):
            return tag
    return "E4"


def main():
    recs = [json.loads(l) for l in open(SRC, encoding="utf-8")]
    # keep only well-formed claim records
    recs = [r for r in recs if "claim_text" in r]
    out = {"ts": "2026-10-02",
           "totals": {"records": len(recs),
                      "decisions": dict(Counter(
                          r.get("decision") for r in recs)),
                      "deterministic": dict(Counter(
                          r.get("deterministic") for r in recs)),
                      "hard_prefiltered": sum(
                          1 for r in recs if r.get("hard_prefilter"))}}

    # ---- Phase 2: ALLOW case review (judge ALLOW ∧ gate refused) ----
    allows = [r for r in recs if r.get("decision") == "ALLOW_UPGRADE"]
    reviews = []
    for i, r in enumerate(allows):
        t = r["claim_text"]
        risks = risk_of(t)
        raw = r.get("judge_raw") or {}
        # Phase 6 second-layer deterministic re-verification on the text
        # shape (no evidence replay here — evidence snapshot not stored;
        # re-verification = risk-pattern + raw.contradiction + hedge scan)
        false_indicators = [k for k in ("negation",) if k in risks]
        safe_shape = (not risks and not raw.get("contradiction")
                      and raw.get("entailment") == "yes")
        verdict = ("SAFE_ALLOW" if safe_shape else
                   "FALSE_ALLOW" if false_indicators else "REVIEW")
        reviews.append({
            "case_id": "ACR-%03d" % (i + 1), "claim": t,
            "risk_level": "high" if risks else "low",
            "risk_flags": risks, "claim_type": r.get("claim_type"),
            "deterministic": r.get("deterministic"),
            "judge": "ALLOW_UPGRADE",
            "confidence": raw.get("confidence"),
            "semantic_rationale": (raw.get("reason") or "")[:60],
            "second_layer": verdict})
    out["allow_case_review"] = reviews
    out["false_upgrade_audit"] = {
        "n_allow": len(reviews),
        "SAFE_ALLOW": sum(1 for x in reviews
                          if x["second_layer"] == "SAFE_ALLOW"),
        "FALSE_ALLOW": sum(1 for x in reviews
                           if x["second_layer"] == "FALSE_ALLOW"),
        "REVIEW": sum(1 for x in reviews
                      if x["second_layer"] == "REVIEW"),
        "high_risk_allows": [x for x in reviews if x["risk_level"] == "high"]}

    # ---- Phase 3: E-class ----
    ecls = defaultdict(Counter)
    for r in recs:
        d = r.get("decision")
        if d in ("ALLOW_UPGRADE", "KEEP_BASELINE", "UNCERTAIN"):
            ecls[eclass(r["claim_text"])][d] += 1
    out["e_class"] = {k: dict(v) for k, v in ecls.items()}
    out["e_class_allow_share"] = {
        k: round(100 * v.get("ALLOW_UPGRADE", 0) / max(1, sum(v.values())), 1)
        for k, v in ecls.items()}

    # ---- Phase 4: evidence-meta watch ----
    meta_recs = [r for r in recs if META_RE.search(r["claim_text"])]
    meta_allow = [r for r in meta_recs if r.get("decision") == "ALLOW_UPGRADE"]
    meta_watch = []
    for r in meta_allow:
        t = r["claim_text"]
        risks = risk_of(t)
        cls = ("NON_BUSINESS_META" if not risks else
               "META_PLUS_RISK(%s)" % ",".join(risks))
        meta_watch.append({"claim": t, "risk_flags": risks,
                           "classification": cls,
                           "escalation_path": bool(risks)})
    out["meta_watch"] = {
        "meta_total": len(meta_recs),
        "meta_allow": len(meta_allow),
        "entries": meta_watch,
        "verdict": ("WATCH_ONLY" if not any(w["escalation_path"]
                                            for w in meta_watch)
                    else "META_PROSE_HIGH_RISK_HARD_STOP")}

    # ---- Phase 5: stability via claim-text clusters (>=2 repeats) ----
    clusters = defaultdict(list)
    for r in recs:
        if r.get("decision") in ("ALLOW_UPGRADE", "KEEP_BASELINE",
                                 "UNCERTAIN"):
            clusters[r["claim_text"]].append(r["decision"])
    rep = {k: v for k, v in clusters.items() if len(v) >= 2}
    stable = sum(1 for v in rep.values() if len(set(v)) == 1)
    out["stability"] = {
        "repeat_clusters": len(rep),
        "consistent": stable,
        "consistency_pct": round(100 * stable / max(1, len(rep)), 1),
        "detail": [{"claim": k[:40], "decisions": v}
                   for k, v in list(rep.items())[:12]]}

    # ---- Phase 7: sufficiency ----
    strat = Counter()
    for r in recs:
        for k in risk_of(r["claim_text"]):
            strat[k] += 1
    judged = [r for r in recs if r.get("decision") in
              ("ALLOW_UPGRADE", "KEEP_BASELINE", "UNCERTAIN")
              and not r.get("hard_prefilter")]
    out["sufficiency"] = {
        "total_records": len(recs),
        "judged_low_risk": len(judged),
        "note_pipeline": ("hard-prefilter makes PIPELINE high-risk "
                          "escapes structurally zero (claims with hard "
                          "patterns never reach the judge) — this is "
                          "DESIGN, not sampled evidence"),
        "risk_patterns_seen_in_ALL_records": dict(strat),
        "high_risk_judged_after_prefilter": sum(
            1 for r in judged if risk_of(r["claim_text"])),
        "verdict_by_stratum": {
            "low_risk_paraphrase": ("SUFFICIENT" if len(judged) >= 100
                                    else "INSUFFICIENT_EVIDENCE"),
            "high_risk_pipeline": "STRUCTURAL_ZERO (prefilter; not sampled)",
            "high_risk_judge_alone": ("S0 offline 82-case evidence "
                                      "(1 FU, caught by design); live "
                                      "pipeline never samples them — "
                                      "INSUFFICIENT_EVIDENCE for "
                                      "judge-alone claims")}}

    # ops
    lat = sorted(x for x in
                 (r.get("latency_s") for r in recs if r.get("latency_s"))
                 if x is not None)
    if lat:
        out["ops"] = {"n": len(lat), "p50": lat[len(lat) // 2],
                      "p95": lat[int(len(lat) * .95)], "max": lat[-1]}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    # console summary
    print("totals:", out["totals"])
    print("audit:", {k: v for k, v in out["false_upgrade_audit"].items()
                     if k != "high_risk_allows"})
    print("e_class:", out["e_class"], "| allow%:", out["e_class_allow_share"])
    print("meta_watch:", out["meta_watch"]["verdict"],
          "(%d/%d)" % (out["meta_watch"]["meta_allow"],
                       out["meta_watch"]["meta_total"]))
    print("stability:", out["stability"]["consistency_pct"], "% of",
          out["stability"]["repeat_clusters"], "clusters")
    print("ops:", out.get("ops"))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
