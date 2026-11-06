# Production readiness — v0.5 Secure Solara Preview

Release gates for exposing Solara Docs to real users (roadmap Phases 1–2). Every **P0 gate**
must be ticked, with a date and commit, before the first invite goes out. Audit references
(A1…) point to [SECURITY_AUDIT.md](SECURITY_AUDIT.md). The MVP gates in
[RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) still apply.

## Database plan (free tier would have expired 2026-11-28)

Decision (2026-11-04): the seeded demo data is disposable, so no backup was taken before the
upgrade.

- [x] Render dashboard → `docworkspace-db` → upgraded from Free to a paid plan (`basic-256mb`),
      matching `render.yaml` so a Blueprint sync will not revert it. (2026-11-04)
- [ ] Confirm point-in-time recovery / daily backups appear on the database's Recovery tab.
- [ ] `/health/ready` reports `database: ok` after the upgrade.

## P0 gates — identity and authorization (Phase 1)

- [x] DOC-001 OAuth sign-in with GitHub and Google works on the deployed site (ADR-009). Owner signed in with both, 2026-11-05 @ `ed73c8b`
- [ ] DOC-002 Users persist across restarts; a second provider links to the same user by verified email
- [ ] DOC-002 A non-allowlisted email is refused, and removing an email ends its sessions
- [x] DOC-004 `/api/demo/*` returns 404 in production, and the seed does not run there (A1, A2, A4). Smoke script, 2026-11-05 @ `1a2beda`
- [ ] DOC-005 Session cookie is `__Host-`, HttpOnly, Secure, SameSite=Lax, and the token is never in a response body (A6, A8)
- [ ] DOC-005 Logout invalidates the session server-side, so a replayed cookie gets 401 (A5)
- [x] DOC-005 Cross-origin `POST` (including multipart upload) is rejected with 403 (A7). Smoke script, 2026-11-05 @ `1a2beda`
- [x] DOC-003 Sharing is by email of an existing account, and there is no user directory endpoint (A9). #40
- [x] DOC-008 Isolation matrix: every document/attachment/import/grant route × {owner, viewer, stranger, anonymous} returns the expected status (A10). `tests/test_isolation.py`, #40
- [x] DOC-006 A stranger gets 404 for attachment list and download, including with a valid attachment id from another document. `tests/test_isolation.py`, #40

## P0 gates — data and operations

- [ ] DOC-007 Database on a paid plan with backups (above)
- [ ] DOC-007 **Restore drill:** restore the latest dump into a scratch database, run `alembic current`, spot-check a document
- [ ] DOC-007 R2 bucket is private (no public URL) and its API token is scoped to that bucket only
- [ ] OAuth client secrets and `SESSION_SECRET` live only in Render env vars, and `.env.example` lists names without values
- [ ] **Demo-data cleanup at cut-over:** `python scripts/purge_demo_data.py` (dry run), then
      `--yes` in the Render Shell. Removes Alice/Bob/Charlie, their documents, grants and R2 objects.
      Do this before the first invite (RUNBOOK → Production cut-over).
- [x] `scripts/smoke_deployed.sh` updated for OAuth: anonymous/security checks always, and the
      document journey with `SMOKE_SESSION` (2026-11-05)
- [ ] `SMOKE_SESSION=… scripts/smoke_deployed.sh` → "All checks passed" on the release commit
- [ ] Rollback rehearsed: redeploy the previous commit, and migrations stay backward-compatible for one release
      (rule and steps: RUNBOOK → Rollback and migrations; downgrade/upgrade checked in CI)
- [ ] API on the Starter plan in the Render dashboard (matches `render.yaml`), and the first
      **Post-deploy smoke** run on `main` is green

## P1 — before v1.0

- [ ] A11 Shared rate-limit store, if the API ever runs more than one instance
- [ ] A12 Orphaned R2 object sweep
- [ ] A13 R2 object versioning or lifecycle policy documented in the RUNBOOK
- [x] Virus scanning for uploads (#29): **deferred, risk accepted for v1.0** (below)

## Accepted risk: no virus scanning of uploads (#29)

Decision (2026-11-05, owner): ship v1.0 without malware scanning and revisit it with #55
(more attachment types), since binary formats raise the risk.

**Why it is acceptable now**
- Only `.txt`, `.md` and `.docx` are accepted. Contents are checked against the type: text must be
  UTF-8 with no NUL bytes, a `.docx` must be a real Word package (macro-enabled `.docm` is refused),
  and zip bombs are refused. Everything else gets a 415 (`tests/test_upload_security.py`).
- Downloads are never rendered by the browser: `Content-Disposition: attachment`, the stored type
  (`text/plain` for text), `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`.
- Files are private: the R2 bucket has no public URL, and a file is only served after checking
  that the requester can read its document (`tests/test_isolation.py`).
- Users are invited (allowlist), and sharing is read-only by email, so a file reaches only people
  the uploader chose.

**Remaining risk:** an invited user could share a malicious `.docx` (for example one exploiting a
Word vulnerability) with someone else. It would open in their desktop Word, not in Solara Docs.

**Revisit when:** any binary type (images, PDF) is accepted (#55), sharing goes beyond
invited users, or the number of users grows past a small trusted group.

## Sign-off

| Gate set | Name | Date | Commit |
| --- | --- | --- | --- |
| Database deadline | | | |
| Identity & authorization | | | |
| Data & operations | | | |
