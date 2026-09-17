"""Real-LLM smoke test (Phase 2.6, §48) — NOT part of any regression.

Requires a real provider via env, e.g.:

    set LLM_PROVIDER=glm
    set LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
    set LLM_MODEL=glm-4.6
    set LLM_API_KEY=...
    python -m runtime.agent.smoke_test

Exits 0 when the agent asks for clarification on a vague input ("test") AND
completes a knowledge Q&A turn — proving the real path end to end.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from runtime.agent import AgentState, ProviderNotConfigured, provider_from_env, run_agent_turn  # noqa: E402
from runtime.agent.state import AgentState  # noqa: E402
from runtime.agent.tools import ToolContext  # noqa: E402
from runtime import orchestrator as orch  # noqa: E402
from runtime.state import case_state as cs  # noqa: E402
from runtime import tasks as tk  # noqa: E402


def _turn(provider, text):
    wf = orch.load_workflow()
    state = cs.new_case_state("agentsmoke", wf)
    tk.init_tasks(state, wf)
    ctx = ToolContext(state, wf, "run_smoke", persist=lambda: None)
    agent_state = AgentState("run_smoke", "agentsmoke", "chat_smoke")
    events = []

    def emit(event_type, data):
        events.append((event_type, data))

    outcome = run_agent_turn(provider, agent_state, text, ctx, emit)
    return outcome, agent_state, state, events


def main() -> int:
    from runtime.agent.config import load_llm_config

    try:
        cfg = load_llm_config()          # process env over <repo root>/.env
        provider = cfg.to_provider()
    except ProviderNotConfigured as e:
        print("SKIP: %s" % e)
        return 0

    d = cfg.describe()                    # key-free view
    print("provider=%s model=%s fast_model=%s base_url=%s"
          % (d["provider"], d["model"], d.get("fast_model"), d["base_url"]))

    out1, _, state1, ev1 = _turn(provider, "test")
    asked = out1.action == "ask_user"
    print("[1] 'test' -> action=%s status=%s msg=%s" % (out1.action, out1.status, out1.message[:120]))
    print("    artifacts=%s steps=%d" % (sorted((state1.get("artifacts") or {}).keys()),
                                         out1 and len(ev1)))
    if not asked:
        print("FAIL: vague input did not trigger ask_user")
        return 1
    if state1.get("artifacts"):
        print("FAIL: artifacts were produced for 'test'")
        return 1

    out2, _, _, ev2 = _turn(provider, "百万医疗险和重疾险有什么区别？")
    used_kb = any(e[0] == "tool_started" and e[1].get("tool") == "knowledge_search" for e in ev2)
    print("[2] QA -> action=%s status=%s kb_used=%s" % (out2.action, out2.status, used_kb))
    print("    msg=%s" % out2.message[:200])
    if out2.status != "completed":
        print("FAIL: QA turn did not complete")
        return 1

    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
