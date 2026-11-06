# ADR-012: Export and document lifecycle

- **Status:** Accepted (2026-11-05). Implements DOC-028 to DOC-033 (Phase 5). Export shipped in
  PR 13 (#52); trash and recovery in PR 14.
- **Context:** The roadmap asks that "exports preserve supported structure, attachments are
  retrievable, and users can take their work elsewhere", and for a deletion and recovery
  policy. The API runs on Render's free web plan (no cron jobs, 512 MB). Documents are Tiptap
  JSON ([ADR-001](0001-tiptap-json-canonical-format.md)); attachments are private R2 objects
  ([ADR-005](0005-private-object-storage.md)).
- **Decision:**
  1. **Markdown is the export format** (DOC-028). CommonMark that our own importer reads back
     to the same structure: the title becomes a level-1 heading; headings, paragraphs, bold,
     italic, nested and numbered lists and line breaks are kept; underline is written as
     `<u>…</u>`; alignment and font sizes are dropped. Markdown syntax typed as text is
     escaped so it stays text.
  2. **PDF is print-to-PDF** (DOC-029). "Print or save as PDF" opens the browser's print dialog
     with a print stylesheet: only the title and the document, dark text on white, headings
     kept with what follows. The tab title is set to the document title so the suggested file
     name is right. No server PDF libraries.
  3. **One document or everything** (DOC-030, DOC-033).
     - *Export* on any document anyone can read: a `.md`, or a `.zip` with the Markdown and an
       `attachments/` folder holding the original files (linked from the Markdown).
     - *Export all* on My Documents: one `.zip` of every document the caller **owns**, archived
       included, one folder per document, plus `index.md` listing each document with the
       caller's own folder, tags and dates. Documents shared with the caller are not included.
     - Exporting one document fails (503, retry) if an attachment can't be read. *Export all*
       instead skips it, lists it in `index.md` and reports the count, so one lost file never
       blocks someone from taking the rest of their work.
     - Archives are spooled to a temporary file and streamed; exports are limited to 10 per
       minute per user.
  4. **Trash with 30-day recovery** (DOC-031). Deleting sets `documents.deleted_at`; nothing
     else changes.
     - Only the owner can delete. The document then looks missing (404) on every document
       route, for everyone including the owner, and drops out of lists, search, folder and tag
       counts and *Export all*.
     - Grants, attachments, folders and tags are kept, so *Restore* brings it back exactly as it
       was, including its archive state. Deleting and restoring do not change `updated_at`.
     - The owner's Trash (`/api/trash`) lists it with the date it will be removed. *Delete
       forever* removes it and its attachment objects at once.
     - After 30 days it is purged for good. The free plan has no cron, so the API purges at
       most once an hour per instance, in a background task after a document or Trash listing;
       `scripts/purge_trash.py` does it on demand.
     - After deleting from the editor, My Documents offers *Undo*.
  5. **Revision history is deferred** past v1.0 (DOC-032) and will be designed with autosave
     (#27).
- **Consequences:** Export needs no migration; Trash adds `documents.deleted_at` (migration
  0006, with a partial index). A purged document can only come back from a database backup.
  Server-side PDF, Word export, exporting shared documents in *Export all*, YAML front matter,
  a configurable retention period and revision history can be added later.
