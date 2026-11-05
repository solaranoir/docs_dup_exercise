import { useEffect, useId, useState, type FormEvent } from "react";
import { api, type DocumentFull, type TemplateSummary } from "../api";
import { Modal } from "./Modal";

const BLANK = "";

/** ``YYYY-MM-DD`` in the user's own time zone (an evening plan shouldn't be dated tomorrow). */
export function localDate(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** "POTA Activation Plan, 2026-11-05": ready to rename (ADR-011). */
export function templateTitle(template: Pick<TemplateSummary, "name">, now?: Date): string {
  return `${template.name}, ${localDate(now)}`;
}

/** "New document": Blank or one of the built-in templates, with a preview (DOC-024, DOC-026). */
export function NewDocumentDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (doc: DocumentFull) => void;
}) {
  const [templates, setTemplates] = useState<TemplateSummary[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [choice, setChoice] = useState(BLANK);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ids = useId();

  useEffect(() => {
    if (!open || templates) return;
    let current = true;
    api.listTemplates().then(
      (list) => current && setTemplates(list),
      () => current && setLoadError(true),
    );
    return () => {
      current = false;
    };
  }, [open, templates]);

  const selected = templates?.find((t) => t.id === choice) ?? null;

  const create = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const dialog = e.currentTarget.closest("dialog");
    setBusy(true);
    setError(null);
    try {
      const doc = await api.createDocument(
        selected ? { template: selected.id, title: templateTitle(selected) } : {},
      );
      // Leave the top layer before navigating: while a modal <dialog> is open the rest of the
      // page is inert, so the router could not move focus to the new page's <main>.
      dialog?.close();
      onCreated(doc);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  const close = () => {
    setChoice(BLANK);
    setError(null);
    setBusy(false);
    onClose();
  };

  return (
    <Modal title="New document" open={open} onClose={close}>
      <form className="new-doc" onSubmit={(e) => void create(e)}>
        <div className="new-doc-body">
          <fieldset className="template-choices">
            <legend>Start from</legend>
            <label className="template-choice">
              <input
                type="radio"
                name="template"
                value={BLANK}
                checked={choice === BLANK}
                onChange={() => setChoice(BLANK)}
                aria-labelledby={`${ids}-blank-name`}
                aria-describedby={`${ids}-blank`}
              />
              <span>
                <strong id={`${ids}-blank-name`}>Blank document</strong>
                <span id={`${ids}-blank`} className="template-desc">
                  An empty page.
                </span>
              </span>
            </label>
            {templates?.map((t) => (
              <label key={t.id} className="template-choice">
                <input
                  type="radio"
                  name="template"
                  value={t.id}
                  checked={choice === t.id}
                  onChange={() => setChoice(t.id)}
                  aria-labelledby={`${ids}-${t.id}-name`}
                  aria-describedby={`${ids}-${t.id}`}
                />
                <span>
                  <strong id={`${ids}-${t.id}-name`}>{t.name}</strong>
                  <span id={`${ids}-${t.id}`} className="template-desc">
                    {t.description}
                  </span>
                </span>
              </label>
            ))}
            {!templates && !loadError && <p className="loading">Loading templates…</p>}
            {loadError && <p className="hint">Templates couldn't be loaded; you can still start blank.</p>}
          </fieldset>
          <section className="template-preview" aria-labelledby={`${ids}-preview`}>
            <h3 id={`${ids}-preview`}>Preview</h3>
            {selected ? (
              <>
                <p className="template-preview-title">{templateTitle(selected)}</p>
                <ul>
                  {selected.sections.map((s) => (
                    <li key={s.heading}>
                      <strong>{s.heading}</strong>
                      {s.fields.length > 0 && <span>{s.fields.join(" · ")}</span>}
                    </li>
                  ))}
                </ul>
                <p className="hint">Everything is editable once it's created.</p>
              </>
            ) : (
              <p className="hint">An empty document called “Untitled document”.</p>
            )}
          </section>
        </div>
        {error && <p role="alert">{error}</p>}
        <div className="modal-actions">
          <button type="button" onClick={close}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={busy}>
            Create
          </button>
        </div>
      </form>
    </Modal>
  );
}
