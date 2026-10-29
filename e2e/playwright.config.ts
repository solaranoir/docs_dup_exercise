import { defineConfig, devices } from "@playwright/test";

// Starts API (migrate + seed + uvicorn) and the Vite dev server, unless already running.
// PYTHON defaults to the backend venv; CI sets PYTHON=python.
const python = process.env.PYTHON ?? ".venv/bin/python";
const reuse = !process.env.CI;

// Local S3-compatible server (moto) so attachments run end-to-end without cloud credentials.
const storageEnv = {
  STORAGE_ENDPOINT: "http://localhost:9000",
  STORAGE_BUCKET: "e2e-attachments",
  STORAGE_ACCESS_KEY: "test",
  STORAGE_SECRET_KEY: "test",
  STORAGE_REGION: "us-east-1",
  STORAGE_AUTO_CREATE_BUCKET: "true",
  // The suite logs in far more than a person would; production limits are tested in pytest.
  LOGIN_RATE_LIMIT_PER_MINUTE: "1000",
  UPLOAD_RATE_LIMIT_PER_MINUTE: "1000",
};

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
      command: `${python} -m moto.server -p 9000`,
      cwd: "../backend",
      url: "http://localhost:9000/moto-api/",
      reuseExistingServer: reuse,
      timeout: 60_000,
    },
    {
      command: `${python} -m alembic upgrade head && ${python} scripts/seed_demo.py && ${python} -m uvicorn app.main:app --port 8000`,
      cwd: "../backend",
      url: "http://localhost:8000/health/ready",
      env: { ...storageEnv, ...(process.env.DATABASE_URL ? { DATABASE_URL: process.env.DATABASE_URL } : {}) },
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
