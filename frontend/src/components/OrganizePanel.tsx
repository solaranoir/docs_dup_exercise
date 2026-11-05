import { useEffect, useId, useState } from "react";
import { api, type DocumentFull, type Folder } from "../api";
import { TagEditor } from "./TagEditor";

/**
 * The signed-in user's own folder and tags for this document (ADR-010). Saved immediately and
 * independently of the document's Save: organising is not editing, so viewers and archived
 * documents can be organised too.
 */
export function OrganizePanel({ doc }: { doc: DocumentFull }) {
  const [folders, setFolders] = useState<Folder[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [folderId, setFolderId] = useState<number | null>(doc.folder_id);
  const [tags, setTags] = useState<string[]>(doc.tags);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState("");
  const folderSelect = useId();

  useEffect(() => {
    api.listFolders().then(setFolders, () => setFolders([]));
    api.listTags().then(
      (t) => setSuggestions([...new Set([...t.tags.map((x) => x.tag), ...t.suggestions])]),
      () => setSuggestions([]),
    );
  }, []);

  const save = async (action: () => Promise<void>, message: string) => {
    setError(null);
    try {
      await action();
      setSaved(message);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const changeFolder = (value: string) => {
    const next = value ? Number(value) : null;
    const previous = folderId;
    setFolderId(next);
    void save(async () => {
      try {
        await api.setFolder(doc.id, next);
      } catch (e) {
        setFolderId(previous);
        throw e;
      }
    }, next === null ? "Removed from folder" : `Filed in ${folders.find((f) => f.id === next)?.name}`);
  };

  const changeTags = (next: string[]) => {
    const previous = tags;
    setTags(next);
    void save(async () => {
      try {
        setTags((await api.setTags(doc.id, next)).tags);
      } catch (e) {
        setTags(previous);
        throw e;
      }
    }, "Tags saved");
  };

  return (
    <section className="organize" aria-label="Organise (only you see this)">
      <div className="organize-folder">
        <label htmlFor={folderSelect}>Folder</label>
        <select id={folderSelect} value={folderId ?? ""} onChange={(e) => changeFolder(e.target.value)}>
          <option value="">No folder</option>
          {folders.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </select>
      </div>
      <TagEditor tags={tags} suggestions={suggestions} onChange={changeTags} />
      <p className="organize-note">
        Only you see your folders and tags.{" "}
        {/* aria-live rather than role="status": the page already has the document's save status. */}
        <span aria-live="polite" className="visually-hidden">
          {saved}
        </span>
      </p>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
