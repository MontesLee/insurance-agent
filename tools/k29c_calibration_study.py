# -*- coding: utf-8 -*-
"""K.29-C Phase 2/3 — Claim Support calibration study (OFFLINE ONLY).

Zero production changes. Two replay surfaces:

  A. K.28-II frozen golden corpus (104 single-claim cases, N1-N10 attack
     families) — clause-aware per the frozen shadow convention
     (tools/claim_shadow_eval.py judge_case: split -> judge each clause
     -> a case passes a POLICY iff every fact clause passes it).
  B. K.29-B A-fixed benchmark claim_rows (real final-attempt generations)
     — per-policy refusal flips + risk profile of newly-passing claims.

Policies (gate-level acceptance over the deterministic judge verdict;
citation-presence gate untouched by every candidate):
  C1  = current   : accept iff SUPPORTED
  C2  = paraphrase: accept iff SUPPORTED or PARTIAL
  C3  = guidance  : guidance/evidence-absence claims exempt — ONLY when
                    the clause carries NO numeric anchor and NO product/
                    regulatory token (guard added after probe P-C3-01/02
                    showed bare-regex exemption escapes wrapped numbers);
                    everything else per C1
  C4  = metadata  : accept iff C1 or ws-normalized SUPPORTED or
                    anchor-metadata-projected SUPPORTED (metadata fields
                    projected into label+value prose the anchor matcher
                    reads: 生效日期2019年12月1日 / 版本号X)
  C234= combined  : C2 or C3 or C4 (informational)

Verdict strings normalized (production 'PARTIAL' == shadow
'PARTIALLY_SUPPORTED' — both map to PARTIAL here).

Output: tmp/obs/k29c_calibration_study.json + console summary.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from runtime.grounding.shadow import support as sup      # noqa: E402
from runtime.grounding.shadow.claims import split_claims  # noqa: E402
from runtime.grounding import claim_support as cs        # noqa: E402

GOLDEN = os.path.join(REPO, "tests", "golden", "claim-evidence-shadow.v1.json")
TAXONOMY = os.path.join(REPO, "tests", "golden", "k29c_claim_taxonomy.json")
BENCH = ["A_fixed_main_all", "A_fixed_flash_all"]
OUT = os.path.join(REPO, "tmp", "obs", "k29c_calibration_study.json")
AS_OF = date(2026, 9, 29)

META_RE = re.compile(
    r"证据|资料|未提及|未载明|未给出|未提供|没有.{0,6}(记载|明确)|"
    r"无法.{0,8}(给出|基于)|未记载|未规定|未单独|未专门|未覆盖|未说明|仅有标题")
GUIDE_RE = re.compile(
    r"建议|应该|可以考虑|先.{1,8}再|一般建议|通常建议|优先|"
    r"需要.{0,6}(考虑|注意)|通读|如实|咨询|查阅|阅读")
HIGH_RISK_RE = re.compile(
    r"P0\d{2}|demo-|这款|该产品|某产品|保险法|管理办法|监管|银保监|"
    r"令第|施行|保证.{0,6}(续保|赔付|返还)|承诺")
NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:天|日|万|万元|元|%|岁|周岁|年|倍|次)")

POLICIES = ["C1", "C2", "C3", "C3v2", "C4", "C234", "C2C3v2"]


def norm(v):
    return "PARTIAL" if v == "PARTIALLY_SUPPORTED" else v


def judge(text, ctype, anchors, evidence):
    return norm(sup.judge_support(text, ctype, anchors, evidence,
                                  AS_OF)["support_status"])


def judge_ws(text, ctype, anchors, evidence):
    items = [{**it, "content": re.sub(r"\s+", "", it.get("content") or "")}
             for it in evidence]
    return judge(text, ctype, anchors, items)


def _iso_to_cn(d):
    d = str(d)
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", d)
    if not m:
        return str(d)
    y, mo, da = (int(x) for x in m.groups())
    return "%d年%d月%d日" % (y, mo, da)


def _meta_projection(it):
    """Project governance metadata into label+value prose the anchor
    matcher reads (numbers adjacent to their unit characters)."""
    parts = [it.get("content") or "", it.get("source_name") or "",
             it.get("document_name") or ""]
    if it.get("version"):
        parts.append("版本号%s" % it["version"])
    if it.get("effective_from"):
        cn = _iso_to_cn(it["effective_from"])
        parts.append("生效日期%s" % cn)
        parts.append("自%s起施行" % cn)
    if it.get("effective_to"):
        cn = _iso_to_cn(it["effective_to"])
        parts.append("失效日期%s" % cn)
    return " ".join(parts)


def judge_meta(text, ctype, anchors, evidence):
    items = [{**it, "content": _meta_projection(it)} for it in evidence]
    return judge(text, ctype, anchors, items)


def clause_guarded_guidance(text, anchors):
    """C3-v1 exemption (kept for the record): guidance/meta prose without
    numeric anchors or high-risk tokens. Probe findings: P-C3-02 escapes
    (anchor regex misses range '3-5倍') and P-C3-04 over-blocks (meta
    prose mentioning 该产品) -> superseded by clause_guarded_guidance_v2."""
    if not (META_RE.search(text) or GUIDE_RE.search(text)):
        return False
    if anchors:
        return False
    if HIGH_RISK_RE.search(text):
        return False
    return True


def clause_guarded_guidance_v2(text, anchors):
    """C3-v2 exemption (probe-hardened):
    - evidence-absence prose (META_RE) is exempt when it carries NO
      numeric anchor (mentioning 该产品 inside '证据未提及X' is safe);
    - general guidance (GUIDE_RE) is exempt only with no anchor, no
      NUM_RE hit (catches '3-5倍' ranges the anchor regex misses) and
      no product/regulatory token."""
    if META_RE.search(text):
        return not anchors and not NUM_RE.search(text)
    if GUIDE_RE.search(text):
        return (not anchors and not NUM_RE.search(text)
                and not HIGH_RISK_RE.search(text))
    return False


def clause_accept(policy, text, ctype, anchors, evidence,
                  verdict=None, ws_verdict=None, meta_verdict=None):
    if ctype not in ("C-FACT",):        # exempt classes stay exempt
        return True
    if verdict is None:
        verdict = judge(text, ctype, anchors, evidence)
    if policy == "C1":
        return verdict == "SUPPORTED"
    if policy == "C2":
        return verdict in ("SUPPORTED", "PARTIAL")
    if policy == "C3":
        if clause_guarded_guidance(text, anchors):
            return True
        return verdict == "SUPPORTED"
    if policy == "C3v2":
        if clause_guarded_guidance_v2(text, anchors):
            return True
        return verdict == "SUPPORTED"
    if policy == "C4":
        if verdict == "SUPPORTED":
            return True
        if evidence is None:
            # benchmark replay: no stored evidence — ws approximation
            return ws_verdict == "SUPPORTED"
        if ws_verdict is None:
            ws_verdict = judge_ws(text, ctype, anchors, evidence)
        if ws_verdict == "SUPPORTED":
            return True
        if meta_verdict is None:
            meta_verdict = judge_meta(text, ctype, anchors, evidence)
        return meta_verdict == "SUPPORTED"
    if policy == "C234":
        return any(clause_accept(p, text, ctype, anchors, evidence,
                                 verdict, ws_verdict, meta_verdict)
                   for p in ("C2", "C3", "C4"))
    if policy == "C2C3v2":
        # safest useful combination: paraphrase + guarded guidance,
        # WITHOUT the unsound C4 formulation
        return clause_accept("C2", text, ctype, anchors, evidence,
                             verdict, ws_verdict, meta_verdict) or                clause_accept("C3v2", text, ctype, anchors, evidence,
                             verdict, ws_verdict, meta_verdict)
    raise ValueError(policy)


def case_clauses(text, evidence):
    """Split + judge every clause under the three judge variants."""
    out = []
    for c in split_claims(text):
        t, ty, an = c["claim_text"], c["claim_type"], c["anchors"]
        out.append({
            "text": t, "type": ty, "anchors": an,
            "v": judge(t, ty, an, evidence) if ty == "C-FACT" else None,
            "ws": judge_ws(t, ty, an, evidence) if ty == "C-FACT" else None,
            "meta": judge_meta(t, ty, an, evidence) if ty == "C-FACT"
                    else None})
    return out


# ---------------- A. golden corpus replay ----------------
def replay_golden():
    corpus = json.load(open(GOLDEN, encoding="utf-8"))
    rows = []
    for case in corpus["cases"]:
        if isinstance(case["expected"], dict):
            continue                      # S-streaming per-sentence cases
        ev = case.get("evidence") or []
        clauses = case_clauses(case["claim_text"], ev)
        row = {"case_id": case["case_id"], "class": case["class"],
               "expected": case["expected"], "clauses": len(clauses)}
        for p in POLICIES:
            row[p] = all(clause_accept(p, c["text"], c["type"],
                                       c["anchors"], ev, c["v"], c["ws"],
                                       c["meta"])
                         for c in clauses)
        rows.append(row)
    agg = {}
    for p in POLICIES:
        esc = [r for r in rows if r[p] and r["expected"] in
               ("UNSUPPORTED", "CONTRADICTED")]
        pesc = [r for r in rows if r[p] and r["expected"] == "PARTIAL"]
        fref = [r for r in rows if not r[p] and
                r["expected"] == "SUPPORTED"]
        agg[p] = {"escape": len(esc),
                  "escape_cases": sorted(r["case_id"] for r in esc),
                  "partial_escape": len(pesc),
                  "partial_escape_cases": sorted(
                      r["case_id"] for r in pesc),
                  "false_refusal": len(fref),
                  "false_refusal_cases": sorted(
                      r["case_id"] for r in fref)[:10],
                  "families_escape": dict(Counter(
                      r["class"] for r in esc)),
                  "families_partial_escape": dict(Counter(
                      r["class"] for r in pesc))}
    return {"n_cases": len(rows), "per_policy": agg, "rows": rows}


# ---------------- B. benchmark replay ----------------
def replay_benchmark():
    tax = json.load(open(TAXONOMY, encoding="utf-8"))
    claims_by_rec = defaultdict(list)
    for c in tax["claims"]:
        claims_by_rec[(c["case_id"], c["slot"])].append(c)
    out = {}
    for f in BENCH:
        slot = "main" if "main" in f else "flash"
        recs = [json.loads(l) for l in open(os.path.join(
            REPO, "tmp", "obs", "k29b", f + ".jsonl"), encoding="utf-8")]
        refuted = [r for r in recs
                   if r.get("failure_reason") == "citation_gate_rejected"]
        flips = {p: [] for p in POLICIES}
        newly = {p: [] for p in POLICIES}
        for r in refuted:
            cl = claims_by_rec.get((r["case_id"], slot), [])
            vs = r.get("gate_violations") or []
            has_nc = any("no_citation" in v for v in vs)
            if has_nc:
                continue        # citation side untouched by candidates
            for p in POLICIES:
                ok = all(clause_accept(p, c["text"], "C-FACT",
                                       cs.numeric_anchors(
                                           cs._CITATION_RE.sub("", c["text"])),
                                       None, norm(c["support"]),
                                       norm(c.get("support_ws") or ""),
                                       None)
                         for c in cl)
                if ok and cl:
                    flips[p].append(r["case_id"])
                    for c in cl:
                        c1 = clause_accept("C1", c["text"], "C-FACT",
                                           cs.numeric_anchors(
                                               cs._CITATION_RE.sub(
                                                   "", c["text"])),
                                           None, norm(c["support"]),
                                           norm(c.get("support_ws") or ""),
                                           None)
                        if not c1:
                            newly[p].append(c)
        out[slot] = {
            "refused_records": len(refuted),
            "flips": {p: {"n": len(v), "cases": v}
                      for p, v in flips.items()},
            "newly_passing_claims": {
                p: {"n": len(v),
                    "numeric": sum(1 for c in v
                                   if NUM_RE.search(c["text"])),
                    "high_risk": sum(1 for c in v
                                     if HIGH_RISK_RE.search(c["text"])),
                    "by_type": dict(Counter(c["type"] for c in v))}
                for p, v in newly.items()}}
    return out


# ---------------- C. C3/C4 adversarial probes ----------------
def run_probes():
    tax = json.load(open(TAXONOMY, encoding="utf-8"))
    rows = []
    for pr in tax["c3_c4_probes"]:
        bare = cs._CITATION_RE.sub("", pr["claim"])
        clauses = case_clauses(bare, pr["evidence"])
        res = {}
        for p in POLICIES:
            res[p] = all(clause_accept(p, c["text"], c["type"],
                                       c["anchors"], pr["evidence"],
                                       c["v"], c["ws"], c["meta"])
                         for c in clauses)
        target_policy = {"C3": "C3v2", "C4": "C4"}[pr["target"]]
        rows.append({"id": pr["id"], "target": pr["target"],
                     "claim": pr["claim"][:50],
                     "expected_gate": pr["expected_gate"],
                     "policy_accept": res,
                     "pass": res[target_policy] ==
                             (pr["expected_gate"] == "ACCEPT")})
    return rows


def main():
    out = {"ts": "2026-10-02",
           "golden_replay": replay_golden(),
           "benchmark_replay": replay_benchmark(),
           "c3_c4_probes": run_probes()}
    g = out["golden_replay"]
    out["golden_replay"] = {k: v for k, v in g.items() if k != "rows"}
    out["golden_rows_debug"] = g["rows"]      # full audit trail
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("wrote", OUT)
    print("\n=== GOLDEN REPLAY (n=%d) ===" % out["golden_replay"]["n_cases"])
    for p, a in out["golden_replay"]["per_policy"].items():
        print("  %-5s escape=%d %-28s partial_esc=%d %-22s false_refusal=%d" % (
            p, a["escape"], str(a["escape_cases"])[:28],
            a["partial_escape"], str(a["partial_escape_cases"])[:22],
            a["false_refusal"]))
    print("\n=== BENCHMARK REPLAY ===")
    for slot, b in out["benchmark_replay"].items():
        print(" slot=%s (refused=%d)" % (slot, b["refused_records"]))
        for p in POLICIES:
            fl = b["flips"][p]
            np_ = b["newly_passing_claims"][p]
            print("  %-5s flips=%2d %s | newly-passing=%2d (numeric=%d high_risk=%d types=%s)" % (
                p, fl["n"], ",".join(fl["cases"])[:34], np_["n"],
                np_["numeric"], np_["high_risk"], np_["by_type"]))
    print("\n=== C3/C4 PROBES ===")
    for r in out["c3_c4_probes"]:
        print("  %-8s %-4s expect=%-6s pass=%-5s | %s" % (
            r["id"], r["target"], r["expected_gate"], r["pass"],
            r["claim"]))


if __name__ == "__main__":
    main()
