import { lazy, Suspense, useEffect, useState } from "react";
import { api, type DocumentSummary } from "../api";
import { navigate } from "../router";
import { useDocumentTitle } from "../useDocumentTitle";

const ImportDialog = lazy(() =>
  import("../components/ImportDialog").then((m) => ({ default: m.ImportDialog })),
);

function Section({ title, docs, empty }: { title: string; docs: DocumentSummary[]; empty: string }) {
  // aria-labelledby takes a space-separated id list, so the id must not contain spaces.
  const headingId = `h-${title.toLowerCase().replace(/\W+/g, "-")}`;
  return (
    <section aria-labelledby={headingId}>
      <h2 id={headingId}>{title}</h2>
      {docs.length === 0 ? (
        <p className="empty">{empty}</p>
      ) : (
        <ul className="doc-list">
          {docs.map((d) => (
            <li key={d.id}>
              <a href={`#/doc/${d.id}`}>{d.title}</a>
              {d.permission !== "owner" && (
                <span className={`badge badge-${d.permission}`}>
                  {d.permission === "viewer" ? "View only" : "Can edit"} · {d.owner.display_name}
                </span>
              )}
              <time dateTime={d.updated_at}>{new Date(d.updated_at).toLocaleString()}</time>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** First-run guidance, shown until the user owns a document (DOC-014). Points at the page's
 * own buttons rather than duplicating them. */
function Onboarding() {
  return (
    <section className="onboarding" aria-labelledby="h-welcome">
      <h2 id="h-welcome">Welcome to Solara Docs</h2>
      <p>
        A notebook for station logs, activation plans, antenna experiments and research notes.
        Start with <strong>New document</strong>, or bring existing notes in with{" "}
        <strong>Import file</strong>.
      </p>
      <ul>
        <li>
          <strong>Write</strong>
          <span>
            Headings, lists and emphasis. Save with the button or <kbd>Ctrl+S</kbd> / <kbd>⌘S</kbd>.
          </span>
        </li>
        <li>
          <strong>Import</strong>
          <span>Plain text, Markdown or Word (.docx) files become editable documents.</span>
        </li>
        <li>
          <strong>Attach</strong>
          <span>Keep logs, photos and data files with the document they belong to.</span>
        </li>
        <li>
          <strong>Share</strong>
          <span>Give someone read-only access by email once they have signed in.</span>
        </li>
      </ul>
    </section>
  );
}

export function DocumentList() {
  useDocumentTitle("My Documents");
  const [docs, setDocs] = useState<DocumentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listDocuments().then(setDocs, (e: Error) => setError(e.message));
  }, []);

  const [importOpen, setImportOpen] = useState(false);

  const createNew = async () => {
    const doc = await api.createDocument();
    navigate(`#/doc/${doc.id}`);
  };

  if (error) return <p role="alert">{error}</p>;
  if (!docs) return <p className="loading">Loading…</p>;
  const owned = docs.filter((d) => d.permission === "owner");
  return (
    <div className="documents">
      <div className="documents-head">
        <div>
          <h1>My Documents</h1>
          <p>Your notes and the documents others have shared with you.</p>
        </div>
        <div className="actions">
          <button type="button" onClick={() => setImportOpen(true)}>
            Import file
          </button>
          <button type="button" className="primary" onClick={createNew}>
            New document
          </button>
        </div>
      </div>
      {importOpen && (
        <Suspense fallback={<p className="loading">Loading…</p>}>
          <ImportDialog
            open={importOpen}
            onClose={() => setImportOpen(false)}
            target={{ kind: "new", onCreated: (doc) => navigate(`#/doc/${doc.id}`) }}
          />
        </Suspense>
      )}
      {owned.length === 0 && <Onboarding />}
      <Section title="Owned by me" docs={owned} empty="No documents yet. Create one to get started." />
      <Section
        title="Shared with me"
        docs={docs.filter((d) => d.permission !== "owner")}
        empty="Nothing has been shared with you yet."
      />
    </div>
  );
}
