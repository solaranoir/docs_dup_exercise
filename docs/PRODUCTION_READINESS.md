# Production readiness: v1.0 Solara Docs

Release gates for Solara Docs v1.0 (roadmap Phases 1–6). Each ticked gate names its evidence: a
test that CI runs on every commit, a deployed check, or an owner action with a date. Gates marked
**Owner** need the Render or Cloudflare dashboard, or a real signed-in account; they are also in
[RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) in the order to do them. Audit references (A1…)
point to [SECURITY_AUDIT.md](SECURITY_AUDIT.md).

Evidence as of 2026-11-06: [CI @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951200)
and [post-deploy smoke @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951212),
plus the tests added by the v1.0 release PR (`test_orphans.py`, the stricter production secret
check). Test counts on the release branch: backend 364, frontend 65, e2e 27.

## v1.0 exit condition

- [x] "A new user creates a doc from a template, edits, attaches, organizes, exports and retrieves
      it; another user cannot read it without permission." `e2e/tests/v1_journey.spec.ts`: a
      template document is edited, attached to, filed and tagged, exported and found again after
      signing out and back in. Another user is refused through the link, the API, search, export
      and the attachment, including after a share is revoked while they have it open. [CI @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951200)

## Hosting

- [x] Database on a paid plan (`basic-256mb`), matching `render.yaml` so a Blueprint sync will not
      revert it. Upgraded 2026-11-04; the seeded demo data was disposable, so no backup was taken.
- [x] `/health/ready` reports `database: ok` and `storage: ok`. [post-deploy smoke @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951212)
- [ ] **Owner:** the API shows the **Starter** plan in the Render dashboard (matches `render.yaml`).
- [ ] **Owner:** daily backups and point-in-time recovery appear on the database's Recovery tab.

## Identity and authorization (Phase 1)

- [x] DOC-001 GitHub and Google sign-in work on the deployed site (ADR-009). Owner signed in with
      both, 2026-11-05 @ `ed73c8b`.
- [x] DOC-002 Accounts persist, a returning sign-in reuses the account, and a second provider
      links to the same account by verified email (an unverified email is refused).
      `test_oauth.py`: `test_returning_sign_in_reuses_account`,
      `test_second_provider_links_by_verified_email`, `test_unverified_email_rejected`. [CI @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951200)
- [x] DOC-002 An email that isn't invited gets nothing, and removing an invite ends that person's
      sessions and blocks their next sign-in. `test_oauth.py`: `test_uninvited_email_gets_nothing`,
      `test_revoked_invite_blocks_returning_user`; `test_sessions.py`:
      `test_revoking_invite_signs_user_out`. [CI @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951200)
- [x] DOC-004 `/api/demo/*` returns 404 in production and the seed does not run there (A1, A2, A4).
      `test_sessions.py`: `test_demo_routes_absent_when_disabled`, `test_seed_skips_when_demo_disabled`;
      deployed: [post-deploy smoke @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951212) ("demo sign-in disabled").
- [x] DOC-005 The session cookie is `__Host-`, HttpOnly, Secure and SameSite=Lax, and the token is
      never in a response body; only its hash is stored (A6, A8). `test_sessions.py`:
      `test_login_sets_hardened_cookie_and_never_returns_token`,
      `test_production_cookie_is_host_prefixed_and_secure`, `test_only_token_hash_is_stored`. [CI @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951200)
- [x] DOC-005 Logout ends the session on the server, so a replayed cookie gets 401 (A5).
      `test_sessions.py`: `test_logout_ends_session_server_side`. Idle (7 days) and absolute
      (30 days) expiry: `test_idle_expiry`, `test_absolute_expiry`. In the browser, an ended session
      keeps unsaved edits and offers sign-in again (`v1_journey.spec.ts`). [CI @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951200)
- [x] DOC-005 Cross-origin writes, including multipart uploads, are refused with 403 (A7).
      `test_sessions.py`: `test_csrf_origin_check_on_writes`,
      `test_csrf_blocks_cross_site_multipart_upload`; deployed: [post-deploy smoke @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951212).
- [x] DOC-003 Sharing is by email of an existing account, with no user directory endpoint (A9). #40
- [x] DOC-008 Isolation matrix: every document-scoped route, including export and Trash, ×
      {owner, viewer, stranger, anonymous}. A guard test fails if a new route is missing from
      the matrix (A10). `test_isolation.py`. [CI @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951200)
