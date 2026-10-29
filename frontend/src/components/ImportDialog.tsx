import { useState } from "react";
import { api, UPLOAD_ACCEPT, type DocumentFull, type ImportMode, type ImportPreview } from "../api";
import { ContentPreview } from "./ContentPreview";
import { Modal } from "./Modal";

type Target =
  | { kind: "new"; onCreated: (doc: DocumentFull) => void }
  | {
      kind: "existing";
      document: DocumentFull;
      onApplied: (doc: DocumentFull) => void;
    };

/**
 * Upload → server converts → preview with fidelity warnings → user confirms.
 * Nothing is stored until confirmation; Replace asks for an extra confirmation.
 */
export function ImportDialog({
  open,
  onClose,
  target,
}: {
  open: boolean;
  onClose: () => void;
  target: Target;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [title, setTitle] = useState("");
  const [mode, setMode] = useState<ImportMode>("append");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setFile(null);
    setPreview(null);
    setError(null);
    setMode("append");
  };
  const close = () => {
    reset();
    onClose();
  };

  const choose = async (picked: File | undefined) => {
    reset();
    if (!picked) return;
    setFile(picked);
    setBusy(true);
    try {
      const result = await api.previewImport(picked);
      setPreview(result);
      setTitle(result.title);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (!preview || !file) return;
    if (
      target.kind === "existing" &&
      mode === "replace" &&
      !window.confirm("Replace the entire document with the imported content? This cannot be undone.")
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (target.kind === "new") {
        target.onCreated(await api.createFromImport(title.trim() || preview.title, preview.content_json));
      } else {
        const { document } = await api.importInto(
          target.document.id,
          file,
          mode,
          target.document.revision,
        );
        target.onApplied(document);
      }
      close();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={target.kind === "new" ? "Import file as new document" : "Import into this document"}
      open={open}
      onClose={close}
    >
      <label className="field">
        File (.txt, .md or .docx, up to 10 MB)
        <input type="file" accept={UPLOAD_ACCEPT} onChange={(e) => void choose(e.target.files?.[0])} />
      </label>
      {busy && !preview && <p className="loading">Converting…</p>}
      {error && (
        <p role="alert" className="notice notice-error">
          {error}
        </p>
      )}
      {preview && (
        <>
          {preview.warnings.length > 0 ? (
            <div className="notice notice-warn" role="note" aria-label="Conversion warnings">
              <strong>Some formatting could not be kept:</strong>
              <ul>
                {preview.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="hint">Converted without losing supported formatting.</p>
          )}
          {target.kind === "new" ? (
            <label className="field">
              Title
              <input value={title} maxLength={160} onChange={(e) => setTitle(e.target.value)} />
            </label>
          ) : (
            <fieldset className="field">
              <legend>How should the content be added?</legend>
              <label>
                <input type="radio" name="mode" checked={mode === "append"} onChange={() => setMode("append")} />{" "}
                Append to the end
              </label>
              <label>
                <input type="radio" name="mode" checked={mode === "replace"} onChange={() => setMode("replace")} />{" "}
                Replace all content
              </label>
            </fieldset>
          )}
          <p className="hint">Preview</p>
          <ContentPreview content={preview.content_json} />
          <div className="modal-actions">
            <button type="button" onClick={close}>
              Cancel
            </button>
            <button type="button" className="primary" disabled={busy} onClick={() => void confirm()}>
              {target.kind === "new" ? "Create document" : mode === "replace" ? "Replace content" : "Append content"}
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}
