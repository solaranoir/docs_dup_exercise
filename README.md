# Solara Docs

Technical notes, field logs and experiments for [Solara Radio](https://solararadio.netlify.app).
A private, invite-only document workspace: write formatted documents, import `.txt` / `.md` /
`.docx`, attach files, and share documents read-only with other members by email.

**Live:** https://docworkspace-web.onrender.com · reached from Solara Radio → Tools, and links
back there from every page.

_README updated 2026-11-04._ The previous MVP README is archived in
[History and archive](#history-and-archive).

## What it does

- **Sign in with GitHub or Google.** Only invited email addresses can sign in (an allowlist kept
  by the operator). Sessions are server-side, in an HttpOnly cookie.
- **Write.** Rich-text editor with headings, bold/italic/underline, lists and four text sizes.
  Saving is explicit (Save button or Ctrl/⌘+S), with an unsaved-changes indicator, a warning
  before leaving, and conflict detection if the document changed in another tab.
- **Import** `.txt`, `.md` and `.docx` as a new document, or append/replace into an existing one.
  A preview lists anything the import cannot keep (tables, images, colours…) before saving.
- **Attach** files to a document (10 MB each, up to 10 per document), stored privately in
  Cloudflare R2 and downloaded through the API.
- **Share** a document read-only with another member by email. There is no user directory: the
  person must have signed in once. The owner can revoke access at any time.

The interface uses Solara Radio's visual foundation (midnight/gunmetal surfaces, copper and sage
controls, Georgia headings) and works on phones.

## Stack

React 19 + Tiptap 3 (Vite) · FastAPI · PostgreSQL 16 (documents as JSONB) · Cloudflare R2
(S3-compatible) · Render (static site + web service + Postgres). The static site rewrites `/api/*`
to the API, so the browser sees one origin and the session cookie stays first-party.

```
backend/        FastAPI app (app/), Alembic migrations, tests, scripts/
frontend/       React + Tiptap single-page app
e2e/            Playwright journeys
docs/           Roadmap, runbook, security audit, readiness gates, ADRs, archive
scripts/        smoke_deployed.sh (post-deploy verification)
render.yaml     Render Blueprint
```

Architecture: [ARCHITECTURE.md](ARCHITECTURE.md) · Decisions: [docs/adr/](docs/adr/) (ADR-001 …
ADR-009; authentication is [ADR-009](docs/adr/0009-oauth-allowlist-authentication.md)) ·
Roadmap: [docs/ROADMAP.md](docs/ROADMAP.md) · Operations: [docs/RUNBOOK.md](docs/RUNBOOK.md) ·
Release gates: [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md) · Security audit:
[docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md)

## Run it locally

Prerequisites: Python 3.12+, Node 22+, Docker (Docker Desktop, OrbStack or colima). [mise](https://mise.jdx.dev)
pins Node and Python via `mise.toml`.

```bash
mise install
cp .env.example backend/.env          # local defaults, including ENABLE_DEMO_AUTH=true
docker compose up -d db               # PostgreSQL 16 in a project-scoped volume

cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.lock && pip install -e . --no-deps
alembic upgrade head
python scripts/seed_demo.py           # demo users Alice, Bob, Charlie (only with demo auth on)
python -m moto.server -p 9000 &       # in-memory S3 for attachments
uvicorn app.main:app --reload         # http://localhost:8000/docs

cd ../frontend
npm ci
npm run dev                           # http://localhost:5173 (proxies /api to :8000)
```

Locally, the sign-in page offers the demo identities **Alice** (owner), **Bob** (recipient) and
**Charlie** (no access). Demo sign-in exists only when `ENABLE_DEMO_AUTH=true`; the API refuses
to start with it in production. To try real OAuth locally, create separate development OAuth
apps with the callback `http://localhost:5173/api/auth/{github,google}/callback` and fill in the
`GITHUB_*` / `GOOGLE_*` values.

Health: `curl localhost:8000/health/live` and `/health/ready` (reports `database` and `storage`).

## Tests

```bash
cd backend  && ruff check . && ruff format --check . && mypy && pytest
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
cd e2e      && npm ci && npx playwright install chromium && npx playwright test
```

Run `pytest` against PostgreSQL by setting `TEST_DATABASE_URL` (for example a
`docworkspace_test` database in the docker container); without it the suite falls back to
SQLite. Playwright starts moto, the API and Vite itself and uses `DATABASE_URL` from the
environment, so point it at a scratch database. CI runs all three suites on PostgreSQL 16 for
every pull request.

## Configuration

Backend settings live on **docworkspace-api** only; secrets never go on the static site.

| Name | Purpose |
| --- | --- |
| `ENVIRONMENT` | `development` / `production`. Production enforces https origins, a real `SESSION_SECRET` and demo auth off |
| `DATABASE_URL` | PostgreSQL URL (`postgres://` is normalised to the psycopg driver) |
| `SESSION_SECRET` | Signs the short-lived OAuth flow cookie |
| `CORS_ORIGINS` | JSON list of trusted browser origins, used for CORS and the CSRF origin check |
| `PUBLIC_BASE_URL` | Public web origin for OAuth callbacks (defaults to the first `CORS_ORIGINS` entry) |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | GitHub sign-in; the provider appears only when both are set |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google sign-in (a *Web application* OAuth client) |
| `ENABLE_DEMO_AUTH` | Development/tests only: seeded Alice/Bob/Charlie sign-in |
| `SESSION_IDLE_SECONDS` / `SESSION_ABSOLUTE_SECONDS` | Session lifetime, default 7 days idle / 30 days absolute |
| `STORAGE_ENDPOINT`, `STORAGE_BUCKET`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`, `STORAGE_REGION` | Private object storage (R2: region `auto`). Without a bucket, attachments return 503 |
| `STORAGE_AUTO_CREATE_BUCKET` | Local/CI only |
| `MAX_UPLOAD_BYTES` / `MAX_ATTACHMENTS_PER_DOCUMENT` | Defaults 10 MB / 10 |
| `LOGIN_RATE_LIMIT_PER_MINUTE` / `UPLOAD_RATE_LIMIT_PER_MINUTE` | Defaults 20 per IP / 30 per user |
| `LOG_LEVEL` | Default `INFO`; JSON log lines with `request_id` |
| `VITE_API_BASE_URL` | Frontend build: API origin; empty = same-origin `/api` |
| `VITE_SOLARA_TOOLS_URL` | Frontend build: "Solara Radio Tools" return link (default `https://solararadio.netlify.app/tools`) |

## Operating it

Inviting people, removing access, OAuth setup, deploys, rollback and the production cut-over
are in the [runbook](docs/RUNBOOK.md). The common ones:

```bash
# Render → docworkspace-api → Shell
python scripts/allow_email.py add someone@example.com      # invite
python scripts/allow_email.py remove someone@example.com   # revoke and end their sessions
python scripts/allow_email.py list
```

Deploys come from `main` through `render.yaml`. Migrations run before the API starts. After a
deploy, run `scripts/smoke_deployed.sh "" "" <commit>`; set `SMOKE_SESSION` to a session cookie
value to include the signed-in journey.

## Limitations and what's next

No real-time collaboration, comments, version history, public links, editor (write) grants or
autosave yet. Imports are best-effort, attachments are not virus-scanned
([#29](https://github.com/solaranoir/docs_dup_exercise/issues/29)), and rate limits are
per-instance. The remaining roadmap phases (document organisation, search, export, deletion and
recovery, revision history) are in [docs/ROADMAP.md](docs/ROADMAP.md).

## History and archive

This repository began as the **Document Workspace MVP**, planned as four weekly milestones and
delivered on 2026-10-29: a single-user editor with view-only sharing between seeded demo identities. Its plan and delivery
log are in [docs/PLAN.md](docs/PLAN.md). In November 2026 it was turned into Solara Docs:

| Date | Change |
| --- | --- |
| 2026-10-29 | MVP weeks 1–4: editor and documents, imports and sharing, attachments, hardening and release |
| 2026-11-04 | Roadmap, security audit and readiness gates; Render Postgres upgraded to a paid plan |
| 2026-11-04 | Identity schema and invite allowlist; server-side sessions and CSRF origin check; demo sign-in off in production |
| 2026-11-04 | GitHub and Google sign-in; share by email; cross-user isolation tests; cut-over tooling |
| 2026-11-04 | Solara look and feel, return link to Solara Radio Tools, onboarding, phone layout |

The original MVP README, with its setup instructions as they were, is preserved at
[docs/archive/README-mvp.md](docs/archive/README-mvp.md). Superseded decisions remain in
[docs/adr/](docs/adr/) and are marked as such (ADR-004, seeded demo identities, is superseded by
ADR-009).
