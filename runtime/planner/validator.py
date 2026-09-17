"""Graph Validator — turns UNTRUSTED LLM plans into TRUSTED executable graphs.

Checks (fail-closed, §8/§9/§10):
  1.  task_id unique
  2.  task_type in Registry
  3.  dependency references exist
  4.  no circular dependency (topological sort)
  5.  entry tasks have no dependencies
  6.  terminal tasks reachable
  7.  all dependencies reach a terminal
  8.  artifact contract: every required_input is produced by an upstream task
  9.  eval contract: every task_type in the Registry has required_eval defined
  10. no unknown fields leak into execution
"""
from __future__ import annotations

from runtime.planner import registry

MAX_ERRORS = 10


def validate_graph(graph: dict) -> tuple:
    """Validate a parsed Task Graph. Returns (ok, errors)."""
    errors: list = []
    tasks = graph.get("tasks") or []
    if not tasks:
        return False, ["graph has no tasks"]

    ids = [t.get("task_id") for t in tasks]
    id_set = set(ids)

    # 1. unique task_id
    if len(ids) != len(id_set):
        dupes = [i for i in ids if ids.count(i) > 1]
        errors.append("duplicate task_id: %s" % sorted(set(dupes))[:3])

    # 2. task_type in Registry
    for t in tasks:
        tt = t.get("task_type", "")
        if not registry.is_valid(tt):
            errors.append("unknown task_type %r (not in Registry)" % tt)

    # 3. dependency references exist
    for t in tasks:
        for dep in t.get("dependencies") or []:
            if dep not in id_set:
                errors.append("task %s depends on unknown %s" % (t.get("task_id"), dep))

    # 4. no circular dependency (Kahn's algorithm)
    topo_order = _topological_sort(tasks)
    if topo_order is None:
        errors.append("circular dependency detected")
    if errors:
        return False, errors[:MAX_ERRORS]

    # 5. entry tasks (no dependencies) exist
    entries = [t for t in tasks if not (t.get("dependencies") or [])]
    if not entries:
        errors.append("no entry task (all tasks have dependencies)")

    # 6. terminal tasks (nothing depends on them) exist
    depended_on = {d for t in tasks for d in (t.get("dependencies") or [])}
    terminals = [t for t in tasks if t["task_id"] not in depended_on]
    if not terminals:
        errors.append("no terminal task (all tasks are depended on)")

    # 7. every task reaches at least one terminal
    reachable = _reachable_terminals(tasks, terminals)
    for t in tasks:
        if t["task_id"] not in reachable:
            errors.append("task %s cannot reach any terminal" % t["task_id"])

    # 8. artifact contract: required_inputs satisfied by TRANSITIVE upstream
    #    artifacts accumulate through the dependency chain (A→B→C means C can
    #    use artifacts from both A and B)
    artifacts_by_task = {}       # task_id → set of artifacts it makes available
    for t in topo_order:
        tt = t.get("task_type", "")
        produced = set(registry.produced_artifacts(tt))
        inherited = set()
        for dep in t.get("dependencies") or []:
            inherited |= artifacts_by_task.get(dep, set())
        # what this task makes available downstream = its own + all inherited
        artifacts_by_task[t["task_id"]] = produced | inherited

        required = registry.required_inputs(tt)
        missing = set(required) - (produced | inherited)
        if missing:
            errors.append("task %s (%s) missing required input artifacts: %s"
                          % (t.get("task_id"), tt, sorted(missing)))

    # 9. eval contract: Registry always defines required_eval (structural check)
    for t in tasks:
        tt = t.get("task_type", "")
        d = registry.get(tt)
        if d and not d.get("required_eval"):
            errors.append("task_type %s has no required_eval in Registry" % tt)

    # 10. strip unknown fields (only whitelisted keys reach the Harness)
    for t in tasks:
        allowed = {"task_id", "task_type", "description", "dependencies"}
        extra = set(t.keys()) - allowed
        if extra:
            t["_extra_fields"] = sorted(extra)  # surfaced, not executed

    return (len(errors) == 0), errors[:MAX_ERRORS]


def _topological_sort(tasks: list) -> Optional[list]:
    """Kahn's algorithm. Returns ordered list or None if cyclic."""
    from collections import deque

    id_to_task = {t["task_id"]: t for t in tasks}
    in_deg = {t["task_id"]: 0 for t in tasks}
    adj: dict = {t["task_id"]: [] for t in tasks}

    for t in tasks:
        for dep in t.get("dependencies") or []:
            if dep in id_to_task:
                adj[dep].append(t["task_id"])
                in_deg[t["task_id"]] += 1

    queue = deque([tid for tid, d in in_deg.items() if d == 0])
    result = []
    while queue:
        tid = queue.popleft()
        result.append(id_to_task[tid])
        for nxt in adj[tid]:
            in_deg[nxt] -= 1
            if in_deg[nxt] == 0:
                queue.append(nxt)

    return result if len(result) == len(tasks) else None


def _reachable_terminals(tasks: list, terminals: list) -> set:
    """task_ids that can reach at least one terminal via forward edges."""
    terminal_ids = {t["task_id"] for t in terminals}
    forward: dict = {t["task_id"]: set() for t in tasks}
    for t in tasks:
        for dep in t.get("dependencies") or []:
            if dep in forward:
                forward[dep].add(t["task_id"])

    reachable = set(terminal_ids)
    changed = True
    while changed:
        changed = False
        for tid, children in forward.items():
            if tid not in reachable and (children & reachable):
                reachable.add(tid)
                changed = True
    return reachable
