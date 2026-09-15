"""Step 4 Phase 7 — Attribute-level Evidence Grounding (V0.2).

Step 2's evidence chain stopped at "Product -> required evidence DOMAIN -> Evidence
Available", which is too coarse: a medical product read as "backed by evidence" merely
because some medical document was retrieved. This suite locks the V0.2 upgrade:

    Product Attribute -> Evidence Requirement -> Evidence Chunk -> SUPPORTED / UNSUPPORTED / CONFLICT

Checks
  * the five configured attributes are grounded per product, and the matcher is
    deterministic + rules-driven (amount variants: catalog `10000元` vs KB `1 万元`);
  * NOT_CHECKABLE is an INDEPENDENT THIRD STATE and is never folded into SUPPORTED;
  * rollup precedence: UNSUPPORTED / CONFLICT / NOT_CHECKABLE all beat SUPPORTED;
  * a REQUIRED attribute the evidence does not state is a positive UNSUPPORTED and DOES
    downgrade the product (EVIDENCE_UNSUPPORTED, product inadmissible) — the whole point;
  * an OPTIONAL attribute being UNSUPPORTED is recorded but does NOT block
    (otherwise every demo product would be rejected and the grounding would be useless);
  * the verdict reaches the recommendation layer (carried on the candidate projection);
  * REAL pipeline sanity: the normal COMPLETE path is not regressed.

Exit 0 = all checks pass.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

CAND_SCRIPTS = os.path.join(REPO, ".trae", "skills", "product-candidate-provider", "scripts")
REC_SCRIPTS = os.path.join(REPO, ".trae", "skills", "recommendation", "scripts")
BENCH_DIR = os.path.join(REPO, "evals", "agent-benchmark")
for p in (REPO, CAND_SCRIPTS, REC_SCRIPTS):
    if p not in sys.path:
        sys.path.insert(0, p)

from knowledge.evidence import attribute_grounding as ag  # noqa: E402
import product_candidate_engine as ce  # noqa: E402
import runtime.orchestrator as orch  # noqa: E402

passed = failed = 0
lines = []


def chk(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    lines.append("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                                ("  -- " + str(detail)) if (detail and not ok) else ""))


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BENCH = _load_module("bench_harness_p7", os.path.join(BENCH_DIR, "run_agent_benchmark.py"))
RULES = ag.load_rules()
STATUSES = RULES["statuses"]
S_OK, S_UNSUP = STATUSES["supported"], STATUSES["unsupported"]
S_CONFLICT, S_NC = STATUSES["conflict"], STATUSES["not_checkable"]
CATALOG = ce.load_catalog()
P001 = dict(CATALOG["products"][0])

MED_EVIDENCE = [{"evidence_id": "EV-M", "document_name": "01_medical_insurance.md",
                 "content": "百万医疗险主要解决大额医疗费用支出风险，通常提供高额住院医疗报销额度；"
                            "一般设有免赔额（常见 1 万元）与报销上限。"}]

# --------------------------------------------------------------------------- #
lines.append("=== G: determined matching (rules-driven, format-aware) ===")
g = ag.ground_product_attributes(P001, MED_EVIDENCE, RULES)
attrs = g["attributes"]
chk("configured attribute set matches the rules file",
    set(attrs.keys()) == {a["id"] for a in RULES["attributes"]}, sorted(attrs.keys()))
chk("coverage_type is SUPPORTED when the evidence discusses the product type",
    attrs["coverage_type"]["status"] == S_OK, attrs["coverage_type"])
chk("amount variants bridge catalog `10000元` and KB `1 万元`",
    attrs["deductible"]["status"] == S_OK, attrs["deductible"])
chk("rollup is SUPPORTED when every REQUIRED attribute is SUPPORTED",
    g["rollup"] == S_OK, g["rollup"])
chk("an attribute the product never declares is NOT_CHECKABLE",
    ag.ground_product_attributes({"product_id": "X"}, MED_EVIDENCE, RULES)["attributes"]
    ["coverage_type"]["status"] == S_NC, "declared-nothing product")

# --------------------------------------------------------------------------- #
lines.append("")
lines.append("=== G: NOT_CHECKABLE is an independent third state ===")
nc = ag.ground_product_attributes(P001, [], RULES)
chk("no evidence text at all -> NOT_CHECKABLE (not SUPPORTED)",
    all(v["status"] == S_NC for v in nc["attributes"].values()), nc["rollup"])
chk("NOT_CHECKABLE rollup is a distinct value",
    nc["rollup"] == S_NC and nc["rollup"] != S_OK, nc["rollup"])

# required attribute that is UNSUPPORTED must win over SUPPORTED optional ones
mixed = ag.ground_product_attributes(
    {**P001, "product_type": "accident"}, MED_EVIDENCE, RULES)
chk("a REQUIRED attribute the evidence contradicts wins -> UNSUPPORTED",
    mixed["rollup"] == S_UNSUP, mixed["rollup"])
chk("...and the offending attribute is named",
    mixed["attributes"]["coverage_type"]["status"] == S_UNSUP,
    mixed["attributes"]["coverage_type"])

# CONFLICT beats NOT_CHECKABLE, UNSUPPORTED beats CONFLICT
conf = ag.ground_product_attributes(
    P001, [dict(MED_EVIDENCE[0], conflict=True)], RULES)
chk("a conflicting chunk -> CONFLICT (not SUPPORTED)",
    conf["attributes"]["coverage_type"]["status"] == S_CONFLICT, conf["attributes"]["coverage_type"])
chk("CONFLICT rollup surfaces", conf["rollup"] == S_CONFLICT, conf["rollup"])

# optional-only failure must NOT block
opt_only = copy.deepcopy(P001)
opt_only.pop("constraints", None)          # drops deductible/renewal/term claims
opt_out = ag.ground_product_attributes(opt_only, MED_EVIDENCE, RULES)
chk("optional attributes being uncheckable does not change the required verdict",
    opt_out["rollup"] == S_OK, opt_out["rollup"])

# --------------------------------------------------------------------------- #
lines.append("")
lines.append("=== G: the verdict reaches the candidate / recommendation layers ===")
rules = ce.load_rules()
ev_ok = ce.resolve_evidence(P001, {"evidence": MED_EVIDENCE}, rules)
chk("candidate evidence stays AVAILABLE when required attributes are grounded",
    ev_ok["available"] is True and ev_ok["status"] == "AVAILABLE", ev_ok["status"])
chk("candidate evidence exposes the grounding block", bool(ev_ok.get("grounding")), ev_ok.keys())
chk("candidate evidence exposes the attribute rollup",
    ev_ok.get("attribute_rollup") == S_OK, ev_ok.get("attribute_rollup"))

ev_bad = ce.resolve_evidence({**P001, "product_type": "accident"},
                             {"evidence": MED_EVIDENCE}, rules)
chk("an unsupported REQUIRED attribute downgrades the candidate to not-available",
    ev_bad["available"] is False and ev_bad["status"] == "MISSING", ev_bad["status"])
chk("...reporting the reason as UNSUPPORTED rather than missing",
    ev_bad.get("attribute_rollup") == S_UNSUP, ev_bad.get("attribute_rollup"))

# real project() carries it into the recommendation's candidate shape
proj = _load_module("proj_p7", os.path.join(REC_SCRIPTS, "product_candidates_to_candidate_solutions.py"))
pc_artifact = {"status": "COMPLETE", "catalog": {"catalog_version": "0.1"},
               "candidates": [{
                   "candidate_id": "C001", "product_id": "P001", "product_type": "medical",
                   "solution_id": "SOL-001", "related_gap_ids": ["GAP-R1-001"],
                   "related_risk_ids": ["R1-001"], "admissible": True,
                   "coverage_direction_match": "MATCH", "coverage_direction_hits": ["医疗"],
                   "eligibility": {"status": "ELIGIBLE"},
                   "evidence": ev_bad,
                   "is_demo": True, "product_version": "1.0", "catalog_version": "0.1",
               }]}
projected, _trace = proj.project(pc_artifact, {"risks": []}, proj.load_rules())
pv = (projected[0].get("_product_validation") or {}) if projected else {}
chk("projection carries the attribute rollup into the recommendation input",
    pv.get("evidence_attribute_rollup") == S_UNSUP, pv.get("evidence_attribute_rollup"))
chk("projection names the unsupported attributes",
    pv.get("evidence_unsupported_attributes") == sorted(
        k for k, v in (ev_bad["grounding"]["attributes"]).items() if v["status"] == S_UNSUP)
    and "coverage_type" in (pv.get("evidence_unsupported_attributes") or []),
    pv.get("evidence_unsupported_attributes"))

# --------------------------------------------------------------------------- #
lines.append("")
lines.append("=== G: real pipeline is not regressed ===")
with open(os.path.join(BENCH_DIR, "manifest.json"), encoding="utf-8") as f:
    manifest = json.load(f)
case = next(c for c in manifest["cases"] if c["id"] == "bm-complete-006-single-medical")
with open(os.path.join(REPO, manifest["seeds_file"]), encoding="utf-8") as f:
    base = json.load(f)
wf = orch.load_workflow()
state, rep = BENCH.run_case(case, wf, base, manifest["seeds_file"],
                            os.path.join(REPO, manifest["empty_kb"]))
arts = state.get("artifacts") or {}
pc = arts.get("product-candidates") or {}
cands = pc.get("candidates") or []
chk("COMPLETE case still reaches COMPLETED", state.get("status") == "COMPLETED", state.get("status"))
chk("candidates carry a grounding block", bool(cands) and all(
    (c.get("evidence") or {}).get("grounding") for c in cands), len(cands))
chk("no candidate is rejected for EVIDENCE_UNSUPPORTED on the healthy path",
    not any("EVIDENCE_UNSUPPORTED" in (c.get("reject_reason_codes") or []) for c in cands),
    [c.get("reject_reason_codes") for c in cands])
rec = (arts.get("product-recommendation") or {}).get("payload") or {}
chk("recommendation is still COMPLETE", rec.get("status") == "COMPLETE", rec.get("status"))
# reverse: the grounding really is doing work -- a wrong claim IS rejected
chk("reverse: a product whose evidence does not state its type IS rejected",
    ev_bad["available"] is False)

# --------------------------------------------------------------------------- #
print("\n".join(lines))
print("-" * 70)
print("STEP4-P7 EVIDENCE GROUNDING: %d/%d checks passed" % (passed, passed + failed))
print("RESULT: %s" % ("ALL GREEN" if failed == 0 else "FAILURES PRESENT"))
sys.exit(0 if failed == 0 else 1)
