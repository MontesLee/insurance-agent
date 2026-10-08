import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev proxy: the UI talks to the FastAPI runtime server as if same-origin.
// The runtime stays the single source of truth — the UI only consumes it.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        // Pilot canon (phase-28k / phase-28k-final-exit-audit): the live
        // backend runs on :8123 (python -m runtime.server, strict);
        // :8000 is documented as STOPPED (phase-28j §5, OWNER_DECISION).
        // Defaulting to :8000 here silently produced ECONNREFUSED on
        // every /api call whenever the dev server was started without
        // RUNTIME_API — the browser then received zero events (no live
        // streaming deltas). RUNTIME_API still overrides.
        target: process.env.RUNTIME_API ?? "http://127.0.0.1:8123",
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
