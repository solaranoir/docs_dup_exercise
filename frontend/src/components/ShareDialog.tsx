import { useEffect, useState, type FormEvent } from "react";
import { api, type Grant } from "../api";
import { Modal } from "./Modal";

/** Owner-only. View-only sharing (decision #7) with existing accounts, by email (ADR-009). */
export function ShareDialog({
  open,
  onClose,
  documentId,
}: {
  open: boolean;
  onClose: () => void;
  documentId: string;
}) {
  const [grants, setGrants] = useState<Grant[]>([]);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    api.listGrants(documentId).then(setGrants, (e: Error) => setError(e.message));
  }, [open, documentId]);

  const share = async (event: FormEvent) => {
    event.preventDefault();
    if (!email.trim()) return;
    setError(null);
    setBusy(true);
    try {
      const grant = await api.grant(documentId, email.trim());
      setGrants((g) => [...g.filter((x) => x.user_id !== grant.user_id), grant]);
      setEmail("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (grant: Grant) => {
    setError(null);
    try {
      await api.revoke(documentId, grant.user_id);
      setGrants((g) => g.filter((x) => x.user_id !== grant.user_id));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const close = () => {
    setError(null); // a stale error shouldn't greet the next opening
    onClose();
  };

  return (
    <Modal title="Share document" open={open} onClose={close}>
      <p className="hint">People you share with can view this document and its attachments, but not edit.</p>
      {error && (
        <p role="alert" className="notice notice-error">
          {error}
        </p>
      )}
      <form className="share-form" onSubmit={(e) => void share(e)}>
        <label htmlFor="share-email">Email address</label>
        <input
          id="share-email"
          type="email"
          autoComplete="off"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="name@example.com"
          required
        />
        <button type="submit" className="primary" disabled={busy}>
          Share
        </button>
      </form>
      {grants.length === 0 ? (
        <p className="hint">Not shared with anyone yet.</p>
      ) : (
        <ul className="share-list" aria-label="People with access">
          {grants.map((g) => (
            <li key={g.user_id}>
              <span>
                {g.display_name}
                {g.email && <span className="hint"> · {g.email}</span>}
              </span>
              <span className="badge badge-viewer">Viewer</span>
              <button type="button" onClick={() => void revoke(g)}>
                Revoke {g.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
