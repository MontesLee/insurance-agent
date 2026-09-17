"""LLM Provider abstraction (Phase 2.6).

One protocol, pluggable providers. V0.1 ships:

  * OpenAICompatProvider — any OpenAI-compatible /chat/completions endpoint
    (OpenAI / DeepSeek / Qwen / GLM open platform / local vLLM), via env:
        LLM_PROVIDER=openai_compat (or openai/deepseek/qwen/glm — all map here)
        LLM_BASE_URL=https://.../v1        (optional, provider default otherwise)
        LLM_MODEL=...
        LLM_API_KEY=...  (or OPENAI_API_KEY)
  * FakeLLMProvider — deterministic scripted responses for tests/CI (no network).

Rules (spec §12/§26/§42):
  * keys live ONLY in env; never in events/trace/artifacts/logs;
  * the frontend never knows the provider — it stops at FastAPI;
  * usage (tokens/latency/model) is surfaced for observability, prompts are not.
"""
from __future__ import annotations

import json
import os
import time

import httpx
from typing import Any, Optional, Protocol  # noqa: F401 (Any/Optional re-exported)


class ProviderNotConfigured(RuntimeError):
    """Raised when Agent Mode is requested but no LLM provider is configured.

    Callers must fail CLOSED with a clear message — never silently fall back to
    the deterministic demo (spec §41)."""


class ToolSpec:
    def __init__(self, name: str, description: str, parameters: dict):
        self.name = name
        self.description = description
        self.parameters = parameters

    def as_openai(self) -> dict:
        return {"type": "function",
                "function": {"name": self.name, "description": self.description,
                             "parameters": self.parameters}}


class ToolCall:
    def __init__(self, id: str, name: str, arguments: dict):
        self.id = id
        self.name = name
        self.arguments = arguments


class LLMResponse:
    def __init__(self, text: Optional[str], tool_calls: list,
                 usage: Optional[dict] = None, latency_ms: Optional[float] = None):
        self.text = text
        self.tool_calls = tool_calls        # list[ToolCall]
        self.usage = usage or {}            # {input_tokens, output_tokens}
        self.latency_ms = latency_ms


Message = dict  # {"role": system|user|assistant|tool, "content": str,
#                  "tool_calls": [...] (assistant), "tool_call_id": str (tool)}


class LLMProvider(Protocol):
    name: str
    model: str

    def generate(self, messages: list, tools: list) -> LLMResponse:
        ...


# --------------------------------------------------------------------------- #
# env-based construction
# --------------------------------------------------------------------------- #
def provider_from_env(env: Optional[dict] = None) -> LLMProvider:
    """Resolve the provider from the unified config layer.

    env=None → process env merged over <repo root>/.env (real usage);
    env={..} → that mapping only (pure, test-friendly — .env is not read).
    """
    from runtime.agent.config import load_llm_config

    cfg = load_llm_config(env=env, dotenv_path=(None if env is None else False))
    if cfg.provider in ("fake", "mock", "fakellm"):
        raise ProviderNotConfigured(
            "FakeLLMProvider is test-only and cannot be selected via env.")
    return cfg.to_provider()


_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
}


