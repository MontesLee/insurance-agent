"""Phase 2.6 — LLM provider layer tests (runtime/agent/model.py).

FakeLLM only: no network, no API key, CI-safe (spec §46/§47).

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_agent_model.py`.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Checks, run_sections  # noqa: E402

from runtime.agent.model import (FakeLLMProvider, OpenAICompatProvider,  # noqa: E402
                                 ProviderNotConfigured, ToolSpec, provider_from_env)

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


@section
def test_provider_from_env(c: Checks):
    base = {"LLM_PROVIDER": "openai", "LLM_MODEL": "gpt-x", "LLM_API_KEY": "sk-test"}
    p = provider_from_env(dict(base))
    c.chk("env: openai provider constructed", p.name == "openai" and p.model == "gpt-x")
    c.chk("env: provider aliases map to openai-compat",
          provider_from_env({"LLM_PROVIDER": "glm", "LLM_MODEL": "glm-4",
                             "LLM_API_KEY": "k", "LLM_BASE_URL": "http://x/v1"}).name == "glm")

    for env in ({}, {"LLM_PROVIDER": "openai"}, {"LLM_PROVIDER": "openai", "LLM_MODEL": "m"}):
        try:
            provider_from_env(env)
            c.chk("env: missing config raises ProviderNotConfigured", False, env)
        except ProviderNotConfigured as e:
            c.chk("env: missing config raises ProviderNotConfigured (%s)" % bool(env),
                  "Demo Mode" in str(e) or "configure" in str(e).lower())
    try:
        provider_from_env({"LLM_PROVIDER": "fake"})
        c.chk("env: fake provider rejected via env", False)
    except ProviderNotConfigured:
        c.chk("env: fake provider rejected via env", True)


@section
def test_fake_provider_scripting(c: Checks):
    fake = FakeLLMProvider([
        ("record_client_profile", {"family_profile": {}}),
        "INVALID:{bad json",
        ("agent_decide", {"action": "finish", "message": "ok"}),
        RuntimeError("boom"),
        "plain text answer",
    ])
    tools = [ToolSpec("agent_decide", "d", {"type": "object"})]

    r1 = fake.generate([{"role": "user", "content": "hi"}], tools)
    c.chk("fake: tool call emitted", r1.tool_calls[0].name == "record_client_profile")
    r2 = fake.generate([], tools)
    c.chk("fake: INVALID marker yields malformed args",
          r2.tool_calls[0].arguments == {"junk": "INVALID:{bad json"})
    r3 = fake.generate([], tools)
    c.chk("fake: scripted decision", r3.tool_calls[0].arguments["action"] == "finish")
    try:
        fake.generate([], tools)
        c.chk("fake: exception passthrough", False)
    except RuntimeError:
        c.chk("fake: exception passthrough", True)
    r5 = fake.generate([], tools)
    c.chk("fake: plain text + exhaustion fallback",
          r5.text == "plain text answer" and fake.generate([], tools).text.startswith("(fake"))


@section
def test_openai_compat_encoding(c: Checks):
    p = OpenAICompatProvider(name="x", model="m", api_key="k", base_url="http://localhost:9/v1")
    m = {"role": "assistant", "content": "",
         "tool_calls": [type("C", (), {"id": "1", "name": "t", "arguments": {"a": 1}})()]}
    enc = p._encode(m)
    c.chk("encode: tool_calls serialized as function json",
          enc["tool_calls"][0]["function"]["name"] == "t"
          and '"a": 1' in enc["tool_calls"][0]["function"]["arguments"])
    c.chk("encode: tool role message",
          p._encode({"role": "tool", "content": "r", "tool_call_id": "1", "name": "t"})
          .get("tool_call_id") == "1")
    c.chk("api key never appears on the provider surface",
          not any("sk-" in str(v) for v in (p.name, p.model, p._base_url)))


def main():
    return run_sections(SECTIONS, "webui_test_agent_model_log.txt", "RUNTIME AGENT MODEL")


if __name__ == "__main__":
    sys.exit(main())
