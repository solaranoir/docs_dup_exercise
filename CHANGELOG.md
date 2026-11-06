# Changelog

Solara Docs: technical notes, field logs and experiments for Solara Radio. Releases follow the
roadmap in [docs/ROADMAP.md](docs/ROADMAP.md). Each release is a GitHub release tagged `vX.Y.Z`
on `main`.

## 1.0.0 (2026-11-06)

The first release for real users. A new user can create a document from a template, edit it,
attach files, organise it, export it and come back to it later. Nobody else can read it unless
they are given access. The roadmap's v1.0 exit condition is tested end to end in
`e2e/tests/v1_journey.spec.ts`.

### Sign-in and security (Phase 1)
- Sign in with GitHub or Google. Only invited email addresses can sign in (ADR-009). Removing an
  invite signs that person out everywhere.
- Server-side sessions in a `__Host-` HttpOnly, Secure, SameSite=Lax cookie. Sessions expire
  after 7 days idle or 30 days in total. Signing out ends the session on the server.
- Writes from other sites are refused (Origin check, including file uploads). The demo
  identities are switched off in production and the API refuses to start with them on.
- Share a document read-only by email with someone who has signed in once. There is no user
  directory. Owners can revoke access at any time.
- Every document, attachment, import, export, Trash and sharing route is tested for the owner,
  a viewer, a stranger and a signed-out visitor (`backend/tests/test_isolation.py`).

### Solara look and navigation (Phase 2)
- Solara Radio's colours, type and spacing, with a "Solara Radio Tools" link back to the Tools
  Library on every page. The layout works on phones.
- Real page addresses (`/doc/<id>`), onboarding for new users, and an editor you can use from the
  keyboard (toolbar arrow keys, a shortcut list, skip link).

### Organising and finding documents (Phase 3)
- Search titles and content, limited to documents you can read.
- Personal folders and tags that only you see, including on documents shared with you. Filter
  by folder and tag.
- Sort by last edited, created or title. Recently opened documents, duplicate, archive and
  restore.

### Templates (Phase 4)
- A New document picker with POTA Activation Plan, Satellite Observation Log, Antenna Experiment
  and Research/Engineering Notes. A template creates an ordinary document titled with today's
  date (ADR-011).

### Export and deletion (Phase 5)
- Export a document as Markdown (a `.zip` with its attachments when it has any), or print or save
  it as PDF. **Export all** downloads everything you own as one `.zip` with an index.
- Delete moves a document to the Trash. You can restore it within 30 days, with its sharing,
  attachments, folder and tags, or delete it for good (ADR-012).

### Quality and operations (Phase 6)
- If your session ends while you are editing, a banner explains what happened and keeps your
  unsaved text on the page. Sign in again in a new tab, then save.
- Automated accessibility checks (WCAG 2.1 AA, axe-core) on every page and dialog.
- Upload security tests: disguised HTML, disallowed types, fake and zip-bomb Word files, hostile
  file names.
- The API runs on Render's Starter plan (no sleeping). Migrations run before each deploy, and a
  rollback to older code no longer fails on a newer database (`scripts/migrate.py`).
- A GitHub Action checks the live site after every deploy and once a day.
- `scripts/sweep_orphans.py` removes stored files that no attachment points at (audit A12).

### Fixed
- Adding two tags in quick succession could lose one.
- The "• List" and "1. List" toolbar buttons had accessible names that didn't include their
  visible text.
- The onboarding text promised photos and data files, but only `.txt`, `.md` and `.docx` are
  accepted.
- The deploy smoke check left its test document in the Trash.
- Production now also refuses to start with the `.env.example` placeholder `SESSION_SECRET`, or
  any secret shorter than 32 characters.

### Known limitations
- Attachments and imports accept only `.txt`, `.md` and `.docx`. Photos, PDF, CSV and ADIF are
  planned in #55.
- Uploads are not virus-scanned. This is an accepted risk for v1.0 (#29,
  [PRODUCTION_READINESS](docs/PRODUCTION_READINESS.md)).
- Search matches whole words and word starts, not text inside words (#50).
- There is no real-time collaboration, comments, version history, public links, edit access for
  others, or autosave (#27).

## 0.1.0: Document Workspace MVP (2026-10-29)

A single-user rich-text editor with explicit save and conflict detection. It imported `.txt`,
`.md` and `.docx`, stored attachments privately on R2, and shared documents view-only between
the seeded demo identities Alice, Bob and Charlie. See [docs/PLAN.md](docs/PLAN.md) and the
archived [MVP README](docs/archive/README-mvp.md).
