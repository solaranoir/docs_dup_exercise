# ADR-003: Explicit Save with revision compare-and-swap

- **Status:** Accepted (2026-10-29)
- **Context:** Two tabs or users can edit the same document. Silent overwrites lose work.
- **Decision:** Every write sends `expected_revision`; the server runs
  `UPDATE … WHERE id = ? AND revision = ?` and increments the revision. A mismatch returns
  **409** with `current_revision` and recovery guidance; the UI offers "Reload latest version".
  Saving is explicit (button or Ctrl/Cmd+S) with an unsaved-changes indicator and leave guards.
- **Alternatives:** last-write-wins (data loss); locking (stale locks, poor UX); autosave
  (deferred: #27).
- **Consequences:** No lost updates; concurrent edits are rejected rather than merged. Imports
  (append/replace) use the same check.
- **Revisit when:** autosave (#27) or collaborative editing is introduced.
