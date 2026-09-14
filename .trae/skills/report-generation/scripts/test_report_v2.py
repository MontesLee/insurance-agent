"""Report Generation V2 architecture invariants.

These assert what the dataset cannot: that the report layer owns NO business
judgment. It copies, normalizes, renders and validates — it never decides.

Run: python .trae/skills/report-generation/scripts/test_report_v2.py
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR))))
for p in (HERE, REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from report_generation_engine import generate_report, load_rules  # noqa: E402
from upstream_results_adapter import normalize_input  # noqa: E402

MANIFEST = os.path.join(SKILL_DIR, "evals", "cases", "v2-dataset-manifest.json")
LOG = os.path.join(SKILL_DIR, "evals", "cases", "_report_v2_unit_log.txt")
MONEY = re.compile(r"[0-9][0-9,]*(\.[0-9]+)?\s*(万元|元|万)")

rules = load_rules()
manifest = json.load(io.open(MANIFEST, encoding="utf-8"))
CASES = {c["name"]: c for c in manifest["cases"]}

results = []


def check(name, fn):
    try:
        problems = fn() or []
    except Exception as e:  # noqa: BLE001
        problems = ["EXCEPTION: %r" % e]
    results.append((name, not problems, problems))


def _money_tokens(text):
    out = set()
    for m in MONEY.findall(text or ""):
        out.add((m if isinstance(m, str) else "".join(m)).replace(" ", ""))
    return out


# --- 1. canonical gap is the ONLY source for section 04 -----------------------
def t1():
    case = CASES["v2_canonical_gap_suppresses_derivation"]
    out = generate_report(case["input"], rules)
    gaps = out["structured_report"]["coverage_gaps"]
    bad = [g for g in gaps if g.get("derivation") != "canonical"]
    if bad:
        return ["%d non-canonical entries in section 04" % len(bad)]
    want = len(case["input"]["coverage_gap_analysis"]["payload"]["gaps"])
    if len(gaps) != want:
        return ["section 04 has %d gaps, canonical artifact has %d" % (len(gaps), want)]
    return []


check("canonical_gap_is_sole_source", t1)


# --- 2. gap_level is copied verbatim, never recomputed ------------------------
def t2():
    case = json.loads(json.dumps(CASES["v2_full_chain"]))
    gaps = case["input"]["coverage_gap_analysis"]["payload"]["gaps"]
    sentinel = "SENTINEL_LEVEL"
    gaps[0]["gap_level"] = sentinel
    out = generate_report(case["input"], rules)
    got = {g.get("gap_level") for g in out["structured_report"]["coverage_gaps"]}
    if sentinel not in got:
        return ["upstream gap_level %r not carried through verbatim (got %r)" % (sentinel, got)]
    return []


check("gap_level_copied_verbatim", t2)


# --- 3. strategy text is copied verbatim (no paraphrase, no product names) ----
def t3():
    case = CASES["v2_full_chain"]
    out = generate_report(case["input"], rules)
    upstream = case["input"]["solution_plan"]["payload"]["solutions"]
    rendered = out["structured_report"]["solution_strategies"]
    if len(rendered) != len(upstream):
        return ["strategy count %d != upstream %d" % (len(rendered), len(upstream))]
    by_id = {s.get("solution_id"): s for s in upstream}
    for r in rendered:
        u = by_id.get(r.get("solution_id"))
        if u is None:
            return ["strategy %r has no upstream counterpart" % r.get("solution_id")]
        for field in ("objective", "coverage_direction"):
            if r.get(field) != u.get(field):
                return ["strategy %s.%s rewritten: %r != %r"
                        % (r.get("solution_id"), field, r.get(field), u.get(field))]
    return []


check("strategy_text_verbatim", t3)


# --- 4. no monetary expression appears that is not traceable to upstream ------
def t4():
    case = CASES["v2_full_chain"]
    out = generate_report(case["input"], rules)
    allowed = _money_tokens(json.dumps(case["input"], ensure_ascii=False))
    allowed |= _money_tokens(json.dumps(out["structured_report"], ensure_ascii=False))
    bad = _money_tokens(out["rendered_report"]) - allowed
    if bad:
        return ["monetary tokens with no upstream source: %r" % sorted(bad)]
    return []


check("no_untraceable_money", t4)


# --- 5. legacy alias and canonical key are interchangeable --------------------
def t5():
    case = json.loads(json.dumps(CASES["v2_full_chain"]))
    inp = case["input"]
    pr = inp.pop("product_recommendation")
    ke = inp.pop("knowledge_evidence")
    inp["recommendation"] = pr
    inp["knowledge_search"] = ke
    a = generate_report(case["input"], rules)
    # rebuild original
    case2 = json.loads(json.dumps(CASES["v2_full_chain"]))
    b = generate_report(case2["input"], rules)
    if a["structured_report"]["recommended_directions"] != b["structured_report"]["recommended_directions"]:
        return ["legacy alias produced different recommended_directions"]
    if a["structured_report"]["evidence_summary"] != b["structured_report"]["evidence_summary"]:
        return ["legacy alias produced different evidence_summary"]
    return []


check("legacy_alias_equivalence", t5)


# --- 6. canonical envelope and raw skill output are interchangeable -----------
def t6():
    case = json.loads(json.dumps(CASES["v2_full_chain"]))
    inp = case["input"]
    # strip the canonical envelope -> raw payload
    inp["coverage_gap_analysis"] = inp["coverage_gap_analysis"]["payload"]
    inp["solution_plan"] = inp["solution_plan"]["payload"]
    a = generate_report(case["input"], rules)
    b = generate_report(CASES["v2_full_chain"]["input"], rules)
    if a["structured_report"]["coverage_gaps"] != b["structured_report"]["coverage_gaps"]:
        return ["envelope vs raw produced different coverage_gaps"]
    if a["structured_report"]["solution_strategies"] != b["structured_report"]["solution_strategies"]:
        return ["envelope vs raw produced different solution_strategies"]
    return []


check("envelope_and_raw_equivalent", t6)


# --- 7. derived fallback is always labelled -----------------------------------
def t7():
    case = CASES["v2_derived_fallback_warning"]
    out = generate_report(case["input"], rules)
    if out["structured_report"]["coverage_gap_derivation"] != "derived":
        return ["derivation not marked derived"]
    gaps = out["structured_report"]["coverage_gaps"]
    bad = [g for g in gaps if g.get("derivation") != "derived"]
    if bad:
        return ["%d gap entries not tagged derived" % len(bad)]
    if not any("GAP_SOURCE_DERIVED_NOT_CANONICAL" in w for w in out["metadata"]["warnings"]):
        return ["missing GAP_SOURCE_DERIVED_NOT_CANONICAL warning"]
    return []


check("derived_fallback_labelled", t7)


# --- 8. evidence is listed, never weighed -------------------------------------
def t8():
    case = CASES["v2_evidence_conflict"]
    out = generate_report(case["input"], rules)
    ev = out["structured_report"]["evidence_summary"]
    up = case["input"]["knowledge_evidence"]["payload"]["evidence"]
    if len(ev) != len(up):
        return ["evidence count %d != upstream %d" % (len(ev), len(up))]
    for r, u in zip(ev, up):
        if r.get("content") != u.get("content"):
            return ["evidence content rewritten"]
        if bool(r.get("conflict")) != bool(u.get("conflict")):
            return ["evidence conflict flag altered"]
    # the report must not turn evidence into a conclusion
    forbidden = ["因此建议", "综上推荐", "推荐购买"]
    for f in forbidden:
        if f in out["rendered_report"]:
            return ["report drew a conclusion from evidence: %r" % f]
    return []


check("evidence_listed_not_weighed", t8)


# --- 9. adapter never mutates the upstream artifacts it is handed -------------
def t9():
    case = json.loads(json.dumps(CASES["v2_full_chain"]))
    before = json.dumps(case["input"], ensure_ascii=False, sort_keys=True)
    generate_report(case["input"], rules)
    after = json.dumps(case["input"], ensure_ascii=False, sort_keys=True)
    if before != after:
        return ["upstream input was mutated by the report layer"]
    return []


check("no_upstream_mutation", t9)


# --- 10. cross-artifact conflict is surfaced, not adjudicated ------------------
def t10():
    case = CASES["v2_gap_vs_risk_conflict"]
    out = generate_report(case["input"], rules)
    if not out["metadata"]["conflicts"]:
        return ["no conflict surfaced"]
    for c in out["metadata"]["conflicts"]:
        if "不自行裁决" not in c:
            return ["conflict text does not state non-adjudication: %r" % c]
    # the gap itself must still be reported as upstream stated it
    gaps = out["structured_report"]["coverage_gaps"]
    if not any(g.get("coverage_status") == "NONE" for g in gaps):
        return ["report silently corrected the upstream gap status"]
    return []


check("conflict_surfaced_not_adjudicated", t10)


# --------------------------------------------------------------------------- #
lines = []
all_ok = True
for name, ok, problems in results:
    lines.append("[%s] %s" % ("PASS" if ok else "FAIL", name))
    for p in problems:
        lines.append("       - %s" % p)
    if not ok:
        all_ok = False
lines.append("")
lines.append("REPORT V2 INVARIANTS: %s" % ("ALL GREEN" if all_ok else "FAILURES PRESENT"))
text = "\n".join(lines)
print(text)
io.open(LOG, "w", encoding="utf-8").write(text)
sys.exit(0 if all_ok else 1)
