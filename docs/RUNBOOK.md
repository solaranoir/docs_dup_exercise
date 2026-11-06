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
and its attachment objects for good: the free plan has no cron, so this runs at most once an hour
per instance, after someone loads My Documents or their Trash. To check or run it by hand:

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

## Costs (free tier, as deployed)

$0: free web service (sleeps when idle), free static site, free Postgres (expires after 30 days),
R2 free tier. Upgrade path: Starter web service (no sleep), Basic Postgres (backups, no expiry).
Check Render's pricing page for current amounts.
