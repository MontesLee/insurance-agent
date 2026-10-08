# -*- coding: utf-8 -*-
"""K.29-C FIX-3 Phase 1.5 — Benchmark v2 quality gate (OFFLINE).

Checks: schema, duplicates, source leakage, gate/judge consistency,
family-rule consistency, hard-negative subtype coverage.
Output: tmp/obs/k29c_fix3_benchmark_v2_quality.json (PASS/FAIL).
"""
import json
import re
from collections import Counter

SRC = 'tests/golden/k29c_fix3_benchmark_v2.jsonl'
OUT = 'tmp/obs/k29c_fix3_benchmark_v2_quality.json'
REQUIRED = ["case_id", "family", "risk_level", "claim", "evidence",
            "expected_gate", "expected_judge", "source_type", "rationale"]
GATES = {"ACCEPT", "REJECT"}
JUDGES = {"ENTAILED", "NOT_ENTAILED", "CONTRADICTED", "EXEMPT"}
NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:天|日|万|万元|元|%|岁|周岁|年|倍|次)")

cases = [json.loads(l) for l in open(SRC, encoding='utf-8')]
issues = []
warns = []

# 1) schema
ids = set()
for c in cases:
    for k in REQUIRED:
        if k not in c:
            issues.append("schema:%s missing %s" % (c.get("case_id"), k))
    if c["expected_gate"] not in GATES:
        issues.append("gate-value:%s" % c["case_id"])
    if c["expected_judge"] not in JUDGES:
        issues.append("judge-value:%s" % c["case_id"])
    if c["case_id"] in ids:
        issues.append("dup-id:%s" % c["case_id"])
    ids.add(c["case_id"])
    if c["family"] not in ("F1", "F2", "F3", "F4", "F5", "F6"):
        issues.append("family:%s" % c["case_id"])
    if not isinstance(c["evidence"], list):
        issues.append("evidence-not-list:%s" % c["case_id"])

# 2) duplicates (normalized claim text)
def norm(s):
    return re.sub(r"[\s，。、；:：()（）]+", "", re.sub(r"\[E\d+\]", "", s or ""))
seen = {}
for c in cases:
    n = norm(c["claim"]) + "|" + norm("".join(
        e.get("content", "") for e in c["evidence"]))
    if n in seen:
        issues.append("dup-claim:%s==%s" % (c["case_id"], seen[n]))
    seen[n] = c["case_id"]

# 3) source leakage: REJECT case whose claim is a verbatim substring of
# evidence (trivially detectable, weak negative) / F1-ACCEPT verbatim
# (not a paraphrase at all)
for c in cases:
    claim_n = norm(c["claim"])
    for e in c["evidence"]:
        ev_n = norm(e.get("content", ""))
        if claim_n and claim_n in ev_n:
            if c["expected_gate"] == "REJECT":
                issues.append("leak-reject-verbatim:%s" % c["case_id"])
            elif c["family"] == "F1":
                issues.append("leak-f1-accept-verbatim:%s" % c["case_id"])

# 4) gate/judge cross consistency
for c in cases:
    g, j, f = c["expected_gate"], c["expected_judge"], c["family"]
    if f == "F3" and not (g == "ACCEPT" and j == "EXEMPT"):
        issues.append("f3-consistency:%s" % c["case_id"])
    if g == "ACCEPT" and j in ("NOT_ENTAILED", "CONTRADICTED"):
        issues.append("gate-judge:%s ACCEPT but %s" % (c["case_id"], j))
    if g == "REJECT" and j == "EXEMPT":
        issues.append("gate-judge:%s REJECT but EXEMPT" % c["case_id"])
    if f == "F2" and not (g == "REJECT" and j == "CONTRADICTED"):
        issues.append("f2-consistency:%s" % c["case_id"])
    if f == "F4" and c.get("numeric_premise_expected") is not True:
        issues.append("f4-premise-flag:%s" % c["case_id"])
    if (f == "F4" and NUM_RE.search(c["claim"]) is None
            and c.get("subtype") != "hidden-premise"):
        issues.append("f4-no-number:%s" % c["case_id"])
    if f == "F3" and (NUM_RE.search(c["claim"]) or c["evidence"]):
        # F3 evidence-absence prose may cite nothing; guidance carries no numbers
        if NUM_RE.search(c["claim"]):
            issues.append("f3-has-number:%s" % c["case_id"])
    if g == "REJECT" and not c["evidence"] and f != "F4":
        issues.append("no-evidence-reject:%s" % c["case_id"])

# 5) hard-negative / subtype coverage
fam = Counter(c["family"] for c in cases)
quota = {"F1": 20, "F2": 10, "F3": 10, "F4": 10, "F5": 15, "F6": 8}
for f, q in quota.items():
    if fam[f] < q:
        issues.append("quota:%s %d<%d" % (f, fam[f], q))
f1 = [c for c in cases if c["family"] == "F1"]
if not any(c["expected_gate"] == "REJECT" and "泛化" in c["rationale"] for c in f1):
    issues.append("coverage:F1-overgeneralization-missing")
if not any("半真" in c["rationale"] for c in f1):
    issues.append("coverage:F1-half-truth-missing")
f2t = Counter()
for c in cases:
    if c["family"] == "F2":
        for t in ("negation-flip", "direction-flip", "condition-flip", "value-flip"):
            if t in c["rationale"]:
                f2t[t] += 1
for t in ("negation-flip", "direction-flip", "condition-flip"):
    if f2t[t] < 2:
        issues.append("coverage:F2-%s<2" % t)
f4s = Counter(c.get("subtype") for c in cases if c["family"] == "F4")
for t in ("sourced", "unsourced", "range-change", "unit-change", "hidden-premise", "trap"):
    if f4s[t] < 1:
        issues.append("coverage:F4-%s-missing" % t)
f5t = Counter(c.get("subtype") for c in cases if c["family"] == "F5")
for t in ("verbatim", "identity", "meta-pin", "adversarial"):
    if f5t[t] < 1:
        issues.append("coverage:F5-%s-missing" % t)
f5_text = " ".join(c["rationale"] + c["claim"] for c in cases if c["family"] == "F5")
for word, tag in (("等待期", "waiting"), ("免责", "exclusion"), ("续保", "benefit"), ("施行", "date")):
    if word not in f5_text:
        issues.append("coverage:F5-%s-missing" % tag)
f6t = Counter(c.get("conflict_type") for c in cases if c["family"] == "F6")
for t in ("consistent", "anchor-conflict", "version-conflict", "window-conflict", "qualitative-conflict"):
    if f6t[t] < 1:
        issues.append("coverage:F6-%s-missing" % t)

gate_pass = not issues
out = {"n_cases": len(cases), "families": dict(fam),
       "gates": dict(Counter(c["expected_gate"] for c in cases)),
       "issues": issues, "warnings": warns,
       "QUALITY_GATE": "PASS" if gate_pass else "FAIL"}
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
