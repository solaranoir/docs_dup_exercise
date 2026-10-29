/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const api = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  // Same-origin /api in dev and on Render (static-site rewrite), so the session cookie works.
  server: { port: 5173, proxy: { "/api": api, "/health": api } },
  preview: { port: 4173, proxy: { "/api": api, "/health": api } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/setupTests.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
