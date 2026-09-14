import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    // Same-origin in dev too (docs/adr/0010-frontend-hosting.md §3): the browser only ever
    // talks to the Vite origin, which proxies /api through to `make serve-mock`'s backend —
    // no CORS needed anywhere, in dev or in production.
    proxy: {
      "/api": "http://127.0.0.1:8080",
    },
  },
  test: {
    environment: "jsdom",
  },
});
