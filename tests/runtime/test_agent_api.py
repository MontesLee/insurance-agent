"""Phase 2.6 — Agent Chat API tests (runtime/server.py Mode B endpoints).

FakeLLM behind the real FastAPI stack: POST /api/chats[/{id}/messages[/stream]],
GET /api/chats/{id}, run/SSE/artifact endpoints REUSED for agent runs, 503 when
no provider is configured (never a silent demo fallback), 409 chat_busy, and
the §28 "test" regression.

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_agent_api.py`.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Checks, make_client, run_sections, stream_events, wait_terminal  # noqa: E402

from runtime.agent import FakeLLMProvider  # noqa: E402

SECTIONS = []

ASK = ("agent_decide", {"action": "ask_user", "reason": "insufficient_client_information",
                        "required_fields": ["age", "health", "goal", "budget"],
                        "message": "先告诉我：1) 为谁配置 2) 年龄 3) 想解决的问题 4) 预算"})


def section(fn):
    SECTIONS.append(fn)
    return fn


def _client(script):
    client, mgr, bus = make_client()
    mgr.agent_provider = FakeLLMProvider(script)
    return client, mgr, bus


def _wait(client, rid):
    return wait_terminal(client, rid)


@section
def test_config_and_503_when_not_configured(c: Checks):
    client, mgr, _ = make_client()   # NO injected provider, env clean?
    os.environ.pop("LLM_PROVIDER", None)
    os.environ.pop("LLM_API_KEY", None)
    cfg = client.get("/api/agent/config").json()
    c.chk("config: reports unconfigured cleanly",
          cfg["configured"] is False and cfg["provider"] is None, cfg)

    r = client.post("/api/chats/chat_x/messages", json={"text": "test"})
    c.chk("send without provider -> 503 with llm_provider_not_configured",
          r.status_code == 503 and r.json()["detail"]["error"] == "llm_provider_not_configured",
          r.status_code)
    c.chk("503 message tells the user to configure or switch to Demo Mode",
          "Demo Mode" in r.json()["detail"]["message"])
    c.chk("no run was created on 503 (fail closed, no silent fallback)",
          client.get("/api/runs").status_code in (404, 405)
          or mgr.bus.stats()["runs"] == 0)


@section
def test_chat_lifecycle_and_test_input_regression(c: Checks):
    client, mgr, _ = _client([ASK])
    created = client.post("/api/chats")
    c.chk("POST /api/chats creates a chat", created.status_code == 201
          and created.json()["chat_id"].startswith("chat_"))
    chat_id = created.json()["chat_id"]

    r = client.post("/api/chats/%s/messages" % chat_id, json={"text": "test"})
    body = r.json()
    c.chk("message -> run started", r.status_code == 200 and body["run_id"].startswith("run_"),
          body)
    rid = body["run_id"]

    run = _wait(client, rid)
    c.chk("'test' ends waiting (asks the user), NOT a report",
          run["status"] == "waiting", run["status"])
    chat = client.get("/api/chats/%s" % chat_id).json()
    c.chk("chat holds user + assistant ask message",
          [m["role"] for m in chat["messages"]] == ["user", "assistant"]
          and "1" in chat["messages"][1]["content"] and "2" in chat["messages"][1]["content"])
    c.chk("chat links the run", chat["runs"] == [rid])

    arts = client.get("/api/runs/%s/artifacts" % rid).json()["artifacts"]
    c.chk("NO artifacts were produced for 'test' (no demo seeding, no pipeline)",
          arts == [], arts)
    evs = client.get("/api/runs/%s/events" % rid).json()["events"]
    c.chk("agent events streamed through the RUN endpoints",
          [e["event_type"] for e in evs][0] == "run_started"
          and "agent_step_started" in [e["event_type"] for e in evs])


@section
def test_sse_stream_for_agent_run(c: Checks):
    client, mgr, _ = _client([
        ("knowledge_search", {"query": "百万医疗险 重疾险 区别"}),
        ("agent_decide", {"action": "finish", "message": "依据知识库证据回答完毕。"}),
    ])
    rid = client.post("/api/chats/chat_sse/messages",
                      json={"text": "百万医疗险和重疾险有什么区别？"}).json()["run_id"]
    evs = stream_events(client, "/api/runs/%s/stream" % rid)
    types = [e["event_type"] for e in evs]
    c.chk("agent run streams over the EXISTING SSE endpoint",
          types[0] == "run_started" and types[-1] == "run_completed")
    c.chk("stream shows understanding -> tool -> decision",
          "agent_step_started" in types and "tool_started" in types
          and "agent_decision" in types)
    ids = [e["event_id"] for e in evs]
    c.chk("event ids contiguous for the agent run",
          ids == ["evt_%06d" % i for i in range(1, len(evs) + 1)])


@section
def test_full_agent_chain_via_api(c: Checks):
    profile = {"family_profile": {"age": {"value": 4}},
               "financial_profile": {"budget": {"value": "1万/年"}},
               "existing_protection": {"existing_insurance": {"value": "无"}}}
    script = [
        ("agent_decide", {"action": "call_tool", "tool": "record_client_profile",
                          "arguments": profile}),
        ("agent_decide", {"action": "call_tool", "tool": "record_requirement_analysis",
                          "arguments": {"requirements": [
                              {"requirement_id": "R", "requirement_type": "medical",
                               "summary": "住院医疗", "priority": "P1_HIGH"}]}}),
        ("agent_decide", {"action": "call_tool", "tool": "record_risk_assessment",
                          "arguments": {"risks": [
                              {"risk_id": "R1", "risk_category": "R1_medical",
                               "risk_name": "住院费用", "priority": "P1_HIGH"}]}}),
        ("coverage_gap_analysis", {}), ("solution", {}),
        ("product_candidate_provider", {}), ("recommendation", {}),
        ("report_generation", {}),
        ("agent_decide", {"action": "finish", "message": "分析完成，报告已生成。"}),
    ]
    client, mgr, _ = _client(script)
    rid = client.post("/api/chats/chat_full/messages",
                      json={"text": "给4岁孩子买保险，预算1万，担心住院。"}).json()["run_id"]
    run = _wait(client, rid)
    c.chk("full agent chain completes", run["status"] == "completed", run["status"])

    arts = client.get("/api/runs/%s/artifacts" % rid).json()["artifacts"]
    types_ = sorted(a["artifact_type"] for a in arts)
    c.chk("9 canonical artifacts via the EXISTING artifacts endpoint",
          len(types_) == 9 and "insurance-report" in types_, types_)
    rep = client.get("/api/runs/%s/artifacts/insurance-report" % rid).json()
    c.chk("report is the runtime's own artifact (markdown present)",
          rep["artifact"]["payload"].get("status") == "success"
          and len(rep["artifact"]["payload"].get("rendered_report", "")) > 500)

    chat = client.get("/api/chats/chat_full").json()
    c.chk("assistant final reply attached to the chat with run linkage",
          chat["messages"][-1]["role"] == "assistant"
          and chat["messages"][-1]["run_id"] == rid)

    evs = client.get("/api/runs/%s/events" % rid).json()["events"]
    blob = json.dumps(evs, ensure_ascii=False).lower()
    import re
    # NB: 'sk-' alone matches 'risk-assessment' — match real key SHAPES instead
    c.chk("event hygiene: no key material / no prompts",
          all(k not in blob for k in ("api_key", "authorization", "system prompt"))
          and re.search(r"sk-[a-z0-9_-]{16,}", blob) is None
          and re.search(r"bearer\s+[a-z0-9._-]{16,}", blob) is None)


@section
def test_chat_busy_409(c: Checks):
    slow = [("agent_decide", {"action": "ask_user", "message": "请补充信息",
                              "required_fields": ["age"], "reason": "r"})]
    client, mgr, _ = _client(slow + slow)  # two turns available
    r1 = client.post("/api/chats/chat_busy/messages", json={"text": "hi"})
    rid1 = r1.json()["run_id"]
    r2 = client.post("/api/chats/chat_busy/messages", json={"text": "again"})
    c.chk("second message while running -> 409 chat_busy with the active run",
          r2.status_code == 409 and r2.json()["error"] == "chat_busy"
          and r2.json()["run_id"] == rid1, (r2.status_code, r2.json()))
    _wait(client, rid1)
    r3 = client.post("/api/chats/chat_busy/messages", json={"text": "after finish"})
    c.chk("after the turn ends the chat accepts the next message",
          r3.status_code == 200, r3.status_code)
    _wait(client, r3.json()["run_id"])


@section
def test_demo_mode_untouched(c: Checks):
    client, mgr, _ = _client([])
    r = client.post("/api/runs", json={"case_id": "bm-complete-001"})
    c.chk("deterministic Mode A still runs alongside agent mode",
          r.status_code == 201, r.status_code)
    run = wait_terminal(client, r.json()["run_id"])
    c.chk("Mode A completes as before", run["status"] == "completed", run["status"])


def main():
    return run_sections(SECTIONS, "webui_test_agent_api_log.txt", "RUNTIME AGENT API")


if __name__ == "__main__":
    sys.exit(main())
