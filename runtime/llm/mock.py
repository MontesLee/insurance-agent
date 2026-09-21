"""Deterministic Mock LLM Provider — Phase 23.

Offline, deterministic, fast, no network. For unit tests, evaluation,
regression, and failure injection. NEVER pretends to be a real
provider — every response records provider="mock".
"""
from __future__ import annotations

import time

from .types import (
    LLMError, LLMProvider, LLMRequest, LLMResponse, LLMUsage,
    ProviderResponseError, RateLimitError, TimeoutError,
    AuthenticationError, AuthorizationError, ProviderUnavailableError,
    InvalidRequestError, UNKNOWN)


class MockLLMProvider(LLMProvider):
    """Deterministic mock with failure-injection support. Returns
    fixed content or triggers a specific error after N calls."""

    name = "mock"

    def __init__(self, content: str = "MOCK_LLM_RESPONSE",
                 fail_with: str = "", fail_after: int = 0):
        self._content = content
        self._fail_with = fail_with      # "", "timeout", "429", "401", etc
        self._fail_after = fail_after    # 0 = always fail if fail_with set
        self.call_count = 0

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        if self._fail_with and (self._fail_after == 0
                                or self.call_count > self._fail_after):
            self._raise_error(self._fail_with)
        usage = LLMUsage(
            prompt_tokens=100, completion_tokens=20, total_tokens=120)
        return LLMResponse(
            request_id=request.request_id,
            provider=self.name,
            model=request.model or "mock-model",
            content=self._content,
            finish_reason="stop",
            usage=usage,
            latency_ms=1,
            response_id="mock_resp_%d" % self.call_count)

    def _raise_error(self, kind: str):
        m = {
            "timeout": lambda: TimeoutError("mock timeout"),
            "429": lambda: RateLimitError("mock rate limit"),
            "401": lambda: AuthenticationError("mock auth failed"),
            "403": lambda: AuthorizationError("mock forbidden"),
            "500": lambda: ProviderUnavailableError("mock server error"),
            "malformed": lambda: ProviderResponseError(
                "mock malformed response"),
            "invalid_request": lambda: InvalidRequestError("mock bad request"),
        }
        fn = m.get(kind)
        if fn:
            raise fn()
        raise ProviderResponseError("mock unknown failure: %s" % kind)
