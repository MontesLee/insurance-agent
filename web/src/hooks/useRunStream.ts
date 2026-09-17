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
 *  * the stream closes itself on the terminal event (run_completed / run_failed);
 *  * `stop()` only DISCONNECTS THE VIEW ("stop viewing") — the runtime keeps
 *    executing; `resume()` re-attaches from the persisted cursor. There is no
 *    cancel API and the UI never pretends otherwise.
 */
import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Run, RuntimeEvent, RunStatus } from "../types/runtime";
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
  /** true after stop(): view disconnected, run continues server-side */
  viewStopped: boolean;
  /** disconnect the view only (no fake cancel) */
  stop: () => void;
  /** re-attach from the persisted cursor */
  resume: () => void;
}

export function useRunStream(runId: string | null): UseRunStream {
  const [state, dispatch] = useReducer(runReducer, null as RunUiState | null);
  const [error, setError] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [viewStopped, setViewStopped] = useState(false);
  const [resumeKey, setResumeKey] = useState(0);
  const stateRef = useRef<RunUiState | null>(null);
  stateRef.current = state;
  /** synchronous terminal flag — render state can be stale right after dispatch */
  const terminalRef = useRef(false);
  const stoppedRef = useRef(false);
  const esRef = useRef<EventSource | null>(null);

  const stop = useMemo(
    () => () => {
      stoppedRef.current = true;
      esRef.current?.close();
      esRef.current = null;
      setStreaming(false);
      setViewStopped(true);
    },
    [],
  );

  const resume = useMemo(
    () => () => {
      setResumeKey((k) => k + 1);
    },
    [],
  );

  useEffect(() => {
    if (!runId) {
      setError(null);
      setStreaming(false);
      setViewStopped(false);
      return;
    }

    let closed = false;
    stoppedRef.current = false;
    terminalRef.current = false;
    setViewStopped(false);

    async function prime(): Promise<void> {
      // 1) authoritative metadata (stage order / status) — the pipeline skeleton
      try {
        const run = await api.getRun(runId!);
        if (!closed) dispatch({ type: "init", runId: runId!, stageOrder: run.stage_order ?? [] });
        if (!closed && !LIVE.has(run.status)) {
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

      // 3) live tail — only when the run has not finished and the view is open
      if (terminalRef.current || closed || stoppedRef.current) return;

      const cursor = loadCursor(runId!);
      const es = new EventSource(api.streamUrl(runId!, cursor ?? undefined));
      esRef.current = es;
      setStreaming(true);
      es.addEventListener("runtime", (ev: MessageEvent<string>) => {
        const event = JSON.parse(ev.data) as RuntimeEvent;
        if (event.run_id !== runId) return; // defensive: never mix runs
        if (event.event_id && event.event_id <= (loadCursor(runId!) ?? "")) return; // dedupe durable ids
        dispatch({ type: "event", event });
        if (event.event_id) saveCursor(runId!, event.event_id);
        if (isTerminal(event)) {
          terminalRef.current = true;
          esRef.current?.close();
          esRef.current = null;
          setStreaming(false);
        }
      });
      es.onerror = () => {
        // EventSource retries automatically (with Last-Event-ID); on a finished
        // run the server closes immediately, so stop instead of reconnecting
        if (terminalRef.current || stoppedRef.current) {
          esRef.current?.close();
          esRef.current = null;
          setStreaming(false);
        }
      };
    }

    void prime();
    return () => {
      closed = true;
      esRef.current?.close();
      esRef.current = null;
      setStreaming(false);
    };
  }, [runId, resumeKey]);

  return useMemo(
    () => ({ state, error, streaming, viewStopped, stop, resume }),
    [state, error, streaming, viewStopped, stop, resume],
  );
}

const LIVE = new Set(["queued", "running"]);

function humanError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 404) return "Run 不存在（可能属于已重启的上一个后端会话）。";
    return `Runtime server error ${e.status}`;
  }
  return "无法连接 runtime server。";
}

/**
 * useRunMeta — authoritative Run metadata: load once, poll while the run is live.
 * Shared by the chat inspector and Developer Mode (the UI never infers status).
 */
export function useRunMeta(runId: string | null): { meta: Run | null; error: string | null } {
  const [meta, setMeta] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) {
      setMeta(null);
      setError(null);
      return;
    }
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const run: Run = await api.getRun(runId);
        if (stopped) return;
        setMeta(run);
        setError(null);
        const live: RunStatus[] = ["queued", "running"];
        if (live.includes(run.status)) {
          timer = setTimeout(tick, 700);
        }
      } catch (e) {
        if (!stopped) {
          setError(
            e instanceof ApiError && e.status === 404
              ? "Run 不存在（可能属于已重启的上一个后端会话）。"
              : "无法连接 runtime server。",
          );
        }
      }
    };
    void tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [runId]);

  return { meta, error };
}
