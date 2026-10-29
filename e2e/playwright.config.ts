import { defineConfig, devices } from "@playwright/test";

// Starts API (migrate + seed + uvicorn) and the Vite dev server, unless already running.
// PYTHON defaults to the backend venv; CI sets PYTHON=python.
const python = process.env.PYTHON ?? ".venv/bin/python";
const reuse = !process.env.CI;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `${python} -m alembic upgrade head && ${python} scripts/seed_demo.py && ${python} -m uvicorn app.main:app --port 8000`,
      cwd: "../backend",
      url: "http://localhost:8000/health/ready",
      reuseExistingServer: reuse,
      timeout: 60_000,
    },
    {
      command: "npm run dev -- --port 5173 --strictPort",
      cwd: "../frontend",
      url: "http://localhost:5173",
      reuseExistingServer: reuse,
      timeout: 60_000,
    },
  ],
});
