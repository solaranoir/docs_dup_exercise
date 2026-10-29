# Document Workspace MVP

Single-user editing + explicit-user sharing workspace: React/Tiptap frontend, FastAPI API,
PostgreSQL persistence, S3-compatible attachment storage. Demo-quality release with seeded
identities (Alice, Bob, Charlie) — **not secure for public internet use** (see ADR-004).

Status: **Week 2 — Documents** (rich-text editor, document CRUD, revision conflicts, E2E).
Plan and task tracking: [docs/PLAN.md](docs/PLAN.md) and the GitHub issues.

## Layout

```
backend/        FastAPI app (app/), Alembic migrations, tests, scripts/seed_demo.py
frontend/       React + Tiptap (Week 2)
e2e/            Playwright suites (Week 2–4)
docs/           Plan, ADRs
render.yaml     Render Blueprint
```

## Local run (backend)

Prerequisites: Python 3.12+, Node 22+, PostgreSQL 16. Recommended contained setup (no global
services): [mise](https://mise.jdx.dev) pins Node/Python via `mise.toml`, and Postgres/MinIO run
in containers (Docker Desktop, OrbStack, or `brew install colima docker docker-compose &&
colima start`).

```bash
mise install                          # Node 22 + Python 3.12 from mise.toml
cp .env.example backend/.env          # adjust DATABASE_URL / SESSION_SECRET
docker-compose up -d db               # or `docker compose`; data in a project-scoped volume
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock && pip install -e . --no-deps
alembic upgrade head
python scripts/seed_demo.py           # idempotent
uvicorn app.main:app --reload         # http://localhost:8000/docs
```

Check: `curl localhost:8000/health/live`, `curl localhost:8000/health/ready`.

## Local run (frontend)

```bash
cd frontend
npm ci
npm run dev                           # http://localhost:5173, proxies /api to :8000
```

Sign in as Alice/Bob/Charlie, then **New document**. Save with the button or Ctrl/Cmd+S.
Saving is manual: **autosave is not available yet** (planned for a future release, see
[#27](https://github.com/solaranoir/docs_dup_exercise/issues/27)). The status indicator shows
unsaved changes, and the app warns before you leave with unsaved edits.

Demo login: `POST /api/demo/login {"login_key": "alice"}` sets an httpOnly signed session
cookie and also returns a bearer token (for API tests). `GET /api/me` returns the principal.

## Tests and checks

```bash
cd backend  && ruff check . && ruff format --check . && mypy && pytest
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
cd e2e      && npm ci && npx playwright install chromium && npx playwright test
```

Playwright starts the API (migrate + seed + uvicorn on :8000) and Vite (:5173) itself unless
they are already running; it uses `DATABASE_URL` from the environment.

`pytest` uses `TEST_DATABASE_URL` when set (PostgreSQL in CI); otherwise a temporary SQLite
file so the suite runs without a server. CI on every PR runs everything against PostgreSQL 16.

## Environment variables

| Name | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL URL (`postgres://` is normalised to psycopg driver) |
| `SESSION_SECRET` | Signs demo sessions; required when `ENVIRONMENT=production` |
| `ENVIRONMENT` | `development` / `production` (secure cookies, secret check) |
| `CORS_ORIGINS` | JSON list of allowed browser origins |
| `STORAGE_*` | Object storage (Week 3) |
| `VITE_API_BASE_URL` | Optional API origin; empty = same origin (`/api` proxied/rewritten) |

## Deploy (Render)

1. Render dashboard → **New → Blueprint** → select this repo; `render.yaml` provisions
   `docworkspace-db` (PostgreSQL), `docworkspace-api` (FastAPI) and `docworkspace-web`
   (static site; rewrites `/api/*` to the API so the session cookie is first-party).
2. `SESSION_SECRET` is generated; set `CORS_ORIGINS` once the frontend URL exists.
3. Start command runs `alembic upgrade head` and the idempotent seed, then uvicorn on `$PORT`.
4. Verify `https://<api>.onrender.com/health/ready` returns `{"status":"ok"}`.

Free plan caveats: the web service sleeps when idle; free PostgreSQL expires after 30 days.

## Known limitations (MVP)

No real-time collaboration, comments, version history, public links, email invites, SSO, or
offline sync. Demo identities must be replaced with real auth before public release.

Planned for future releases (post-MVP, not available yet):

- **Autosave** — the MVP uses explicit Save (button or Ctrl/Cmd+S) with an unsaved-changes
  indicator and leave-page warnings. Autosave will be considered in a future release
  ([#27](https://github.com/solaranoir/docs_dup_exercise/issues/27)).
- **More text sizes** — the editor offers four fixed sizes (Small, Normal, Large, Extra large);
  additional fixed sizes are tracked in
  [#26](https://github.com/solaranoir/docs_dup_exercise/issues/26).
