"""Unified trace context — Phase 25A.

One contextvar-backed context carries the identity of WHAT is being
executed, so logs / metrics / errors join on structured fields instead
of greppable coincidences:

    request → task → skill → tool → result

Ids are deterministic-shaped (prefixed, fixed width) and generated at
ONE place. Downstream layers NARROW the context (child contexts), they
never invent new ad-hoc identifiers. Observability-only: importing
this module changes no business behavior.
"""
from __future__ import annotations

import contextvars
import uuid
from contextlib import contextmanager
from typing import Optional

# id prefixes keep log greps unambiguous (req_ / corr_ / trc_)
_PREFIX = {"request": "req", "correlation": "corr", "trace": "trc"}


def new_id(kind: str) -> str:
    p = _PREFIX.get(kind, kind)
    return "%s_%s" % (p, uuid.uuid4().hex[:16])


class TraceContext:
    """Immutable snapshot of the execution identity. Fields the caller
    has not narrowed stay empty — never guessed."""

    __slots__ = ("request_id", "correlation_id", "trace_id", "project_id",
                 "case_id", "task_id", "skill_name", "tool_name")

    def __init__(self, request_id="", correlation_id="", trace_id="",
                 project_id="", case_id="", task_id="", skill_name="",
                 tool_name=""):
        self.request_id = request_id
        self.correlation_id = correlation_id
        self.trace_id = trace_id
        self.project_id = project_id
        self.case_id = case_id
        self.task_id = task_id
        self.skill_name = skill_name
        self.tool_name = tool_name

    def child(self, **over) -> "TraceContext":
        """Narrowed copy: a task child of a request, a skill child of a
        task. Unspecified fields inherit (same correlation/trace)."""
        base = {k: getattr(self, k) for k in self.__slots__}
        base.update({k: v for k, v in over.items() if k in self.__slots__})
        return TraceContext(**base)

    def fields(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}

    def __repr__(self):  # pragma: no cover — debug aid
        return "TraceContext(%s)" % ", ".join(
            "%s=%s" % (k, v) for k, v in self.fields().items() if v)


_current: contextvars.ContextVar = contextvars.ContextVar(
    "obs_trace_context", default=None)


def current() -> TraceContext:
    """The active context (an EMPTY context when none was entered —
    callers never need to null-check)."""
    return _current.get() or TraceContext()


@contextmanager
def use_context(ctx: TraceContext):
    """Enter ctx for the duration of the with-block (restores the
    previous context afterwards)."""
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)


@contextmanager
def start_request(project_id: str = "", case_id: str = "",
                  correlation_id: str = ""):
    """One inbound request: fresh request_id + trace_id; correlation_id
    propagates across requests when supplied (e.g. a retry), else it is
    the request's own correlation root."""
    rid = new_id("request")
    ctx = TraceContext(
        request_id=rid,
        correlation_id=correlation_id or new_id("correlation"),
        trace_id=new_id("trace"),
        project_id=project_id, case_id=case_id)
    with use_context(ctx) as c:
        yield c


@contextmanager
def span(task_id: str = "", skill_name: str = "", tool_name: str = "",
         case_id: str = "", project_id: str = ""):
    """Narrow the active context for one task/skill/tool execution.
    Same request/correlation/trace — deeper identity."""
    ctx = current().child(task_id=task_id or current().task_id,
                          skill_name=skill_name or current().skill_name,
                          tool_name=tool_name or current().tool_name,
                          case_id=case_id or current().case_id,
                          project_id=project_id or current().project_id)
    with use_context(ctx) as c:
        yield c


def attach_context(**fields) -> TraceContext:
    """Set/extend the ambient context WITHOUT a with-block (used at
    composition boundaries where a context manager is impractical,
    e.g. seeding case_id once a run's case is known). Returns the new
    context."""
    ctx = current().child(**fields)
    _current.set(ctx)
    return ctx
