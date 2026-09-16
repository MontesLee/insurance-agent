import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./client";

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("API layer", () => {
  it("409 body parses into the case_already_running contract", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch(409, { error: "case_already_running", run_id: "run_active", case_id: "c1" }),
    );
    const err = await api.createRun("c1").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(409);
    expect((err as ApiError).conflict).toEqual({
      error: "case_already_running",
      run_id: "run_active",
      case_id: "c1",
    });
  });

  it("non-conflict errors expose status only", async () => {
    vi.stubGlobal("fetch", mockFetch(404, { detail: "unknown run_id" }));
    const err = await api.getRun("run_nope").catch((e) => e);
    expect((err as ApiError).conflict).toBeNull();
    expect((err as ApiError).status).toBe(404);
  });

  it("network failure becomes ApiError(0) with a human message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    const err = await api.getRun("run_x").catch((e) => e);
    expect((err as ApiError).status).toBe(0);
    expect((err as ApiError).message).toContain("Cannot reach the runtime server");
  });

  it("streamUrl carries the resume cursor; omitted when absent", () => {
    expect(api.streamUrl("run_1")).toBe("/api/runs/run_1/stream");
    expect(api.streamUrl("run_1", "evt_000020")).toBe(
      "/api/runs/run_1/stream?after_event_id=evt_000020",
    );
  });
});
