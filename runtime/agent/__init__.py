"""Real LLM Agent Execution (Phase 2.6).

Layering (spec §55):
    LLM   = reasoning / decision layer        (runtime/agent/model.py)
    Tool  = agent-facing skill interface      (runtime/agent/tools.py)
    Skill = domain capability                 (.trae/skills + existing engines)
    Artifact / Eval / Repair / CaseState / RuntimeEvent = unchanged runtime

Mode B (agent) runs SIDE BY SIDE with Mode A (deterministic / evaluation) —
nothing in the deterministic path is modified.
"""
from runtime.agent.model import (FakeLLMProvider, LLMProvider, LLMResponse,
                                 ProviderNotConfigured, ToolCall, ToolSpec,
                                 provider_from_env)
from runtime.agent.config import LLMConfig, load_llm_config, redact_secrets
from runtime.agent.state import AgentState
from runtime.agent.agent import MAX_AGENT_STEPS, AgentOutcome, run_agent_turn
from runtime.agent.chats import ChatManager

__all__ = [
    "LLMProvider", "FakeLLMProvider", "LLMResponse", "ToolCall", "ToolSpec",
    "ProviderNotConfigured", "provider_from_env", "LLMConfig", "load_llm_config",
    "redact_secrets", "AgentState", "AgentOutcome",
    "run_agent_turn", "MAX_AGENT_STEPS", "ChatManager",
]
