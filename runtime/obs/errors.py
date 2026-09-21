"""Error taxonomy — Phase 25C.

Every failure a production operator can see is classified
DETERMINISTICALLY (exception-type table + explicit overrides, no
guessing, no bare except → FAILED). The classification answers the
two operational questions: can we retry, and who must act.

Classification NEVER changes control flow — callers still raise /
handle exactly as before; this module only EXPLAINS failures.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ---- taxonomy ------------------------------------------------------- #
CONFIG_ERROR = "CONFIG_ERROR"
AUTH_ERROR = "AUTH_ERROR"
VALIDATION_ERROR = "VALIDATION_ERROR"
PROVIDER_ERROR = "PROVIDER_ERROR"
NETWORK_ERROR = "NETWORK_ERROR"
TIMEOUT = "TIMEOUT"
RATE_LIMIT = "RATE_LIMIT"
LLM_ERROR = "LLM_ERROR"
KNOWLEDGE_ERROR = "KNOWLEDGE_ERROR"
GOVERNANCE_ERROR = "GOVERNANCE_ERROR"
EVIDENCE_ERROR = "EVIDENCE_ERROR"
PROVENANCE_ERROR = "PROVENANCE_ERROR"
PERSISTENCE_ERROR = "PERSISTENCE_ERROR"
CONCURRENCY_ERROR = "CONCURRENCY_ERROR"
INTERNAL_ERROR = "INTERNAL_ERROR"
USER_INPUT_ERROR = "USER_INPUT_ERROR"
CANCELLED = "CANCELLED"

ALL_CLASSES = (CONFIG_ERROR, AUTH_ERROR, VALIDATION_ERROR,
               PROVIDER_ERROR, NETWORK_ERROR, TIMEOUT, RATE_LIMIT,
               LLM_ERROR, KNOWLEDGE_ERROR, GOVERNANCE_ERROR,
               EVIDENCE_ERROR, PROVENANCE_ERROR, PERSISTENCE_ERROR,
               CONCURRENCY_ERROR, INTERNAL_ERROR, USER_INPUT_ERROR,
               CANCELLED)


@dataclass(frozen=True)
class ClassifiedError:
    error_code: str            # stable machine code, e.g. "KNW-REGISTRY"
    error_class: str           # one of ALL_CLASSES
    retryable: bool            # a retry COULD in principle help
    safe_to_retry: bool        # a retry is SIDE-EFFECT FREE
    operator_action: str       # what the runbook says to do
    user_visible: bool         # safe to surface to the end user
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "error_class": self.error_class,
            "retryable": self.retryable,
            "safe_to_retry": self.safe_to_retry,
            "operator_action": self.operator_action,
            "user_visible": self.user_visible,
        }


# class-level defaults: (class, retryable, safe_to_retry,
#                        operator_action, user_visible)
_DEFAULTS = {
    CONFIG_ERROR:      (False, False, "fix configuration", False),
    AUTH_ERROR:        (False, False, "check credentials", False),
    VALIDATION_ERROR:  (False, True, "inspect input", True),
    PROVIDER_ERROR:    (True, False, "check provider", False),
    NETWORK_ERROR:     (True, True, "check connectivity", False),
    TIMEOUT:           (True, True, "retry / check latency", False),
    RATE_LIMIT:        (True, True, "backoff, check quota", False),
    LLM_ERROR:         (True, False, "check llm provider", False),
    KNOWLEDGE_ERROR:   (True, False, "check knowledge backend", False),
    GOVERNANCE_ERROR:  (False, False, "review governance data", False),
    EVIDENCE_ERROR:    (False, False, "review evidence", False),
    PROVENANCE_ERROR:  (False, False, "review provenance chain", False),
    PERSISTENCE_ERROR: (True, False, "check postgresql", False),
    CONCURRENCY_ERROR: (True, False, "check locks / re-run", False),
    INTERNAL_ERROR:    (False, False, "investigate logs", False),
    USER_INPUT_ERROR:  (False, True, "correct the input", True),
    CANCELLED:         (False, True, "no action", True),
}


def _mk(error_code: str, error_class: str, message: str = ""
        ) -> ClassifiedError:
    r, s, op, uv = _DEFAULTS[error_class]
    return ClassifiedError(error_code=error_code, error_class=error_class,
                           retryable=r, safe_to_retry=s,
                           operator_action=op, user_visible=uv,
                           message=message[:200])


# ---- exception-type table (deterministic; first match wins) -------- #
# (exception PATH suffix, error_code, error_class) — paths keep this
# table stable against import refactors.
_TABLE = (
    # knowledge provider boundary (Phase 14/18)
    ("knowledge.provider.base.ProviderConfigError",
     "KNW-CONFIG", CONFIG_ERROR),
    ("knowledge.provider.base.ProviderUnavailable",
     "KNW-UNAVAILABLE", NETWORK_ERROR),
    ("knowledge.provider.base.ProviderResponseInvalid",
     "KNW-BADRESPONSE", PROVIDER_ERROR),
    ("knowledge.provider.base.KnowledgeSearchError",
     "KNW-SEARCH", KNOWLEDGE_ERROR),
    # governance / registry (14.3 / 24A)
    ("knowledge.governance.model.RegistryError",
     "GOV-REGISTRY", GOVERNANCE_ERROR),
    # LLM gateway (Phase 23)
    ("runtime.llm.types.LLMError", "LLM-GENERIC", LLM_ERROR),
    ("runtime.llm.types.ConfigurationError", "LLM-CONFIG", CONFIG_ERROR),
    ("runtime.llm.types.AuthenticationError", "LLM-AUTH", AUTH_ERROR),
    ("runtime.llm.types.RateLimitError", "LLM-RATELIMIT", RATE_LIMIT),
    ("runtime.llm.types.ProviderUnavailableError",
     "LLM-UNAVAILABLE", PROVIDER_ERROR),
    ("runtime.llm.types.ProviderResponseError",
     "LLM-BADRESPONSE", PROVIDER_ERROR),
    ("runtime.llm.types.PIIBlockedError", "LLM-PII", VALIDATION_ERROR),
    ("runtime.llm.types.BudgetExceededError",
     "LLM-BUDGET", VALIDATION_ERROR),
    ("runtime.llm.types.UnknownProviderError",
     "LLM-UNKNOWNPROVIDER", CONFIG_ERROR),
    # persistence (22A/22B/13)
    ("runtime.state.persistence.PersistenceConfigError",
     "PST-CONFIG", PERSISTENCE_ERROR),
    ("psycopg2.OperationalError", "PST-CONNECT", PERSISTENCE_ERROR),
    ("psycopg2.InterfaceError", "PST-INTERFACE", PERSISTENCE_ERROR),
    ("psycopg2.Error", "PST-SQL", PERSISTENCE_ERROR),
    ("runtime.state.durable.LockNotAcquiredError",
     "PST-LOCK", CONCURRENCY_ERROR),
    # web auth (13)
    ("runtime.auth.AuthenticationError", "AUTH-REQUEST", AUTH_ERROR),
    # generic
    ("TimeoutError", "NET-TIMEOUT", TIMEOUT),
    ("ConnectionError", "NET-REFUSED", NETWORK_ERROR),
    ("FileNotFoundError", "PST-FILE", PERSISTENCE_ERROR),
    ("PermissionError", "PST-PERMISSION", PERSISTENCE_ERROR),
    ("json.JSONDecodeError", "VAL-BADJSON", VALIDATION_ERROR),
    ("ValueError", "VAL-VALUE", VALIDATION_ERROR),
    ("TypeError", "VAL-TYPE", VALIDATION_ERROR),
    ("KeyError", "VAL-KEY", VALIDATION_ERROR),
    ("KeyboardInterrupt", "APP-CANCELLED", CANCELLED),
    ("asyncio.CancelledError", "APP-CANCELLED", CANCELLED),
)


def classify(error: BaseException) -> ClassifiedError:
    """Deterministic classification. Exact module-qualified type match
    first, then MRO walk (subclasses inherit their parent's class),
    then INTERNAL_ERROR — never a bare FAILED."""
    if not isinstance(error, BaseException):
        return _mk("APP-INTERNAL", INTERNAL_ERROR, str(error))
    seen = []
    for exc in type(error).__mro__:
        path = "%s.%s" % (exc.__module__, exc.__name__)
        seen.append(path)
        for suffix, code, klass in _TABLE:
            if path.endswith(suffix):
                return _mk(code, klass, str(error))
    return _mk("APP-INTERNAL", INTERNAL_ERROR,
               "%s (%s)" % (type(error).__name__, str(error)))


# ---- explicit semantic records (non-exception outcomes) ------------ #
def governance_denial(reasons: list) -> ClassifiedError:
    """A governance DENY is a normal fail-closed outcome, not an
    exception — but operators must see it classified."""
    return _mk("GOV-DENY", GOVERNANCE_ERROR,
               ",".join(str(r) for r in reasons)[:120])


def abstention(reason: str = "") -> ClassifiedError:
    return _mk("KNW-ABSTAIN", KNOWLEDGE_ERROR, reason[:120])
