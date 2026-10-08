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
                   fast_provider: Optional[LLMProvider] = None,
                   deadline_at: Optional[float] = None) -> AgentOutcome:
    """One user turn through the agent loop. `emit(event_type, data)` publishes
    RuntimeEvents (agent_step_started / agent_decision / tool_* …).

    Cost tiers (Lawgent-style, explicit rule): step 1 — understanding the fresh
    user input — runs on the MAIN provider; every subsequent routine
    continue-after-a-tool-result step runs on `fast_provider` (LLM_FAST_MODEL).
    `fast_provider=None` (or unset LLM_FAST_MODEL) keeps single-tier behaviour
    exactly as before.

    28.K.24 (L2): `deadline_at` is the ABSOLUTE monotonic run deadline —
    every provider call's wall-clock budget is clamped to the REMAINING
    run budget (retries never re-arm the run deadline)."""
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
            try:    # 28.K.30: retry-exhaustion observation record
                import runtime.obs as _obs
                _obs.log("agent.llm_call", level="WARN", status="EXHAUSTED",
                         step=step, model=getattr(active, "model", "unknown"),
                         retries=LLM_RETRY, run_id=agent_state.run_id)
            except Exception:  # noqa: BLE001
                pass
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
        # 28.K.30: per-call OBSERVATION record (pure side-observation —
        # the tiering audit needs per-call model/latency/token ground
        # truth; the gateway only sees QA-slice calls, agent-loop calls
        # had no obs record). Metadata only, fail-quiet.
        try:
            import runtime.obs as _obs
            _obs.log("agent.llm_call", status="OK", step=step,
                     model=getattr(active, "model", "unknown"),
                     duration_ms=response.latency_ms,
                     input_tokens=response.usage.get("input_tokens"),
                     output_tokens=response.usage.get("output_tokens"),
                     tool_calls=[c.name for c in (response.tool_calls
                                                  or [])][:3],
                     run_id=agent_state.run_id)
        except Exception:  # noqa: BLE001 — observation must not break
            pass

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
            # 28.K.1 (P2-①): the consumer-visible message is the fixed
            # natural-language template ONLY. The raw tool summary names
            # internal stages/tools — it stays in the EVENT stream
            # (tool_* summary + final agent_decision reason) where
            # Developer/Operator diagnostics read it, and is never
            # appended to the delivered message.
            return _finish(agent_state, um_id,
                           AgentOutcome("finish", NEEDS_REVIEW_MESSAGE,
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


def _generate_with_retry(provider, messages, tool_specs, agent_state, emit,
                         deadline_at=None):
    """Provider call + malformed-output bounded retry (spec §34).

    Prefers the streaming interface when the provider has one: text/reasoning
    deltas are forwarded via emit("agent_stream_delta", ...) for the live UI
    (transient — never persisted to event history); the assembled response is
    returned as before. Malformed = provider error, or a tool-call whose
    arguments fail schema validation twice in a row for the SAME attempt →
    counted here only for provider/parse failures; schema feedback goes
    through the message loop.

    28.K.29-A (user-visible answer streaming): the FINAL user answer is
    generated as agent_decide's `message` tool ARGUMENT — raw argument
    fragments arrive on the provider stream (kind=tool_args). Those
    fragments are consumed here with a JSON-aware incremental extractor:
    ONLY agent_decide with action=finish surfaces its `message` as
    content deltas on the `answer` channel (the message-position stream
    bubble — never a step box, spec §11); every other tool's arguments
    stay internal (spec §7); ask_user does NOT stream (its schema can be
    rejected after partial emission — live K.29 finding); reasoning
    deltas remain kind=reasoning (E-2: never rendered). A retry attempt
    emits a reset marker first so the consumer buffer converges to the
    winning attempt. This is REAL provider streaming — no
    buffering-then-fake-typing.

    28.K.24 (L2): every attempt runs under a WALL-CLOCK watchdog (the
    same thread+join pattern as the QA gateway adapter, 28.B5.1) — the
    provider's per-read httpx timeout cannot be extended forever by
    slow-drip chunks. The budget is min(generation wall, REMAINING run
    deadline); a retry is only started when the remaining budget clears
    the minimum floor. On exhaustion the call raises llm TimeoutError
    (retryable → bounded attempts → needs_review fail-closed), and the
    RUN deadline supervisor (server) owns the terminal transition."""
    from runtime.agent.answer_stream import scan_decide, visible_message
    from runtime.run_deadline import generation_budget
    from runtime.llm.types import TimeoutError as LLMTimeout

    # mirrors _clip(args.get("message"), 1200) in the finish/ask_user
    # handlers — the streamed text and the delivered transcript message
    # converge to the SAME length
    _MAX_ANSWER = 1200
    _EMITTED = {"len": 0}        # total answer chars emitted this call

    def _reset_answer_stream() -> None:
        if _EMITTED["len"] > 0:
            emit("agent_stream_delta",
                 {"kind": "content", "channel": "answer",
                  "reset": True, "text": ""})
            _EMITTED["len"] = 0

    def _consume_tool_args(state: dict, delta: dict) -> None:
        name = delta.get("tool") or ""
        text = delta.get("text") or ""
        # the tool name arrives progressively; only agent_decide's
        # arguments may ever surface — anything else stays internal
        if not "agent_decide".startswith(name):
            return
        state["raw"] += text
        action, msg_raw = scan_decide(state["raw"])
        if action:
            state["action"] = action
        # finish ONLY: an ask_user attempt can fail SCHEMA validation
        # AFTER its message partially streamed (observed live in the
        # K.29 benchmark — the loop then continues and the leaked
        # question would sit in the answer position). finish+message is
        # inherently schema-valid, so it cannot leak a rejected draft.
        if state.get("action") != "finish":
            return
        visible = visible_message(msg_raw)
        if not visible.startswith(state["emitted"]):
            # the model rewrote its prefix mid-stream — re-anchor the
            # consumer buffer instead of emitting garbage
            _reset_answer_stream()
            state["emitted"] = ""
        room = _MAX_ANSWER - len(state["emitted"])
        if room <= 0:
            return
        fragment = visible[len(state["emitted"]):][:room]
        if fragment:
            emit("agent_stream_delta",
                 {"kind": "content", "channel": "answer", "text": fragment})
            state["emitted"] += fragment
            _EMITTED["len"] = len(state["emitted"])

    last_error = None
    for attempt in range(LLM_RETRY + 1):
        # a retry discards any partial answer the failed attempt streamed
        _reset_answer_stream()
        a_state = {"raw": "", "emitted": "", "action": None}
        try:
            budget = generation_budget(deadline_at)  # raises when exhausted

            def _call():
                stream = getattr(provider, "stream_generate", None)
                if stream is None:
                    return provider.generate(messages, tool_specs)
                gen = stream(messages, tool_specs)
                try:
                    while True:
                        delta = next(gen)
                        kind = delta.get("kind")
                        if kind == "tool_args":
                            # raw tool arguments NEVER cross the consumer
                            # boundary directly (28.K.29-A policy)
                            _consume_tool_args(a_state, delta)
                            continue
                        emit("agent_stream_delta",
                             {"kind": kind,
                              "text": delta.get("text", "")[:400]})
                except StopIteration as stop:
                    return stop.value        # assembled LLMResponse

            box = {}

            def _run():
                try:
                    box["resp"] = _call()
                except Exception as exc:  # noqa: BLE001 — surfaced below
                    box["err"] = exc

            import threading
            t = threading.Thread(target=_run, daemon=True,
                                 name="agent-gen-watchdog")
            t.start()
            t.join(budget)
            if "resp" in box:
                return box["resp"]
            if "err" in box:
                raise box["err"]
            raise LLMTimeout(
                "agent generation wall-clock exceeded %.0fs "
                "(run-budget-clamped)" % budget)
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
    """LLM-facing tool-result projection. 28.K.25-S1 source hygiene:
    internal identifier KEYS (artifact_id/eval_id/run_id…) are dropped
    before the JSON reaches the model — the model cannot echo what it
    never sees. Internal state (tool_history/events/registry) keeps the
    real IDs; nothing about storage or linkage changes."""
    import json
    from runtime.consumer_hygiene import strip_internal_ids_for_llm
    slim = {k: v for k, v in result.items() if k in
            ("status", "summary", "artifact_type",
             "eval_status", "data")}
    return json.dumps(strip_internal_ids_for_llm(slim),
                      ensure_ascii=False)[:2000]


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
