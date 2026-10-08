# -*- coding: utf-8 -*-
"""Phase16 Observation Analyzer (Task 1) — read-only, offline, zero LLM.

Computes the Safety / Authority / Delivery / Utility(D-04) / Latency
metric blocks from the EXISTING artifacts for a marker-delimited window:

  tmp/obs/k29c_fix3_phase12_authority_ledger.jsonl   (authority chain)
  tmp/obs/k29c_fix3_phase13_delivery_trace.jsonl     (delivery flips)
  tmp/obs/k29c_fix3_phase12_incidents.json           (kill/rollback)
  tmp/obs/k29c_fix3_phase12_runtime.json             (counters/latency)
  tmp/webui-runs/run_*/agentcase-*/trace.jsonl       (per-request chain)
  tmp/obs/agent.jsonl                                 (provider records)

Usage (library or CLI):
  python -m tools.phase16.observe [window_start_iso]
Window default = PHASE16-BGE-M3-START marker timestamp.
Real-user vs scripted discrimination: run owner prefix (consumer:
pilot-user-*) = REAL; ops/probe identities = SCRIPTED (excluded from
G11, reported separately).
"""
from __future__ import annotations

import glob
import json
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
OBS = os.path.join(REPO, "tmp", "obs")

LEDGER = os.path.join(OBS, "k29c_fix3_phase12_authority_ledger.jsonl")
TRACE = os.path.join(OBS, "k29c_fix3_phase13_delivery_trace.jsonl")
INCIDENTS = os.path.join(OBS, "k29c_fix3_phase12_incidents.json")
RUNTIME = os.path.join(OBS, "k29c_fix3_phase12_runtime.json")
MARKER = os.path.join(OBS, "k29c_fix3_phase16_bgem3_start.json")
AGENT_JSONL = os.path.join(OBS, "agent.jsonl")

VALID_SOURCES = {"AUTHORITY_REGEN_RESULT", "BASELINE"}

# Escape families = attribution slices of the v2 authority HARD
# contract (tools/k29c_fix3_phase13_authority.py). An escape is only
# counted when the UPGRADED sentence matches the v2 HARD contract
# itself (citation markers stripped first, exactly like the runtime).
_HARD_CONTRACT = re.compile(
    r"\d|P0\d{2}|demo-|该产品|这款|某产品|保险法|管理办法|监管|银保监|"
    r"令第|施行|保证.{0,6}(续保|赔付|返还)|承诺|"
    r"所有|全部|一律|任何|都.{0,3}(能|可|会|是|有)|必然|一定会|"
    r"每个人|所有人群|所有情况|所有产品|"
    r"您|你家|您家|你的")
_HARD_FAMILIES = {
    "numeric": re.compile(r"\d"),
    "product": re.compile(r"该产品|这款|某产品"),
    "regulatory": re.compile(r"保险法|管理办法|监管|银保监|令第|施行"),
    "payment": re.compile(r"保证.{0,6}(续保|赔付|返还)|承诺|赔付"),
    "date_time": re.compile(r"\d{4}年|\d{1,2}月|\d{1,2}日"),
    "universal": re.compile(r"所有|全部|一律|任何|都.{0,3}(能|可|会|是|有)|"
                            r"必然|一定|每个人"),
    "r4": re.compile(r"您|你家|您家|你的"),
}