- [x] DOC-006 A stranger gets 404 for attachment list and download, including with a valid
      attachment id from another document. `test_isolation.py`. [CI @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951200)
- [x] Production refuses to start with unsafe settings (demo auth on, placeholder
      `SESSION_SECRET`, non-https origins). `test_sessions.py`:
      `test_production_refuses_unsafe_config`; `test_oauth.py`:
      `test_production_requires_https_public_origin`. [CI @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951200)

## Uploads, accessibility and the browser (Phase 6)

- [x] Upload security: disguised HTML is served as a `text/plain` download; disallowed and double
      extensions, empty, binary, fake and zip-bomb `.docx` files are refused; hostile file names
      are neutralised. `test_upload_security.py` (21 tests). [CI @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951200)
- [x] Accessibility: axe-core WCAG 2.1 A/AA checks on sign-in, not found, My Documents, search,
      archived and Trash sections, the editor (clean, unsaved, archived, read-only) and every
      dialog, with no violations. `e2e/tests/accessibility.spec.ts`. [CI @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951200)
- [x] Security headers on the static site (CSP, `X-Frame-Options: DENY`, `nosniff`,
      `Referrer-Policy`). `render.yaml`; CSP and frame options checked by [post-deploy smoke @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951212).

## Data and operations

- [x] Migrations run in a pre-deploy step; a failed migration fails the deploy and the previous
      version keeps serving. A rollback to older code on a newer schema doesn't fail
      (`scripts/migrate.py`, `test_migrations.py`). Every migration's downgrade is checked
      against seeded data in CI. [CI @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951200)
- [x] Post-deploy smoke checks run automatically after each deploy and daily
      (`.github/workflows/deploy-smoke.yml`). First run green: [post-deploy smoke @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951212).
- [x] Secrets live only in Render env vars: `render.yaml` marks OAuth and storage values
      `sync: false` and generates `SESSION_SECRET`. `.env.example` holds only blank or local
      placeholder values, and a scan of the repository found no credentials (2026-11-06).
- [ ] **Owner:** R2 bucket is private (no public `r2.dev` URL or custom domain) and its API token is
      scoped to that bucket only (Cloudflare → R2 → bucket → Settings; R2 → Manage API tokens).
- [ ] **Owner, DOC-007 restore drill:** restore into a new database, check `alembic current`, and
      spot-check a document (RUNBOOK → Restore drill).
- [ ] **Owner, demo-data cleanup at cut-over:** `python scripts/purge_demo_data.py`, then `--yes`,
      in the Render Shell, before the first invite (RUNBOOK → Production cut-over).
- [ ] **Owner:** `SMOKE_SESSION=… scripts/smoke_deployed.sh "" "" <release commit>` → "All checks
      passed" (the signed-in journey; the public checks run automatically).
- [ ] **Owner:** rollback rehearsed once: Render → API → Events → Rollback to the previous deploy,
      `/health/live` shows that commit, then roll forward again (RUNBOOK → Rollback and migrations).

## Audit items A11–A13

- [x] A11 Rate limits are kept in memory per instance. **Accepted:** the API runs as one Starter
      instance. Revisit before adding instances or autoscaling (move the limiter to Postgres).
- [x] A12 Orphaned R2 objects: `scripts/sweep_orphans.py` (dry run by default) finds stored files
      no attachment points at, older than an hour, and deletes them with `--yes`
      (`test_orphans.py`, including paging through more than 1,000 objects). [CI @ `a05ab2f`](https://github.com/solaranoir/docs_dup_exercise/actions/runs/42174951200)
- [x] A13 R2 versioning and lifecycle: documented in RUNBOOK → Attachment storage, retention and
      recovery, and a restore drill procedure in RUNBOOK → Restore drill. R2 keeps no object versions. Attachments are never overwritten (each upload gets a
      new key), deletion is recoverable for 30 days through the Trash, and Export all is the
      user-side backup.
- [x] Virus scanning for uploads (#29): **deferred, risk accepted for v1.0** (below).

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
| Automated gates (CI and post-deploy smoke) | | | |
| Owner gates (hosting, R2, restore drill, cut-over, signed-in smoke, rollback) | | | |
| v1.0 release | | | |
