/**
 * useRunStream — subscribe to a run's RuntimeEvent stream (SSE) with resume.
 *
 * Correctness rules:
 *  * live events and replayed events go through the SAME reducer, so a refreshed
 *    page rebuilds the identical pipeline state (no client-side invention);
 *  * the last received event_id is persisted per run (sessionStorage) and used as
 *    `?after_event_id` when (re)opening — page refresh / reconnect never re-sends
 *    or loses the timeline. The browser's own Last-Event-ID reconnect is also
 *    honoured server-side;
 *  * the stream closes itself on the terminal event (run_completed / run_failed).
 */
import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { RuntimeEvent } from "../types/runtime";
import { isTerminal, runReducer, type RunUiState } from "../state/runReducer";

const cursorKey = (runId: string) => `webui:lastEventId:${runId}`;

export function loadCursor(runId: string): string | null {
  try {
    return sessionStorage.getItem(cursorKey(runId));
  } catch {
    return null;
  }
}

export function saveCursor(runId: string, eventId: string): void {
  try {
    sessionStorage.setItem(cursorKey(runId), eventId);
  } catch {
    /* storage unavailable — resume degrades to full replay, still correct */
  }
}

export interface UseRunStream {
  state: RunUiState | null;
  error: string | null;
  /** true while the SSE stream is open */
  streaming: boolean;
}

export function useRunStream(runId: string | null): UseRunStream {
  const [state, dispatch] = useReducer(runReducer, null as RunUiState | null);
  const [error, setError] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const stateRef = useRef<RunUiState | null>(null);
  stateRef.current = state;
  /** synchronous terminal flag — render state can be stale right after dispatch */
  const terminalRef = useRef(false);

  useEffect(() => {
    if (!runId) {
      setError(null);
      setStreaming(false);
      return;
    }

    let closed = false;
    let es: EventSource | null = null;

    async function prime(): Promise<void> {
      // 1) authoritative metadata (stage order / status) — the pipeline skeleton
      let stageOrder: RunUiState["stageOrder"] = [];
      try {
        const run = await api.getRun(runId!);
        stageOrder = run.stage_order ?? [];
        if (!closed) dispatch({ type: "init", runId: runId!, stageOrder });
        if (!closed && !RUNNING.has(run.status)) {
          dispatch({ type: "meta", status: run.status, currentStage: run.current_stage });
        }
      } catch (e) {
        if (!closed) setError(humanError(e));
      }

      // 2) replay what already happened (page refresh / late attach)
      try {
        const existing = await api.getEvents(runId!);
        if (!closed) dispatch({ type: "events", events: existing.events });
        for (const e of existing.events) saveCursor(runId!, e.event_id);
        terminalRef.current = existing.events.some(isTerminal);
      } catch (e) {
        if (!closed) setError(humanError(e));
      }

      // 3) live tail — only when the run has not finished yet
      if (terminalRef.current || closed) return;

      const cursor = loadCursor(runId!);
      es = new EventSource(api.streamUrl(runId!, cursor ?? undefined));
      setStreaming(true);
      es.addEventListener("runtime", (ev: MessageEvent<string>) => {
        const event = JSON.parse(ev.data) as RuntimeEvent;
        if (event.run_id !== runId) return; // defensive: never mix runs
        if (event.event_id <= (loadCursor(runId!) ?? "")) return; // dedupe on resume
        dispatch({ type: "event", event });
        saveCursor(runId!, event.event_id);
        if (isTerminal(event)) {
          terminalRef.current = true;
          es?.close();
          setStreaming(false);
        }
      });
      es.onerror = () => {
        // EventSource retries automatically (with Last-Event-ID); on a finished
        // run the server closes immediately, so stop instead of reconnecting
        if (terminalRef.current) {
          es?.close();
          setStreaming(false);
        }
      };
    }

    void prime();
    return () => {
      closed = true;
      es?.close();
      setStreaming(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  return useMemo(() => ({ state, error, streaming }), [state, error, streaming]);
}

const RUNNING = new Set(["queued", "running"]);

function humanError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 404) return "Run not found — it may belong to a previous server session.";
    return `Runtime server error ${e.status}`;
  }
  return "Unable to connect to the runtime server.";
}
