# Document Workspace MVP

Single-user editing + explicit-user sharing workspace: React/Tiptap frontend, FastAPI API,
PostgreSQL persistence, S3-compatible attachment storage. Demo-quality release with seeded
identities (Alice, Bob, Charlie) — **not secure for public internet use** (see ADR-004).

Status: **Week 1 — Foundation** (API skeleton, schema, demo login, health, CI, Render Blueprint).
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

Demo login: `POST /api/demo/login {"login_key": "alice"}` sets an httpOnly signed session
cookie and also returns a bearer token (for API tests). `GET /api/me` returns the principal.

## Tests and checks

```bash
cd backend
ruff check . && ruff format --check . && mypy && pytest
```

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

## Deploy (Render)

1. Render dashboard → **New → Blueprint** → select this repo; `render.yaml` provisions
   `docworkspace-db` (PostgreSQL) and `docworkspace-api` (FastAPI).
2. `SESSION_SECRET` is generated; set `CORS_ORIGINS` once the frontend URL exists.
3. Start command runs `alembic upgrade head` and the idempotent seed, then uvicorn on `$PORT`.
4. Verify `https://<api>.onrender.com/health/ready` returns `{"status":"ok"}`.

Free plan caveats: the web service sleeps when idle; free PostgreSQL expires after 30 days.

## Known limitations (MVP)

No real-time collaboration, comments, version history, public links, email invites, SSO, or
offline sync. Demo identities must be replaced with real auth before public release.
