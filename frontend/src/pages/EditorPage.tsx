import { EditorContent, useEditor } from "@tiptap/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type DocumentFull } from "../api";
import { AttachmentsPanel } from "../components/AttachmentsPanel";
import { ImportDialog } from "../components/ImportDialog";
import { KeyboardHelp } from "../components/KeyboardHelp";
import { OrganizePanel } from "../components/OrganizePanel";
import { SaveStatus, type SaveState } from "../components/SaveStatus";
import { ShareDialog } from "../components/ShareDialog";
import { displayShortcut, Toolbar, TOOLBAR_SHORTCUT } from "../components/Toolbar";
import { normalizeContent } from "../content";
import { extensions } from "../editorExtensions";
import { Link } from "../components/Link";
import { navigate, navigationGuard, paths } from "../router";
import { useDocumentTitle } from "../useDocumentTitle";

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
        <Link to={paths.list}>Back to documents</Link>
      </div>
    );
  if (!doc) return <p className="loading">Loading…</p>;
  // Archiving/restoring changes editability, so start a fresh editor for the new state.
  return <DocumentEditor key={doc.archived_at ?? "active"} initial={doc} onReplace={setDoc} />;
}

function DocumentEditor({
  initial,
  onReplace,
}: {
  initial: DocumentFull;
  onReplace: (doc: DocumentFull) => void;
}) {
  const isViewer = initial.permission === "viewer";
  const archived = initial.archived_at !== null;
  const readOnly = isViewer || archived;
  const isOwner = initial.permission === "owner";
  const [busy, setBusy] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [title, setTitle] = useState(initial.title);
  useDocumentTitle(title || "Untitled document");
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
    editorProps: {
      attributes: {
        "aria-label": "Document body",
        class: "editor-body",
        role: "textbox",
        "aria-multiline": "true",
        ...(readOnly ? { "aria-readonly": "true" } : { "aria-describedby": "editor-keyboard-hint" }),
      },
    },
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

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
    } catch (e) {
      setSaveState("error");
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const duplicate = () =>
    run(async () => {
      const copy = await api.duplicateDocument(initial.id);
      navigate(paths.doc(copy.id));
    });
  const setArchived = (value: boolean) =>
    run(async () => {
      onReplace(await (value ? api.archiveDocument(initial.id) : api.restoreDocument(initial.id)));
    });
  const saveFirst = dirty ? "Save your changes first" : undefined;

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
        <Link to={paths.list}>
          <span aria-hidden="true">← </span>Documents
        </Link>
        {isViewer && (
          <span className="badge badge-viewer">View only · shared by {initial.owner.display_name}</span>
        )}
        {archived && <span className="badge badge-archived">Archived</span>}
        {!readOnly && <SaveStatus state={saveState} />}
        <button type="button" onClick={() => void duplicate()} disabled={busy || dirty} title={saveFirst}>
          Duplicate
        </button>
        {isOwner && !archived && (
          <button type="button" onClick={() => void setArchived(true)} disabled={busy || dirty} title={saveFirst}>
            Archive
          </button>
        )}
        {!readOnly && (
          <>
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
      <OrganizePanel doc={initial} />
      {archived && (
        <div className="notice notice-archived" role="note">
          <span>
            Archived {new Date(initial.archived_at!).toLocaleDateString()}. It's hidden from document
            lists and can't be edited{isOwner ? " until you restore it" : ""}.
          </span>
          {isOwner && (
            <button type="button" onClick={() => void setArchived(false)} disabled={busy}>
              Restore
            </button>
          )}
        </div>
      )}
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
      {!readOnly && (
        <p id="editor-keyboard-hint" className="visually-hidden">
          Press {displayShortcut(TOOLBAR_SHORTCUT)} to move to the formatting toolbar.
        </p>
      )}
      <EditorContent editor={editor} className="editor" />
      {!readOnly && <KeyboardHelp />}
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
        />
      )}
    </div>
  );
}
