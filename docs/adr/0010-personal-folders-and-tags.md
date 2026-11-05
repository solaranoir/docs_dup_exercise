# ADR-010: Personal folders and tags

- **Status:** Accepted (2026-11-04). Implements DOC-016 (collections/folders) and DOC-018 (tags).
- **Context:** Phase 3 asks that users can organise and find documents. Sharing is read-only and
  by email ([ADR-006](0006-view-only-grants-first.md), [ADR-009](0009-oauth-allowlist-authentication.md)),
  the user base is small and invite-only, and documents a user cannot read must look missing
  (404). Viewers should be able to organise what is shared with them, and nobody's labels should
  leak to anyone else through a share.
- **Decision:**
  1. **Personal organisation.** Folders and tags belong to a *user*, keyed by
     `(user_id, document_id)`. Each user organises their own view, including documents shared
     with them. Nothing is visible to other users, including the document owner.
  2. **One-level folders, at most one per document.** A folder says where a document lives
     ("2026 POTA"); tags cut across folders (`pota`, `cw`). No nesting.
  3. **Sharing stays per document.** Folders are private and cannot be shared; one grant is
     still exactly one document.
  4. **Free-form tags with a starter set.** Tags are normalised (trimmed, lowercased, spaces →
     `-`, 1–32 characters, at most 20 per document). The UI suggests `pota`, `sota`, `satellite`,
     `antenna`, `contest`, `research`; Phase 4 templates may apply these.
  5. **Organising is not editing.** Filing or tagging does not change `revision` or
     `updated_at`, needs only read access, and works on archived documents.
  6. **Lifecycle.** Deleting a folder ungroups its documents (never deletes them). Duplicating a
     document copies the duplicating user's own folder and tags. Losing access to a shared
     document hides it with its folder/tag rows; they are removed when the document or user is
     deleted (cascades). Another user's folder id is answered with 404.
  7. **Navigation.** A folder selector and tag filters on My Documents, kept in the URL query
     (`?folder=<id>|unfiled&tag=<tag>`). No separate collection pages yet.
- **Consequences:** Schema adds `folders`, `document_folders` and `document_tags`; existing
  documents start unfiled and untagged. Folder sharing, nested folders, several folders per
  document, or owner-visible tags can be added later as additive migrations. Search gains
  `folder`/`tag` filters when DOC-017 and this change are both merged.
