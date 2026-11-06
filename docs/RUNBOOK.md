# Runbook — Document Workspace on Render

## Services

| Service | Type | URL | Notes |
| --- | --- | --- | --- |
| `docworkspace-web` | Static site | https://docworkspace-web.onrender.com | Rewrites `/api/*` → API; CSP + security headers |
| `docworkspace-api` | Python web service (Starter) | https://docworkspace-api.onrender.com | Always on; migrations run as a pre-deploy step |
| `docworkspace-db` | PostgreSQL 16 (`basic-256mb`) | internal | Paid plan: backups, no expiry |
| R2 bucket | Cloudflare R2 | `document-workspace-attachments` | Private; credentials only in Render env |

All three Render resources are managed by the Blueprint (`render.yaml`, branch `main`).

## Deploy

1. Merge a PR to `main` → Render auto-deploys the API and static site; the Blueprint syncs
   `render.yaml` changes (new services/env keys). Check **Blueprints → Syncs** after changing it.
2. API deploy: build → **pre-deploy** `python scripts/migrate.py` (`alembic upgrade head`, once,
   before the new instance starts) → uvicorn on `$PORT` behind Render's proxy → `/health/ready` must pass before traffic
   moves over. A failed migration or health check fails the deploy and the previous version keeps
   serving. No demo seed in production (ADR-009).
3. Verify, automatically: the **Post-deploy smoke** GitHub Action (`.github/workflows/deploy-smoke.yml`)
   runs on every push to `main`. It waits (up to 25 min) until `/health/live` reports the pushed
   commit, then runs `scripts/smoke_deployed.sh` anonymously: served commit, database and storage
   readiness, static site and deep links, security headers, 401s for signed-out calls, cross-site
   writes blocked, demo sign-in off, OAuth offered. It also runs daily at 13:17 UTC and can be run by
   hand (Actions → Post-deploy smoke → Run workflow). A failure emails whoever pushed.
4. At release, also run the signed-in journey by hand (below: Smoke test against production).

