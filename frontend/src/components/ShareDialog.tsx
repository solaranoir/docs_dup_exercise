import { useEffect, useState } from "react";
import { api, type Grant, type User } from "../api";
import { Modal } from "./Modal";

/** Owner-only. MVP sharing is view-only with existing seeded accounts (decision #7). */
export function ShareDialog({
  open,
  onClose,
  documentId,
  ownerId,
}: {
  open: boolean;
  onClose: () => void;
  documentId: string;
  ownerId: number;
}) {
  const [users, setUsers] = useState<User[]>([]);
  const [grants, setGrants] = useState<Grant[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    Promise.all([api.demoUsers(), api.listGrants(documentId)]).then(
      ([u, g]) => {
        setUsers(u.filter((x) => x.id !== ownerId));
        setGrants(g);
      },
      (e: Error) => setError(e.message),
    );
  }, [open, documentId, ownerId]);

  const toggle = async (user: User, hasAccess: boolean) => {
    setError(null);
    try {
      if (hasAccess) {
        await api.revoke(documentId, user.id);
        setGrants((g) => g.filter((x) => x.user_id !== user.id));
      } else {
        const grant = await api.grant(documentId, user.id);
        setGrants((g) => [...g.filter((x) => x.user_id !== user.id), grant]);
      }
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <Modal title="Share document" open={open} onClose={onClose}>
      <p className="hint">People you share with can view this document and its attachments, but not edit.</p>
      {error && (
        <p role="alert" className="notice notice-error">
          {error}
        </p>
      )}
      <ul className="share-list">
        {users.map((u) => {
          const hasAccess = grants.some((g) => g.user_id === u.id);
          return (
            <li key={u.id}>
              <span>{u.display_name}</span>
              {hasAccess && <span className="badge badge-viewer">Viewer</span>}
              <button
                type="button"
                className={hasAccess ? undefined : "primary"}
                onClick={() => void toggle(u, hasAccess)}
              >
                {hasAccess ? `Revoke ${u.display_name}` : `Share with ${u.display_name}`}
              </button>
            </li>
          );
        })}
      </ul>
    </Modal>
  );
}
