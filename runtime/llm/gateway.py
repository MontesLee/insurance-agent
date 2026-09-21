"""LLM Gateway — Phase 23.

The single, governed, observable, fail-closed path for ALL LLM calls.
Skills NEVER call providers directly; they go through the Gateway.

Capabilities (each individually testable):
  policy check (R-05) · PII gate · timeout · retry (bounded,
  transient-only) · rate limit (process-local) · token budget ·
  circuit breaker (process-local) · cost accounting (UNKNOWN when
  unconfigured) · observability (request_id + correlation_id +
  metadata-only logging) · error normalization (business sees only
  LLMError subclasses).
"""
from __future__ import annotations

import time
from typing import Optional

from .types import (
    BudgetExceededError, ConfigurationError, LLMError, LLMProvider,
    LLMRequest, LLMResponse, PIIBlockedError, ProviderUnavailableError,
    RateLimitError, TimeoutError, UnknownProviderError, UNKNOWN)

_DEFAULT_TIMEOUT = 60.0
_DEFAULT_MAX_RETRIES = 2


class CircuitBreaker:
    """Process-local circuit breaker (CLOSED → OPEN → HALF_OPEN).
    Not distributed; suitable for single-process pilot."""

    def __init__(self, failure_threshold: int = 5,
                 recovery_timeout_s: float = 30.0):
        self.threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_s
        self.state = "CLOSED"
        self._failures = 0
        self._opened_at = 0.0

    def allow(self) -> bool:
        if self.state == "OPEN":
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        return True

    def record_success(self):
        self._failures = 0
        self.state = "CLOSED"

    def record_failure(self):
        self._failures += 1
        if self._failures >= self.threshold or self.state == "HALF_OPEN":
            self.state = "OPEN"
            self._opened_at = time.monotonic()


class RateLimiter:
    """Process-local token-bucket rate limiter (per provider).
    Process-local: NOT suitable for multi-worker production (Phase 26)."""

    def __init__(self, max_requests: int = 60, window_s: float = 60.0):
        self.max = max_requests
        self.window = window_s
        self._timestamps = []

    def allow(self) -> bool:
        now = time.monotonic()
        self._timestamps = [t for t in self._timestamps
                            if now - t < self.window]
        if len(self._timestamps) >= self.max:
            return False
        self._timestamps.append(now)
        return True


