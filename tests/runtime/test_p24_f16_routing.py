"""Phase 24D — F-16 gap-domain routing regression matrix (pure unit).

F-16 claimed: "the gap engine routes R4 (life/death risk) to the
savings domain, so life requirements never reach a TERM_LIFE solution."

Verified against the ACTUAL engines (2026-09-21): the claim does NOT
reproduce — risk_category_to_domain maps R4→life (original commit
0459f00, never changed) and solution-mapping maps life→TERM_LIFE. This
suite freezes the full matrix required by the Phase 24 spec §35 so a
future regression cannot silently re-introduce cross-domain routing:

  single-domain: R4 / life / savings / health / accident
  combinations:  R4+health · R4+savings · R4+health+savings
  multi-demand:  one requirement hitting multiple gap domains
  unknown:       unregistered risk_category → general, no guessing
  conflicting:   requirement_type with no matching risk domain →
                 information gap, never a misrouted solution
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Checks, run_sections  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
SKILLS = [
    os.path.join(REPO, ".trae", "skills", "coverage-gap-analysis",
                 "scripts"),
    os.path.join(REPO, ".trae", "skills", "solution", "scripts"),
]
for p in SKILLS:
    if p not in sys.path:
        sys.path.insert(0, p)

from coverage_gap_engine import analyze as gap_analyze  # noqa: E402
import solution_engine as se  # noqa: E402

SECTIONS = []

EXPECT_DOMAIN = {"R1": "medical", "R2": "critical_illness",
                 "R3": "accident", "R4": "life", "R5": "savings"}
EXPECT_SOLUTION = {"medical": "MEDICAL", "critical_illness":
                   "CRITICAL_ILLNESS", "accident": "ACCIDENT",
                   "life": "TERM_LIFE", "savings": "SAVINGS",
                   "general": "GENERAL"}


def section(fn):
    SECTIONS.append(fn)
    return fn


def _risk(rid, cat, prio="P1"):
    return {"risk_id": rid, "risk_category": cat,
            "risk_name": "risk %s" % cat, "priority": prio,
            "existing_protection": "无",
            "coverage_assessment": {"protected_amount": 0,
                                    "unprotected_amount": 100}}


def _reqs(*types):
    return {"requirements": [
        {"requirement_id": "Q%d" % i, "requirement_type": t}
        for i, t in enumerate(types, 1)]}


REQ_TYPE_TO_DOMAIN = {"life": "life", "savings": "savings",
                      "health": "medical",
                      "critical_illness": "critical_illness",
                      "accident": "accident", "general": "general"}


def _chain(c, label, cats, req_types, expect_domains):
    """Run risk→gap→solution and assert the domain routing at BOTH
    stages: gap.domain comes from structured risk_category, every gap
    references only requirements from its own domain, and each
    solution's solution_type matches the domain it serves."""
    risks = [_risk("R%s%d" % (cat[-1], i), cat) for i, cat in
             enumerate(cats, 1)]
    risk = {"analysis_status": "FORMAL", "overall_confidence": 0.8,
            "risks": risks}
    req = _reqs(*req_types)
    req_ids_of_domain = {}
    for r in req["requirements"]:
        d = REQ_TYPE_TO_DOMAIN.get(r["requirement_type"], "general")
        req_ids_of_domain.setdefault(d, set()).add(r["requirement_id"])
    gap = gap_analyze(None, req, risk)
    got_domains = {g["domain"] for g in gap["gaps"]}
    c.chk("%s: gap domains == %s" % (label, sorted(expect_domains)),
          got_domains == set(expect_domains),
          "got %s" % sorted(got_domains))
    for g in gap["gaps"]:
        rel = set(g.get("related_requirement_ids", []))
        c.chk("%s: gap %s references only own-domain requirements"
              % (label, g["gap_id"]),
              rel <= req_ids_of_domain.get(g["domain"], set()),
              "gap %s refs %s" % (g["domain"], sorted(rel)))
    sol = se.analyze(gap, req, risk)
    solutions = sol.get("solutions") or []
    got_types = sorted({s.get("solution_type") for s in solutions})
    expect_types = sorted({EXPECT_SOLUTION[d] for d in expect_domains})
    c.chk("%s: solution types == %s" % (label, expect_types),
          got_types == expect_types, "got %s" % got_types)


