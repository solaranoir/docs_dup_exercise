# Document Workspace MVP — Demo Presentation Notes (3–5 min, target ~4:00)

Speaker and slide notes for a short live demo. Facts reflect the state after PR #31
(Weeks 1–4 merged and deployed, 2026-10-29). Release sign-off is tracked in #21.

Live app: https://docworkspace-web.onrender.com
Repo: https://github.com/solaranoir/docs_dup_exercise

Pre-flight (do ~1–2 min before presenting):
- Open https://docworkspace-api.onrender.com/health/ready to wake the free-tier API (cold start 30–50 s). Expect `{"status":"ok","database":"ok","storage":"ok"}`.
- Optional confidence check from a clone: `scripts/smoke_deployed.sh` → "All checks passed" (20 checks, ~1 min; cleans up after itself).
- Have sample files ready: sample.docx, sample.md, sample.txt (repo: backend/tests/fixtures/).
- Use two browser windows or plan to use "Switch user" between Alice, Bob, Charlie.

---

## 1. Title + pitch (0:00–0:15, ~15 s)

Slide title: Document Workspace MVP

- A rich-text document workspace: create, format, import, attach, and share documents.
- Portfolio/demo release for 2–20 seeded users (Alice, Bob, Charlie).
- Live on Render; React + FastAPI + PostgreSQL + Cloudflare R2.
- First full iteration delivered in a 90-minute, PR-driven session.

Say:
- "This is a single-user editing workspace with explicit sharing — a reliable vertical slice, not real-time collaboration."
- "Everything you'll see is running live on Render right now."

## 2. Problem & goals (0:15–0:35, ~20 s)

Slide title: Goals and Success Measures

- Core workflow: create, format, save, refresh and reopen without guidance.
- Import: .txt / .md / .docx become editable drafts, with clear warnings about lost fidelity.
- Sharing: owner grants user B access; B sees "Shared with me"; user C is denied.
- Durability: documents, formatting and grants survive refresh and service restart.
- Quality: critical end-to-end journeys pass; no open P0/P1 defects.

Say:
- "These come straight from the product proposal, and each one maps to an automated test."

## 3. Architecture (0:35–1:00, ~25 s)

Slide title: Architecture and Key Decisions

- Frontend: React 19 + Vite + Tiptap 3, deployed as a Render static site; `/api/*` is rewritten to the API so the session cookie is same-origin/first-party.
- API: FastAPI + SQLAlchemy + Alembic migrations; signed demo session (httpOnly cookie); principal always derived server-side.
- Data: PostgreSQL stores users, documents (Tiptap JSON in JSONB + revision), grants, attachment metadata.
- Files: Cloudflare R2 private bucket; bytes never on the service disk.
- Decisions: Tiptap JSON is canonical; explicit Save + revision compare-and-swap (stale save → 409, never silent overwrite); seeded demo identities; view-only grants first (role column ready for editors).

Say:
- "The editor's JSON is the source of truth, and the server validates it against an allowlist — no HTML is ever stored."
- "Conflicts are rejected, not merged: if your copy is stale you get a 409 and a 'Reload latest version' path."

## 4. Live demo (1:00–3:00, ~2 min)

Slide title: Live Demo — Alice, Bob and Charlie

