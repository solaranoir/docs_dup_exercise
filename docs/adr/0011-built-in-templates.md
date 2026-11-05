# ADR-011: Built-in document templates

- **Status:** Accepted (2026-11-05). Implements DOC-023 to DOC-027 (Phase 4).
- **Context:** The roadmap asks for radio and engineering templates (POTA Activation Plan,
  Satellite Observation Log, Antenna Experiment, Research/Engineering Notes) and requires that
  "each template produces a fully editable document without introducing a separate specialized
  data model". It also records "use templates rather than specialized radio forms for MVP".
- **Decision:**
  1. **Built-in only.** The four templates live in code (`backend/app/templates.py`), each with
     an `id`, a `version` and a description, and change only through pull requests. There are
     no user-created or admin-managed templates yet.
  2. **Ordinary documents.** Creating from a template copies the template's content into a new
     document (`POST /api/documents {"template": id, "title": …}`). Nothing links the document
     back to its template, so it shares, searches, organises, imports and exports like any
     other document, and a new template version never changes existing documents.
  3. **Labelled lines.** Each section is a level-2 heading, then bold `Label:` lines to fill in
     and an optional italic hint; free-form sections end with an empty bullet list. Only node
     types the editor and `validate_content` already accept are used (no tables). An unmarked
     trailing space after each label keeps typed answers out of the bold mark.
  4. **One entry point.** "New document" opens a picker: *Blank document* (selected by default)
     or a template, each with a description and a preview of its sections and fields
     (`GET /api/templates` returns the outline, not the content).
  5. **Prefill the title only.** A template document is titled `<Template name>, YYYY-MM-DD`
     using the user's local date. Templates do not apply tags or folders, and the template id is
     not stored on the document.
  6. **Versioned and tested.** Tests validate every template as editor content, check that the
     roadmap's fields are present and searchable, and pin a fingerprint per `(id, version)`, so
     changing a template's content without bumping its version fails CI.
- **Consequences:** No migration. User-defined templates ("save as template"), tables in
  templates, auto-tagging from templates, or recording a document's template are additive
  later. Template wording lives in Python, so editing it needs a deploy.
