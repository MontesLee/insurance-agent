/**
 * Three-space application shell (Phase 28.E-1).
 *
 *   Consumer  #/chat            — the product surface (chat-first)
 *   Operator  #/operator/review — review / approval / feedback
 *   Developer #/developer/*     — dashboard / runtime console
 *
 * The URL is the navigation boundary: unknown routes fall back to the
 * CONSUMER space, and the legacy localStorage mode key is no longer
 * consulted (a space is restored by its URL, never by client state).
 *
 * AUTH POLICY = DEFERRED OWNER DECISION — this boundary is navigation
 * only, not security; see
 * docs/production/phase-28e0-consumer-surface-design-audit.md §12.
 */
import { useRoute } from "./app/route";
import { ConsumerShell } from "./components/shell/ConsumerShell";
import { InternalShell } from "./components/shell/InternalShell";

export default function App() {
  const route = useRoute();
  if (route.space !== "consumer") {
    return <InternalShell route={route} />;
  }
  return <ConsumerShell reportRef={route.view === "report" ? route.ref : undefined} />;
}
