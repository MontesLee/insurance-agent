"""28.K.28 latency analyzer — merge client + server profiles + obs logs.

Inputs
    tmp/obs/perf-bench/client_*.json   (benchmark driver, client clock)
    tmp/obs/run-profiles/{run_id}.json (run profiler, server monotonic)
    tmp/obs/agent.jsonl                (llm.call / knowledge.search)

Derives, per run:
    phase spans (intent / knowledge / per-step LLM / tools / final gap)
    category buckets (LLM / Knowledge / Tools / App overhead)
    client-vs-server split (network + SSE delivery + render-side lag)
    wall-clock vs span-sum (sequential sum vs real critical path)

Aggregates per case (min / max / mean / median; P95 = max at n=3,
labelled honestly) and prints Top-5 slowest operations per run.

Read-only; writes tmp/obs/perf-bench/summary.json.
"""
from __future__ import annotations

import glob
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
BENCH = os.path.join(ROOT, "tmp", "obs", "perf-bench")
PROFILES = os.path.join(ROOT, "tmp", "obs", "run-profiles")
OBS = os.path.join(ROOT, "tmp", "obs", "agent.jsonl")

TERMINAL = ("run_completed", "run_failed")

# read-only durable-event backfill: the live backend's event history
# carries the agent loop's tool name in the top-level `skill` field
# (server emit() maps data.tool -> skill); older profile files captured
# only data.tool. Merging by event_id restores tool attribution for
# already-recorded runs without re-running anything.
_backend = os.environ.get("PERF_BENCH_BASE", "http://127.0.0.1:8123")
_key_cache: list = []


def _bench_key() -> str:
    if _key_cache:
        return _key_cache[0]
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from perf.benchmark_chat import load_key  # noqa: E402
    _key_cache.append(load_key())
    return _key_cache[0]


def _backfill_skills(run_id: str, events: list) -> None:
    """event_id -> skill map from the live bus history (read-only GET)."""
    try:
        import httpx
        r = httpx.get("%s/api/runs/%s/events" % (_backend, run_id),
                      headers={"Authorization": "Bearer %s" % _bench_key()},
                      timeout=10.0)
        if r.status_code != 200:
            return
        skills = {e.get("event_id"): (e.get("skill") or
                                      (e.get("data") or {}).get("tool"))
                  for e in r.json().get("events", [])}
        for e in events:
            if not e.get("tool") and e.get("event_id"):
                e["tool"] = skills.get(e["event_id"])
    except Exception:  # noqa: BLE001 — backfill is best-effort
        pass


