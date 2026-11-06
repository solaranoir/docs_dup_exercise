import { useEffect, useId, useRef, useState } from "react";
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

  // Saves go out one at a time, in order, and only the newest change's answer is applied:
  // otherwise a quick second tag could be overwritten by the first request's late response,
  // or the server could apply the requests out of order and keep the stale list. Changes made
  // while a save is in flight collapse into one follow-up save of the newest value.
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const latest = useRef({ tags: 0, folder: 0 });
  const savedTags = useRef(doc.tags);
  const savedFolder = useRef(doc.folder_id);
  const [pending, setPending] = useState(0);

  // Leaving the page (reload, close) mid-save would drop it; in-app navigation is fine.
  useEffect(() => {
    if (pending === 0) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [pending]);

  const enqueue = <T,>(
    kind: "tags" | "folder",
    send: () => Promise<T>,
    onSaved: (result: T) => void,
    onFailed: () => void,
    message: string,
  ) => {
    const seq = ++latest.current[kind];
    setError(null);
    setPending((n) => n + 1);
    queue.current = queue.current.then(async () => {
      try {
        if (seq !== latest.current[kind]) return; // superseded before it was sent
        const result = await send();
        if (seq === latest.current[kind]) {
          onSaved(result);
          setSaved(message);
        }
      } catch (e) {
        if (seq === latest.current[kind]) {
          onFailed();
          setError((e as Error).message);
        }
      } finally {
        setPending((n) => n - 1);
      }
    });
  };

  const changeFolder = (value: string) => {
    const next = value ? Number(value) : null;
    setFolderId(next);
    enqueue(
      "folder",
      () => api.setFolder(doc.id, next),
      () => (savedFolder.current = next),
      () => setFolderId(savedFolder.current),
      next === null ? "Removed from folder" : `Filed in ${folders.find((f) => f.id === next)?.name}`,
    );
  };

  const changeTags = (next: string[]) => {
    setTags(next);
    enqueue(
      "tags",
      () => api.setTags(doc.id, next),
      (result) => {
        savedTags.current = result.tags;
        setTags(result.tags);
      },
      () => setTags(savedTags.current),
      "Tags saved",
    );
  };

  return (
    <section className="organize" aria-label="Organise (only you see this)" aria-busy={pending > 0}>
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