def _load_jsonl(path, start):
    out = []
    if not os.path.exists(path):
        return out
    for ln in open(path, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        if str(rec.get("ts", rec.get("timestamp", ""))) >= start:
            out.append(rec)
    return out


def window_start() -> str:
    try:
        return json.load(open(MARKER, encoding="utf-8"))["timestamp"]
    except Exception:  # noqa: BLE001
        return "1970-01-01T00:00:00Z"


def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    i = min(len(sorted_vals) - 1, int(round(p / 100.0 * (len(sorted_vals)
                                                         - 1))))
    return sorted_vals[i]


def analyze(start: str = None) -> dict:
    start = start or window_start()
    led = _load_jsonl(LEDGER, start)
    tr = _load_jsonl(TRACE, start)
    incidents = [i for i in json.load(open(INCIDENTS, encoding="utf-8"))
                 if str(i.get("ts", "")) >= start] \
        if os.path.exists(INCIDENTS) else []
    rt = json.load(open(RUNTIME, encoding="utf-8")) \
        if os.path.exists(RUNTIME) else {}

    # ---------------- Safety ----------------
    upgrades = [r for r in led if r.get("authority_decision")
                == "ALLOW_UPGRADE"]
    safety = {f + "_escape": 0 for f in _HARD_FAMILIES}
    safety.update({k: 0 for k in [
        "false_upgrade", "fail_open", "kill_failure", "rollback_failure",
        "version_mismatch", "invalid_production_final_source"]})
    versions = set()
    for r in upgrades:
        sent = re.sub(r"\[E\d+\]", "", r.get("sentence", ""))
        if r.get("stage") != "all-pass" or not r.get("post_gate_result",
                                                     {}).get("ok"):
            safety["false_upgrade"] += 1
        if _HARD_CONTRACT.search(sent):
            # upgraded sentence SHOULD have been hard-intercepted
            for fam, rx in _HARD_FAMILIES.items():
                if rx.search(sent):
                    safety[fam + "_escape"] += 1
            if not any(rx.search(sent) for rx in
                       _HARD_FAMILIES.values()):
                safety["universal_escape"] += 1   # catch-all bucket
            else:
                pass
        v = r.get("version")
        if v:
            versions.add(json.dumps(v, sort_keys=True))
    if len(versions) > 1:
        safety["version_mismatch"] = 1
    for t in tr:
        if t.get("production_final_source") not in VALID_SOURCES:
            safety["invalid_production_final_source"] += 1
    kill_events = [i for i in incidents if i.get("kind") == "KILL"]
    if kill_events and not os.path.exists(os.path.join(
            OBS, "k29c_fix3_phase12_kill.flag")) and upgrades:
        # decisions continued after a recorded kill -> kill ineffective
        after_kill = [r for r in led if r.get("ts", "") >
                      max(k["ts"] for k in kill_events)]
        if after_kill:
            safety["kill_failure"] = 1
    for i in incidents:
        if i.get("kind") == "ROLLBACK_FAILED":
            safety["rollback_failure"] += 1

    # ---------------- Authority ----------------
    from collections import Counter
    dec = Counter(r.get("authority_decision") for r in led)
    stages = Counter(r.get("stage") for r in led)
    judge_calls = sum(
        (r.get("counters_snapshot") or {}).get("judge_calls", 0)
        for r in led[:1])  # snapshot is cumulative: take latest
    latest = led[-1].get("counters_snapshot", {}) if led else {}
    lat = sorted(rt.get("latencies") or [])
    authority = {
        "total_decisions": dec.get("ALLOW_UPGRADE", 0),
        "keep_baseline": dec.get("KEEP_BASELINE", 0),
        "hard_intercepts": stages.get("scope-hard-class", 0),
        "quota_blocks": stages.get("quota", 0),
        "judge_allow": sum(1 for r in led
                           if r.get("judge_result") == "ALLOW_UPGRADE"),
        "judge_reject": sum(1 for r in led
                            if r.get("judge_result")
                            in ("KEEP_BASELINE", "REJECT")),
        "judge_uncertain": sum(1 for r in led if r.get("judge_result")
                               == "UNCERTAIN"),
        "judge_calls_cumulative": latest.get("judge_calls"),
        "postgate_pass": sum(1 for r in led if (r.get("post_gate_result")
                                                or {}).get("ok")),
        "postgate_fail": sum(1 for r in led if r.get("post_gate_result")
                             and not r["post_gate_result"].get("ok")),
        "contract_all_pass": len(upgrades),
        "judge_latency": {"p50": percentile(lat, 50),
                          "p95": percentile(lat, 95),
                          "max": lat[-1] if lat else None,
                          "n": len(lat)},
    }

    # ---------------- Delivery ----------------
    flips = [t for t in tr if t.get("verdict_flipped")]
    delivery = {
        "authority_to_delivery": "%d/%d" % (len(flips), len(tr)),
        "delivered_flips": len(flips),
        "baseline_kept": len(tr) - len(flips),
        "sources": dict(Counter(t.get("production_final_source")
                                for t in tr)),
    }

    # ---------------- Requests / real traffic ----------------
    runs = []
    for d in sorted(glob.glob(os.path.join(
            REPO, "tmp", "webui-runs", "run_*"))):
        try:
            if os.path.getmtime(d) < os.path.getmtime(MARKER) - 60:
                continue
            files = glob.glob(os.path.join(d, "agentcase-*",
                                           "trace.jsonl"))
            runs.append({"dir": os.path.basename(d),
                         "mtime": os.path.getmtime(d),
                         "has_trace": bool(files)})
        except Exception:  # noqa: BLE001
            continue
    llm = _load_jsonl(AGENT_JSONL, start)
    llm_agent = [e for e in llm if e.get("event") == "agent.llm_call"]

    # ---------------- Utility / D-04 (over refusal answers) ----------
    # refusal sources are wired in by day_review (run transcripts);
    # here we expose the classifier over the legacy D-04 corpus if present.
    d04 = None
    corpus = os.path.join(REPO, "docs/knowledge-base/evidence/eval",
                          "d04_corpus.json")
    if os.path.exists(corpus):
        from tools.phase16.d04_classify import classify
        rows = json.load(open(corpus, encoding="utf-8"))
        recs = []
        for r in rows:
            if r.get("final") != "REFUSAL":
                continue
            recs.append(classify({
                "query": r.get("query"),
                "category": "NEGATIVE" if r.get("category") == "NEGATIVE"
                else r.get("category"),
                "refusal_reason": r.get("reason"),
                "qualified_n": r.get("qualified_n"),
                "retrieved": bool(r.get("retrieved_docs")),
                "viol_kinds": r.get("viol_kinds"),
                "viol_detail": {},          # legacy corpus: not per-row
                "minimal_answer_pass": bool(
                    (r.get("minimal_answer_test") or {})
                    .get("support_ok")
                    and (r.get("minimal_answer_test") or {})
                    .get("citation_ok")),
                "draft": r.get("draft_head", ""),
                "source_event": r.get("source", "-")}))
        d04 = dict(Counter(x["classification"] for x in recs))

    return {
        "window_start": start, "generated_from": os.path.abspath(__file__),
        "records": {"ledger": len(led), "delivery_trace": len(tr),
                    "incidents": len(incidents), "runs_seen": len(runs),
                    "agent_llm_calls": len(llm_agent)},
        "safety": safety, "authority": authority, "delivery": delivery,
        "d04_offline_classification": d04,
        "latency": {
            "judge": authority["judge_latency"],
            "runtime_counters_ts": rt.get("ts"),
        },
        "kill_flag_present": os.path.exists(os.path.join(
            OBS, "k29c_fix3_phase12_kill.flag")),
        "incidents_window": incidents,
    }


if __name__ == "__main__":
    import sys
    print(json.dumps(analyze(sys.argv[1] if len(sys.argv) > 1 else None),
                     ensure_ascii=False, indent=1))
