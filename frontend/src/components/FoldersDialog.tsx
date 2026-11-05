import { useState, type FormEvent } from "react";
import { api, type Folder } from "../api";
import { Modal } from "./Modal";

/** Create, rename and delete the user's folders. Deleting ungroups documents (ADR-010). */
export function FoldersDialog({
  open,
  onClose,
  folders,
  onChanged,
}: {
  open: boolean;
  onClose: () => void;
  folders: Folder[];
  onChanged: () => void;
}) {
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [rename, setRename] = useState("");
  const [error, setError] = useState<string | null>(null);

  const run = async (action: () => Promise<unknown>) => {
    setError(null);
    try {
      await action();
      onChanged();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    }
  };

  const create = async (e: FormEvent) => {
    e.preventDefault();
    if (await run(() => api.createFolder(name))) setName("");
  };
  const saveRename = async (e: FormEvent, id: number) => {
    e.preventDefault();
    if (await run(() => api.renameFolder(id, rename))) setEditing(null);
  };
  const remove = (folder: Folder) => {
    const docs = folder.document_count === 1 ? "1 document" : `${folder.document_count} documents`;
    if (!window.confirm(`Delete the folder "${folder.name}"? Its ${docs} will stay, just unfiled.`)) return;
    void run(() => api.deleteFolder(folder.id));
  };

  return (
    <Modal
      title="Folders"
      open={open}
      onClose={() => {
        setError(null);
        setEditing(null);
        onClose();
      }}
    >
      <p className="hint">Folders are private to you. Each document can be in one folder.</p>
      <form className="folder-form" onSubmit={(e) => void create(e)}>
        <label>
          New folder
          <input value={name} maxLength={60} onChange={(e) => setName(e.target.value)} placeholder="2026 POTA" />
        </label>
        <button type="submit" className="primary" disabled={!name.trim()}>
          Create
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      {folders.length === 0 ? (
        <p className="empty">No folders yet.</p>
      ) : (
        <ul className="folder-list">
          {folders.map((f) =>
            editing === f.id ? (
              <li key={f.id}>
                <form className="folder-form" onSubmit={(e) => void saveRename(e, f.id)}>
                  <label>
                    <span className="visually-hidden">Rename {f.name}</span>
                    <input value={rename} maxLength={60} autoFocus onChange={(e) => setRename(e.target.value)} />
                  </label>
                  <button type="submit" className="primary" disabled={!rename.trim()}>
                    Save
                  </button>
                  <button type="button" onClick={() => setEditing(null)}>
                    Cancel
                  </button>
                </form>
              </li>
            ) : (
              <li key={f.id}>
                <span className="folder-name">{f.name}</span>
                <span className="folder-count">{f.document_count}</span>
                <button
                  type="button"
                  aria-label={`Rename ${f.name}`}
                  onClick={() => {
                    setEditing(f.id);
                    setRename(f.name);
                  }}
                >
                  Rename
                </button>
                <button type="button" aria-label={`Delete ${f.name}`} onClick={() => remove(f)}>
                  Delete
                </button>
              </li>
            ),
          )}
        </ul>
      )}
    </Modal>
  );
}