class LLMGateway:
    """Unified LLM gateway. Wrap any LLMProvider with governance."""

    def __init__(self, provider: LLMProvider, *,
                 timeout_s: float = _DEFAULT_TIMEOUT,
                 max_retries: int = _DEFAULT_MAX_RETRIES,
                 rate_limit_per_min: int = 60,
                 circuit_threshold: int = 5,
                 circuit_recovery_s: float = 30.0,
                 strict_mode: bool = False,
                 log_sink: Optional[list] = None):
        self.provider = provider
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.rate_limiter = RateLimiter(rate_limit_per_min, 60.0)
        self.circuit = CircuitBreaker(circuit_threshold,
                                       circuit_recovery_s)
        self.call_log = log_sink if log_sink is not None else []
        self._strict_mode = strict_mode

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Single entry point. All policies applied in order:
        policy → PII → rate limit → circuit → budget → retry loop."""
        request.timeout_s = min(request.timeout_s or self.timeout_s,
                                self.timeout_s)
        # 1. R-05 provider policy (in strict modes with real client data,
        #    unverified providers are BLOCKED)
        self._check_policy(request)
        # 2. PII gate (block before any provider call)
        self._check_pii(request)
        # 3. rate limit
        if not self.rate_limiter.allow():
            raise RateLimitError("LLM rate limit exceeded",
                                provider=self.provider.name)
        # 4. circuit breaker
        if not self.circuit.allow():
            raise ProviderUnavailableError(
                "LLM circuit breaker OPEN (provider %s failing)"
                % self.provider.name, provider=self.provider.name)
        # 5. token budget preflight
        self._check_budget(request)
        # 6. retry loop (bounded, transient-only)
        last_error = None
        for attempt in range(1 + self.max_retries):
            try:
                resp = self._do_generate(request, attempt)
                self.circuit.record_success()
                self._log(request, resp, attempt=attempt, status="OK")
                return resp
            except LLMError as e:
                last_error = e
                if not getattr(e, "retryable", False):
                    self.circuit.record_failure()
                    self._log(request, None, attempt=attempt,
                              status="FAIL", error=type(e).__name__)
                    raise
                self.circuit.record_failure()
                self._log(request, None, attempt=attempt,
                          status="RETRY", error=type(e).__name__)
        self._log(request, None, attempt=self.max_retries,
                  status="EXHAUSTED", error=type(last_error).__name__)
        raise last_error

    # ---- internal --------------------------------------------------------- #
    def _do_generate(self, request: LLMRequest, attempt: int
                     ) -> LLMResponse:
        """Single provider call with timeout + error normalization."""
        import httpx
        start = time.perf_counter()
        try:
            resp = self.provider.generate(request)
            resp.attempt_count = attempt
            return resp
        except LLMError:
            raise
        except httpx.TimeoutException as e:
            raise TimeoutError(
                "LLM timeout after %ss: %s" % (request.timeout_s,
                                                str(e)[:80]),
                provider=self.provider.name)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 429:
                raise RateLimitError("LLM 429 rate limited",
                                     provider=self.provider.name)
            if code == 401:
                raise TimeoutError if False else type(
                    "AuthError", (LLMError,), {})(  # noqa: F841
                    "LLM 401 authentication failed")
            if code == 403:
                raise ConfigurationError(
                    "LLM 403 forbidden", provider=self.provider.name)
            if code == 400:
                raise InvalidRequestError(
                    "LLM 400 invalid request: %s" % str(e)[:80],
                    provider=self.provider.name)
            if code == 422:
                raise ContextLengthError(
                    "LLM 422 context length exceeded",
                    provider=self.provider.name)
            if 500 <= code < 600:
                raise ProviderUnavailableError(
                    "LLM %d provider server error" % code,
                    provider=self.provider.name)
            raise ProviderUnavailableError(
                "LLM HTTP %d" % code, provider=self.provider.name)
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise ProviderUnavailableError(
                "LLM provider unreachable: %s" % str(e)[:80],
                provider=self.provider.name)
        except Exception as e:  # noqa: BLE001 — normalize everything
            if isinstance(e, (TimeoutError, ProviderUnavailableError)):
                raise LLMError(
                    "LLM provider failure: %s" % str(e)[:80],
                    provider=self.provider.name,
                    retryable=True)
            raise LLMError(
                "LLM unexpected error: %s" % str(e)[:80],
                provider=self.provider.name)

    def _check_policy(self, request: LLMRequest) -> None:
        """R-05 gate: in strict mode, real client data requires
        verified provider policy."""
        from runtime.agent import data_policy
        if self.provider.name == "mock":
            return  # mock provider never sends data anywhere
        if self._strict_mode:
            mode, reason = data_policy.client_data_mode(), ""
            allowed, why = data_policy.client_data_allowed()
            if not allowed:
                raise PIIBlockedError(
                    "R-05 provider policy: %s" % why)

    def _check_pii(self, request: LLMRequest) -> None:
        """Block credential-shaped values and deny-listed fields before
        any provider call. Reuses the existing redact() deny-list."""
        from runtime.state.dataprotection import SENSITIVE_FIELDS
        _CREDENTIAL_KEYS = ("api_key", "password", "secret",
                            "access_token", "credential")
        _CRED_VALUE_MARKERS = ("sk-", "ghp_", "Bearer ", "-----BEGIN")
        for msg in request.messages:
            content = str(msg.get("content", ""))
            for marker in _CRED_VALUE_MARKERS:
                if marker in content:
                    raise PIIBlockedError(
                        "credential-shaped value (%r…) blocked before "
                        "provider call" % marker[:4])
            if isinstance(msg.get("content"), dict):
                for k in msg["content"]:
                    if k.lower() in SENSITIVE_FIELDS | frozenset(
                            _CREDENTIAL_KEYS):
                        raise PIIBlockedError(
                            "sensitive field %r blocked before provider "
                            "call" % k)
        if request.system_prompt:
            for marker in _CRED_VALUE_MARKERS:
                if marker in request.system_prompt:
                    raise PIIBlockedError(
                        "credential in system prompt")

    def _check_budget(self, request: LLMRequest) -> None:
        if request.max_total_tokens is not None and request.max_tokens \
                and request.max_tokens > request.max_total_tokens:
            raise BudgetExceededError(
                "max_tokens %d > max_total_tokens budget %d"
                % (request.max_tokens, request.max_total_tokens))

    def _log(self, request, response, *, attempt=1, status="OK",
             error=""):
        """Metadata-only logging: no raw prompts, no secrets.
        Phase 25: the single observability choke point — every terminal
        outcome and every retry passes here exactly once, so metrics
        and the structured log see the complete LLM story (observation
        only; this method cannot change the business result)."""
        self.call_log.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                       time.gmtime()),
            "request_id": request.request_id,
            "correlation_id": request.correlation_id,
            "provider": self.provider.name,
            "model": request.model,
            "attempt": attempt,
            "status": status,
            "error_type": error,
            "latency_ms": response.latency_ms if response else None,
            "usage": (response.usage.to_dict()
                      if response and response.usage else None),
            "cost_status": (response.cost.status if response
                            else UNKNOWN),
        })
        try:
            self._observe(request, response, attempt, status, error)
        except Exception:  # noqa: BLE001 — observability must not break calls
            pass

    def _observe(self, request, response, attempt, status, error):
        """Phase 25 instrumentation (pure side-observation)."""
        import runtime.obs as obs
        m = obs.default_metrics()
        if status == "OK":
            m.inc("llm_calls_total")
            m.inc("llm_success_total")
        elif status == "EXHAUSTED":
            # terminal summary AFTER the last RETRY line — the final
            # failure was already counted by that RETRY; recounting
            # here would double-count one provider call
            pass
        else:                       # RETRY / FAIL (one provider call)
            m.inc("llm_calls_total")
            m.inc("llm_failure_total")
            m.inc("llm_failure_total", error=str(error))
            if "Timeout" in str(error):
                m.inc("llm_timeout_total")
            elif "RateLimit" in str(error):
                m.inc("llm_rate_limit_total")
        if response is not None and response.latency_ms is not None:
            m.observe("llm_duration", response.latency_ms)
        usage = (response.usage.to_dict()
                 if response and response.usage else None)
        m.record_tokens(self.provider.name,
                        usage.get("total_tokens") if usage else None)
        obs.log(
            "llm.call", level=("INFO" if status == "OK" else "WARN"),
            status=status, duration_ms=(response.latency_ms
                                        if response else None),
            provider=self.provider.name, model=request.model,
            attempt=attempt, max_attempts=1 + self.max_retries,
            error_type=str(error) if error else None,
            tokens=(usage.get("total_tokens") if usage
                    else obs.UNKNOWN))

    def describe(self) -> dict:
        """Safe info dump: no secrets."""
        return {
            "provider": self.provider.name,
            "timeout_s": self.timeout_s,
            "max_retries": self.max_retries,
            "circuit_state": self.circuit.state,
            "calls_logged": len(self.call_log),
        }
