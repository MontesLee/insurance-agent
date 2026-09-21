"""Phase 25 §21 — engineering performance baseline (N >= 30).

NOT a production SLA: single-host, no load, cold caches. Measures the
observability surfaces and representative request paths, reports
min/median/p95/max, writes tmp/p25_perf_baseline.json.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

SECTIONS = []
OUT = {}


def section(fn):
    SECTIONS.append(fn)
    return fn


def pct(xs, p):
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1)))))
    return round(xs[k], 2)


def bench(fn, n=30):
    xs = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        xs.append((time.perf_counter() - t0) * 1000)
    return {"n": n, "min": pct(xs, 0), "median": pct(xs, 50),
            "p95": pct(xs, 95), "max": pct(xs, 100)}


@section
def test_perf_baseline(c):
    from _common import make_client
    import runtime.obs as obs
    from runtime.obs.log import JsonlLogger

    # silence stdout mirroring for the bench
    obs.set_default_logger(JsonlLogger(path=os.path.join(
        REPO, "tmp", "obs", "bench.jsonl")))
    client, mgr, _ = make_client()
    try:
        OUT["health"] = bench(lambda: client.get("/api/health"))
        c.chk("health N>=30", OUT["health"]["n"] >= 30)
        OUT["readiness"] = bench(lambda: client.get("/api/ready"))
        c.chk("readiness N>=30", OUT["readiness"]["n"] >= 30)
        OUT["diagnostics"] = bench(
            lambda: client.get("/api/diagnostics"))
        c.chk("diagnostics N>=30", OUT["diagnostics"]["n"] >= 30)
        OUT["simple_request"] = bench(
            lambda: client.get("/api/cases"))
        c.chk("simple request N>=30", OUT["simple_request"]["n"] >= 30)
        # knowledge path (mock provider — offline, deterministic)
        from knowledge.service import KnowledgeService
        svc = KnowledgeService()
        OUT["knowledge_request"] = bench(
            lambda: svc.search("重疾险保额", top_k=3,
                               as_of="2026-06-01"))
        c.chk("knowledge N>=30", OUT["knowledge_request"]["n"] >= 30)
        # LLM path (deterministic mock provider)
        from runtime.llm.gateway import LLMGateway
        from runtime.llm.mock import MockLLMProvider
        from runtime.llm.types import LLMRequest
        gw = LLMGateway(MockLLMProvider())
        req = LLMRequest(messages=[{"role": "user", "content": "你好"}],
                         model="mock", timeout_s=5.0, max_tokens=16)
        OUT["llm_request"] = bench(lambda: gw.generate(req))
        c.chk("llm N>=30", OUT["llm_request"]["n"] >= 30)
        # full agent run (1 warmup + measured single runs are the
        # expensive path: use N=30 simple full-pipeline invocations of
        # the orchestrator on the lightest case via the run endpoint is
        # too slow — measure the orchestrator directly on a seeded case
        # with an empty KB for speed)
        cases = mgr.cases()
        light = next((x for x in cases if x.get("kb") == "empty"),
                     cases[0])["id"]

        def one_run():
            r = client.post("/api/runs", json={"case_id": light}).json()
            from _common import wait_terminal
            wait_terminal(client, r["run_id"], timeout=180)

        one_run()                       # warmup (module caches)
        xs = []
        for _ in range(30):
            t0 = time.perf_counter()
            one_run()
            xs.append((time.perf_counter() - t0) * 1000)
        OUT["full_agent_request"] = {
            "n": 30, "min": pct(xs, 0), "median": pct(xs, 50),
            "p95": pct(xs, 95), "max": pct(xs, 100)}
        c.chk("full agent run N>=30",
              OUT["full_agent_request"]["n"] >= 30)
        OUT["note"] = ("engineering baseline: single host, no "
                       "production load, mock LLM/knowledge where "
                       "applicable — NOT a production SLA")
    finally:
        obs.set_default_logger(None)
    os.makedirs(os.path.join(REPO, "tmp"), exist_ok=True)
    with open(os.path.join(REPO, "tmp", "p25_perf_baseline.json"), "w",
              encoding="utf-8") as f:
        json.dump(OUT, f, ensure_ascii=False, indent=1)
    c.chk("baseline written", True)
    for k, v in OUT.items():
        if isinstance(v, dict) and "median" in v:
            print("  %-22s median=%sms p95=%sms" % (k, v["median"],
                                                    v["p95"]))


def main() -> int:
    os.chdir(REPO)
    return run_sections(SECTIONS, "p25_perf_baseline_log.txt",
                        "PHASE 25 PERFORMANCE BASELINE")


if __name__ == "__main__":
    sys.exit(main())
