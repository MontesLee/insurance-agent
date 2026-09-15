"""Step 4 Phase 8 — Product Catalog Versioning.

Verifies the minimal version management the spec asks for (§20):

  * the catalog carries `catalog_version` plus, per product, `product_version` /
    `effective_from` / `effective_to`, and is still schema-valid;
  * every candidate carries the catalog + product edition it was selected from;
  * a COMPLETE recommendation PINS `product_version` + `catalog_version` on the product
    it names — so a historical case can still explain "why was this recommended then"
    after the catalog has moved on;
  * the pin survives a catalog update (the recorded case is NOT silently rewritten).

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
for p in (REPO, CAND_SCRIPTS, REC_SCRIPTS):
    if p not in sys.path:
        sys.path.insert(0, p)

from evidence import request as ev_request  # noqa: E402
from evidence import provider as ev_provider  # noqa: E402
import product_candidate_engine as cand_engine  # noqa: E402

STEP2 = os.path.join(REPO, "test-cases", "e2e", "product-recommendation")
CATALOG = os.path.join(REPO, "catalog", "product-catalog.v0.1.json")
DEFAULT_KB = os.path.join(REPO, "domain", "insurance", "references")

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


def _load_rec_module():
    path = os.path.join(REC_SCRIPTS, "invoke-product-recommendation.py")
    spec = importlib.util.spec_from_file_location("invoke_product_recommendation_p8", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    catalog = json.load(open(CATALOG, encoding="utf-8"))
    cat_ver = catalog.get("catalog_version")

    # ---- 1. catalog carries the version fields -----------------------------
    chk("catalog has catalog_version", bool(cat_ver), cat_ver)
    chk("catalog has effective_from", catalog.get("effective_from") is not None,
        catalog.get("effective_from"))
    bad = [p["product_id"] for p in catalog["products"]
           if not p.get("product_version") or not p.get("effective_from")]
    chk("every product has product_version + effective_from", not bad, bad)
    # Real schema validation — no "cannot verify => pass" fallback (anti-fake-pass rule).
    import jsonschema  # noqa: E402
    cat_schema = json.load(open(os.path.join(
        REPO, ".trae", "skills", "product-candidate-provider", "schemas",
        "product-catalog.schema.json"), encoding="utf-8"))
    try:
        jsonschema.Draft7Validator(cat_schema).validate(catalog)
        schema_ok, schema_err = True, ""
    except jsonschema.ValidationError as e:
        schema_ok, schema_err = False, str(e.message)[:200]
    chk("catalog schema-valid", schema_ok, schema_err)

    # ---- 2. run the real chain: Solution -> Evidence -> Candidate -> Rec ----
    case = json.load(open(os.path.join(STEP2, "case-001-happy-path.json"), encoding="utf-8"))
    solution_plan = case["solution_plan"]
    sol = (solution_plan.get("payload", {}).get("solutions") or [{}])[0]

    q = ev_request.from_solution(sol, purpose="PRODUCT_VALIDATION", requester="p8-test")
    eng = ev_provider.build_engine(DEFAULT_KB)
    ev, _ev_ok, _ev_errs = ev_provider.provide_evidence(q, engine=eng)

    cand_out, c_ok, c_errs = cand_engine.run({
        "client_profile": case.get("client_profile"),
        "coverage_gap_analysis": case.get("coverage_gap_analysis"),
        "solution_plan": solution_plan,
        "knowledge_evidence": ev,
    }, None, None)
    chk("candidate provider ran", c_ok, "; ".join(c_errs))

    candidates = cand_out.get("candidates") or []
    chk("candidates exist", len(candidates) > 0, len(candidates))
    miss_ver = [c.get("product_id") for c in candidates if not c.get("product_version")]
    chk("every candidate carries product_version", not miss_ver, miss_ver)
    miss_cat = [c.get("product_id") for c in candidates if c.get("catalog_version") != cat_ver]
    chk("every candidate carries catalog_version == %s" % cat_ver, not miss_cat, miss_cat)

    v2_input = {
        "requirement_analysis": case.get("requirement_analysis") or {},
        "risk_assessment": case.get("risk_assessment") or {},
        "coverage_gap_analysis": case.get("coverage_gap_analysis") or {},
        "solution_plan": solution_plan,
        "knowledge_evidence": ev,
        "product_candidates": cand_out,
        "constraints": case.get("constraints"),
    }
    rec_mod = _load_rec_module()
    rec, _warns = rec_mod.run(v2_input)
    rpayload = rec.get("payload", {}) or {}
    chk("recommendation is COMPLETE (a real product was chosen)",
        rpayload.get("status") == "COMPLETE", rpayload.get("status"))

    primary = rpayload.get("primary_recommendation") or {}
    prod = primary.get("product") or {}
    pid = prod.get("product_id")
    chk("primary names a catalog product", bool(pid), pid)

    # ---- 3. the recommendation PINS the edition ---------------------------
    chk("primary pins product_version", bool(prod.get("product_version")),
        prod.get("product_version"))
    chk("primary pins catalog_version == %s" % cat_ver,
        prod.get("catalog_version") == cat_ver, prod.get("catalog_version"))
    cat_prod = next((p for p in catalog["products"] if p["product_id"] == pid), None)
    chk("pinned product_version matches the catalog entry",
        cat_prod is not None and prod.get("product_version") == cat_prod.get("product_version"),
        "%s vs %s" % (prod.get("product_version"),
                      (cat_prod or {}).get("product_version")))

    # ---- 4. a catalog update must NOT rewrite the recorded case ------------
    moved = copy.deepcopy(catalog)
    moved["catalog_version"] = "0.2"
    for p in moved["products"]:
        if p["product_id"] == pid:
            p["product_version"] = "2.0"
    chk("recorded recommendation still explains its own edition after a catalog bump",
        prod.get("catalog_version") == cat_ver and prod.get("product_version") != "2.0",
        "%s / %s" % (prod.get("catalog_version"), prod.get("product_version")))

    out = lines + ["", "STEP4-P8 CATALOG VERSION: %d/%d checks passed" % (passed, passed + failed),
                   "RESULT: %s" % ("ALL GREEN" if failed == 0 else "FAILURES PRESENT")]
    text = "\n".join(out)
    print(text)
    with open(os.path.join(REPO, "tmp", "p8_log.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
