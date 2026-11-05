# Architecture — Solara Docs (Document Workspace MVP)

A single-user editing and explicit-sharing workspace: create and format documents, import
`.txt`/`.md`/`.docx`, attach files, and share view-only with other seeded users. Designed as a
reliable, demo-quality vertical slice, not real-time collaboration.

## System overview

```
Browser (React 19 + Tiptap 3)
   │  same origin: https://docworkspace-web.onrender.com
   ▼
Render static site ── /api/* rewrite ──► FastAPI (Render web service)
   (CSP, security headers)                 │  auth · policy · validation · imports
                                           ├──► PostgreSQL 16 (Render)  users, documents (JSONB), grants, attachment metadata
                                           └──► Cloudflare R2 (private)  attachment bytes
```

- **Frontend** (`frontend/`): React 19 + Vite, Tiptap 3 editor, hash routing (`#/doc/:id`).
  The editor and import preview are lazy-loaded, so the initial bundle is about 228 kB.
- **API** (`backend/app/`): FastAPI, SQLAlchemy 2, Alembic migrations, Pydantic validation.
- **Storage:** PostgreSQL holds all structured data; R2 holds attachment bytes only. Nothing is
  written to the service disk (Render's filesystem is ephemeral).

## Request flow

1. The browser calls `/api/...` on its own origin; the static site rewrites to the API, so the
   signed session cookie stays first-party (`onrender.com` subdomains are cross-site).
2. Middleware assigns a request id, adds security headers and writes a JSON access log line.
3. `auth.py` derives the principal from the signed session; no route trusts a client user id.
4. `policy.py` decides owner / editor / viewer / none (deny by default). No access → **404**,
   so a document's existence is not revealed; a viewer writing → **403**.
5. Writes use compare-and-swap on `revision` (`UPDATE … WHERE revision = expected`); a stale
   save returns **409** and the UI offers "Reload latest version".

## Data model

| Table | Key fields | Integrity |
| --- | --- | --- |
| `users` | `login_key`, `display_name` | unique `login_key` |
| `documents` | `owner_id`, `title`, `content_json` (JSONB), `revision` | title 1–160, revision ≥ 1 |
| `document_grants` | `document_id`, `grantee_id`, `role`, `granted_by` | unique (document, grantee); role ∈ viewer/editor |
| `attachments` | `document_id`, `original_name`, `mime_type`, `size_bytes`, `object_key` | unique key; cascade on document delete |

`content_json` is the canonical Tiptap/ProseMirror JSON, validated server-side against an
allowlist of nodes, marks, attributes and font sizes (`content.py`). No HTML is ever stored.

## Imports and attachments

- **Validation** (`uploads.py`): extension allowlist, 10 MB streaming cap (413), UTF-8/NUL
  sniffing for text, ZIP structure and zip-bomb guard for `.docx` (415), basename-only filenames.
- **Conversion** (`imports.py`): every format becomes the editor's subset, with de-duplicated
  fidelity warnings (tables, images, links, HTML, deep headings…). The preview stores nothing;
  creating a document or Append/Replace into one is a separate, revision-checked step.
- **Attachments** (`storage.py`): object keys are `documents/{doc}/attachments/{uuid}` (never user
  input); downloads stream through the API after authorization with `Content-Disposition:
  attachment` and `nosniff`. Limit: 10 per document.

## Cross-cutting concerns

| Concern | Approach |
| --- | --- |
| Identity | Seeded Alice/Bob/Charlie, `itsdangerous`-signed session; demo only (ADR-004) |
| Abuse | Rate limits: 20 logins/min per IP, 30 uploads/min per user (in-process, per instance) |
| Browser security | Strict CSP, `X-Frame-Options: DENY`, `nosniff`, `no-referrer` |
| Observability | JSON logs with `request_id`; `/health/live` reports the deployed commit; `/health/ready` checks DB and storage |
| Configuration | Env vars only; secrets live in Render on the API service, never in git or the static site |

## Deployment and quality

- **Render Blueprint** (`render.yaml`): static site, API web service, managed PostgreSQL; R2
  credentials set in the dashboard. API start runs migrations and the idempotent seed.
- **CI** (every PR): ruff, mypy --strict, pytest on PostgreSQL 16; ESLint, tsc, Vitest, build;
  Playwright critical journeys with moto standing in for S3.
- **Post-deploy:** `scripts/smoke_deployed.sh` runs 20 checks through the live site (served
  commit, storage round trip, permission matrix) and cleans up after itself.

## Known limits and evolution

Single instance on Render's free tier (API sleeps when idle; free Postgres expires ~2026-11-28).
Not built: real-time collaboration, autosave (#27), editor grants and real authentication (#22),
virus scanning (#29). Collaborative editing would need a CRDT-based redesign instead of
whole-document revision checks.

Details: [docs/adr/](docs/adr/) (ADR-001…008), [docs/RUNBOOK.md](docs/RUNBOOK.md),
[README.md](README.md).
