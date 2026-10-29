# Delivery plan — 90-minute first iteration

Source: *Document Workspace Product Proposal* and *Implementation Roadmap* (v1.0, 2026-10-29).
The roadmap's four one-week iterations are compressed into four time-boxes. Every task is a
GitHub issue. **Agent** = can be completed autonomously; **User** = needs a decision,
credential, account, or sign-off. All work lands via PR; nothing merges without user approval.

| Time-box | Roadmap week | Agent tasks | User tasks / gates |
| --- | --- | --- | --- |
| 0–20 min | Week 1 Foundation | #1 INF-01, #2 INF-02, #3 AUTH-01, #4 OBS-01 | #5 Render Blueprint, #6 Node/Docker install, #7 confirm decisions, review Week 1 PR |
| 20–45 min | Week 2 Documents | #9 DOC-01, #10 DOC-02, #11 DOC-03, #12 UX-01 | Review PR; usability check of editor |
| 45–70 min | Week 3 Imports + sharing | #13 FILE-01, #14 FILE-02, #15 FILE-03, #16 SHARE-01, #17 SHARE-02 | #8 S3 bucket + credentials, review PR |
| 70–90 min | Week 4 Hardening | #18 QA-01, #19 SEC-01, #20 OPS-01 | #21 clean-room walkthrough, deployed smoke test, release sign-off |
| Backlog | — | — | #22 NEXT-01 (P2) |

## Dependency / critical path

```
#7 decisions ─┐
#1 repo/CI ──▶ #2 schema+migration ──▶ #3 demo auth ──▶ #9 doc CRUD ──▶ #11 revisions ──▶ #16 sharing ──▶ #18 E2E
#6 Node ─────────────────────────────────────────────▶ #10 editor ──▶ #17 shared UI ──┘
#8 storage creds ──▶ #15 attachments (deploy only; local tests use a fake store)
#5 Render ──▶ deployed smoke test (#21)
```

## Assumptions in force (pending #7)

Demo/portfolio audience; view-only grants; seeded identities; import supports Append and
Replace; 10 MB/file, 10 attachments/doc; `.txt`, `.md`, `.docx` only.

## Week 1 exit evidence

| Evidence | Status |
| --- | --- |
| Repo layout, lockfile, `.env.example`, lint/typecheck | Done in Week 1 PR (frontend lockfile waits on #6) |
| Schema + Alembic migration (all four entities) | Done; verified on SQLite locally, PostgreSQL in CI |
| Seeded login (Alice/Bob/Charlie), server-derived principal | Done; tests cover tamper/unknown/identity switch |
| Health endpoints `/health/live`, `/health/ready` | Done |
| CI green | Runs on the PR |
| API/DB deployed on Render | **Blocked on #5 (user)** — Blueprint ready |

## Status (end of Week 4)

Weeks 1–3 merged (#24, #25, #28) and deployed; Week 4 in the hardening PR. Remaining user task:
#21 clean-room walkthrough + release sign-off ([RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)).

## P0 requirement → automated evidence

| Requirement | Backend (pytest) | Browser (Playwright) |
| --- | --- | --- |
| F1 create/rename/list/open/save; title 1–160 | `test_documents.py` (CRUD, title validation) | `editor_persistence.spec.ts`, `invalid_inputs.spec.ts` (empty title) |
| F1 formatting persists (H1–H3, marks, lists, size) | `test_documents.py::test_create_save_reopen_preserves_structure` | `editor_persistence.spec.ts` (refresh keeps H1/bold/italic/bullets) |
| F1 safe content (schema validation) | `test_documents.py::test_malformed_content_rejected` | `invalid_inputs.spec.ts` (malformed/unsafe JSON → 422) |
| F1 save states, unsaved warning | — | `editor_persistence.spec.ts` (status, Cmd+S, leave prompt) |
| F1 revision conflicts (409) | `test_documents.py::test_stale_revision_is_rejected_with_409` | `editor_persistence.spec.ts` (conflict + reload) |
| F2 txt/md/docx conversion + warnings | `test_imports.py` (per-format converters) | `import_formats.spec.ts` |
| F2 append / replace with revision check | `test_imports.py::test_append_and_replace_into_existing` | `import_formats.spec.ts` (append → replace + confirm) |
| F2 reject unsupported/oversize/binary/fake docx | `test_imports.py::test_rejected_uploads`, oversize, zip, traversal | `import_formats.spec.ts`, `invalid_inputs.spec.ts` |
| F2 attachments durable + authorized | `test_attachments.py` (round trip, authz, limits, S3 via moto) | `attachments.spec.ts` (download bytes, reload) |
| F3 grant/revoke, viewer read-only, Charlie denied | `test_grants.py` | `sharing_permissions.spec.ts` (UI + direct API 403/404) |
| F4 persistence across restart | `test_hardening.py::test_data_survives_api_restart` | Deployed: release checklist restart step |
| Security: rate limits, headers, request ids | `test_hardening.py` | — |
| Deployed stack | — | `scripts/smoke_deployed.sh` (20 checks incl. served commit) |
