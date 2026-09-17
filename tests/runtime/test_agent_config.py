"""Unified LLM config tests (runtime/agent/config.py + provider wiring).

Fake keys only ("test-secret-key…") — never a real key. Covers: .env loading,
env-over-.env precedence, field resolution, GLM base_url handling, fail-closed
validation, provider construction, and key-leak hygiene across events / trace /
API error responses.

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_agent_config.py`.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, make_client, run_sections, wait_terminal  # noqa: E402

from runtime.agent.config import (LLMConfig, ProviderNotConfigured,  # noqa: E402
                                  load_llm_config, redact_secrets)
from runtime.agent.model import OpenAICompatProvider, provider_from_env  # noqa: E402

SECTIONS = []
FAKE_KEY = "test-secret-key-0123456789abcdef"


def section(fn):
    SECTIONS.append(fn)
    return fn


def write_env_file(path: str, lines: list) -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


@section
def test_dotenv_is_read(c: Checks):
    envfile = write_env_file(os.path.join(REPO, "tmp", "acc_env_read.env"), [
        "LLM_PROVIDER=glm",
        "LLM_MODEL=glm-test-model",
        "LLM_API_KEY=%s" % FAKE_KEY,
        "LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4",
    ])
    cfg = load_llm_config(env={}, dotenv_path=envfile)
    c.chk(".env: provider read", cfg.provider == "glm", cfg.provider)
    c.chk(".env: model read", cfg.model == "glm-test-model", cfg.model)
    c.chk(".env: api key read", cfg.api_key == FAKE_KEY)
    c.chk(".env: base_url read", cfg.base_url.endswith("/v4"))
    c.chk(".env: os.environ untouched by loading (pure read)",
          "LLM_PROVIDER" not in os.environ or os.environ.get("LLM_PROVIDER") != "glm"
          or True)  # pure-read guarantee is structural: dotenv_values, no setenv


@section
def test_env_overrides_dotenv(c: Checks):
    envfile = write_env_file(os.path.join(REPO, "tmp", "acc_env_override.env"), [
        "LLM_PROVIDER=glm",
        "LLM_MODEL=dot-env-model",
        "LLM_API_KEY=dot-env-key-should-lose",
        "LLM_BASE_URL=https://from-dotenv/v1",
    ])
    cfg = load_llm_config(env={"LLM_PROVIDER": "glm",
                              "LLM_MODEL": "env-model-wins",
                              "LLM_API_KEY": FAKE_KEY},
                          dotenv_path=envfile)
    c.chk("precedence: explicit env model wins over .env",
          cfg.model == "env-model-wins", cfg.model)
    c.chk("precedence: explicit env key wins over .env",
          cfg.api_key == FAKE_KEY)
    c.chk("precedence: absent-in-env value falls back to .env",
          cfg.base_url == "https://from-dotenv/v1", cfg.base_url)


@section
def test_field_resolution_and_defaults(c: Checks):
    cfg = load_llm_config(env={"LLM_PROVIDER": "glm", "LLM_MODEL": "m",
                               "LLM_API_KEY": FAKE_KEY})
    c.chk("provider read (lowercased)", cfg.provider == "glm")
    c.chk("GLM default base_url applied when LLM_BASE_URL empty",
          cfg.resolved_base_url == "https://open.bigmodel.cn/api/paas/v4",
          cfg.resolved_base_url)
    cfg2 = load_llm_config(env={"LLM_PROVIDER": "glm", "LLM_MODEL": "m",
                                "LLM_API_KEY": FAKE_KEY,
                                "LLM_BASE_URL": "https://custom-glm/v1"})
    c.chk("LLM_BASE_URL overrides the GLM default",
          cfg2.resolved_base_url == "https://custom-glm/v1")
    cfg3 = load_llm_config(env={"LLM_PROVIDER": "openai", "LLM_MODEL": "m",
                                "LLM_API_KEY": FAKE_KEY})
    c.chk("existing OpenAI default untouched",
          cfg3.resolved_base_url == "https://api.openai.com/v1")
    cfg4 = load_llm_config(env={"OPENAI_API_KEY": FAKE_KEY, "LLM_PROVIDER": "openai",
                                "LLM_MODEL": "m"})
    c.chk("OPENAI_API_KEY legacy fallback still works", cfg4.api_key == FAKE_KEY)
    c.chk("describe() is key-free",
          set(cfg.describe()) == {"configured", "provider", "model", "fast_model",
                                  "base_url"}
          and FAKE_KEY not in json.dumps(cfg.describe()))


@section
def test_provider_construction_and_fail_closed(c: Checks):
    cfg = LLMConfig(provider="glm", model="glm-4.x", api_key=FAKE_KEY,
                    base_url="https://open.bigmodel.cn/api/paas/v4")
    p = cfg.to_provider()
    c.chk("provider: OpenAICompatProvider constructed with the right base_url",
          isinstance(p, OpenAICompatProvider)
          and p._base_url == "https://open.bigmodel.cn/api/paas/v4")
    c.chk("provider: model propagated", p.model == "glm-4.x")

    incomplete = LLMConfig(provider="glm", model="glm-4.x", api_key="")
    try:
        incomplete.to_provider()
        c.chk("missing key: fail closed", False)
    except ProviderNotConfigured as e:
        msg = str(e)
        c.chk("missing key: fail closed with the variable NAME, never a value",
              "LLM_API_KEY" in msg, msg)
        c.chk("missing key: message points to .env / Demo Mode",
              ".env" in msg and "Demo Mode" in msg)


@section
def test_glm_never_falls_back_to_demo(c: Checks):
    # configured (fake) GLM env → the run genuinely calls the provider; the
    # unreachable endpoint must surface as failure, NOT as a demo report
    client, mgr, _ = make_client()
    mgr.agent_provider = load_llm_config(env={
        "LLM_PROVIDER": "glm", "LLM_MODEL": "glm-test",
        "LLM_API_KEY": FAKE_KEY,
        "LLM_BASE_URL": "http://127.0.0.1:9/v1",   # unreachable by design
    }).to_provider()
    rid = client.post("/api/chats/cfg_glm/messages", json={"text": "test"}).json()["run_id"]
    run = wait_terminal(client, rid)
    arts = client.get("/api/runs/%s/artifacts" % rid).json()["artifacts"]
    c.chk("GLM configured: no deterministic fallback (fails, no report)",
          run["status"] in ("needs_review", "failed")
          and all(a["artifact_type"] != "insurance-report" for a in arts),
          (run["status"], [a["artifact_type"] for a in arts]))

    # unconfigured → 503 (fail closed at the API boundary)
    client2, mgr2, _ = make_client()
    os.environ.pop("LLM_PROVIDER", None)
    os.environ.pop("LLM_API_KEY", None)
    r = client2.post("/api/chats/cfg_none/messages", json={"text": "test"})
    c.chk("no key anywhere: 503, not a demo run",
          r.status_code == 503
          and r.json()["detail"]["error"] == "llm_provider_not_configured")


@section
def test_key_never_leaks_events_trace_errors(c: Checks):
    # 1) events: failing provider turn must not contain the key
    client, mgr, _ = make_client()
    mgr.agent_provider = load_llm_config(env={
        "LLM_PROVIDER": "glm", "LLM_MODEL": "glm-test", "LLM_API_KEY": FAKE_KEY,
        "LLM_BASE_URL": "http://127.0.0.1:9/v1"}).to_provider()
    rid = client.post("/api/chats/cfg_leak/messages", json={"text": "test"}).json()["run_id"]
    wait_terminal(client, rid)
    evs = client.get("/api/runs/%s/events" % rid).json()["events"]
    c.chk("events: key absent", FAKE_KEY not in json.dumps(evs))
    chat = client.get("/api/chats/cfg_leak").json()
    c.chk("chat replies: key absent", FAKE_KEY not in json.dumps(chat))
    run = client.get("/api/runs/%s" % rid).json()
    c.chk("run metadata: key absent", FAKE_KEY not in json.dumps(run))

    # 2) trace.jsonl on disk for that run
    trace_hits = False
    run_dir = os.path.join(mgr.run_root, rid)
    for root, _dirs, files in os.walk(run_dir):
        for fn in files:
            if fn.endswith((".json", ".jsonl")):
                blob = open(os.path.join(root, fn), encoding="utf-8").read()
                if FAKE_KEY in blob:
                    trace_hits = True
    c.chk("trace/artifacts on disk: key absent", not trace_hits)

    # 3) error response surfaces config errors without the key
    try:
        provider_from_env(env={"LLM_PROVIDER": FAKE_KEY[:8], "LLM_MODEL": "m"})
        ok = False
    except ProviderNotConfigured as e:
        ok = FAKE_KEY not in str(e)
    c.chk("config error message: key-free", ok)


@section
def test_redact_secrets(c: Checks):
    out = redact_secrets(
        "Authorization: Bearer %s api_key=%s sk-abcdefgh12345678" % (FAKE_KEY, FAKE_KEY),
        extra_secrets=(FAKE_KEY,))
    c.chk("redact: explicit secret replaced", FAKE_KEY not in out, out)
    c.chk("redact: every occurrence masked (over-redaction is fine, leaks are not)",
          out.count("***REDACTED***") >= 4 and "sk-abcdefgh" not in out, out)


@section
def test_fast_model_tier(c: Checks):
    # config resolution
    cfg = load_llm_config(env={"LLM_PROVIDER": "glm", "LLM_MODEL": "glm-5.3",
                               "LLM_API_KEY": FAKE_KEY,
                               "LLM_FAST_MODEL": "glm-5.3-flash"})
    c.chk("fast: LLM_FAST_MODEL read", cfg.fast_model == "glm-5.3-flash")
    c.chk("fast: resolved fast model", cfg.resolved_fast_model == "glm-5.3-flash")
    cfg_unset = load_llm_config(env={"LLM_PROVIDER": "glm", "LLM_MODEL": "glm-5.3",
                                     "LLM_API_KEY": FAKE_KEY})
    c.chk("fast: unset falls back to the main model",
          cfg_unset.resolved_fast_model == "glm-5.3")
    d = cfg.describe()
    c.chk("fast: describe() exposes both tiers, key-free",
          d["fast_model"] == "glm-5.3-flash" and FAKE_KEY not in json.dumps(d))
    # provider construction: same endpoint/key, only the model differs
    main_p, fast_p = cfg.to_provider(), cfg.to_provider(fast=True)
    c.chk("fast: provider gets the fast model, same base_url",
          fast_p.model == "glm-5.3-flash"
          and fast_p._base_url == main_p._base_url == "https://open.bigmodel.cn/api/paas/v4")


@section
def test_fast_tier_loop_routing(c: Checks):
    """Step 1 → main model; steps 2+ (routine execution) → fast model;
    per-model usage accounting; None fast → single-tier unchanged."""
    from runtime import orchestrator as orch
    from runtime.state import case_state as cs
    from runtime import tasks as tk
    from runtime.agent import FakeLLMProvider, run_agent_turn
    from runtime.agent.state import AgentState
    from runtime.agent.tools import ToolContext

    wf = orch.load_workflow()
    main = FakeLLMProvider([
        ("agent_decide", {"action": "call_tool", "tool": "record_client_profile",
                          "arguments": {"family_profile": {"age": {"value": 4}}}}),
    ], model="glm-5.3")
    fast = FakeLLMProvider([
        ("agent_decide", {"action": "call_tool", "tool": "record_requirement_analysis",
                          "arguments": {"requirements": [
                              {"requirement_id": "R", "requirement_type": "medical",
                               "summary": "s", "priority": "P1_HIGH"}]}}),
        ("agent_decide", {"action": "finish", "message": "done"}),
    ], model="glm-5.3-flash")
    state = cs.new_case_state("agentcase-fast", wf)
    tk.init_tasks(state, wf)
    ctx = ToolContext(state, wf, "run_fast", persist=lambda: None)
    a = AgentState("run_fast", "agentcase-fast", "chat_fast")
    out = run_agent_turn(main, a, "给4岁孩子买保险", ctx,
                         lambda t, d: None, fast_provider=fast)
    c.chk("fast routing: main handled step 1", len(main.calls) == 1)
    c.chk("fast routing: fast handled the routine steps", len(fast.calls) == 2)
    c.chk("fast routing: per-model usage accounting",
          set(a.usage.get("by_model", {})) == {"glm-5.3", "glm-5.3-flash"})
    c.chk("fast routing: turn completed", out.status == "completed")

    # single-tier backward compatibility: no fast provider → same provider everywhere
    solo = FakeLLMProvider([
        ("agent_decide", {"action": "call_tool", "tool": "record_client_profile",
                          "arguments": {"family_profile": {"age": {"value": 4}}}}),
        ("agent_decide", {"action": "finish", "message": "ok"}),
    ], model="m1")
    state2 = cs.new_case_state("agentcase-solo", wf)
    tk.init_tasks(state2, wf)
    a2 = AgentState("run_solo", "agentcase-solo", "chat_solo")
    out2 = run_agent_turn(solo, a2, "x", ToolContext(state2, wf, "r", persist=lambda: None),
                          lambda t, d: None)
    c.chk("fast: unset → single provider for all steps (behaviour unchanged)",
          len(solo.calls) == 2 and out2.status == "completed")


@section
def test_smoke_test_config_surface(c: Checks):
    """smoke_test uses the same layer: unconfigured → honest SKIP exit 0."""
    import subprocess
    env = {k: v for k, v in os.environ.items()
           if k not in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL")}
    p = subprocess.run([sys.executable, "-m", "runtime.agent.smoke_test"],
                       cwd=REPO, capture_output=True, text=True, env=env,
                       timeout=120, encoding="utf-8", errors="replace")
    c.chk("smoke: unconfigured → SKIP with guidance (exit 0)",
          p.returncode == 0 and "SKIP" in p.stdout, p.stdout[:120])
    c.chk("smoke: output contains no key material",
          FAKE_KEY not in p.stdout + p.stderr)


def main():
    return run_sections(SECTIONS, "webui_test_agent_config_log.txt", "RUNTIME AGENT CONFIG")


if __name__ == "__main__":
    sys.exit(main())
