import { lazy, Suspense, useCallback, useEffect, useState, type ReactNode } from "react";
import { api, type DocumentSummary } from "../api";
import { Link } from "../components/Link";
import { navigate, paths } from "../router";
import { useDocumentTitle } from "../useDocumentTitle";

const ImportDialog = lazy(() =>
  import("../components/ImportDialog").then((m) => ({ default: m.ImportDialog })),
);

export type SortKey = "edited" | "created" | "title" | "title-desc";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "edited", label: "Last edited" },
  { key: "created", label: "Newest first" },
  { key: "title", label: "Title A–Z" },
  { key: "title-desc", label: "Title Z–A" },
];
const SORT_STORAGE_KEY = "solara-docs:sort";
const RECENT_LIMIT = 5;
const collator = new Intl.Collator(undefined, {
  sensitivity: "base",
  numeric: true,
});

export function sortDocuments(
  docs: DocumentSummary[],
  key: SortKey,
): DocumentSummary[] {
  const byTime =
    (field: "updated_at" | "created_at") =>
    (a: DocumentSummary, b: DocumentSummary) =>
      b[field].localeCompare(a[field]);
  const compare = {
    edited: byTime("updated_at"),
    created: byTime("created_at"),
    title: (a: DocumentSummary, b: DocumentSummary) =>
      collator.compare(a.title, b.title),
    "title-desc": (a: DocumentSummary, b: DocumentSummary) =>
      collator.compare(b.title, a.title),
  }[key];
  return [...docs].sort(compare);
}

export function recentlyOpened(docs: DocumentSummary[]): DocumentSummary[] {
  return docs
    .filter((d) => d.last_opened_at)
    .sort((a, b) => b.last_opened_at!.localeCompare(a.last_opened_at!))
    .slice(0, RECENT_LIMIT);
}

/** Remembered per browser; storage can be unavailable (private mode), so never required. */
function useSortPreference(): [SortKey, (key: SortKey) => void] {
  const [key, setKey] = useState<SortKey>(() => {
    try {
      const saved = window.localStorage.getItem(SORT_STORAGE_KEY);
      return SORTS.some((s) => s.key === saved) ? (saved as SortKey) : "edited";
    } catch {
      return "edited";
    }
  });
  const update = (next: SortKey) => {
    setKey(next);
    try {
      window.localStorage.setItem(SORT_STORAGE_KEY, next);
    } catch {
      /* preference just won't persist */
    }
  };
  return [key, update];
}

const formatTime = (iso: string) => new Date(iso).toLocaleString();

type When = "edited" | "created" | "opened";

function DocTime({ doc, when }: { doc: DocumentSummary; when: When }) {
  const [label, iso] =
    when === "opened"
      ? ["Opened", doc.last_opened_at!]
      : when === "created"
        ? ["Created", doc.created_at]
        : ["Edited", doc.updated_at];
  return (
    <time dateTime={iso}>
      {label} {formatTime(iso)}
    </time>
  );
}

function Section({
  title,
  docs,
  empty,
  when,
  action,
}: {
  title: string;
  docs: DocumentSummary[];
  empty?: string;
  when: When;
  action?: (doc: DocumentSummary) => ReactNode;
}) {
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
              <Link to={paths.doc(d.id)}>{d.title}</Link>
              {d.permission !== "owner" && (
                <span className={`badge badge-${d.permission}`}>
                  {d.permission === "viewer" ? "View only" : "Can edit"} ·{" "}
                  {d.owner.display_name}
                </span>
              )}
              <DocTime doc={d} when={when} />
              {action?.(d)}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Archived documents load only on request, so the main list stays fast and uncluttered. */
function ArchivedSection({ onRestored }: { onRestored: () => void }) {
  const [docs, setDocs] = useState<DocumentSummary[] | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api.listDocuments(true).then(setDocs, (e: Error) => setError(e.message));
  const toggle = () => {
    if (!open && docs === null) void load();
    setOpen(!open);
  };
  const restore = async (doc: DocumentSummary) => {
    try {
      await api.restoreDocument(doc.id);
      await load();
      onRestored();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="archived">
      <button
        type="button"
        className="link-button"
        aria-expanded={open}
        onClick={toggle}
      >
        {open ? "Hide archived documents" : "Show archived documents"}
      </button>
      {open && error && <p role="alert">{error}</p>}
      {open && !error && docs === null && <p className="loading">Loading…</p>}
      {open && docs && (
        <Section
          title="Archived"
          docs={docs}
          empty="No archived documents."
          when="edited"
          action={(d) =>
            d.permission === "owner" ? (
              <button
                type="button"
                onClick={() => void restore(d)}
                aria-label={`Restore ${d.title}`}
              >
                Restore
              </button>
            ) : null
          }
        />
      )}
    </div>
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
  const [sort, setSort] = useSortPreference();

  const load = useCallback(() => {
    api.listDocuments().then(setDocs, (e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  const [importOpen, setImportOpen] = useState(false);

  const createNew = async () => {
    const doc = await api.createDocument();
    navigate(paths.doc(doc.id));
  };

  if (error) return <p role="alert">{error}</p>;
  if (!docs) return <p className="loading">Loading…</p>;
  const sorted = sortDocuments(docs, sort);
  const owned = sorted.filter((d) => d.permission === "owner");
  const recent = recentlyOpened(docs);
  const when: When = sort === "created" ? "created" : "edited";
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
            target={{ kind: "new", onCreated: (doc) => navigate(paths.doc(doc.id)) }}
          />
        </Suspense>
      )}
      {owned.length === 0 && <Onboarding />}
      {recent.length > 0 && <Section title="Recently opened" docs={recent} when="opened" />}
      {docs.length > 1 && (
        <div className="list-controls">
          <label>
            Sort by{" "}
            <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
              {SORTS.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      <Section
        title="Owned by me"
        docs={owned}
        empty="No documents yet. Create one to get started."
        when={when}
      />
      <Section
        title="Shared with me"
        docs={sorted.filter((d) => d.permission !== "owner")}
        empty="Nothing has been shared with you yet."
        when={when}
      />
      <ArchivedSection onRestored={load} />
    </div>
  );
}