Render deploys on every commit rather than waiting for CI (`autoDeployTrigger: checksPass`):
the post-deploy smoke run is itself a check on the merged commit, so Render would wait for a run
that is waiting for Render. Branch protection keeps failing code out of `main` instead.

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
| Sign-in page shows no GitHub/Google buttons, or errors | `/api` rewrite not reaching the API, or API down | Check `/health/live` on the API URL; check static site **Redirects/Rewrites** (`/api/*` → API `/api/*`) |
| `429 Too many requests` | Rate limit (20 logins/min/IP, 30 uploads/min/user) | Wait for `Retry-After`; tune `LOGIN_RATE_LIMIT_PER_MINUTE` / `UPLOAD_RATE_LIMIT_PER_MINUTE` |
| `409` on save | Document changed elsewhere | Expected: UI offers "Reload latest version" |
| Deploy **failed** in the pre-deploy step | Migration error | Previous version is still serving. Read the deploy log, fix forward in a PR; see Rollback and migrations |
| Post-deploy smoke: "did not serve <commit> within 25 minutes" | Deploy failed, is stuck, or served stale code (#30) | Check API → Events; for a stale build, **Clear build cache & deploy** |

## Rollback and migrations

**Rule for migrations: the previous release must run against the new schema.** Add columns as
nullable (or with a server default), add tables and indexes freely; never rename or drop in the
same release that stops using something. Remove it one release later. Every migration so far
(0001–0006) follows this, so rolling back code never needs a schema downgrade. Each migration
also has a working `downgrade()`; CI checks `downgrade -1`, `downgrade base` and `upgrade head`
against seeded data on every PR.

- **Roll back code** (first choice): Render → docworkspace-api (or -web) → Events → the last good
  deploy → **Rollback**, or revert the PR on GitHub and let auto-deploy run (do this as well after
  a Rollback, or the next push brings the bad commit back). Either way the older code meets a
  database migrated past what it knows. `scripts/migrate.py` sees that, logs "database is at …,
  newer than this code's migrations", and leaves the schema alone instead of failing the deploy;
  the rule above makes the older code safe on it. (A plain `alembic upgrade head` would fail
  with "Can't locate revision".)
- **A migration failed during deploy:** nothing to roll back. The pre-deploy step runs in a
  transaction (PostgreSQL DDL is transactional), the deploy is marked failed, and the previous
  version keeps serving. Fix forward.
- **Schema downgrade** (rare: only if a migration itself is wrong): Render → docworkspace-api →
  Shell, *while the newer code is still deployed* (it has the migration's `downgrade()`):
  `alembic current`, then `alembic downgrade -1`, then roll back the code. A downgrade that drops a column or table **destroys the data in it**: take
  a backup first (database → Recovery / Backups) and say so in the incident notes.
- **Data:** the paid database has daily backups and point-in-time recovery (Recovery tab).
  Practise a restore into a scratch database before relying on it (PRODUCTION_READINESS →
  restore drill). Attachment objects in R2 are only deleted when a document is deleted for good.

## OAuth sign-in (ADR-009)

| Provider | Where | Callback URL |
| --- | --- | --- |
| GitHub | Settings → Developer settings → OAuth Apps | `https://docworkspace-web.onrender.com/api/auth/github/callback` |
| Google | Cloud Console → APIs & Services → Credentials (Web application) | `https://docworkspace-web.onrender.com/api/auth/google/callback` |

Set `GITHUB_CLIENT_ID/SECRET` and `GOOGLE_CLIENT_ID/SECRET` on `docworkspace-api`. A provider
shows on the sign-in page only when both of its values are set (`GET /api/auth/methods`).
Callbacks use the web origin (first `CORS_ORIGINS` entry, or `PUBLIC_BASE_URL`), so the
`/api/*` rewrite keeps cookies first-party. Google needs a client of type **Web application**
(a Desktop client has no redirect URI field), and while its audience is in Testing mode only
listed test users can sign in. Both providers accept several redirect URIs. Prefer separate
dev apps or clients (callback `http://localhost:5173/api/auth/{provider}/callback`) so
laptops never hold the production secrets.

Sign-in failures redirect to `/?auth_error=<reason>` and log
`sign-in failed provider=… reason=…` (never emails or tokens):

| Reason | Meaning / fix |
| --- | --- |
| `not_invited` | Email not on the allowlist → `allow_email.py add` |
| `unverified_email` | GitHub primary / Google email not verified at the provider |
| `expired` | Flow cookie missing or older than 10 min (slow sign-in, blocked cookies) |
| `cancelled` | User declined on the provider's consent screen |
| `failed` | State mismatch, provider error, or wrong client secret/callback URL (see `detail=`) |

## Invite allowlist (ADR-009)

Only allowlisted emails can sign in once OAuth ships. From `backend/` locally (with
`DATABASE_URL` set), or in the Render API service's **Shell** tab:

```bash
python scripts/allow_email.py add someone@example.com --note "POTA club"
python scripts/allow_email.py list
python scripts/allow_email.py remove someone@example.com   # ends their sessions at once
```

Removing an email keeps the user's documents, and re-adding it restores access.


## Production cut-over: remove demo data

One-off, after OAuth sign-in works. In the Render API service's **Shell** tab:

```bash
python scripts/purge_demo_data.py          # dry run: lists demo users, documents, grants, objects
python scripts/purge_demo_data.py --yes    # deletes them (database first, then R2 objects)
```

It removes only users with a `login_key` (Alice/Bob/Charlie) and their sessions, documents,
grants and attachments, including uploads they made into other documents and grants made to
them. Real (OAuth) accounts are untouched. It refuses to run if a demo user has an OAuth
identity, or if attachment objects exist while storage is unconfigured. Objects it cannot
delete from R2 are listed (exit code 1) for manual removal. Re-running it is harmless.

## Trash and permanent deletion (ADR-012)

Deleting a document moves it to its owner's Trash. Nobody else can see it there, and the owner
can restore it with its shares, attachments, folder and tags. After 30 days the API removes it
and its attachment objects for good. This runs inside the API (no separate cron job to pay for
or monitor), at most once an hour per instance, after someone loads My Documents or their Trash. To check or run it by hand:

```bash
# Render → docworkspace-api → Shell
python scripts/purge_trash.py          # dry run: how many documents are in Trash and due
python scripts/purge_trash.py --yes    # remove everything past 30 days now
```

A document can't be recovered after it's removed (or after its owner chooses *Delete forever*),
except from a database backup. If the script reports attachment objects it could not delete,
they are orphans in R2 and safe to remove there.

## Smoke test against production

```bash
scripts/smoke_deployed.sh                                  # anonymous checks only
SMOKE_SESSION=<__Host-sd_session value> scripts/smoke_deployed.sh   # + document journey
```

Copy the cookie value from DevTools → Application → Cookies after signing in. It is a live
session, so don't paste it anywhere shared, and sign out afterwards to end it. Sharing checks
run only where demo sign-in is enabled (local/CI).
## Secrets and configuration

Set on **docworkspace-api** only (never on the static site — its env is baked into public JS):
`SESSION_SECRET` (Blueprint-generated), `STORAGE_ENDPOINT`, `STORAGE_BUCKET`,
`STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`. `STORAGE_REGION=auto` comes from `render.yaml`.
Rotating `SESSION_SECRET` signs everyone out (harmless for the demo).

## Costs (as deployed for v1.0)

Paid: Starter web service for the API, `basic-256mb` Postgres (backups, no expiry). Free: the
static site, R2 within its free tier, and GitHub Actions minutes for the smoke runs (a few
minutes per deploy plus one daily run). Check Render's and Cloudflare's pricing pages for current
amounts. Both plans are pinned in `render.yaml`, so a Blueprint sync never downgrades them.
