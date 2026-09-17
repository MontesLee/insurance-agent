"""Agent Loop (Phase 2.6) — bounded, structured, fail-closed.

    LLM (understand / decide / tool-call)
        ↓ native tool calling + JSON-Schema-validated arguments
    ToolRegistry → existing Skills / CaseState / Eval / Repair
        ↓ structured result observed by the LLM
    next decision … until ask_user | finish | hard stop

Hard limits (spec §13/§34/§35): MAX_AGENT_STEPS=12, LLM_RETRY=2 on malformed
structured output. Every limit hit ⇒ NEEDS_REVIEW, never fake success (§44).
Events carry actions and summaries ONLY — never hidden reasoning (§23).
"""
from __future__ import annotations

from typing import Callable, Optional

from runtime.agent import prompts, schemas as S
from runtime.agent.model import LLMProvider, ToolSpec
from runtime.agent.state import AgentState
from runtime.agent.tools import ToolContext, build_registry, validate_arguments

MAX_AGENT_STEPS = 12
LLM_RETRY = 2


class AgentOutcome:
    def __init__(self, action: str, message: str, status: str, reason: str = "",
                 required_fields: Optional[list] = None):
        self.action = action            # ask_user | finish
        self.message = message          # user-facing text (no CoT)
        self.status = status            # waiting_user | completed | needs_review | failed
        self.reason = reason
        self.required_fields = required_fields or []


def run_agent_turn(provider: LLMProvider, agent_state: AgentState,
                   user_text: str, ctx: ToolContext,
                   emit: Callable[[str, dict], None],
                   fast_provider: Optional[LLMProvider] = None) -> AgentOutcome:
    """One user turn through the agent loop. `emit(event_type, data)` publishes
    RuntimeEvents (agent_step_started / agent_decision / tool_* …).

    Cost tiers (Lawgent-style, explicit rule): step 1 — understanding the fresh
    user input — runs on the MAIN provider; every subsequent routine
    continue-after-a-tool-result step runs on `fast_provider` (LLM_FAST_MODEL).
    `fast_provider=None` (or unset LLM_FAST_MODEL) keeps single-tier behaviour
    exactly as before."""
    registry = build_registry()
    tool_specs = [ToolSpec(t["name"], t["description"], t["parameters"])
                  for t in (list(S.DIALOGUE_TOOLS) + list(S.STAGE_TOOLS)
                            + list(S.QA_TOOLS)
                            + [dict(S.AGENT_DECIDE)])]
    agent_state.provider = provider.name
    agent_state.model = provider.model

    # build the LLM context BEFORE registering the current message:
    # messages_for_llm() replays past turns, build_messages() appends the
    # current user_text exactly once (registering first duplicated it)
    messages = prompts.build_messages(prompts.SYSTEM_PROMPT, agent_state,
                                      user_text, [])
    um_id = agent_state.add_user(user_text)

    def _feedback(response, note: str) -> None:
        """Bounce a malformed/unknown decision back to the model as context."""
        messages.append({"role": "assistant", "content": "",
                         "tool_calls": response.tool_calls})
        messages.append({"role": "system", "content": note})

    for step in range(1, MAX_AGENT_STEPS + 1):
        agent_state.turn = step
        emit("agent_step_started", {"step": step})
        active = provider if (step == 1 or fast_provider is None) else fast_provider

        response = _generate_with_retry(active, messages, tool_specs,
                                        agent_state, emit)
        if response is None:  # provider/malformed budget exhausted → fail closed
            return _finish(agent_state, um_id,
                           AgentOutcome("finish", AGENT_ERROR_MESSAGE,
                                        "needs_review",
                                        "llm_invalid_output_or_provider_error"),
                           emit)

        agent_state.usage["llm_calls"] += 1
        agent_state.usage["input_tokens"] += (response.usage.get("input_tokens") or 0)
        agent_state.usage["output_tokens"] += (response.usage.get("output_tokens") or 0)
        agent_state.usage["latency_ms"] = round(
            (agent_state.usage["latency_ms"] or 0) + (response.latency_ms or 0), 1)
        _bymodel = agent_state.usage.setdefault("by_model", {}).setdefault(
            getattr(active, "model", "unknown"),
            {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0})
        _bymodel["llm_calls"] += 1
        _bymodel["input_tokens"] += (response.usage.get("input_tokens") or 0)
        _bymodel["output_tokens"] += (response.usage.get("output_tokens") or 0)

        # plain text with no tool call is only acceptable as a final answer
        call = response.tool_calls[0] if response.tool_calls else None
        if call is None:
            text = (response.text or "").strip() or AGENT_ERROR_MESSAGE
            return _finish(agent_state, um_id,
                           AgentOutcome("finish", text, "completed"), emit)

        # ---- decision channel: agent_decide -------------------------------- #
        if call.name == "agent_decide":
            args = call.arguments
            action = args.get("action")
            # intent routing: record the user's classified intent (first
            # decision of the turn wins; it flows to events and AgentOutcome)
            intent = args.get("intent") or ""
            if intent and not agent_state.intent:
                agent_state.intent = intent
            emit("agent_decision", {"step": step, "action": action,
                                    "intent": intent or agent_state.intent,
                                    "reason": _clip(args.get("reason"), 120)})
            if action == "ask_user":
                fields = [str(f)[:60] for f in (args.get("required_fields") or [])][:8]
                agent_state.facts_asked.extend(fields)
                return _finish(agent_state, um_id,
                               AgentOutcome("ask_user", _clip(args.get("message"), 1200),
                                            "waiting_user",
                                            _clip(args.get("reason"), 120) or "insufficient_information",
                                            fields), emit)
            if action == "finish":
                return _finish(agent_state, um_id,
                               AgentOutcome("finish", _clip(args.get("message"), 1200),
                                            "completed"), emit)
            if action == "call_tool":
                name = args.get("tool") or ""
                if name not in registry:
                    _feedback(response, "tool %s is unknown; available: %s"
                              % (name, ", ".join(sorted(registry))))
                    continue
                call = _as_call(call, name, args.get("arguments") or {})
            else:
                _feedback(response, "invalid action %r — use ask_user | call_tool | finish"
                          % action)
                continue

        # ---- tool execution -------------------------------------------------- #
        tool = registry.get(call.name)
        if tool is None:
            _feedback(response, "unknown tool %s" % call.name)
            continue

        invalid = validate_arguments(tool, call.arguments)
        if invalid:
            _feedback(response, "arguments for %s failed schema validation: %s"
                      % (call.name, invalid))
            continue

        emit("tool_started", {"step": step, "tool": call.name})
        result = tool.execute(call.arguments, ctx)
        etype = "tool_failed" if result.get("status") == "failed" else "tool_completed"
        emit(etype, {"step": step, "tool": call.name,
                     "status": result.get("status"),
                     "artifact_id": result.get("artifact_id"),
                     "eval_id": result.get("eval_id"),
                     "summary": _clip(result.get("summary"), 160)})
        agent_state.tool_history.append({
            "tool": call.name, "status": result.get("status"),
            "artifact_id": result.get("artifact_id"),
            "eval_id": result.get("eval_id")})

        # fail closed on eval-driven blocks (spec §20/§44)
        if result.get("status") == "needs_review":
            return _finish(agent_state, um_id,
                           AgentOutcome("finish",
                                        "%s\n\n%s" % (NEEDS_REVIEW_MESSAGE,
                                                      _clip(result.get("summary"), 300)),
                                        "needs_review",
                                        "eval_failed_after_repair"), emit)

        messages.append({"role": "assistant", "content": "",
                         "tool_calls": response.tool_calls})
        messages.append({"role": "tool", "tool_call_id": call.id or call.name,
                         "name": call.name,
                         "content": _tool_content(result)})
        continue

    # step budget exhausted
    emit("agent_decision", {"step": MAX_AGENT_STEPS, "action": "stop",
                            "reason": "max_agent_steps_exceeded"})
    return _finish(agent_state, um_id,
                   AgentOutcome("finish", STEP_LIMIT_MESSAGE, "needs_review",
                                "max_agent_steps_exceeded"), emit)


