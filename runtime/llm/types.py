"""LLM Gateway type system — Phase 23.

Unified contract for all LLM interactions. Skills NEVER see provider
SDKs; they see LLMRequest/LLMResponse/LLMError. Provider-specific
parameters stay in provider adapters.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

UNKNOWN = "UNKNOWN"


def _now_ms() -> int:
    return round(time.perf_counter() * 1000)


def _new_id(prefix: str) -> str:
    return "%s_%s" % (prefix, uuid.uuid4().hex[:12])


# ---- errors ---------------------------------------------------------------- #
class LLMError(RuntimeError):
    """Base: every LLM failure is an LLMError subclass — business code
    never sees httpx/SDK exceptions."""
    def __init__(self, message: str, *, provider: str = "",
                 retryable: bool = False):
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class ConfigurationError(LLMError):
    pass


class AuthenticationError(LLMError):
    pass


class AuthorizationError(LLMError):
    pass


class RateLimitError(LLMError):
    def __init__(self, message, retry_after_s=None, **kw):
        super().__init__(message, retryable=True, **kw)
        self.retry_after_s = retry_after_s


class TimeoutError(LLMError):
    def __init__(self, message, **kw):
        super().__init__(message, retryable=True, **kw)


class ProviderUnavailableError(LLMError):
    def __init__(self, message, **kw):
        super().__init__(message, retryable=True, **kw)


class InvalidRequestError(LLMError):
    pass


class ContextLengthError(LLMError):
    pass


class ContentPolicyError(LLMError):
    pass


class ProviderResponseError(LLMError):
    pass


class UnknownProviderError(LLMError):
    pass


class BudgetExceededError(LLMError):
    pass


class PIIBlockedError(LLMError):
    pass


# ---- request ---------------------------------------------------------------- #
@dataclass
class LLMRequest:
    messages: list                                    # [{role, content}]
    model: str = ""                                  # explicit model
    system_prompt: str = ""
    temperature: float = 0.7
    max_tokens: Optional[int] = None                 # provider response cap
    max_total_tokens: Optional[int] = None           # budget hard-stop
    timeout_s: float = 60.0
    request_id: str = field(default_factory=lambda: _new_id("llm_req"))
    correlation_id: str = ""
    metadata: dict = field(default_factory=dict)
    # tool-calling support (existing agent tool protocol)
    tools: list = field(default_factory=list)        # [ToolSpec or dict]

    def __post_init__(self):
        if not self.correlation_id:
            self.correlation_id = self.request_id


# ---- response --------------------------------------------------------------- #
@dataclass
class LLMUsage:
    prompt_tokens: object = UNKNOWN
    completion_tokens: object = UNKNOWN
    total_tokens: object = UNKNOWN

    def to_dict(self):
        return {"prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.total_tokens}


@dataclass
class LLMCost:
    input_cost: object = UNKNOWN
    output_cost: object = UNKNOWN
    total_cost: object = UNKNOWN
    currency: str = UNKNOWN

    @property
    def status(self):
        return UNKNOWN if self.total_cost is UNKNOWN else "KNOWN"


@dataclass
class LLMResponse:
    request_id: str
    provider: str
    model: str
    content: Optional[str]
    finish_reason: str = ""
    usage: LLMUsage = field(default_factory=LLMUsage)
    cost: LLMCost = field(default_factory=LLMCost)
    latency_ms: int = 0
    response_id: str = ""
    tool_calls: list = field(default_factory=list)
    attempt_count: int = 1


# ---- provider protocol ------------------------------------------------------- #
class LLMProvider:
    """Minimal: generate one completion. No embeddings, no streaming,
    no fine-tuning. Provider adapters implement this; the Gateway
    wraps them with policy/PII/budget/timeout/retry/observability."""
    name: str = ""

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError
