# Security audit — pre–Solara Docs (2026-11-04)

Scope: identity, authorization, attachments, sessions/CSRF/CORS, hosting and data durability,
audited at `main` @ `1584a48` against roadmap Phase 1 (DOC-001 … DOC-008). Severity: **P0** blocks
v0.5 (any real user), **P1** blocks v1.0, **P2** tracked.

## Summary

The authorization layer is sound: `policy.py` is deny-by-default, and every document,
attachment, import and grant route resolves access through `load_document` /
`load_editable`. No route trusts a client-supplied user id. Hidden documents return 404 and
view-only writes return 403. The release blockers are **identity** (anyone can be anyone) and
**data durability** (the database expires on 2026-11-28).

## Findings

| # | Sev | Area | Finding | Evidence | Fix (roadmap) |
| --- | --- | --- | --- | --- | --- |
| A1 | P0 | Identity | `POST /api/demo/login {"login_key": "alice"}` signs in as any user with no credential. | `routes/demo.py` | OAuth + allowlist, demo routes off in production (DOC-001, DOC-004, ADR-009) |
| A2 | P0 | Identity | `GET /api/demo/users` lists every account unauthenticated: user enumeration once accounts carry real names/emails. | `routes/demo.py`, `ShareDialog.tsx` | Remove; share by email (DOC-004) |
| A3 | P0 | Durability | Render free Postgres expires ~2026-11-28; all documents, grants and attachment metadata go with it. | `render.yaml` (`plan: free`) | Upgrade to paid plan with backups (DOC-007) |
| A4 | P0 | Ops | Production start runs `seed_demo.py`, recreating Alice/Bob/Charlie on every boot. | `render.yaml` startCommand | Seed only outside production (DOC-004) |
| A5 | P1 | Sessions | Sessions are stateless signed tokens: logout only clears the browser cookie; a copied token stays valid for 12 h and cannot be revoked server-side. | `auth.py`, `demo_logout` | Server-side session table, hashed tokens, revoke on logout (DOC-005) |
| A6 | P1 | Sessions | Login returns the session token in the JSON body, so it is readable by page JavaScript despite the httpOnly cookie. | `LoginOut.token` | Cookie only; tests use a test-only helper (DOC-005) |
| A7 | P1 | CSRF | No CSRF token. JSON writes are protected by CORS preflight and `SameSite=Lax`, but multipart uploads (`/attachments`, `/imports`) are "simple" requests. Safe today only because `onrender.com` is on the Public Suffix List; a shared custom domain (e.g. `docs.` beside other Solara subdomains) would make sibling hosts same-site. | `main.py`, `auth.py` | Reject unsafe methods whose `Origin` / `Sec-Fetch-Site` is not the app origin (DOC-005) |
| A8 | P1 | Cookies | Cookie is `dw_session` without the `__Host-` prefix, so a sibling subdomain could set or shadow it. | `auth.py` | `__Host-sd_session; Secure; Path=/` (DOC-005) |
| A9 | P1 | Sharing | Grants target a numeric `user_id`; with real users, ids are guessable and owners can share with anyone in the database. | `routes/grants.py` | Grant by email of an existing account (DOC-003) |
| A10 | P1 | Testing | Cross-user tests cover read/revoke and attachments; there is no single matrix proving **every** endpoint denies a stranger. | `tests/test_grants.py`, `test_attachments.py` | Parametrized route × role isolation test (DOC-008) |
| A11 | P2 | Abuse | Rate limits are in-process (reset on restart, not shared across instances). | `ratelimit.py` | Acceptable single-instance; revisit before scaling |
| A12 | P2 | Storage | Failed R2 deletes leave orphaned objects (logged only); no reconciliation. | `attachments.py`, `documents.py` | Periodic orphan sweep (DOC-031) |
| A13 | P2 | Backups | R2 has no versioning or lifecycle policy documented; Postgres restore never rehearsed. | `docs/RUNBOOK.md` | Restore drill in readiness checklist (DOC-007) |

## Verified OK

- Document read/update/delete, attachments list/upload/download/delete, imports and grant
  management all authorize through `policy.py`; attachment lookups also check
  `attachment.document_id == doc_id` (no cross-document id reuse).
- Downloads stream through the API after authorization with `Content-Disposition: attachment`,
  `nosniff`, `Cache-Control: private, no-store`; object keys never contain user input.
- Content is validated server-side against a node/mark allowlist; no HTML is stored.
- Uploads: extension allowlist, 10 MB streaming cap, docx zip-bomb guard.
- CORS: explicit origin list with credentials; production refuses the dev session secret.
- Security headers and CSP on both API and static site.