AGENT_ERROR_MESSAGE = ("抱歉，这次我没能生成有效的分析步骤，已停止并转人工复核。"
                       "不会输出未经校验的结果。")
NEEDS_REVIEW_MESSAGE = ("这一步没有通过系统的质量校验（自动修复后仍未通过），"
                        "我已停止分析并标记为需要人工复核。")
STEP_LIMIT_MESSAGE = ("本次分析达到了单轮最大步骤数上限，已停止并转人工复核，"
                      "避免无限循环。")


def _generate_with_retry(provider, messages, tool_specs, agent_state, emit):
    """Provider call + malformed-output bounded retry (spec §34).

    Prefers the streaming interface when the provider has one: text/reasoning
    deltas are forwarded via emit("agent_stream_delta", ...) for the live UI
    (transient — never persisted to event history); the assembled response is
    returned as before. Malformed = provider error, or a tool-call whose
    arguments fail schema validation twice in a row for the SAME attempt →
    counted here only for provider/parse failures; schema feedback goes
    through the message loop."""
    last_error = None
    for attempt in range(LLM_RETRY + 1):
        try:
            stream = getattr(provider, "stream_generate", None)
            if stream is None:
                return provider.generate(messages, tool_specs)
            gen = stream(messages, tool_specs)
            try:
                while True:
                    delta = next(gen)
                    emit("agent_stream_delta", {"kind": delta.get("kind"),
                                                "text": delta.get("text", "")[:400]})
            except StopIteration as stop:
                return stop.value            # assembled LLMResponse
        except Exception as e:  # noqa: BLE001 — provider errors fail closed
            last_error = e
            emit("agent_step_error", {"attempt": attempt + 1,
                                      "error_type": type(e).__name__})
    agent_state.status = "needs_review"
    return None


def _as_call(call, name: str, arguments: dict):
    from runtime.agent.model import ToolCall
    return ToolCall(id=call.id or name, name=name, arguments=arguments)


def _tool_content(result: dict) -> str:
    import json
    slim = {k: v for k, v in result.items() if k in
            ("status", "summary", "artifact_id", "artifact_type", "eval_id",
             "eval_status", "data")}
    return json.dumps(slim, ensure_ascii=False)[:2000]


def _clip(text, limit: int) -> str:
    s = str(text or "").strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _finish(agent_state: AgentState, um_id: str, outcome: AgentOutcome,
            emit) -> AgentOutcome:
    agent_state.status = outcome.status
    agent_state.add_assistant(outcome.message,
                              "ask" if outcome.action == "ask_user" else "finish",
                              um_id)
    emit("agent_decision", {"action": outcome.action if outcome.action != "ask_user"
                            else "ask_user", "final": True,
                            "intent": agent_state.intent,
                            "status": outcome.status,
                            "reason": _clip(outcome.reason, 120)})
    return outcome
