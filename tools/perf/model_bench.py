"""28.K.30 candidate-model benchmark — SHADOW / OFFLINE only.

Task-equivalent per-call comparison of the provider's model tiers on
the REAL agent tasks (same system prompt, same user message, same 11
tool specs, same schema; ONLY the model name differs). Never touches
the production route/config — direct provider calls, results to
tmp/obs/k30/model_bench.json.

Tasks (from the real D-case planning shape):
  step1     — fresh user input -> first decision (tool-calling)
  continue  — after one tool result -> next decision
  final     — after full pipeline results -> finish decision with the
              user-facing message (long-form generation)

Per model x task x N repeats:
  ttft_ms          first delta of ANY kind (streaming interface)
  first_content_ms first content/tool_args delta
  wall_ms          full call
  input/output tokens, deltas, tool-call validity (name in registry,
  args parseable), plain-text leak (final must be a tool call)
"""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from runtime.agent import prompts, schemas as S  # noqa: E402
from runtime.agent.config import load_llm_config  # noqa: E402
from runtime.agent.model import ToolCall, ToolSpec  # noqa: E402
from runtime.agent.state import AgentState  # noqa: E402

OUT = os.path.join(ROOT, "tmp", "obs", "k30", "model_bench.json")

USER_D = ("我是35岁男性，已婚，有一个3岁的孩子，家庭年收入30万，还有房贷"
          "100万，我和妻子都只有社保，没有任何商业保险。请给我做一份完整的"
          "家庭保障规划分析，包括风险分析、保障缺口识别和具体的保障配置"
          "建议，并生成规划报告。")

TOOL_SPECS = [ToolSpec(t["name"], t["description"], t["parameters"])
              for t in (list(S.DIALOGUE_TOOLS) + list(S.STAGE_TOOLS)
                        + list(S.QA_TOOLS) + [dict(S.AGENT_DECIDE)])]
REGISTRY_NAMES = {t.name for t in TOOL_SPECS}


def _messages_task(task: str) -> list:
    st = AgentState("run_k30bench", "agentcase-k30b", "chat_k30b")
    st.add_user(USER_D)
    msgs = prompts.build_messages(prompts.SYSTEM_PROMPT, st, USER_D, [])
    if task == "step1":
        return msgs
    if task == "continue":
        msgs.append({"role": "assistant", "content": "", "tool_calls": [
            ToolCall(id="c1", name="record_client_profile", arguments={
                "family_profile": {"age": {"value": 35}},
                "financial_profile": {"annual_income": {"value": "30万"}}})]})
        msgs.append({"role": "tool", "tool_call_id": "c1",
                     "name": "record_client_profile",
                     "content": json.dumps({"status": "ok"}, ensure_ascii=False)})
        return msgs
    if task == "final":
        for i, (name, res) in enumerate([
                ("record_requirement_analysis", {"status": "ok"}),
                ("record_risk_assessment", {"status": "ok"}),
                ("coverage_gap_analysis", {"status": "ok"}),
                ("solution", {"status": "ok"}),
                ("report_generation",
                 {"status": "ok", "artifact_type": "insurance-report"})]):
            msgs.append({"role": "assistant", "content": "", "tool_calls": [
                ToolCall(id="c%d" % i, name=name, arguments={})]})
            msgs.append({"role": "tool", "tool_call_id": "c%d" % i,
                         "name": name,
                         "content": json.dumps(res, ensure_ascii=False)})
        msgs.append({"role": "system", "content":
                     "所有分析步骤已完成，报告已生成。请现在调用 agent_decide "
                     "结束本轮：action=finish，message 用中文给用户一个完整、"
                     "具体、包含关键保额建议的总结回答。"})
        return msgs
    raise ValueError(task)


def run_one(provider, task: str) -> dict:
    msgs = _messages_task(task)
    t0 = time.perf_counter()
    ttft = first_ct = None
    deltas = 0
    try:
        gen = provider.stream_generate(msgs, TOOL_SPECS)
        while True:
            try:
                d = next(gen)
            except StopIteration as stop:
                resp = stop.value
                break
            deltas += 1
            now = (time.perf_counter() - t0) * 1000.0
            if ttft is None:
                ttft = now
            if first_ct is None and d.get("kind") in ("content", "tool_args") \
                    and (d.get("text") or ""):
                first_ct = now
        wall = (time.perf_counter() - t0) * 1000.0
        calls = resp.tool_calls or []
        valid = all(c.name in REGISTRY_NAMES for c in calls)
        args_ok = True
        for c in calls:
            try:
                json.dumps(c.arguments)
            except Exception:  # noqa: BLE001
                args_ok = False
        return {"ok": True, "ttft_ms": round(ttft or -1, 1),
                "first_content_ms": round(first_ct or -1, 1),
                "wall_ms": round(wall, 1), "deltas": deltas,
                "input_tokens": (resp.usage or {}).get("input_tokens"),
                "output_tokens": (resp.usage or {}).get("output_tokens"),
                "tool_calls": [c.name for c in calls][:4],
                "tools_valid": valid and bool(calls), "args_parseable": args_ok,
                "plain_text_only": bool(resp.text) and not calls,
                "latency_ms": resp.latency_ms}
    except Exception as e:  # noqa: BLE001 — provider errors are DATA
        return {"ok": False, "wall_ms": round(
            (time.perf_counter() - t0) * 1000.0, 1),
            "error": "%s: %s" % (type(e).__name__, str(e)[:120])}


def main() -> None:
    cfg = load_llm_config()
    models = ["glm-5.3", "glm-5.3-flash", "glm-5.3-flashx", "glm-5-turbo"]
    tasks = ["step1", "continue", "final"]
    repeats = 3
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    results = []
    for model in models:
        for task in tasks:
            for i in range(1, repeats + 1):
                provider = cfg.to_provider().__class__(
                    name=cfg.provider, model=model, api_key=cfg.api_key,
                    base_url=cfg.resolved_base_url,
                    reasoning_effort=cfg.resolved_reasoning_effort)
                r = run_one(provider, task)
                r.update({"model": model, "task": task, "run": i})
                results.append(r)
                print("[bench] %-15s %-9s #%d %s wall=%s ttft=%s out=%s "
                      "tools=%s valid=%s%s" % (
                          model, task, i, "OK " if r.get("ok") else "ERR",
                          r.get("wall_ms"), r.get("ttft_ms"),
                          r.get("output_tokens"), r.get("tool_calls"),
                          r.get("tools_valid"),
                          "" if r.get("ok") else " err=%s" % r.get("error")),
                      flush=True)
                time.sleep(1.0)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)
    print("written: %s" % OUT)


if __name__ == "__main__":
    main()
