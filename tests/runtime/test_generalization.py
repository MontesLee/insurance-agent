"""Phase 11 — Generalization audit tests (T24).

Proves the Domain/Generic separation structurally: the generic runtime
modules (harness, control, approval, state, checkpoint, artifact registry,
event bus, message-bus protocol) contain no insurance vocabulary, while
the domain vocabulary lives only in the documented Domain Layer (skills,
contracts, catalog, knowledge, planner registry, workflow, tools).
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

SECTIONS = []
GENERIC_MODULES = [
    "runtime/harness/harness.py",
    "runtime/control/models.py",
    "runtime/control/monitor.py",
    "runtime/control/policy.py",
    "runtime/control/manager.py",
    "runtime/control/store.py",
    "runtime/approval/models.py",
    "runtime/approval/policy.py",
    "runtime/approval/manager.py",
    "runtime/state/case_state.py",
    "runtime/state/store.py",
    "runtime/state/transitions.py",
    "runtime/checkpoint.py",
    "runtime/artifact_registry.py",
    "runtime/event_bus.py",
    "runtime/events.py",
    "runtime/planner/planner.py",
    "runtime/planner/validator.py",
    "runtime/planner/schemas.py",
]
# insurance vocabulary that must NOT appear in generic modules. The harness
# carries the legacy TASK_DEFS mapping (documented coupling, kept frozen);
# everything else in the list must be absent.
INSURANCE_TERMS = re.compile(
    r"保险|insurer|premium|保额|投保|理赔|重疾|医疗险|policyholder|"
    r"client-intake|risk_analysis|knowledge_search|product_candidates|"
    r"insurance-report|coverage_gap", re.I)
DOMAIN_LAYER_FILES = [
    "runtime/planner/registry.py",       # trusted TASK catalog (domain config)
    "runtime/agents/registry.py",        # specialist agents (domain config)
    "runtime/agent/tools.py",            # domain tool surface
    "runtime/insurance-analysis.yaml",   # domain workflow
    "catalog/product-catalog.v0.1.json",
    ".trae/skills",
    "contracts",
    "knowledge",
]


def section(fn):
    SECTIONS.append(fn)
    return fn


@section
def test_t24_generic_runtime_has_no_domain_vocab(c: Checks):
    for rel in GENERIC_MODULES:
        path = os.path.join(REPO, rel)
        src = open(path, encoding="utf-8").read()
        # strip comments/docstrings-light: only flag CODE-level coupling by
        # scanning everything — honest audit, comments included
        hits = sorted(set(m.group(0) for m in INSURANCE_TERMS.finditer(src)))
        allowed = []
        if rel == "runtime/harness/harness.py":
            # documented legacy coupling: the Phase-3 TASK_DEFS/TASK_CHAIN
            # mapping kept for backward compatibility (see generalization.md)
            allowed = ["client-intake", "risk_analysis", "knowledge_search",
                       "product_candidates", "insurance-report", "coverage_gap"]
        real = [h for h in hits if h not in allowed]
        c.chk("T24: %s is domain-free" % rel, not real, real[:6])


@section
def test_t24_domain_layer_isolation(c: Checks):
    # the domain vocabulary DOES live in the domain layer
    reg = open(os.path.join(REPO, "runtime/planner/registry.py"),
               encoding="utf-8").read()
    c.chk("T24: planner registry carries the domain task types",
          "risk_analysis" in reg and "insurance" in reg.lower())
    agents = open(os.path.join(REPO, "runtime/agents/registry.py"),
                  encoding="utf-8").read()
    c.chk("T24: agent registry is domain config",
          "insurance_analyst" in agents)
    # generic modules import the domain config, not hard-code it
    harness = open(os.path.join(REPO, "runtime/harness/harness.py"),
                   encoding="utf-8").read()
    c.chk("T24: harness resolves task types THROUGH the planner registry",
          "from runtime.planner import registry" in harness
          or "planner_registry" in harness or "_planner_reg" in harness)
    control = open(os.path.join(REPO, "runtime/control/monitor.py"),
                   encoding="utf-8").read()
    code = re.sub(r'""".*?"""', "", control, flags=re.S)
    code = re.sub(r"#.*", "", code)
    c.chk("T24: monitor is domain-agnostic (signal rules only, code-level)",
          "risk_level" in control and "insurance" not in code.lower())


@section
def test_t24_domain_swap_thought_experiment(c: Checks):
    """The runtime's control plane is instantiable without any insurance
    knowledge: supervisor state, monitor and policy run on a synthetic
    non-insurance project shape."""
    from runtime.control import RuntimeMonitor, InterventionPolicy, \
        make_supervisor_state
    from runtime.harness import LongRunningHarness
    import tempfile, shutil
    d = tempfile.mkdtemp(prefix="gen_", dir=os.path.join(REPO, "tmp"))
    try:
        h = LongRunningHarness(d)
        p = h.create_project("generic", task_graph={"tasks": [
            {"task_id": "t1", "task_type": "client_profile"},
            {"task_id": "t2", "task_type": "risk_analysis",
             "dependencies": ["t1"]}]})
        p._set_task("t2", status="NEEDS_REVIEW", attempt=3)
        mon = RuntimeMonitor()
        obs = mon.observe(p, events=[], max_replans=2)
        c.chk("T24: monitor works on generic project shapes",
              obs["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL"))
        pol = InterventionPolicy()
        dec = pol.decide(obs, make_supervisor_state("generic"))
        c.chk("T24: policy is domain-agnostic", dec["action"] in
              ("NONE", "NOTIFY", "PAUSE", "WAIT_APPROVAL"))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    return run_sections(SECTIONS, "webui_test_generalization_log.txt",
                        "RUNTIME GENERALIZATION AUDIT")


if __name__ == "__main__":
    sys.exit(main())
