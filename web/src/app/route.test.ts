/**
 * Route parsing — the E-1 space boundary (Phase 28.E-1).
 *
 * The safety-critical property: an unknown, malformed, or empty URL can
 * NEVER resolve to an internal (operator/developer) surface.
 */
import { describe, expect, it } from "vitest";
import { parseRoute, ROUTES } from "./route";

describe("parseRoute (three-space boundary)", () => {
  it("empty / root / chat resolve to the CONSUMER space", () => {
    expect(parseRoute("")).toEqual({ space: "consumer", view: "chat" });
    expect(parseRoute("#")).toEqual({ space: "consumer", view: "chat" });
    expect(parseRoute("#/")).toEqual({ space: "consumer", view: "chat" });
    expect(parseRoute(`#${ROUTES.consumerChat}`)).toEqual({ space: "consumer", view: "chat" });
  });

  it("unknown or malformed routes NEVER open an internal surface", () => {
    expect(parseRoute("#/whatever")).toEqual({ space: "consumer", view: "chat" });
    expect(parseRoute("#/developer")).toEqual({ space: "consumer", view: "chat" }); // partial path ≠ console
    expect(parseRoute("#/operator")).toEqual({ space: "consumer", view: "chat" });
    expect(parseRoute("#/developer/inspector?run=run_x")).toEqual({ space: "consumer", view: "chat" });
    expect(parseRoute("not-a-hash")).toEqual({ space: "consumer", view: "chat" });
  });

  it("E4-T5: no artifact deep-link surface exists — internal-addressed routes fall back to consumer", () => {
    expect(parseRoute("#/developer/artifact/run_x")).toEqual({ space: "consumer", view: "chat" });
    expect(parseRoute("#/artifact/run_x")).toEqual({ space: "consumer", view: "chat" });
    expect(parseRoute("#/operator/approval/appr_x")).toEqual({ space: "consumer", view: "chat" });
  });

  it("operator and developer routes parse exactly", () => {
    expect(parseRoute(`#${ROUTES.operatorReview}`)).toEqual({ space: "operator", view: "review" });
    expect(parseRoute(`#${ROUTES.developerDashboard}`)).toEqual({
      space: "developer",
      view: "dashboard",
    });
    expect(parseRoute(`#${ROUTES.developerConsole}`)).toEqual({
      space: "developer",
      view: "console",
    });
  });
});
