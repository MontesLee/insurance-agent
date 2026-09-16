import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RunStatusBadge } from "./StatusBadge";

describe("Run status rendering (labels verbatim from the Run status)", () => {
  const cases: [string, RegExp][] = [
    ["queued", /QUEUED/],
    ["running", /RUNNING/],
    ["completed", /COMPLETED/],
    ["failed", /FAILED/],
    ["needs_review", /NEEDS REVIEW/],
    ["waiting", /WAITING FOR CLIENT/],
  ];

  it.each(cases)("status %s renders %s", (status, label) => {
    render(<RunStatusBadge status={status as never} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("unknown status renders UNKNOWN", () => {
    render(<RunStatusBadge status="unknown" />);
    expect(screen.getByText(/UNKNOWN/)).toBeInTheDocument();
  });
});
