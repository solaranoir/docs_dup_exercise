import { useEffect, useState } from "react";
import { api, type DocumentSummary } from "../api";
import { navigate } from "../router";

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

export function DocumentList() {
  const [docs, setDocs] = useState<DocumentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listDocuments().then(setDocs, (e: Error) => setError(e.message));
  }, []);

  const createNew = async () => {
    const doc = await api.createDocument();
    navigate(`#/doc/${doc.id}`);
  };

  if (error) return <p role="alert">{error}</p>;
  if (!docs) return <p className="loading">Loading…</p>;
  return (
    <div className="documents">
      <div className="documents-head">
        <h1>My Documents</h1>
        <button type="button" className="primary" onClick={createNew}>
          New document
        </button>
      </div>
      <Section
        title="Owned by me"
        docs={docs.filter((d) => d.permission === "owner")}
        empty="No documents yet. Create one to get started."
      />
      <Section
        title="Shared with me"
        docs={docs.filter((d) => d.permission !== "owner")}
        empty="Nothing has been shared with you yet."
      />
    </div>
  );
}
