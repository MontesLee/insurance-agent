/**
 * Minimal hash-based routing (Phase 28.E-1) — the space boundary IS the URL.
 *
 * Why hash routing: the project has no router dependency and the dev
 * server serves a single page; a ~40-line hash router gives us
 * refresh-safe, deep-linkable spaces with zero new deps and no server
 * config. It is a navigation boundary, NOT a security boundary —
 * access policy (auth/roles) is a deferred owner decision
 * (docs/production/phase-28e0-consumer-surface-design-audit.md §12).
 *
 * Fail-safe rule: ANY unknown, malformed, or empty route resolves to
 * the CONSUMER space — an accidental URL can never open an internal
 * surface. The legacy `webui:mode` localStorage key is intentionally
 * NOT consulted here.
 */
import { useEffect, useState } from "react";

export type Space = "consumer" | "operator" | "developer";

export interface Route {
  space: Space;
  view: string;
  /** e.g. the opaque artifact reference for /report/{ref} (consumer) */
  ref?: string;
}

export const ROUTES = {
  consumerChat: "/chat",
  operatorReview: "/operator/review",
  developerDashboard: "/developer/dashboard",
  developerConsole: "/developer/console",
} as const;

export function parseRoute(hash: string): Route {
  const path = (hash || "").replace(/^#/, "").split("?")[0] || "/";
  if (path.startsWith("/report/")) {
    // D-05′ consumer deep link: opaque reference ONLY — never a raw run id
    const ref = path.slice("/report/".length);
    return ref
      ? { space: "consumer", view: "report", ref }
      : { space: "consumer", view: "chat" };
  }
  if (path === ROUTES.operatorReview) {
    return { space: "operator", view: "review" };
  }
  if (path === ROUTES.developerDashboard) {
    return { space: "developer", view: "dashboard" };
  }
  if (path === ROUTES.developerConsole) {
    return { space: "developer", view: "console" };
  }
  // "/", "/chat", and everything unrecognized → consumer (fail-safe)
  return { space: "consumer", view: "chat" };
}

export function navigate(path: string): void {
  window.location.hash = "#" + path;
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
