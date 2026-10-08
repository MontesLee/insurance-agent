# -*- coding: utf-8 -*-
"""FIX-3 Phase 5 — judge replay on the FROZEN v2 corpus (OFFLINE).

Runs (no production touch, no prompt/τ change in production):
  flash ×3  (repeatability; qa slot glm-5.3-flash — same as S0/shadow)
  main  ×1  (model-diversity comparator; approved main slot glm-5.3)
Captures RAW judge outputs (entailment/contradiction/exempt/confidence)
so every τ in {0.5,0.6,0.7,0.8,0.9} is recomputed deterministically
offline. Retry policy: ≤2; failures recorded, never deleted.
Output: tmp/obs/k29c_fix3_phase5_replay.jsonl (one record per judgment)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from runtime.grounding.shadow_judge import (  # noqa: E402
    SemanticJudgeClient, JUDGE_SYSTEM_PROMPT)
from runtime.agent.config import load_llm_config  # noqa: E402

V2 = os.path.join(REPO, "tests", "golden",
                  "k29c_fix3_benchmark_v2_frozen.jsonl")
OUT = os.path.join(REPO, "tmp", "obs", "k29c_fix3_phase5_replay.jsonl")


def call_raw(client, claim, evidence_texts):
    """One judge call returning the RAW parsed dict (pre-τ mapping)."""
    t0 = time.time()
    d = client.judge_claim(claim, evidence_texts)
    d["latency_s"] = d.get("latency_s")
    d["_elapsed"] = round(time.time() - t0, 1)
    return d


def main():
    cases = [json.loads(l) for l in open(V2, encoding="utf-8").readlines()[1:]]
    cfg = load_llm_config()
    arms = [("flash", cfg.to_provider(qa=True), 3),
            ("main", cfg.to_provider(), 1)]
    # resume-safe: skip (slot, rep, case) already recorded
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT, encoding="utf-8"):
            try:
                r0 = json.loads(line)
                done.add((r0["slot"], r0["rep"], r0["case_id"]))
            except Exception:
                pass
        fh = open(OUT, "a", encoding="utf-8")
    else:
        fh = open(OUT, "w", encoding="utf-8")
    n = len(done)
    for slot, provider, reps in arms:
        client = SemanticJudgeClient(provider, tau=0.7)
        for rep in range(1, reps + 1):
            for c in cases:
                if (slot, rep, c["case_id"]) in done:
                    continue
                texts = [e.get("content", "") for e in c["evidence"]]
                raw = None
                for attempt in (1, 2, 3):     # retry <=2
                    raw = call_raw(client, c["claim"], texts)
                    if not str(raw.get("decision_reason", "")).startswith("error"):
                        break
                    time.sleep(2.0)
                rec = {"slot": slot, "rep": rep, "case_id": c["case_id"],
                       "family": c["family"], "gold_gate": c["expected_gate"],
                       "gold_judge": c["expected_judge"],
                       "claim": c["claim"][:100],
                       "decision": raw.get("decision"),
                       "reason": raw.get("decision_reason"),
                       "raw": raw.get("judge_raw"),
                       "latency_s": raw.get("latency_s")}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                n += 1
                if n % 20 == 0:
                    print("%d done (%s rep%d)" % (n, slot, rep), flush=True)
            print("ARM DONE %s rep%d (total %d)" % (slot, rep, n), flush=True)
    fh.close()
    print("wrote %d records -> %s" % (n, OUT))


if __name__ == "__main__":
    main()
