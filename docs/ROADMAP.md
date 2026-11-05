# Solara Docs roadmap

Source: *Solara Docs — Document Workspace Integration & Development Roadmap* (November 2026).
This turns the Document Workspace MVP into **Solara Docs**, a technical documentation and
field-notes workspace linked from Solara Radio → Tools. It stays a standalone deployment, and the
repository keeps its name. The MVP delivery history is in [PLAN.md](PLAN.md).

## Decisions (2026-11-04)

| Topic | Decision | Record |
| --- | --- | --- |
| Authentication | OAuth (GitHub + Google), server-side sessions | [ADR-009](adr/0009-oauth-allowlist-authentication.md) |
| Signup | Invite allowlist only during v0.5 | ADR-009 |
| Database | Render Postgres upgraded to a paid plan (2026-11-04); demo data disposable, removed at cut-over | [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) |
| Folders and tags | Personal per user; one-level folders, one per document; sharing stays per document; free-form tags with a starter set | [ADR-010](adr/0010-personal-folders-and-tags.md) |
| Templates | Four built-in templates in code, versioned; ordinary documents with labelled lines; picker behind New document; title prefilled with the local date | [ADR-011](adr/0011-built-in-templates.md) |
| Stack | Keep React/Tiptap, FastAPI, PostgreSQL, R2; no Redis, CRDT or AI in v1.0 | roadmap §9 |

## Releases

| Release | Phases | Exit condition |
| --- | --- | --- |
| v0.5 Secure Solara Preview | 1 Security, 2 Solara UI | [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) P0 gates pass |
| v1.0 Solara Docs | 3 Organization, 4 Templates, 5 Export, 6 QA | A new user creates a doc from a template, edits, attaches, organizes, exports and retrieves it; another user cannot read it without permission |
| v2.0 Connected workspace | Tool-to-document, cloud export | Validated demand |

## Pull request sequence

Security and visual changes never share a PR.

| PR | Scope | Roadmap items |
| --- | --- | --- |
| 1 | Audit, ADR-009, readiness gates, DB plan (this PR) | DOC-007 (plan), audit for DOC-001…008 |
| 2 | Schema: `user_identities`, `allowed_emails`, `sessions`; user `email`; allowlist CLI | DOC-002 |
| 3 | Server-side sessions, `__Host-` cookie, Origin-check CSRF middleware; demo auth gated off in production | DOC-004, DOC-005 |
| 4 | OAuth GitHub + Google: start/callback, account linking, sign-in page | DOC-001 |
| 5 | Share by email; drop user directory; isolation test matrix | DOC-003, DOC-006, DOC-008 |
| 6 | Deployed cut-over: OAuth apps, env vars, demo-data cleanup, smoke script, restore drill | DOC-007, v0.5 sign-off |
| 7+ | Solara branding, return-to-Solara nav, mobile layout, routing, onboarding, a11y | DOC-009…015 |

## Backlog by phase

**Phase 1: Security and production readiness (P0, 10–16 h).** DOC-001 real authentication ·
DOC-002 persistent identities · DOC-003 enforce ownership/grants everywhere · DOC-004 disable demo
impersonation · DOC-005 cookies/CSRF/CORS/expiry · DOC-006 attachment authorization ·
DOC-007 backups/hosting/recovery · DOC-008 cross-user isolation tests.

**Phase 2: Solara integration and UI (P0, 10–16 h).** DOC-009 identity/metadata ·
DOC-010 typography, colors, spacing · DOC-011 return-to-Solara nav · DOC-012 mobile/tablet ·
DOC-013 standard routes instead of hash · DOC-014 empty states/onboarding · DOC-015 editor keyboard a11y.

**Phase 3: Organization and retrieval (P1, 8–14 h).** DOC-016 collections · DOC-017 search with
permission filtering · DOC-018 tags · DOC-019 sorting · DOC-020 duplicate · DOC-021 archive/restore ·
DOC-022 recent documents.

**Phase 4: Radio and engineering templates (P1, 7–11 h).** DOC-023 versioned Tiptap template
registry · DOC-024 create ordinary documents from templates · DOC-025 POTA Activation Plan,
Satellite Observation Log, Antenna Experiment, Research/Engineering Notes · DOC-026 descriptions
and preview · DOC-027 template validation tests.

**Phase 5: Portability and lifecycle (P1, 7–12 h).** DOC-028 Markdown export · DOC-029 PDF export ·
DOC-030 download originals · DOC-031 deletion/recovery policy · DOC-032 revision history (optional) ·
DOC-033 bulk export (optional).

**Phase 6: Testing, deployment, release (P0, 8–12 h).** Auth, sharing revocation and session
expiry tests · full document journey · upload security, CSRF, accessibility · Playwright and
deployed smoke · migrations, backups, rollback · Solara Radio Tools Library entry.

## Future (P2/P3)

Tool-to-document (satellite passes, Radio Atlas results) · POTA plan generation · Nextcloud
export · autosave (#27) · version history · real-time collaboration (needs CRDT redesign) ·
AI-assisted notes. Tool-to-document comes before collaboration.
