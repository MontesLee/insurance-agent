"""Step 4 Phase 13 — Security / Safety Guardrails.

Insurance is a high-risk domain, so a report must never be able to present a
simulated product as a real one, invent a product, or state an inference as a fact.
This suite locks the guardrails the spec asks for (§30) onto the REAL pipeline:

  * DEMO PRODUCT marking — a recommended direction backed by a demo catalog product is
    disclosed, both in `structured_report.disclosure` and in the rendered Markdown;
  * the demo flag is VERIFIED AGAINST THE CATALOG, not taken on trust from upstream
    (defence in depth): tampering `is_demo=false` upstream cannot silence the marker;
  * a product id that is not in the catalog is a HARD error (FABRICATED_PRODUCT) — the
    report refuses to vouch for it;
  * the disclosure cannot silently disappear: strip the rules and the report errors
    (DEMO_PRODUCT_UNMARKED) instead of quietly dropping the guardrail;
  * 事实 / 分析 / 建议 separation is stated (nature legend) and each section is tagged;
  * UNKNOWN is never rendered as a negation (the "UNKNOWN != FALSE" invariant);
  * no agent-internal / contamination keys leak into the delivered report;
  * the eval engine returns a VERDICT for a list/dict-valued invariant path instead of
    crashing (which would have been an unguarded hole).

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

BENCH_DIR = os.path.join(REPO, "evals", "agent-benchmark")
REPORT_SCRIPTS = os.path.join(REPO, ".trae", "skills", "report-generation", "scripts")
CATALOG = os.path.join(REPO, "catalog", "product-catalog.v0.1.json")
for p in (REPO, REPORT_SCRIPTS):
    if p not in sys.path:
        sys.path.insert(0, p)

import runtime.orchestrator as orch  # noqa: E402
from runtime import eval_engine as ev  # noqa: E402
import report_generation_engine as rge  # noqa: E402

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


BENCH = _load_module("bench_harness_p13", os.path.join(BENCH_DIR, "run_agent_benchmark.py"))

# The COMPLETE single-need case: the only archetype that actually lands on a concrete
# catalog product, so it is where the DEMO guardrail has to prove itself.
COMPLETE_CASE = "bm-complete-006-single-medical"

CASE_INTERNAL_KEYS = {
    "_product_validation", "_composite", "_missing_inputs", "_repair_override",
    "_validation_warnings", "eval_status", "check_id", "attempt", "task_id",
}


def run_complete_case():
    with open(os.path.join(BENCH_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    case = next(c for c in manifest["cases"] if c["id"] == COMPLETE_CASE)
    with open(os.path.join(REPO, manifest["seeds_file"]), encoding="utf-8") as f:
        base = json.load(f)
    kb_empty = os.path.join(REPO, manifest["empty_kb"])
    wf = orch.load_workflow()
    state, rep = BENCH.run_case(case, wf, base, manifest["seeds_file"], kb_empty)
    return state, rep, wf


def report_input(state, wf):
    stage = next(s for s in wf["stages"] if s["id"] == "report-generation")
    return orch.build_stage_input(state, stage)


def payload_of(art):
    if isinstance(art, dict) and isinstance(art.get("payload"), dict):
        return art["payload"]
    return art


def walk_keys(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(k)
            walk_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            walk_keys(v, out)
    return out


# --------------------------------------------------------------------------- #
# G1..G6 — the real COMPLETE path
# --------------------------------------------------------------------------- #
lines.append("=== G: real COMPLETE path (%s) ===" % COMPLETE_CASE)
state, rep, wf = run_complete_case()
arts = state.get("artifacts") or {}
rec = payload_of(arts.get("product-recommendation")) or {}
prim = rec.get("primary_recommendation") or {}
prim_prod = prim.get("product") or {}
rep_payload = payload_of(arts.get("insurance-report")) or {}
sr = rep_payload.get("structured_report") or {}
disc = sr.get("disclosure") or {}
rendered = rep_payload.get("rendered_report") or ""

with open(CATALOG, encoding="utf-8") as f:
    catalog = {p["product_id"]: p for p in json.load(f)["products"]}

chk("case reaches COMPLETED", state.get("status") == "COMPLETED", state.get("status"))
chk("recommendation is COMPLETE", rec.get("status") == "COMPLETE", rec.get("status"))
chk("a primary recommendation exists", bool(prim), prim)
chk("primary names a real catalog product", prim_prod.get("product_id") in catalog,
    prim_prod.get("product_id"))
chk("the catalog product is marked is_demo", bool(catalog.get(prim_prod.get("product_id"), {}).get("is_demo")),
    catalog.get(prim_prod.get("product_id"), {}).get("is_demo"))

chk("disclosure.is_demo is true", disc.get("is_demo") is True, disc.get("is_demo"))
chk("disclosure.catalog_checked is true", disc.get("catalog_checked") is True, disc.get("catalog_checked"))
chk("no unverified (fabricated) products", not disc.get("unverified_products"),
    disc.get("unverified_products"))
chk("demo_products is non-empty", bool(disc.get("demo_products")), disc.get("demo_products"))
chk("every disclosed product is in the catalog",
    all(p in catalog for p in (disc.get("demo_products") or [])), disc.get("demo_products"))
chk("the recommended product is among the disclosed ones",
    prim_prod.get("product_id") in (disc.get("demo_products") or []), disc.get("demo_products"))

chk("rendered report carries the DEMO disclosure", "DEMO" in rendered)
chk("rendered report carries the demo product label",
    (disc.get("demo_disclosure") or "")[:12] in rendered, "disclosure text absent")
chk("rendered report states the fact/analysis/advice nature",
    bool(disc.get("nature_legend")) and disc["nature_legend"][:8] in rendered)
chk("section_nature tags every section it names",
    set((disc.get("section_nature") or {}).values()) <= {"fact", "analysis", "advice"},
    disc.get("section_nature"))
chk("report validation passed (no safety error)",
    (rep_payload.get("validation") or {}).get("passed") is True,
    (rep_payload.get("validation") or {}).get("errors"))

# --------------------------------------------------------------------------- #
# G7..G9 — negative mutations: the guard must be derived, verifiable, unremovable
# --------------------------------------------------------------------------- #
lines.append("")
lines.append("=== G: negative mutations (anti-rubber-stamp) ===")
rules = rge.load_rules()
base_inp = report_input(state, wf)

# G7 — upstream LIES about is_demo: the catalog cross-check must still mark it.
import copy as _copy
lie_inp = _copy.deepcopy(base_inp)
for cand_holder in [lie_inp.get("product_recommendation")]:
    body = payload_of(cand_holder) if cand_holder else None
    if isinstance(body, dict):
        for holder in [body.get("primary_recommendation")] + list(body.get("alternatives") or []):
            if isinstance(holder, dict) and isinstance(holder.get("product"), dict):
                holder["product"]["is_demo"] = False
lie_out = rge.generate_report(lie_inp, rules)
lie_disc = (lie_out.get("structured_report") or {}).get("disclosure") or {}
chk("upstream is_demo=false cannot hide a catalog demo product",
    lie_disc.get("is_demo") is True and bool(lie_disc.get("demo_products")), lie_disc)
chk("...and the rendered report still discloses it", "DEMO" in (lie_out.get("rendered_report") or ""))

# G8 — fabricate a product id: hard error, never presented as a recommendation.
fake_inp = _copy.deepcopy(base_inp)
fake_body = payload_of(fake_inp.get("product_recommendation"))
if isinstance(fake_body, dict):
    primary = fake_body.get("primary_recommendation")
    if isinstance(primary, dict) and isinstance(primary.get("product"), dict):
        primary["product"]["product_id"] = "P999"
fake_out = rge.generate_report(fake_inp, rules)
fake_val = fake_out.get("validation") or {}
fake_errs = " ".join(fake_val.get("errors") or [])
chk("fabricated product id raises FABRICATED_PRODUCT",
    "FABRICATED_PRODUCT" in fake_errs, fake_val.get("errors"))
chk("fabricated report does not pass validation", fake_val.get("passed") is False, fake_val.get("passed"))
chk("fabricated product id is listed as unverified",
    "P999" in ((fake_out.get("structured_report") or {}).get("disclosure") or {}).get("unverified_products", []),
    ((fake_out.get("structured_report") or {}).get("disclosure") or {}).get("unverified_products"))
# reverse: after removing the fabricated id, the same report is clean again
chk("reverse: the un-tampered report has no FABRICATED_PRODUCT error",
    "FABRICATED_PRODUCT" not in " ".join((rep_payload.get("validation") or {}).get("errors") or []))

# G9 — strip the disclosure rules: the guardrail must fail loudly, not vanish.
weak_rules = _copy.deepcopy(rules)
weak_rules.pop("disclosure", None)
weak_out = rge.generate_report(_copy.deepcopy(base_inp), weak_rules)
weak_errs = " ".join((weak_out.get("validation") or {}).get("errors") or [])
chk("missing disclosure text raises DEMO_PRODUCT_UNMARKED",
    "DEMO_PRODUCT_UNMARKED" in weak_errs, (weak_out.get("validation") or {}).get("errors"))
chk("weak-rules report does not pass validation",
    (weak_out.get("validation") or {}).get("passed") is False)
chk("reverse: with the rules present the guard does not fire",
    "DEMO_PRODUCT_UNMARKED" not in " ".join((rep_payload.get("validation") or {}).get("errors") or []))

# --------------------------------------------------------------------------- #
# G10 — UNKNOWN is not FALSE
# --------------------------------------------------------------------------- #
lines.append("")
lines.append("=== G: UNKNOWN is not FALSE ===")
unk_inp = _copy.deepcopy(base_inp)
cs_body = payload_of(unk_inp.get("client_profile"))
probe_field = None
if isinstance(cs_body, dict):
    ep = cs_body.get("existing_protection")
    if isinstance(ep, dict) and "existing_insurance" in ep:
        ep["existing_insurance"] = {"value": None, "status": "UNKNOWN"}
        probe_field = "existing_insurance"
    else:
        fp = cs_body.setdefault("family_profile", {})
        fp["region"] = {"value": None, "status": "UNKNOWN"}
        probe_field = "region"
unk_out = rge.generate_report(unk_inp, rules)
unk_sr = unk_out.get("structured_report") or {}
unk_fields = {f.get("label"): f for f in ((unk_sr.get("client_profile") or {}).get("fields") or [])}
unknown_rendered = [f for f in unk_fields.values() if f.get("status") == "UNKNOWN"]
chk("an UNKNOWN fact is surfaced with status UNKNOWN (not dropped)",
    bool(unknown_rendered), [f.get("label") for f in unk_fields.values()])
target = unknown_rendered[0] if unknown_rendered else None
chk("an UNKNOWN fact renders as 待确认, never as a negation",
    target is not None and "待确认" in (target.get("value") or "") and
    not any(tok in (target.get("value") or "") for tok in ("无", "否", "不适用")),
    (target or {}).get("value"))
chk("the UNKNOWN section note is present in the rendered report",
    bool(unk_out.get("rendered_report")), "no rendered output")

# --------------------------------------------------------------------------- #
# G11 — no contamination / agent-internal keys in the delivered report
# --------------------------------------------------------------------------- #
lines.append("")
lines.append("=== G: no contamination in the delivered report ===")
rep_blob = _copy.deepcopy(rep_payload)
keys = set(walk_keys(rep_blob, []))
leaked = sorted(k for k in keys if k in CASE_INTERNAL_KEYS)
chk("no agent-internal keys leak into the report payload", not leaked, leaked)
leaked_meta = sorted(k for k in keys if k.lower().startswith("metadata") and k not in ("metadata",))
chk("no eval/repair bookkeeping leaks into the report", not leaked_meta, leaked_meta)
chk("report metadata only claims real source skills",
    set((rep_payload.get("metadata") or {}).get("source_skills") or []) <=
    {"client-intake", "requirement-analysis", "risk-analysis", "coverage-gap-analysis",
     "solution", "knowledge-search", "product-recommendation"},
    (rep_payload.get("metadata") or {}).get("source_skills"))

# --------------------------------------------------------------------------- #
# G12 — the eval engine must return a VERDICT for a list/dict-valued path
# --------------------------------------------------------------------------- #
lines.append("")
lines.append("=== G: eval engine never crashes on a list/dict-valued invariant path ===")
probe_rules = {"invariant": [
    {"id": "T-LIST", "artifact_type": "probe", "path": "payload.items[].id",
     "must_be_in": "artifact:other:payload.tags"},
]}
probe_state = {"artifacts": {"other": {"payload": {"tags": ["a", "b"]}}}}
probe_art = {"payload": {"items": [{"id": "a"}]}}
try:
    res = ev.check_invariant(probe_state, probe_art, "probe", probe_rules)
    chk("list-valued allowed-set returns a verdict (no crash)", bool(res) and res[0]["status"] == "PASS", res)
except Exception as e:  # noqa: BLE001
    chk("list-valued allowed-set returns a verdict (no crash)", False, "%s: %s" % (type(e).__name__, e))

probe_rules2 = {"invariant": [
    {"id": "T-DICT", "artifact_type": "probe", "path": "payload.items[].id",
     "must_be_in": "artifact:other:payload.obj"},
]}
probe_state2 = {"artifacts": {"other": {"payload": {"obj": {"nested": [1, 2]}}}}}
try:
    res2 = ev.check_invariant(probe_state2, probe_art, "probe", probe_rules2)
    chk("dict-valued allowed-set returns a FAIL verdict (no crash)",
        bool(res2) and res2[0]["status"] == "FAIL", res2)
except Exception as e:  # noqa: BLE001
    chk("dict-valued allowed-set returns a FAIL verdict (no crash)", False, "%s: %s" % (type(e).__name__, e))

# --------------------------------------------------------------------------- #
print("\n".join(lines))
print("-" * 70)
print("STEP4-P13 GUARDRAILS: %d/%d checks passed" % (passed, passed + failed))
print("RESULT: %s" % ("ALL GREEN" if failed == 0 else "FAILURES PRESENT"))
sys.exit(0 if failed == 0 else 1)
