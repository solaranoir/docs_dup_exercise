# Runbook — Document Workspace on Render

## Services

| Service | Type | URL | Notes |
| --- | --- | --- | --- |
| `docworkspace-web` | Static site | https://docworkspace-web.onrender.com | Rewrites `/api/*` → API; CSP + security headers |
| `docworkspace-api` | Python web service (free) | https://docworkspace-api.onrender.com | Sleeps when idle; first request ~30–50 s |
| `docworkspace-db` | PostgreSQL 16 (free) | internal | **Expires ~2026-11-28** (30 days) |
| R2 bucket | Cloudflare R2 | `document-workspace-attachments` | Private; credentials only in Render env |

All three Render resources are managed by the Blueprint (`render.yaml`, branch `main`).

## Deploy

1. Merge a PR to `main` → Render auto-deploys the API and static site; the Blueprint syncs
   `render.yaml` changes (new services/env keys). Check **Blueprints → Syncs** after changing it.
2. API start command: `alembic upgrade head` → `python scripts/seed_demo.py` (idempotent, every
   start — user decision) → uvicorn on `$PORT` behind Render's proxy.
3. Verify (≈1 min): `scripts/smoke_deployed.sh "" "" <commit>` from a clone. It warms the API,
   asserts the **served commit**, database and storage readiness, then exercises login, import,
   append, 409, attachment round-trip, share/revoke, 415, and deletes its test data.

## Health and logs

- `GET /health/live` → `{"status":"ok","commit":"<sha>"}` (commit from `RENDER_GIT_COMMIT`).
- `GET /health/ready` → `database` (`ok` or 503) and `storage` (`ok` / `error` / `unconfigured`).
  Storage errors do **not** fail readiness, so Render won't restart a healthy API over R2 issues.
- Logs are JSON lines with `request_id`, `method`, `path`, `status`, `duration_ms`. Clients can
  pass `X-Request-ID` (≤64 safe chars) and every response echoes it. File contents and request
  bodies are never logged.

## Common incidents

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Deploy shows **Live** but routes/`commit` are old | Stale build (#30) | API → Manual Deploy → **Clear build cache & deploy**; rerun smoke test |
| `/health/ready` `storage: error` | R2 credentials/endpoint wrong or R2 outage | Check `STORAGE_*` on **docworkspace-api** → Environment; attachments return 503 until fixed |
| Static site 404 with `x-render-routing: no-server` | Site not created / routing still propagating | Blueprint → Manual sync; wait a few minutes after creation |
| Login page shows no users | `/api` rewrite not reaching API, or API asleep | Open the API URL to wake it; check static site **Redirects/Rewrites** (`/api/*` → API `/api/*`) |
| `429 Too many requests` | Rate limit (20 logins/min/IP, 30 uploads/min/user) | Wait for `Retry-After`; tune `LOGIN_RATE_LIMIT_PER_MINUTE` / `UPLOAD_RATE_LIMIT_PER_MINUTE` |
| `409` on save | Document changed elsewhere | Expected: UI offers "Reload latest version" |
| DB unavailable after ~30 days | Free Postgres expired | Upgrade the DB plan before ~2026-11-28 |

## Rollback

- **Code:** Render → docworkspace-api (or -web) → Events → pick the last good deploy → **Rollback**.
  Or revert the PR on GitHub and let auto-deploy run.
- **Schema:** migrations are additive so far (single `0001`); rolling back code does not require
  a downgrade. For future migrations, run `alembic downgrade -1` from the Render Shell only if the
  previous code cannot read the new schema.
- **Data:** free Postgres has no point-in-time recovery; paid plans include backups. Attachment
  objects are only deleted when their document/attachment is deleted.

## Secrets and configuration

Set on **docworkspace-api** only (never on the static site — its env is baked into public JS):
`SESSION_SECRET` (Blueprint-generated), `STORAGE_ENDPOINT`, `STORAGE_BUCKET`,
`STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`. `STORAGE_REGION=auto` comes from `render.yaml`.
Rotating `SESSION_SECRET` signs everyone out (harmless for the demo).

## Costs (free tier, as deployed)

$0: free web service (sleeps when idle), free static site, free Postgres (expires after 30 days),
R2 free tier. Upgrade path: Starter web service (no sleep), Basic Postgres (backups, no expiry).
Check Render's pricing page for current amounts.
