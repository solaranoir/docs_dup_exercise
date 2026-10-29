import { FontSize, TextStyle } from "@tiptap/extension-text-style";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type DocumentFull } from "../api";
import { SaveStatus, type SaveState } from "../components/SaveStatus";
import { Toolbar } from "../components/Toolbar";
import { normalizeContent } from "../content";
import { navigate, navigationGuard } from "../router";

/** Only the nodes/marks the server schema accepts (backend/app/content.py). */
export const extensions = [
  StarterKit.configure({
    heading: { levels: [1, 2, 3] },
    blockquote: false,
    codeBlock: false,
    code: false,
    horizontalRule: false,
    strike: false,
    link: false,
  }),
  TextStyle,
  FontSize,
];

export function EditorPage({ id }: { id: string }) {
  const [doc, setDoc] = useState<DocumentFull | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getDocument(id).then(setDoc, (e: ApiError) =>
      setError(e.status === 404 ? "Document not found, or you do not have access to it." : e.message),
    );
  }, [id]);

  if (error)
    return (
      <div className="editor-page">
        <p role="alert">{error}</p>
        <a href="#/">Back to documents</a>
      </div>
    );
  if (!doc) return <p className="loading">Loading…</p>;
  return <DocumentEditor initial={doc} />;
}

function DocumentEditor({ initial }: { initial: DocumentFull }) {
  const readOnly = initial.permission === "viewer";
  const [title, setTitle] = useState(initial.title);
  const [revision, setRevision] = useState(initial.revision);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [message, setMessage] = useState<string | null>(null);
  // Bumped on every edit so a save that finishes mid-typing doesn't claim "saved".
  const editCount = useRef(0);

  const markDirty = useCallback(() => {
    editCount.current += 1;
    setSaveState((s) => (s === "conflict" ? s : "unsaved"));
  }, []);

  const editor = useEditor({
    extensions,
    content: initial.content_json,
    editable: !readOnly,
    onUpdate: markDirty,
    editorProps: { attributes: { "aria-label": "Document body", class: "editor-body" } },
  });

  const dirty = saveState !== "saved";
  useEffect(() => {
    navigationGuard.dirty = dirty && !readOnly;
    if (!navigationGuard.dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, readOnly]);
  useEffect(() => () => void (navigationGuard.dirty = false), []);

  const save = useCallback(async () => {
    if (readOnly || !editor || saveState === "saving") return;
    const trimmed = title.trim();
    if (!trimmed) {
      setSaveState("error");
      setMessage("Title is required.");
      return;
    }
    const startedAt = editCount.current;
    setSaveState("saving");
    try {
      const saved = await api.updateDocument(initial.id, {
        expected_revision: revision,
        title: trimmed,
        content_json: normalizeContent(editor.getJSON()),
      });
      setRevision(saved.revision);
      setMessage(null);
      setSaveState(editCount.current === startedAt ? "saved" : "unsaved");
    } catch (e) {
      const err = e as ApiError;
      setSaveState(err.status === 409 ? "conflict" : "error");
      setMessage(err.message);
    }
  }, [editor, initial.id, readOnly, revision, saveState, title]);

  const saveRef = useRef(save);
  useEffect(() => {
    saveRef.current = save;
  }, [save]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        void saveRef.current();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const reloadLatest = async () => {
    if (!window.confirm("Discard your unsaved edits and load the latest version?")) return;
    const latest = await api.getDocument(initial.id);
    editor?.commands.setContent(latest.content_json, { emitUpdate: false });
    setTitle(latest.title);
    setRevision(latest.revision);
    setMessage(null);
    setSaveState("saved");
  };

  return (
    <div className="editor-page">
      <div className="editor-head">
        <a href="#/" onClick={(e) => (e.preventDefault(), navigate("#/"))}>
          ← Documents
        </a>
        {readOnly ? (
          <span className="badge badge-viewer">View only · shared by {initial.owner.display_name}</span>
        ) : (
          <>
            <SaveStatus state={saveState} />
            <button type="button" className="primary" onClick={() => void save()} disabled={saveState === "saving"}>
              Save
            </button>
          </>
        )}
      </div>
      <input
        className="title-input"
        aria-label="Document title"
        value={title}
        maxLength={160}
        readOnly={readOnly}
        onChange={(e) => {
          setTitle(e.target.value);
          markDirty();
        }}
      />
      {message && (
        <div role="alert" className={`notice notice-${saveState}`}>
          {message}
          {saveState === "conflict" && (
            <button type="button" onClick={() => void reloadLatest()}>
              Reload latest version
            </button>
          )}
        </div>
      )}
      {editor && !readOnly && <Toolbar editor={editor} />}
      <EditorContent editor={editor} className="editor" />
    </div>
  );
}
