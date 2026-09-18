"""Real-LLM smoke test (Phase 2.6, §48) — NOT part of any regression.

This is the OPTIONAL real-LLM smoke (Phase 12 §4.3): it always requires a
configured provider and network. There is deliberately NO deterministic
fallback — an unavailable API is a SKIP, never a fake PASS.

    # configure a real provider first (see .env.example), then:
    python -m runtime.agent.smoke_test          # or: --llm (same thing)

Provider not configured → SKIP (exit 0, clearly labelled).
Provider configured but unreachable → FAIL-closed (exit 1): a live agent
that cannot reach its LLM must never report success.

Note (Phase 12 §4.4): on cp936/GBK Windows consoles, run with
PYTHONIOENCODING=utf-8 — model replies may contain characters GBK cannot
encode, and this script prints them verbatim rather than hiding output.
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


def _safe(text) -> str:
    """Console-encoding-proof print (§4.4): never crash on GBK/cp936 —
    replace unencodable characters instead of dying mid-report."""
    try:
        str(text).encode(sys.stdout.encoding or "utf-8")
        return str(text)
    except (UnicodeEncodeError, LookupError):
        return str(text).encode("ascii", "replace").decode("ascii")


def main() -> int:
    from runtime.agent.config import load_llm_config

    try:
        cfg = load_llm_config()          # process env over <repo root>/.env
        provider = cfg.to_provider()
    except ProviderNotConfigured as e:
        print("SKIP: no provider configured — %s" % e)
        return 0

    d = cfg.describe()                    # key-free view
    print("provider=%s model=%s fast_model=%s base_url=%s"
          % (d["provider"], d["model"], d.get("fast_model"), d["base_url"]))

    # fail-closed reachability probe BEFORE behavioral assertions (§4.3):
    # if the API is unreachable, report FAIL-CLOSED (exit 1) — never a
    # silent fallback and never a behavioral PASS on provider errors.
    try:
        provider.generate([{"role": "user", "content": "回复一个字：好"}],
                          tools=[])
    except Exception as e:  # noqa: BLE001 — any provider outage is fail-closed
        print("FAIL-CLOSED: provider unreachable (%s: %s)"
              % (type(e).__name__, str(e)[:160]))
        print("This is the OPTIONAL real-LLM smoke — it is NOT part of the")
        print("deterministic Quick Start. Network/API availability is required.")
        return 1

    out1, _, state1, ev1 = _turn(provider, "test")
    asked = out1.action == "ask_user"
    print(_safe("[1] 'test' -> action=%s status=%s msg=%s" % (out1.action, out1.status, out1.message[:120])))
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
    print(_safe("    msg=%s" % out2.message[:200]))
    if out2.status != "completed":
        print("FAIL: QA turn did not complete")
        return 1

    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