@section
def test_s1_single_domain(c):
    """Each risk category routes to its own domain end-to-end."""
    _chain(c, "R4 only", ["R4"], ["life"], ["life"])
    _chain(c, "R5/savings only", ["R5"], ["savings"], ["savings"])
    _chain(c, "R1/health only", ["R1"], ["health"], ["medical"])
    _chain(c, "R3/accident only", ["R3"], ["accident"], ["accident"])
    _chain(c, "R2 only", ["R2"], ["critical_illness"],
           ["critical_illness"])
    # the F-16 headline case: R4 death/income-replacement risk MUST be
    # life — never savings — and MUST yield a TERM_LIFE direction
    risk = {"analysis_status": "FORMAL", "overall_confidence": 0.8,
            "risks": [_risk("R4-001", "R4")]}
    gap = gap_analyze(None, _reqs("life"), risk)
    g = gap["gaps"][0]
    c.chk("F-16: R4 gap domain is life", g["domain"] == "life", g)
    c.chk("F-16: R4 direction mentions 定期寿险",
          "定期寿险" in g["target_coverage"]["direction"],
          g["target_coverage"]["direction"])
    sol = se.analyze(gap, _reqs("life"), risk)
    c.chk("F-16: R4 solution is TERM_LIFE",
          (sol.get("solutions") or [{}])[0].get("solution_type")
          == "TERM_LIFE", sol.get("solutions"))


@section
def test_s2_combinations(c):
    """R4 combined with other domains never leaks across domains."""
    _chain(c, "R4+health", ["R4", "R1"], ["life", "health"],
           ["life", "medical"])
    _chain(c, "R4+savings", ["R4", "R5"], ["life", "savings"],
           ["life", "savings"])
    _chain(c, "R4+health+savings", ["R4", "R1", "R5"],
           ["life", "health", "savings"],
           ["life", "medical", "savings"])


@section
def test_s3_multi_demand(c):
    """Multi-demand client: every requirement lands on a gap in its own
    domain; no gap absorbs another domain's requirement."""
    _chain(c, "multi-demand", ["R1", "R2", "R3", "R4", "R5"],
           ["health", "critical_illness", "accident", "life", "savings"],
           ["medical", "critical_illness", "accident", "life", "savings"])
    # a life requirement with NO R4 risk is an information gap — it must
    # NOT be silently served by another domain's gap
    risk = {"analysis_status": "FORMAL", "overall_confidence": 0.8,
            "risks": [_risk("R1-001", "R1")]}
    gap = gap_analyze(None, _reqs("life", "health"), risk)
    info = [i for i in gap.get("information_gaps", [])
            if i.get("domain") == "life"]
    c.chk("orphan life requirement becomes information gap",
          len(info) == 1, gap.get("information_gaps"))
    c.chk("orphan life requirement not routed into medical gaps",
          all(g["domain"] != "life" for g in gap["gaps"]))


@section
def test_s4_unknown_and_conflicting(c):
    """Unknown risk_category → general (explicit fallback, no guessing);
    conflicting requirement/risk domains stay separated."""
    _chain(c, "unknown category", ["R9"], ["general"], ["general"])
    # conflicting: requirement_type that matches NO risk domain while
    # risks exist — must not produce a misrouted solution
    risk = {"analysis_status": "FORMAL", "overall_confidence": 0.8,
            "risks": [_risk("R4-001", "R4")]}
    gap = gap_analyze(None, _reqs("savings"), risk)
    c.chk("conflicting: R4 gap keeps domain life",
          gap["gaps"][0]["domain"] == "life")
    c.chk("conflicting: savings requirement flagged as information gap",
          any(i.get("domain") == "savings"
              for i in gap.get("information_gaps", [])))
    sol = se.analyze(gap, _reqs("savings"), risk)
    c.chk("conflicting: only TERM_LIFE solution produced",
          [s.get("solution_type") for s in (sol.get("solutions") or [])]
          == ["TERM_LIFE"])


@section
def test_s5_no_free_text_routing(c):
    """Routing reads ONLY structured risk_category — a risk whose free
    text screams another domain still routes by its category."""
    r = _risk("R4-001", "R4")
    r["risk_name"] = "储蓄理财缺口储蓄理财"
    r["existing_protection"] = "无任何储蓄和年金"
    risk = {"analysis_status": "FORMAL", "overall_confidence": 0.8,
            "risks": [r]}
    gap = gap_analyze(None, _reqs("life"), risk)
    c.chk("free-text cannot move R4 out of life",
          gap["gaps"][0]["domain"] == "life", gap["gaps"][0]["domain"])


def main() -> int:
    from _common import REPO as _REPO
    os.chdir(_REPO)
    return run_sections(SECTIONS, "p24_f16_routing_log.txt",
                        "PHASE 24D F-16 ROUTING MATRIX")


if __name__ == "__main__":
    sys.exit(main())