Click path (mirrors the roadmap's demo script):
1. Sign in as Alice (owner). Click "New document"; title "Quarterly Notes".
2. Block style → Heading 1, type a heading; type text with Ctrl/Cmd+B bold; add a bulleted list. Status shows "Unsaved changes".
3. Click Save (or Ctrl/Cmd+S) → "All changes saved". Refresh the page: heading, bold and bullets persist.
4. Back to Documents → "Import file" → choose sample.docx. Preview shows converted content plus warnings (e.g. "Tables are not supported and were removed."). Click "Create document".
5. Open a draft → "Import…" → sample.md → keep "Append to the end" → "Append content". Existing text stays; Markdown heading/list added below. (Replace exists too, with a confirmation.)
6. In the Attachments panel → "Attach file" → sample.txt. Click it to download; the file comes back from R2.
7. Click "Share" → "Share with Bob (recipient)" → badge shows Viewer.
8. Switch user → Bob. "Shared with me" lists Quarterly Notes with "View only · Alice (owner)". Open it: read-only, no toolbar, no Save, attachment downloadable.
9. (Optional, if a dev console is handy) A direct API PATCH as Bob returns 403 — enforcement is server-side, not just hidden buttons.
10. Switch user → Charlie. Paste the document URL → "Document not found, or you do not have access to it." (privacy-preserving 404).
11. Switch back to Alice → Share → "Revoke Bob". Switch to Bob → the document is gone.

Say:
- "Notice the save-state indicator and the leave-page warning — there's no autosave in the MVP, by design."
- "Import never stores anything until you confirm; the preview tells you exactly what formatting was lost."
- "Charlie gets the same 404 as a document that doesn't exist, so they can't even learn it exists."

Fallback if the live site is slow: describe steps from the slides and cite the deployed smoke test results in section 5.

## 5. Quality & security (3:00–3:25, ~25 s)

Slide title: Quality and Security

- Tests: 68 pytest (on PostgreSQL 16), 9 Vitest/RTL, 14 Playwright journeys; CI runs backend, frontend and e2e jobs on every PR.
- Server-side content allowlist (nodes, marks, attributes, font sizes, size/depth limits) — no HTML stored.
- Privacy-preserving 404 for documents you can't read; viewers get 403 on edits; owner-only sharing.
- Uploads: .txt/.md/.docx allowlist, 10 MB cap (413), content sniffing (UTF-8/NUL, docx zip structure, zip-bomb guard), filenames sanitized and never used as storage keys; downloads forced as attachment with `nosniff`.
- Deployed smoke test (`scripts/smoke_deployed.sh`, 20/20 against Render after the final merge): served commit matches the merge, R2 byte-identical download round trip, Bob read 200 / edit 403, Charlie 404, after revoke Bob 404.
- Week 4 hardening (shipped, PR #31): rate limits on login and uploads (429 + Retry-After), JSON logs with request IDs, security headers incl. a strict Content-Security-Policy, `/health/live` reports the deployed commit; initial JavaScript cut from ~550 kB to 228 kB by lazy-loading the editor.

Say:
- "Every permission rule is tested at the API, not just the UI — including direct requests that bypass the interface."

## 6. How it was delivered (3:25–3:45, ~20 s)

Slide title: Delivery — 4-Week Roadmap in 90 Minutes

- Roadmap's four weekly iterations compressed into four time-boxes; each roadmap item became a GitHub issue labeled "agent" or "needs-user-input".
- Every change shipped via PR with CI; the agent never merged — a human reviewed and merged each one.
- Human decisions recorded on issues: view-only sharing, seed on every start, free tier, bucket name `document-workspace-attachments`, fixed text sizes.
- E2E caught real bugs: two dialogs sharing one title id (the Share dialog was announced as "Import"), section ids containing spaces (list sections had no accessible name), and an attachment-list race under React StrictMode.
- Real ops incident: Render showed the new commit live but served stale code; fixed with "Clear build cache & deploy", then prevented (#30): non-editable build, commit reported by `/health/live`, and the smoke test asserts it.

Say:
- "The interesting part is the split: the agent did the build work, and the human kept every decision and every merge."

## 7. Limitations & roadmap (3:45–3:55, ~10 s)

Slide title: Limitations and What's Next

- Demo identities are not production-safe; real auth (OIDC), invites, editor grants and versions → #22.
- Autosave → #27; more fixed text sizes → #26; attachment virus scanning → #29.
- No real-time collaboration, comments, public links or offline sync in MVP.
- Free-tier Render: API sleeps when idle; free PostgreSQL expires ~2026-11-28.

Say:
- "These are deliberate exclusions, each tracked as a post-MVP issue."

## 8. Close (3:55–4:05, ~10 s)

Slide title: Takeaway

- A tested, deployed vertical slice: edit, import, attach, share — with server-enforced permissions.
- Repo and issues: https://github.com/solaranoir/docs_dup_exercise

Say:
- "It does a small set of things reliably, and everything it doesn't do yet is written down."
- "Happy to take questions."

---

## Backup / Q&A

- Why not real-time collaboration?
  - Out of MVP scope by design. JSONB + revision checks are simple and transactional; collaborative editing would need a CRDT-based architecture (Phase 3 if demand warrants).
- Why store content as JSONB?
  - Keeps the editor's structure lossless, validates server-side, and gets transactions and constraints from PostgreSQL. Tradeoff: schema migrations needed if the editor schema evolves.
- How do conflicts work?
  - Each save sends the revision it was based on; the DB update only applies if the revision still matches (compare-and-swap). Otherwise 409 with the current revision, and the UI offers "Reload latest version". Nothing is silently overwritten.
- What happens to DOCX tables (and images, tracked changes)?
  - Removed or flattened, with an explicit warning in the import preview before anything is saved. Supported: headings, bold/italic/underline, bulleted/numbered lists.
- Why the same-origin `/api` rewrite?
  - The static site and API live on separate onrender.com subdomains, which are cross-site. Proxying `/api` through the static site keeps the session cookie first-party and avoids CORS/third-party-cookie issues.
- Is the demo login secure?
  - No — it's a seeded, signed demo session for a restricted demo. Sessions are signed server-side and the server never trusts a client-supplied user id, but anyone can pick an identity. Real authentication is required before public release (#22).
- Where are files stored, and are they scanned?
  - Private R2 bucket, downloaded only through the API after an authorization check. No virus scanning yet (post-MVP, #29); mitigated by type allowlist, content sniffing, size cap and forced-download headers.
