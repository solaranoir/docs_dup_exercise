# ADR-001: Tiptap/ProseMirror JSON is the canonical document format

- **Status:** Accepted (2026-10-29)
- **Context:** The editor must round-trip headings, marks, lists and text size exactly, and stored
  content must never carry executable HTML into the renderer.
- **Decision:** Store the editor's JSON document tree (`content_json`). The server validates it
  against an allowlist of nodes, marks, attributes and font sizes (`backend/app/content.py`); the
  client uses the same subset (`frontend/src/editorExtensions.ts`). Imports convert into this subset.
- **Alternatives:** HTML (needs sanitising on every read, lossy round trips); Markdown (no
  underline/text size, ambiguous); a custom schema (more code, no editor support).
- **Consequences:** Structure is preserved byte-for-byte; XSS surface is limited to text. Any editor
  schema change needs a matching server allowlist change (and possibly a data migration).
- **Revisit when:** adding node types (tables, images, links), or moving to collaborative editing.
