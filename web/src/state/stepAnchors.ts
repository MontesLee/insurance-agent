/**
 * STEP-OUTPUT ANCHORING (28.K.29) — which activity row owns which step box.
 *
 * Before this module every step's output box trailed at the BOTTOM of the
 * activity card, so the text was detached from the milestone it belonged to.
 * The box is now rendered UNDER the activity row the step produced; this
 * module computes that ownership.
 *
 * The join is pure event-order arithmetic, no heuristics on content:
 *
 *  1. `foldConsumerActivities` reports, per activity, the index of the event
 *     that CREATED it.
 *  2. Each step bucket (`step-N`) has an origin index: the index of its
 *     `agent_step_started` event. The implicit QA bucket (`qa-composing`) is
 *     opened by a delta that never reaches `events[]` (deltas are transient),
 *     so its origin is "the end of the timeline".
 *  3. The owner is the FIRST activity created AFTER that origin — i.e. the
 *     milestone this step's LLM call went on to produce (the step reasons,
 *     then decides, then a stage starts). When the step produced no new
 *     activity (e.g. it re-ran an already-seen stage, or it just finished),
 *     the owner falls back to the MOST RECENT activity that already existed.
 *     If there is no activity at all the bucket is unanchored (null) and the
 *     caller renders it in the trailing container — never dropped.
 *
 * Rules kept from the rest of the consumer view: nothing here invents
 * progress; an unknown bucket key is simply unanchored; no activity key or
 * event id is ever rendered into the DOM (they stay React-internal).
 */
import type { RuntimeEvent } from "../types/runtime";
import { foldConsumerActivities } from "./activity";

/** Bucket key runReducer uses for an implicit QA-slice composing bucket. */
export const QA_COMPOSING_BUCKET_KEY = "qa-composing";

/** Mirror of runReducer's bucket key: `data.step`, else the running ordinal. */
function bucketKeyOf(e: RuntimeEvent, ordinal: number): string {
  return "step-" + String(e.data["step"] ?? ordinal);
}

/**
 * bucketKey -> owning activity key (null = no activity to attach to).
 * Deterministic: it depends only on the event sequence and the bucket keys.
 */
export function activityAnchors(
  events: RuntimeEvent[],
  bucketKeys: string[],
): Map<string, string | null> {
  const spans = foldConsumerActivities(events).spans;

  // origin index per step bucket
  const origin = new Map<string, number>();
  let ordinal = 0;
  for (let i = 0; i < events.length; i++) {
    const e = events[i]!;
    if (e.event_type !== "agent_step_started") continue;
    ordinal += 1;
    const key = bucketKeyOf(e, ordinal);
    if (!origin.has(key)) origin.set(key, i);
  }

  const anchors = new Map<string, string | null>();
  for (const key of bucketKeys) {
    // qa-composing (and any unknown key) has no step event → end of timeline
    const from = origin.get(key) ?? Number.POSITIVE_INFINITY;
    // spans are in creation order, so firstIndex increases monotonically
    let owner: string | null = null;
    for (const s of spans) {
      if (s.firstIndex > from) {
        owner = s.key;
        break;
      }
    }
    if (owner === null) {
      for (const s of spans) {
        if (s.firstIndex <= from) owner = s.key;
      }
    }
    anchors.set(key, owner);
  }
  return anchors;
}

/**
 * STEP KEYS WHOSE LLM CALL IS STILL IN FLIGHT (28.K.30).
 *
 * The empty step box shows a "正在思考…" liveness line. That line is only
 * truthful while a generation is genuinely underway. Evidence (real pilot
 * run, 2026-09-28): the LLM call is 96–100% of a step's wall time, but the
 * step's tool/stage execution is deterministic Python with NO model running
 * (35–151 ms; the one longer case is the knowledge retrieval span, 4.68 s).
 * During that window the old UI kept claiming the agent was thinking.
 *
 * A step stops being "awaiting" the moment an event proves the model has
 * RETURNED: it picked a tool, the tool ran, or it decided. Those events can
 * only be emitted downstream of a completed generation, so they are safe
 * boundaries to hinge the UI on — no timer, no inference about content.
 *
 * Buckets opened by the QA slice (`qa-composing`) carry no step events at
 * all; they are intentionally absent here and the caller keeps the old
 * behaviour for them.
 */
export function stepsAwaitingModel(events: RuntimeEvent[]): Set<string> {
  const awaiting = new Set<string>();
  for (const e of events) {
    const step = e.data?.["step"];
    if (step === undefined || step === null) continue;
    const key = "step-" + String(step);
    switch (e.event_type) {
      case "agent_step_started":
        awaiting.add(key);
        break;
      // the model already produced its decision — generation is over
      case "tool_started":
      case "tool_failed":
      case "tool_completed":
      case "agent_decision":
        awaiting.delete(key);
        break;
      default:
        break;
    }
  }
  return awaiting;
}
