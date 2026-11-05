# Production readiness — v0.5 Secure Solara Preview

Release gates for exposing Solara Docs to real users (roadmap Phases 1–2). Every **P0 gate**
must be ticked, with a date and commit, before the first invite goes out. Audit references
(A1…) point to [SECURITY_AUDIT.md](SECURITY_AUDIT.md). The MVP gates in
[RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) still apply.

## ⏰ Deadline: database expiry (2026-11-28)

- [ ] **Back up now:** `pg_dump --format=custom "$EXTERNAL_DATABASE_URL" > docworkspace-$(date +%F).dump`
      and store it outside Render.
- [ ] Render dashboard → `docworkspace-db` → upgrade instance type from Free to a paid plan
      (`basic-256mb` or larger). Data is kept on upgrade. `render.yaml` already matches, so a
      Blueprint sync will not revert it.
- [ ] Confirm point-in-time recovery / daily backups appear on the database's Recovery tab.
- [ ] `/health/ready` reports `database: ok` after the upgrade.

## P0 gates — identity and authorization (Phase 1)

- [ ] DOC-001 OAuth sign-in with GitHub and Google works on the deployed site (ADR-009)
- [ ] DOC-002 Users persist across restarts; a second provider links to the same user by verified email
- [ ] DOC-002 A non-allowlisted email is refused, and removing an email ends its sessions
- [ ] DOC-004 `/api/demo/*` returns 404 in production, and the seed does not run there (A1, A2, A4)
- [ ] DOC-005 Session cookie is `__Host-`, HttpOnly, Secure, SameSite=Lax, and the token is never in a response body (A6, A8)
- [ ] DOC-005 Logout invalidates the session server-side, so a replayed cookie gets 401 (A5)
- [ ] DOC-005 Cross-origin `POST` (including multipart upload) is rejected with 403 (A7)
- [ ] DOC-003 Sharing is by email of an existing account, and there is no user directory endpoint (A9)
- [ ] DOC-008 Isolation matrix: every document/attachment/import/grant route × {owner, viewer, stranger, anonymous} returns the expected status (A10)
- [ ] DOC-006 A stranger gets 404 for attachment list and download, including with a valid attachment id from another document

## P0 gates — data and operations

- [ ] DOC-007 Database on a paid plan with backups (above)
- [ ] DOC-007 **Restore drill:** restore the latest dump into a scratch database, run `alembic current`, spot-check a document
- [ ] DOC-007 R2 bucket is private (no public URL) and its API token is scoped to that bucket only
- [ ] OAuth client secrets and `SESSION_SECRET` live only in Render env vars, and `.env.example` lists names without values
- [ ] `scripts/smoke_deployed.sh` updated for OAuth (uses a test-only session in CI, or a manual sign-in step) and passing
- [ ] Rollback rehearsed: redeploy the previous commit, and migrations stay backward-compatible for one release

## P1 — before v1.0

- [ ] A11 Shared rate-limit store, if the API ever runs more than one instance
- [ ] A12 Orphaned R2 object sweep
- [ ] A13 R2 object versioning or lifecycle policy documented in the RUNBOOK
- [ ] Virus scanning for uploads (#29)

## Sign-off

| Gate set | Name | Date | Commit |
| --- | --- | --- | --- |
| Database deadline | | | |
| Identity & authorization | | | |
| Data & operations | | | |