def _load(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _obs_window(submit_wall: str, dur_s: float):
    """llm.call / knowledge.search records inside the run's wall window
    (second-resolution timestamps — joined by [submit, submit+dur+2s])."""
    import datetime as dt
    out = {"llm.call": [], "knowledge.search": []}
    if not os.path.isfile(OBS) or not submit_wall:
        return out
    t0 = dt.datetime.strptime(submit_wall, "%Y-%m-%dT%H:%M:%SZ")
    t1 = t0 + dt.timedelta(seconds=dur_s + 2.0)
    with open(OBS, encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            ev = rec.get("event")
            if ev not in out:
                continue
            try:
                ts = dt.datetime.strptime(rec.get("timestamp", ""),
                                          "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                continue
            if t0 <= ts <= t1:
                out[ev].append(rec)
    return out


def analyze_run(client: dict) -> dict:
    """One run -> full merged profile dict (or the client error)."""
    out = {"case": client.get("case"), "tag": None, "run_id":
           client.get("run_id")}
    if client.get("error"):
        out["error"] = client["error"]
        return out
    rid = client.get("run_id")
    prof_path = os.path.join(PROFILES, "%s.json" % rid)
    if not os.path.isfile(prof_path):
        out["error"] = "no server profile for %s" % rid
        return out
    prof = _load(prof_path)
    evs = prof.get("events") or []
    _backfill_skills(rid, evs)
    out["tag"] = "%s_%d" % (client["case"], client["run_index"])

    def first(et, **kw):
        for e in evs:
            if e["event_type"] == et and all(e.get(k) == v
                                             for k, v in kw.items()):
                return e
        return None

    def t_of(e):
        return e["t_ms"] if e else None

    run_start = first("run_started")
    intent = first("intent_classified")
    terminal = [e for e in evs if e["event_type"] in TERMINAL]
    term = terminal[-1] if terminal else None

    # ---- server-side spans ------------------------------------------------
    spans = []          # {name, start_ms, end_ms, dur} (server clock,
                        # relative to profiler attach)
    intent_lat = (intent or {}).get("intent_latency_ms")
    if intent_lat is not None:
        spans.append({"name": "intent_router", "start_ms":
                      t_of(run_start), "end_ms": t_of(intent),
                      "dur_ms": intent_lat, "exact": True})
    # tool spans: sequential interval walk (tool_started opens, the
    # same tool's next completed/failed closes — never pairs across a
    # second start of the same tool, the naive next-completed rule
    # inflated failed+retry sequences into giant spans)
    open_tools: dict = {}
    for e in evs:
        et, tool = e["event_type"], e.get("tool")
        if et == "agent_stream_delta" or not tool:
            continue
        if et == "tool_started":
            open_tools[tool] = e["t_ms"]
        elif et in ("tool_completed", "tool_failed") and tool in open_tools:
            name = ("knowledge_search" if tool == "knowledge_search"
                    else "tool:%s" % tool)
            spans.append({"name": name, "start_ms": open_tools[tool],
                          "end_ms": e["t_ms"],
                          "dur_ms": round(e["t_ms"] - open_tools[tool], 1),
                          "failed": et == "tool_failed"})
            del open_tools[tool]
    # agent-loop steps: agent_step_started -> next boundary event
    steps = [e for e in evs if e["event_type"] == "agent_step_started"]
    for s in steps:
        nxt = next((e for e in evs if e["event_type"] not in (
            "agent_stream_delta", "agent_step_started")
            and e["t_ms"] > s["t_ms"]), None)
        if not nxt:
            continue
        # within the step, tool time is subtracted (LLM-only span)
        tool_ms = sum(sp["dur_ms"] for sp in spans
                      if sp["start_ms"] is not None
                      and s["t_ms"] <= sp["start_ms"] < nxt["t_ms"]
                      and sp["name"] != "intent_router")
        step_dur = round(nxt["t_ms"] - s["t_ms"], 1)
        spans.append({"name": "agent_step_%s_llm" % (
                         s.get("step") or "?"),
                      "start_ms": s["t_ms"], "end_ms": nxt["t_ms"],
                      "dur_ms": round(max(0.0, step_dur - tool_ms), 1)})
    # QA slice: LLM span = knowledge end -> qa_answered (or refusal path)
    qa = first("qa_answered")
    if qa is not None:
        ks_end = max([sp["end_ms"] for sp in spans
                      if sp["name"] == "knowledge_search"], default=None)
        if ks_end is not None:
            spans.append({"name": "qa_llm_grounding",
                          "start_ms": ks_end, "end_ms": qa["t_ms"],
                          "dur_ms": round(qa["t_ms"] - ks_end, 1)})
    # final gap: last pre-terminal MILESTONE (deltas excluded — they
    # live inside the LLM span) -> terminal. By LIST POSITION, not
    # t_ms comparison: arrival stamps of adjacent events can tie after
    # rounding and a strict < would drop the real milestone.
    if term is not None:
        term_idx = evs.index(term)
        pre = [e for e in evs[:term_idx]
               if e["event_type"] != "agent_stream_delta"]
        if pre:
            last = pre[-1]
            spans.append({"name": "finalize_transcript",
                          "start_ms": last["t_ms"],
                          "end_ms": term["t_ms"],
                          "dur_ms": round(term["t_ms"] - last["t_ms"], 1)})

    # ---- stream milestones ------------------------------------------------
    deltas = [e for e in evs if e["event_type"] == "agent_stream_delta"]
    first_any_delta = deltas[0]["t_ms"] if deltas else None
    first_content = next((e["t_ms"] for e in deltas
                          if e.get("delta_kind") == "content"), None)
    # 28.K.29-A channel split: step narration (channel-less content)
    # vs the final-answer stream (channel=answer)
    first_step_content = next(
        (e["t_ms"] for e in deltas
         if e.get("delta_kind") == "content"
         and e.get("delta_channel") is None), None)
    first_answer = next(
        (e["t_ms"] for e in deltas
         if e.get("delta_channel") == "answer"), None)
    ch_counts: dict = {}
    for e in deltas:
        k = (e.get("delta_kind"), e.get("delta_channel"))
        ch_counts["%s/%s" % k] = ch_counts.get("%s/%s" % k, 0) + 1
    out["server"] = {
        "attach_to_run_started_ms": t_of(run_start),
        "backend_wall_ms": (round(term["t_ms"] - run_start["t_ms"], 1)
                            if term and run_start else None),
        "first_delta_any_ms": first_any_delta,
        "first_content_delta_ms": first_content,
        "first_step_content_ms": first_step_content,
        "first_answer_delta_ms": first_answer,
        "delta_channel_counts": ch_counts,
        "delta_count": len(deltas),
        "spans": spans,
        "span_sum_ms": round(sum(s["dur_ms"] for s in spans), 1),
    }

    # ---- category buckets (EXCLUSIVE durations) ----------------------------
    # tools genuinely nest (e.g. product_candidate_provider internally
    # runs knowledge-search): a parent span's wall time contains its
    # child's. Bucket sums use each span's EXCLUSIVE time (wall minus
    # contained children) so categories never double-count.
    def _exclusive(sp):
        taken = 0.0
        for ch in spans:
            if ch is sp:
                continue
            if (ch["start_ms"] is not None and sp["start_ms"] is not None
                    and sp["start_ms"] <= ch["start_ms"]
                    and ch["end_ms"] is not None
                    and ch["end_ms"] <= sp["end_ms"]
                    and ch["dur_ms"] <= sp["dur_ms"]):
                taken += ch["dur_ms"]
        return max(0.0, sp["dur_ms"] - taken)

    _KNOW = {"knowledge_search", "tool:knowledge_search",
             "knowledge-search", "tool:knowledge-search"}

    def bucket(pred):
        return round(sum(_exclusive(s) for s in spans if pred(s)), 1)
    out["categories"] = {
        "llm_ms": bucket(lambda s: "llm" in s["name"]
                         or s["name"] == "qa_llm_grounding"),
        "knowledge_ms": bucket(lambda s: s["name"] in _KNOW),
        "tools_ms": bucket(lambda s: s["name"].startswith("tool:")
                           and s["name"] not in _KNOW),
        "app_ms": bucket(lambda s: s["name"] in (
            "intent_router", "finalize_transcript")),
    }
    # unattributed = wall − Σ(exclusive) — the honest remainder
    if out["server"]["backend_wall_ms"] is not None:
        _excl_sum = round(sum(_exclusive(s) for s in spans), 1)
        out["categories"]["unattributed_ms"] = round(max(
            0.0, out["server"]["backend_wall_ms"] - _excl_sum), 1)
        out["server"]["exclusive_sum_ms"] = _excl_sum
    else:
        out["categories"]["unattributed_ms"] = None

    # ---- obs join (corroboration: exact gateway/call durations) ----------
    dur_s = (client.get("terminal_ms") or 0) / 1000.0
    obs = _obs_window(client.get("submit_wall"), dur_s)
    out["obs"] = {
        "llm_calls": [{"status": r.get("status"),
                       "duration_ms": r.get("duration_ms"),
                       "provider": r.get("provider"),
                       "purpose": r.get("purpose"),
                       "attempt": r.get("attempt")}
                      for r in obs["llm.call"]],
        "knowledge_searches": [{"status": r.get("status"),
                                "duration_ms": r.get("duration_ms")}
                               for r in obs["knowledge.search"]],
    }

    # ---- client split ------------------------------------------------------
    out["client"] = {k: client.get(k) for k in (
        "ack_ms", "first_event_ms", "first_reasoning_delta_ms",
        "first_content_delta_ms", "terminal_ms", "status",
        "result_status", "stream_events", "stream_deltas")}
    # network + SSE-delivery lag: client terminal - server terminal span
    if client.get("terminal_ms") is not None \
            and out["server"].get("backend_wall_ms") is not None:
        out["client"]["e2e_ms"] = client["terminal_ms"]
        out["client"]["approx_network_overhead_ms"] = round(
            client["terminal_ms"] - out["server"]["backend_wall_ms"]
            - (client.get("ack_ms") or 0), 1)
    return out


def aggregate(runs: list) -> dict:
    """Per-case metric aggregation (honest stats: n=3 -> P95 = max)."""
    by_case: dict = {}
    for r in runs:
        if "error" in r:
            by_case.setdefault(r["case"], []).append(
                {"error": r["error"]})
            continue
        c = r["case"]
        m = {}
        m["e2e_ms"] = (r.get("client") or {}).get("e2e_ms")
        m["ttfc_ms"] = (r.get("client") or {}).get("first_event_ms")
        m["first_content_ms"] = (r.get("client") or {}).get(
            "first_content_delta_ms")
        sv = r.get("server") or {}
        m["first_step_content_ms"] = sv.get("first_step_content_ms")
        m["first_answer_ms"] = sv.get("first_answer_delta_ms")
        m["backend_wall_ms"] = sv.get("backend_wall_ms")
        m["llm_ms"] = (r.get("categories") or {}).get("llm_ms")
        m["knowledge_ms"] = (r.get("categories") or {}).get("knowledge_ms")
        by_case.setdefault(c, []).append(m)
    out = {}
    for case, ms in by_case.items():
        stats = {}
        for key in ("e2e_ms", "ttfc_ms", "first_content_ms",
                    "first_step_content_ms", "first_answer_ms",
                    "backend_wall_ms", "llm_ms", "knowledge_ms"):
            vals = [m[key] for m in ms if isinstance(m.get(key), (int,
                                                                  float))]
            if not vals:
                stats[key] = None
                continue
            stats[key] = {
                "n": len(vals),
                "min": min(vals), "max": max(vals),
                "mean": round(statistics.mean(vals), 1),
                "median": round(statistics.median(vals), 1),
                # with n=3 the P95 IS the max — labelled, not smoothed
                "p95": max(vals) if len(vals) < 20 else round(
                    statistics.quantiles(vals, n=20)[-1], 1),
            }
        stats["errors"] = sum(1 for m in ms if "error" in m)
        out[case] = stats
    return out


def main() -> None:
    client_files = sorted(glob.glob(os.path.join(BENCH, "client_*.json")))
    if not client_files:
        print("no client runs found under %s" % BENCH)
        sys.exit(1)
    runs = []
    for path in client_files:
        runs.append(analyze_run(_load(path)))
    summary = {"runs": runs, "by_case": aggregate(runs)}
    out_path = os.path.join(BENCH, "summary.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)

    for r in runs:
        if "error" in r:
            print("%s: ERROR %s" % (r.get("case"), r["error"]))
            continue
        c, s = r["client"], r["server"]
        print("\n=== %s (%s) status=%s/%s" % (
            r["tag"], r["run_id"], c.get("status"),
            c.get("result_status")))
        print("  client: e2e=%s ack=%s first_event=%s first_content=%s" % (
            c.get("e2e_ms"), c.get("ack_ms"), c.get("first_event_ms"),
            c.get("first_content_ms")))
        print("  server: wall=%s spans_sum=%s exclusive_sum=%s" % (
            s["backend_wall_ms"], s["span_sum_ms"],
            s.get("exclusive_sum_ms")))
        for cat, v in r["categories"].items():
            print("    %-14s %s" % (cat, v))
        top = sorted(s["spans"], key=lambda x: -x["dur_ms"])[:5]
        print("  top spans:")
        for sp in top:
            print("    %-28s %8.1f ms" % (sp["name"], sp["dur_ms"]))
        if r["obs"]["llm_calls"]:
            print("  obs llm.calls: %s" % ", ".join(
                "%s(%sms)" % (x["status"], x["duration_ms"])
                for x in r["obs"]["llm_calls"]))
    print("\nwritten: %s" % out_path)


if __name__ == "__main__":
    main()
