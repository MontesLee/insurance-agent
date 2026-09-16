import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { loadCursor, saveCursor, useRunStream } from "./useRunStream";
import type { RuntimeEvent } from "../types/runtime";
import { initRunState } from "../state/runReducer";

// --------------------------------------------------------------------------- #
// mock transport: fetch for the REST priming, a fake EventSource for the stream
// --------------------------------------------------------------------------- #
const openSources: MockEventSource[] = [];

class MockEventSource {
  static LAST_URL = "";
  url: string;
  closed = false;
  listeners: Record<string, ((e: { data: string }) => void)[]> = {};
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockEventSource.LAST_URL = url;
    openSources.push(this);
  }

  addEventListener(type: string, fn: (e: { data: string }) => void) {
    (this.listeners[type] ??= []).push(fn);
  }

  emit(event: RuntimeEvent) {
    for (const fn of this.listeners["runtime"] ?? []) fn({ data: JSON.stringify(event) });
  }

  close() {
    this.closed = true;
  }
}

vi.stubGlobal("EventSource", MockEventSource);

function ev(n: number, type: string, extra: Partial<RuntimeEvent> = {}): RuntimeEvent {
  return {
    event_id: `evt_${String(n).padStart(6, "0")}`,
    run_id: "run_x",
    timestamp: "2026-09-16T07:00:00Z",
    event_type: type as RuntimeEvent["event_type"],
    stage: null,
    skill: null,
    status: null,
    case_id: "c1",
    artifact_id: null,
    eval_id: null,
    repair_attempt: null,
    message: null,
    data: {},
    ...extra,
  };
}

function stubRest(events: RuntimeEvent[], runStatus = "running") {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/api/runs/run_x")) {
      return Response.json({
        run_id: "run_x", case_id: "c1", status: runStatus,
        started_at: null, completed_at: null, current_stage: null, event_count: events.length,
        result_status: null, reasons: [],
        stage_order: [{ id: "solution", skill: "solution", produces: "solution-plan" }],
      });
    }
    if (url.includes("/events")) {
      return Response.json({ run_id: "run_x", count: events.length, events });
    }
    return Response.json({}, { status: 404 });
  });
}

let currentSource: MockEventSource;

function latestSource(): MockEventSource {
  const s = openSources[openSources.length - 1];
  if (!s) throw new Error("no EventSource opened");
  return s;
}

beforeEach(() => {
  openSources.length = 0;
  MockEventSource.LAST_URL = "";
  sessionStorage.clear();
});

describe("cursor persistence (SSE resume)", () => {
  it("saveCursor/loadCursor round-trips per run", () => {
    saveCursor("run_a", "evt_000007");
    saveCursor("run_b", "evt_000002");
    expect(loadCursor("run_a")).toBe("evt_000007");
    expect(loadCursor("run_b")).toBe("evt_000002");
    expect(loadCursor("run_unknown")).toBeNull();
  });
});

describe("useRunStream", () => {
  it("primes from REST, then opens the live stream and applies events", async () => {
    const fetchMock = stubRest([ev(1, "run_started")]);
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useRunStream("run_x"));
    await waitFor(() => expect(openSources.length).toBe(1));
    currentSource = latestSource();

    // replayed event already applied before the stream opened
    expect(result.current.state?.events.map((e) => e.event_id)).toEqual(["evt_000001"]);

    act(() => currentSource.emit(ev(2, "stage_started", { stage: "solution" })));
    expect(result.current.state?.stages["solution"]?.status).toBe("running");

    act(() => currentSource.emit(ev(3, "run_completed", { status: "completed" })));
    await waitFor(() => expect(currentSource.closed).toBe(true));
    expect(result.current.state?.status).toBe("completed");
    expect(result.current.streaming).toBe(false);
    expect(loadCursor("run_x")).toBe("evt_000003");
  });

  it("opens the stream with ?after_event_id from the persisted cursor", async () => {
    saveCursor("run_x", "evt_000001");
    vi.stubGlobal("fetch", stubRest([ev(1, "run_started")]));
    renderHook(() => useRunStream("run_x"));
    await waitFor(() => expect(openSources.length).toBe(1));
    expect(MockEventSource.LAST_URL).toBe("/api/runs/run_x/stream?after_event_id=evt_000001");
  });

  it("ignores events from a different run (defensive) and stale cursors (no dupes)", async () => {
    saveCursor("run_x", "evt_000005");
    vi.stubGlobal("fetch", stubRest([]));
    const { result } = renderHook(() => useRunStream("run_x"));
    await waitFor(() => expect(openSources.length).toBe(1));
    currentSource = latestSource();

    act(() => {
      currentSource.emit({ ...ev(6, "stage_started", { stage: "solution" }), run_id: "run_OTHER" });
      currentSource.emit(ev(4, "stage_started", { stage: "solution" })); // stale id <= cursor
      currentSource.emit(ev(6, "stage_started", { stage: "solution" })); // fresh
    });
    expect(result.current.state?.events).toHaveLength(1);
    expect(result.current.state?.events[0]!.event_id).toBe("evt_000006");
    expect(loadCursor("run_x")).toBe("evt_000006");
  });

  it("does not open a stream when the run already reached its terminal state", async () => {
    vi.stubGlobal("fetch", stubRest([ev(1, "run_started"), ev(2, "run_completed", { status: "completed" })], "completed"));
    const { result } = renderHook(() => useRunStream("run_x"));
    await waitFor(() => expect(result.current.state?.status).toBe("completed"));
    expect(openSources.length).toBe(0);
    expect(result.current.streaming).toBe(false);
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.stubGlobal("EventSource", MockEventSource);
  vi.restoreAllMocks();
});

// keep initRunState referenced for type-level reuse in future tests
void initRunState;
