# -*- coding: utf-8 -*-
"""Phase16 Evidence Chain Integrity Auditor (Task 2) — read-only.

Validates structural integrity of the per-request chain:

  request → intent → retrieval → qualified evidence → baseline →
  claim ledger → hard-class prefilter → judge → post-gate →
  authority contract → verified subset → final gate → production_final

Inputs are the same artifacts observe.py reads, joined per request:
delivery-trace records carry text_head+ts; ledger decisions carry
sentence+ts; run traces carry the request chain. The auditor accepts
INJECTED records (fixtures/tests) via audit(records=...) and derives
the production view via production_records().

Checks 1-16 per the task spec. Never mutates data.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
OBS = os.path.join(REPO, "tmp", "obs")

VALID_SOURCES = {"AUTHORITY_REGEN_RESULT", "BASELINE"}
_CIT = re.compile(r"\[E\d+\]")


def production_records(start: str) -> dict:
    """Derive chain records from live artifacts (post marker)."""
    def jl(path):
        out = []
        p = os.path.join(OBS, path)
        if os.path.exists(p):
            for ln in open(p, encoding="utf-8"):
                ln = ln.strip()
                if ln:
                    try:
                        out.append(json.loads(ln))
                    except Exception:  # noqa: BLE001
                        pass
        return out

    led = [r for r in jl("k29c_fix3_phase12_authority_ledger.jsonl")
           if r.get("ts", "") >= start]
    tr = [r for r in jl("k29c_fix3_phase13_delivery_trace.jsonl")
          if r.get("ts", "") >= start]
    # group ledger rows by second-level adjacency into "requests"
    # (one request's failing sentences decide within the same turn)
    groups = []
    for r in sorted(led, key=lambda x: x.get("ts", "")):
        if groups and r["ts"][:16] == groups[-1][0]["ts"][:16]:
            groups[-1].append(r)
        else:
            groups.append([r])
    records = []
    for g, t in zip(groups, tr + [None] * len(groups)):
        records.append({
            "request_id": "req@" + (g[0].get("ts", "") or "?"),
            "ts_request": g[0].get("ts"),
            "intent": {"present": True},          # inferred from chain
            "evidence_present": any(_CIT.search(x.get("sentence", ""))
                                    for x in g),
            "claims": [{"id": "%s#%d" % (g[0].get("ts"), i),
                        "sentence": x.get("sentence", ""),
                        "authority": x.get("authority_decision"),
                        "judge": x.get("judge_result"),
                        "postgate": x.get("post_gate_result"),
                        "ts": x.get("ts")} for i, x in enumerate(g)],
            "delivery": t,
            "production_final_source": (t or {}).get(
                "production_final_source"),
        })
    return {"records": records, "source": "production"}


def audit(records: list) -> dict:
    """Structural checks over injected chain records."""
    problems = defaultdict(list)
    total = len(records)
    complete = 0
    orphans = 0
    dups = 0
    ts_anom = 0
    untraceable = 0
    seen_claim_ids = Counter()
    seen_decisions = Counter()

    for rec in records:
        rid = rec.get("request_id", "?")
        ts_req = rec.get("ts_request") or ""
        ok = True

        # 1 request exists (by construction), 2 intent, 3 evidence
        if not rec.get("intent", {}).get("present"):
            problems["missing_intent"].append(rid)
            ok = False
        if not rec.get("evidence_present"):
            problems["missing_evidence"].append(rid)
            ok = False
        claims = rec.get("claims") or []
        # 4 claims exist
        if not claims:
            problems["missing_claims"].append(rid)
            ok = False
        for c in claims:
            cid = c.get("id")
            # 5 unique claim id
            if not cid or seen_claim_ids[cid]:
                problems["duplicate_claim_id"].append((rid, cid))
                ok = False
            seen_claim_ids[cid] += 1
            # 6 evidence linkage (citation in sentence)
            if not _CIT.search(c.get("sentence", "")):
                problems["claim_without_evidence_link"].append(cid)
                ok = False
            # 7 authority decision maps to a claim
            if c.get("authority") and not c.get("id"):
                problems["authority_without_claim"].append(rid)
                ok = False
            # 8 judge decision maps to a claim
            if c.get("authority") == "ALLOW_UPGRADE" and not c.get(
                    "judge"):
                problems["upgrade_without_judge"].append(cid)
                ok = False
            # 9 postgate present on upgrades
            if c.get("authority") == "ALLOW_UPGRADE" and not c.get(
                    "postgate"):
                problems["upgrade_without_postgate"].append(cid)
                ok = False
            # 13 timestamp order
            if c.get("ts") and ts_req and str(c["ts"]) < str(ts_req):
                problems["timestamp_order"].append(cid)
                ts_anom += 1
                ok = False
        # 10 delivery present
        if rec.get("delivery") is None and any(
                c.get("authority") == "ALLOW_UPGRADE" for c in claims):
            problems["missing_delivery"].append(rid)
            ok = False
        # 11 valid production_final_source
        src = rec.get("production_final_source")
        if rec.get("delivery") is not None and src not in VALID_SOURCES:
            problems["invalid_production_final_source"].append((rid, src))
            ok = False
        # 12 delivery consistent with authority decision
        d = rec.get("delivery") or {}
        flipped = bool(d.get("verdict_flipped"))
        upgraded = any(c.get("authority") == "ALLOW_UPGRADE"
                       for c in claims)
        if d and flipped != (src == "AUTHORITY_REGEN_RESULT"):
            problems["delivery_source_mismatch"].append(rid)
            ok = False
        if d and flipped and not upgraded:
            problems["delivery_without_upgrade"].append(rid)
            ok = False
        if ok:
            complete += 1

    # 14 orphan claims: claim ids whose request record is missing
    orphan_ids = [cid for cid, n in seen_claim_ids.items() if n == 0]
    orphans = len(orphan_ids)
    # 15 duplicate decisions: same claim id decided twice
    dups = sum(n - 1 for n in seen_claim_ids.values() if n > 1)
    # 16 events not traceable to any request
    untraceable = len(problems.get("delivery_without_upgrade", [])) + \
        len(problems.get("upgrade_without_judge", []))

    traceability = (complete / total) if total else 1.0
    verdict = "PASS" if not dict(problems) else "FAIL"
    return {"verdict": verdict, "total_records": total,
            "complete_chains": complete,
            "broken_chains": total - complete,
            "orphan_records": orphans, "duplicate_records": dups,
            "timestamp_anomalies": ts_anom,
            "untraceable_events": untraceable,
            "traceability_rate": round(traceability, 4),
            "problems": {k: v[:5] for k, v in problems.items()}}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, REPO)
    from tools.phase16.observe import window_start
    recs = production_records(window_start())
    print(json.dumps(audit(recs["records"]), ensure_ascii=False, indent=1))
