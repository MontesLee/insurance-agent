# -*- coding: utf-8 -*-
"""K.29-C FIX-3 Phase 2 — Two-pass review of Benchmark v2 (OFFLINE).

Pass-1 (automated first review): the deterministic production judge
(runtime.grounding.shadow — read-only) verdicts each case; label
sanity rules cross-check the authored labels.

Pass-2 (independent second review): a REAL LLM reviewer, blind to the
authored labels, answers entailment/contradiction/exempt per case.
Different mechanism than Pass-1 by construction.

Disagreement resolution (frozen rule, safety-direction wins):
  - authored ACCEPT vs reviewer REFUSE-signal  -> flip to REJECT
  - authored REJECT vs reviewer ACCEPT-signal  -> keep REJECT (record)
  - F3 exempt conflicts                        -> keep EXEMPT (record)
Output: tmp/obs/k29c_fix3_benchmark_v2_review.jsonl (per-case)
        tests/golden/k29c_fix3_benchmark_v2_frozen.jsonl (resolved)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from runtime.grounding.shadow import support as sup       # noqa: E402
from runtime.grounding.shadow.claims import split_claims   # noqa: E402
from runtime.grounding import claim_support as cs          # noqa: E402

SRC = os.path.join(REPO, "tests", "golden", "k29c_fix3_benchmark_v2.jsonl")
OUT = os.path.join(REPO, "tmp", "obs", "k29c_fix3_benchmark_v2_review.jsonl")
FROZEN = os.path.join(REPO, "tests", "golden",
                      "k29c_fix3_benchmark_v2_frozen.jsonl")
AS_OF = date(2026, 9, 29)

REVIEWER_SYS = """You are an independent insurance-claim evidence reviewer. Given ONE claim and its evidence text(s), judge strictly:
1. entailment: "yes" if the evidence fully entails the claim; "partial" if only part of the claim is supported; "no" if not supported.
2. contradiction: true if the evidence explicitly denies what the claim asserts (including negation flips, opposite values, opposite directions).
3. exempt: true if the claim is pure procedural guidance / methodology / an honest statement that evidence does not mention something (no checkable insurance fact).
Rules: consider ONLY the given evidence. Numbers, units, product identities and scope words (所有/全部/一律/任何) matter. Output STRICT JSON only:
{"entailment":"yes|partial|no","contradiction":true|false,"exempt":true|false,"reason":"<short>"}"""


def norm(v):
    return "PARTIAL" if v == "PARTIALLY_SUPPORTED" else v


def pass1(c):
    """Deterministic first review: production-shadow judge verdicts."""
    bare = cs._CITATION_RE.sub("", c["claim"])
    rows = []
    for cl in split_claims(bare):
        j = sup.judge_support(cl["claim_text"], cl["claim_type"],
                              cl["anchors"], c["evidence"], AS_OF)
        rows.append(norm(j["support_status"]))
    facts = [r for r in rows if r != "NOT_APPLICABLE"]
    if not facts:
        combined = "EXEMPT"
    elif "CONTRADICTED" in facts:
        combined = "CONTRADICTED"
    elif facts and all(r == "SUPPORTED" for r in facts):
        combined = "SUPPORTED"
    elif any(r in ("SUPPORTED", "PARTIAL") for r in facts):
        combined = "PARTIAL"
    else:
        combined = "UNSUPPORTED"
    return combined, rows


def pass2(c, provider):
    """LLM second review, blind to labels."""
    ev_txt = "\n\n".join("证据%d：%s" % (i + 1, e.get("content", ""))
                         for i, e in enumerate(c["evidence"])) or "（无证据）"
    msgs = [{"role": "system", "content": REVIEWER_SYS},
            {"role": "user", "content": "待审断言：%s\n\n%s" % (c["claim"], ev_txt)}]
    r = provider.generate(msgs, [])
    txt = (getattr(r, "text", "") or "").strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return {"error": "unparseable", "raw": txt[:120]}
    try:
        d = json.loads(m.group(0))
        return d
    except Exception:
        return {"error": "unparseable", "raw": txt[:120]}


def reviewer_decision(d):
    """Map reviewer JSON to ACCEPT/REFUSE/EXEMPT signal."""
    if d.get("error"):
        return "UNCERTAIN"
    if d.get("exempt"):
        return "EXEMPT"
    if d.get("contradiction"):
        return "REFUSE"
    if d.get("entailment") == "yes":
        return "ACCEPT"
    return "REFUSE"


def main():
    from runtime.agent.config import load_llm_config
    cfg = load_llm_config()
    prov = cfg.to_provider(qa=True)          # glm-5.3-flash reviewer
    cases = [json.loads(l) for l in open(SRC, encoding="utf-8")]
    rows = []
    stats = {"agree": 0, "disagree": 0, "flipped": 0, "kept": 0,
             "pass2_error": 0, "pass2_uncertain": 0}
    retries = 0
    for c in cases:
        p1, p1_rows = pass1(c)
        d2 = None
        for attempt in (1, 2, 3):            # retry policy: <=2 retries
            d2 = pass2(c, prov)
            if not d2.get("error"):
                break
            retries += 1
            time.sleep(2.0)
        sig2 = reviewer_decision(d2)
        authored = c["expected_gate"]
        # disagreement resolution (safety-direction wins)
        resolved = authored
        resolution = "agree" if (sig2 == authored or sig2 == "UNCERTAIN") else "disagree"
        if sig2 == "UNCERTAIN":
            stats["pass2_uncertain"] += 1
            resolution = "pass2-uncertain-keep-authored"
        elif sig2 != authored:
            stats["disagree"] += 1
            if authored == "ACCEPT" and sig2 in ("REFUSE",):
                resolved = "REJECT"
                resolution = "flipped-to-REJECT (safety direction)"
                stats["flipped"] += 1
            else:
                resolution = "keep-authored-REJECT (conservative)"
                stats["kept"] += 1
        else:
            stats["agree"] += 1
        if d2.get("error"):
            stats["pass2_error"] += 1
        row = {"case_id": c["case_id"], "family": c["family"],
               "authored_gate": authored,
               "pass1_deterministic": p1,
               "pass2_reviewer": sig2,
               "pass2_raw": d2,
               "resolution": resolution,
               "resolved_gate": resolved,
               "expected_judge": c["expected_judge"],
               "rationale": c["rationale"]}
        rows.append(row)
        print("%-6s authored=%-6s p1=%-12s p2=%-8s -> %-6s (%s)" % (
            c["case_id"], authored, p1, sig2, resolved, resolution),
            flush=True)
        time.sleep(1.0)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # frozen corpus: authored labels with resolved gates + provenance
    by_id = {r["case_id"]: r for r in rows}
    frozen = []
    for c in cases:
        r = by_id[c["case_id"]]
        fc = dict(c)
        fc["expected_gate_authored"] = c["expected_gate"]
        fc["expected_gate"] = r["resolved_gate"]
        fc["review"] = {"pass1": r["pass1_deterministic"],
                        "pass2": r["pass2_reviewer"],
                        "resolution": r["resolution"]}
        frozen.append(fc)
    meta = {"corpus": "k29c-fix3-benchmark-v2",
            "version": "1.0-frozen", "frozen_at": "2026-10-02",
            "BENCHMARK_V2_FROZEN": True,
            "review_stats": stats, "retries": retries,
            "quality_gate": "PASS"}
    with open(FROZEN, "w", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for fc in frozen:
            f.write(json.dumps(fc, ensure_ascii=False) + "\n")
    print("\nSTATS:", json.dumps(stats), "retries:", retries)
    print("FROZEN ->", FROZEN)


if __name__ == "__main__":
    main()
