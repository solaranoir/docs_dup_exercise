import { useState } from "react";
import { api } from "../api";
import { printDocument, saveFile } from "../download";
import { Modal } from "./Modal";

/** Export one document: Markdown (with attachments as a .zip) or print / save as PDF. */
export function ExportDialog({
  open,
  onClose,
  documentId,
  title,
  dirty,
}: {
  open: boolean;
  onClose: () => void;
  documentId: string;
  title: string;
  /** Unsaved edits: Markdown comes from the saved version, so ask for a save first. */
  dirty: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    setError(null);
    onClose();
  };

  const markdown = async () => {
    setBusy(true);
    setError(null);
    try {
      const { blob, filename } = await api.exportDocument(documentId);
      saveFile(blob, filename);
      close();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const pdf = () => {
    close();
    // Print after the dialog has left the top layer, so it isn't part of the page printed.
    window.requestAnimationFrame(() => printDocument(title.trim() || "Untitled document"));
  };

  return (
    <Modal title="Export" open={open} onClose={close}>
      <div className="export-options">
        <div className="export-option">
          <h3>Markdown</h3>
          <p className="hint">
            A <code>.md</code> file that most notes apps and editors can open. If the document has
            attachments, you get a <code>.zip</code> with them alongside.
          </p>
          {dirty && (
            <p className="hint" id="export-save-first">
              Save your changes first: the export uses the saved version.
            </p>
          )}
          <button
            type="button"
            className="primary"
            onClick={() => void markdown()}
            disabled={busy || dirty}
            aria-describedby={dirty ? "export-save-first" : undefined}
          >
            {busy ? "Preparing…" : "Download Markdown"}
          </button>
        </div>
        <div className="export-option">
          <h3>PDF</h3>
          <p className="hint">
            Opens your browser's print dialog with a clean page layout. Choose{" "}
            <strong>Save as PDF</strong> as the printer.
          </p>
          <button type="button" onClick={pdf}>
            Print or save as PDF
          </button>
        </div>
      </div>
      {error && <p role="alert">{error}</p>}
    </Modal>
  );
}