# --------------------------------------------------------------------------- #
# OpenAI-compatible provider (httpx — no SDK dependency)
# --------------------------------------------------------------------------- #
class OpenAICompatProvider:
    def __init__(self, name: str, model: str, api_key: str, base_url: str = "",
                 timeout: float = 60.0):
        self.name = name
        self.model = model
        self._api_key = api_key
        self._base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self._timeout = timeout

    def generate(self, messages: list, tools: list) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "messages": [self._encode(m) for m in messages],
        }
        if tools:
            payload["tools"] = [t.as_openai() if isinstance(t, ToolSpec) else t
                                for t in tools]
            payload["tool_choice"] = "auto"
        t0 = time.perf_counter()
        resp = httpx.post(
            "%s/chat/completions" % self._base_url,
            headers={"Authorization": "Bearer %s" % self._api_key,
                     "Content-Type": "application/json"},
            json=payload, timeout=self._timeout)
        latency = round((time.perf_counter() - t0) * 1000.0, 1)
        if resp.status_code != 200:
            from runtime.agent.config import redact_secrets
            raise RuntimeError("LLM provider error %s: %s" % (
                resp.status_code,
                redact_secrets(resp.text[:200], extra_secrets=(self._api_key,))))
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        calls = []
        for c in msg.get("tool_calls") or []:
            fn = c.get("function") or {}
            args = fn.get("arguments")
            try:
                args = json.loads(args) if isinstance(args, str) else (args or {})
            except json.JSONDecodeError:
                args = {"__raw__": str(args)[:200]}   # surfaced as schema-invalid
            calls.append(ToolCall(id=c.get("id") or "", name=fn.get("name") or "",
                                  arguments=args))
        usage = data.get("usage") or {}
        return LLMResponse(
            text=msg.get("content"),
            tool_calls=calls,
            usage={"input_tokens": usage.get("prompt_tokens"),
                   "output_tokens": usage.get("completion_tokens")},
            latency_ms=latency)

    def stream_generate(self, messages: list, tools: list):
        """Streaming variant: yields {"type": "delta", "kind": "reasoning"|"content",
        "text": str} chunks, then returns an assembled LLMResponse (OpenAI SSE).

        GLM's OpenAI-compatible endpoint streams `reasoning_content` (thinking)
        and `content` deltas plus fragmented tool_calls — all handled here."""
        payload: dict = {
            "model": self.model,
            "messages": [self._encode(m) for m in messages],
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            payload["tools"] = [t.as_openai() if isinstance(t, ToolSpec) else t
                                for t in tools]
            payload["tool_choice"] = "auto"

        text_parts: list = []
        reasoning_parts: list = []
        calls: dict = {}          # index -> {id, name, args_str}
        usage: dict = {}
        t0 = time.perf_counter()

        with httpx.stream("POST", "%s/chat/completions" % self._base_url,
                          headers={"Authorization": "Bearer %s" % self._api_key,
                                   "Content-Type": "application/json"},
                          json=payload, timeout=self._timeout) as resp:
            if resp.status_code != 200:
                body = resp.read().decode("utf-8", "replace")[:200]
                from runtime.agent.config import redact_secrets
                raise RuntimeError("LLM provider error %s: %s" % (
                    resp.status_code, redact_secrets(body, extra_secrets=(self._api_key,))))
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                usage.update(chunk.get("usage") or {})
                delta = ((chunk.get("choices") or [{}])[0]).get("delta") or {}
                rc = delta.get("reasoning_content")
                if rc:
                    reasoning_parts.append(rc)
                    yield {"type": "delta", "kind": "reasoning", "text": rc}
                c = delta.get("content")
                if c:
                    text_parts.append(c)
                    yield {"type": "delta", "kind": "content", "text": c}
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    slot = calls.setdefault(idx, {"id": "", "name": "", "args": ""})
                    fn = tc.get("function") or {}
                    slot["id"] += tc.get("id") or ""
                    slot["name"] += fn.get("name") or ""
                    slot["args"] += fn.get("arguments") or ""

        parsed_calls = []
        for idx in sorted(calls):
            slot = calls[idx]
            try:
                args = json.loads(slot["args"] or "{}")
            except json.JSONDecodeError:
                args = {"__raw__": slot["args"][:200]}
            parsed_calls.append(ToolCall(id=slot["id"], name=slot["name"], arguments=args))
        return LLMResponse(
            text="".join(text_parts) or None,
            tool_calls=parsed_calls,
            usage={"input_tokens": usage.get("prompt_tokens"),
                   "output_tokens": usage.get("completion_tokens")},
            latency_ms=round((time.perf_counter() - t0) * 1000.0, 1))

    @staticmethod
    def _encode(m: Message) -> dict:
        out: dict = {"role": m["role"], "content": m.get("content") or ""}
        if m.get("tool_calls"):
            out["tool_calls"] = [{
                "id": c.id, "type": "function",
                "function": {"name": c.name,
                             "arguments": json.dumps(c.arguments, ensure_ascii=False)},
            } for c in m["tool_calls"]]
        if m.get("tool_call_id"):
            out["tool_call_id"] = m["tool_call_id"]
        if m.get("name"):
            out["name"] = m["name"]
        return out


# --------------------------------------------------------------------------- #
# Fake provider for tests / CI (spec §47) — deterministic, no network
# --------------------------------------------------------------------------- #
class FakeLLMProvider:
    """Scripted responses consumed in order.

    script: list of items —
      * str            -> plain text reply (no tool call)
      * (name, args)   -> one tool call
      * "INVALID:<junk>" -> malformed tool call (arguments fail schema)
      * Exception      -> raised (provider error path)
    """

    def __init__(self, script: list, model: str = "fake-model"):
        self.name = "fake"
        self.model = model
        self._script = list(script)
        self.calls: list = []          # (messages_snapshot_names, tools) per turn

    def generate(self, messages: list, tools: list) -> LLMResponse:
        self.calls.append(([m.get("role") for m in messages], [t.name for t in tools]))
        if not self._script:
            return LLMResponse(text="(fake provider exhausted)", tool_calls=[])
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str) and item.startswith("INVALID:"):
            return LLMResponse(text=None, tool_calls=[ToolCall(
                id="fake%d" % len(self.calls), name="agent_decide",
                arguments={"junk": item})])
        if isinstance(item, tuple):
            name, args = item
            return LLMResponse(text=None, tool_calls=[ToolCall(
                id="fake%d" % len(self.calls), name=name, arguments=dict(args))])
        return LLMResponse(text=item, tool_calls=[],
                           usage={"input_tokens": 10, "output_tokens": 5})

    def stream_generate(self, messages: list, tools: list):
        """Streaming for tests: plain-text replies yield a few deltas (so delta
        plumbing is exercised); tool-call / malformed replies stream nothing
        (matching providers that stream reasoning/content only before tool calls)."""
        self.calls.append(([m.get("role") for m in messages], [t.name for t in tools]))
        if not self._script:
            return LLMResponse(text="(fake provider exhausted)", tool_calls=[])
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, tuple):
            name, args = item
            return LLMResponse(text=None, tool_calls=[ToolCall(
                id="fake%d" % len(self.calls), name=name, arguments=dict(args))])
        if isinstance(item, str) and item.startswith("INVALID:"):
            return LLMResponse(text=None, tool_calls=[ToolCall(
                id="fake%d" % len(self.calls), name="agent_decide",
                arguments={"junk": item})])
        text = str(item)
        for i in range(0, len(text), 24):
            yield {"type": "delta", "kind": "content", "text": text[i:i + 24]}
        return LLMResponse(text=text, tool_calls=[],
                           usage={"input_tokens": 10, "output_tokens": 5})
