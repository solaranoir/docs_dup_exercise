import { useEffect, useRef, useState } from "react";
import { api, UPLOAD_ACCEPT, type Attachment } from "../api";

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function AttachmentsPanel({ documentId, canEdit }: { documentId: string; canEdit: boolean }) {
  const [items, setItems] = useState<Attachment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  // Bumped on every local change so a list response requested earlier can't overwrite it.
  const version = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const requestedAt = version.current;
    api.listAttachments(documentId).then(
      (list) => {
        if (!cancelled && version.current === requestedAt) setItems(list);
      },
      (e: Error) => !cancelled && setError(e.message),
    );
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const added = await api.uploadAttachment(documentId, file);
      version.current += 1;
      setItems((prev) => [...(prev ?? []), added]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };

  const remove = async (a: Attachment) => {
    if (!window.confirm(`Remove attachment “${a.original_name}”?`)) return;
    try {
      await api.deleteAttachment(documentId, a.id);
      version.current += 1;
      setItems((prev) => (prev ?? []).filter((x) => x.id !== a.id));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <section className="attachments" aria-labelledby="attachments-heading">
      <div className="attachments-head">
        <h2 id="attachments-heading">Attachments</h2>
        {canEdit && (
          <label className="button-like">
            {busy ? "Uploading…" : "Attach file"}
            <input
              ref={input}
              type="file"
              accept={UPLOAD_ACCEPT}
              className="visually-hidden"
              aria-label="Attach file"
              disabled={busy}
              onChange={(e) => void upload(e.target.files?.[0])}
            />
          </label>
        )}
      </div>
      {error && (
        <p role="alert" className="notice notice-error">
          {error}
        </p>
      )}
      {items && items.length === 0 && <p className="empty">No attachments.</p>}
      {items && items.length > 0 && (
        <ul className="doc-list">
          {items.map((a) => (
            <li key={a.id}>
              <a href={api.attachmentUrl(documentId, a.id)} download={a.original_name}>
                {a.original_name}
              </a>
              <span className="hint">{formatBytes(a.size_bytes)}</span>
              {canEdit && (
                <button type="button" aria-label={`Remove ${a.original_name}`} onClick={() => void remove(a)}>
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
