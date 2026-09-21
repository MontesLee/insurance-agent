"""GLM Provider Adapter — Phase 23.5 (F-28 fix).

Wraps the existing OpenAICompatProvider, correctly parsing usage
tokens from the real GLM response (prompt_tokens/completion_tokens/
total_tokens are present in GLM's OpenAI-compatible response).
"""
from __future__ import annotations

import os
import time

from .types import (
    LLMProvider, LLMRequest, LLMResponse, LLMUsage, LLMCost,
    UNKNOWN)


class GLMProvider(LLMProvider):
    """Real GLM (智谱 AI) provider via OpenAI-compatible endpoint.
    Parses actual usage from the provider response."""

    name = "glm"

    def __init__(self, model: str = "", api_key: str = "",
                 base_url: str = ""):
        from runtime.agent.model import OpenAICompatProvider
        self._model = model or os.environ.get("LLM_MODEL",
                                              "glm-4-flash")
        self._inner = OpenAICompatProvider(
            name="glm",
            model=self._model,
            api_key=api_key or os.environ.get("LLM_API_KEY", ""),
            base_url=base_url or os.environ.get(
                "LLM_BASE_URL",
                "https://open.bigmodel.cn/api/paas/v4"))

    def generate(self, request: LLMRequest) -> LLMResponse:
        msgs = [{"role": m["role"], "content": m["content"]}
                for m in request.messages]
        if request.system_prompt:
            msgs = [{"role": "system",
                     "content": request.system_prompt}] + msgs
        t0 = time.perf_counter()
        # model.py already parses usage into LLMResponse.usage
        inner = self._inner.generate(msgs, tools=request.tools or [])
        latency = round((time.perf_counter() - t0) * 1000)
        # extract real usage (F-28: model.py puts it in
        # usage={"input_tokens": ..., "output_tokens": ...})
        u = inner.usage or {}
        pt = u.get("input_tokens", UNKNOWN)
        ct = u.get("output_tokens", UNKNOWN)
        tt = (pt + ct if isinstance(pt, int) and isinstance(ct, int)
              else UNKNOWN)
        return LLMResponse(
            request_id=request.request_id,
            provider=self.name,
            model=self._model,
            content=inner.text,
            finish_reason="stop",
            usage=LLMUsage(prompt_tokens=pt, completion_tokens=ct,
                           total_tokens=tt),
            cost=LLMCost(),  # cost stays UNKNOWN without pricing
            latency_ms=latency,
            response_id="glm_resp",
            tool_calls=[c.__dict__ if hasattr(c, "__dict__") else c
                        for c in (inner.tool_calls or [])])
