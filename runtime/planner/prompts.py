"""Planner prompts — minimal, structured-output-first."""
from __future__ import annotations

from runtime.planner.registry import TASK_REGISTRY

PLANNER_SYSTEM_PROMPT = """You are a task planner for an insurance analysis system.
Given a user's request, produce a structured task graph as STRICT JSON.

## Available task types (you may ONLY use these):
{task_catalog}

## Output format (STRICT JSON, no markdown, no explanation):
{{
  "tasks": [
    {{"task_id": "task_001", "task_type": "<from the list above>", "description": "<short>", "dependencies": []}},
    {{"task_id": "task_002", "task_type": "<from the list above>", "description": "<short>", "dependencies": ["task_001"]}}
  ]
}}

## Rules:
1. Only use task_types from the list above. Do NOT invent new ones.
2. Dependencies must reference earlier task_ids.
3. Order tasks so that inputs are produced before they are consumed.
4. Keep the graph minimal: include only tasks needed for the user's request.
5. For a full analysis, use the canonical chain:
   client_profile → requirement_analysis → risk_analysis → coverage_gap →
   solution → knowledge_search → product_candidates → recommendation → report_generation
6. For a partial request (e.g. "just analyze risk"), include only the tasks needed.
7. Return ONLY the JSON object, nothing else.
"""


def build_planner_prompt(request: str, context: Optional[dict] = None) -> str:
    catalog_lines = []
    for tt, d in TASK_REGISTRY.items():
        inputs = ", ".join(d["required_inputs"]) or "(none)"
        outputs = ", ".join(d["produced_artifacts"])
        catalog_lines.append(
            "- %s: %s | inputs: %s | outputs: %s"
            % (tt, d["description"], inputs, outputs))
    catalog = "\n".join(catalog_lines)

    prompt = PLANNER_SYSTEM_PROMPT.format(task_catalog=catalog)
    if context:
        prompt += "\n\n## Context\n%s\n" % json.dumps(context, ensure_ascii=False, default=str)
    prompt += "\n## User request\n%s\n" % request
    return prompt


from typing import Optional  # noqa: E402
import json  # noqa: E402
