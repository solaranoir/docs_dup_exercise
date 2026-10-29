import { EditorContent, useEditor } from "@tiptap/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type DocumentFull } from "../api";
import { AttachmentsPanel } from "../components/AttachmentsPanel";
import { ImportDialog } from "../components/ImportDialog";
import { SaveStatus, type SaveState } from "../components/SaveStatus";
import { ShareDialog } from "../components/ShareDialog";
import { Toolbar } from "../components/Toolbar";
import { normalizeContent } from "../content";
import { extensions } from "../editorExtensions";
import { navigate, navigationGuard } from "../router";

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
  const isOwner = initial.permission === "owner";
  const [importOpen, setImportOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
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
            <button
              type="button"
              onClick={() => setImportOpen(true)}
              disabled={dirty}
              title={dirty ? "Save your changes before importing" : undefined}
            >
              Import…
            </button>
            {isOwner && (
              <button type="button" onClick={() => setShareOpen(true)}>
                Share
              </button>
            )}
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
      <AttachmentsPanel documentId={initial.id} canEdit={!readOnly} />
      {!readOnly && (
        <ImportDialog
          open={importOpen}
          onClose={() => setImportOpen(false)}
          target={{
            kind: "existing",
            document: { ...initial, title, revision },
            onApplied: (doc) => {
              editor?.commands.setContent(doc.content_json, { emitUpdate: false });
              setRevision(doc.revision);
              setMessage(null);
              setSaveState("saved");
            },
          }}
        />
      )}
      {isOwner && (
        <ShareDialog
          open={shareOpen}
          onClose={() => setShareOpen(false)}
          documentId={initial.id}
          ownerId={initial.owner.id}
        />
      )}
    </div>
  );
}
