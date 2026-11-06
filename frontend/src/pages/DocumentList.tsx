import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api, type DocumentSummary, type Folder, type SearchResult } from "../api";
import { FoldersDialog } from "../components/FoldersDialog";
import { NewDocumentDialog } from "../components/NewDocumentDialog";
import { saveFile } from "../download";
import { Link } from "../components/Link";
import { navigate, paths, setSearchParams, useSearchParams } from "../router";
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

function DocRow({
  doc: d,
  when,
  title,
  children,
  folderNames,
}: {
  doc: DocumentSummary;
  when: When;
  title?: ReactNode;
  children?: ReactNode;
  /** When given, the row shows the name of the user's folder for it (ADR-010). */
  folderNames?: Map<number, string>;
}) {
  return (
    <li>
      <Link to={paths.doc(d.id)}>{title ?? d.title}</Link>
      {d.permission !== "owner" && (
        <span className={`badge badge-${d.permission}`}>
          {d.permission === "viewer" ? "View only" : "Can edit"} ·{" "}
          {d.owner.display_name}
        </span>
      )}
      {folderNames && d.folder_id !== null && folderNames.has(d.folder_id) && (
        <span className="doc-folder">
          <span aria-hidden="true">▤ </span>
          <span className="visually-hidden">Folder: </span>
          {folderNames.get(d.folder_id)}
        </span>
      )}
      {d.tags.length > 0 && (
        <span className="doc-tags">
          <span className="visually-hidden">Tags: </span>
          {d.tags.map((t) => (
            <span key={t} className="tag">
              {t}
            </span>
          ))}
        </span>
      )}
      <DocTime doc={d} when={when} />
      {children}
    </li>
  );
}

function Section({
  title,
  docs,
  empty,
  when,
  action,
  folderNames,
}: {
  title: string;
  docs: DocumentSummary[];
  empty?: string;
  when: When;
  action?: (doc: DocumentSummary) => ReactNode;
  /** When given, each row shows the name of the user's folder for it. */
  folderNames?: Map<number, string>;
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
            <DocRow key={d.id} doc={d} when={when} folderNames={folderNames}>
              {action?.(d)}
            </DocRow>
          ))}
        </ul>
      )}
    </section>
  );
}

/** The server returns at most this many hits (DOC-017). */
export const SEARCH_LIMIT = 50;
const SEARCH_DELAY_MS = 250;

interface SearchState {
  /** The query these results answer; lags the input while the user is still typing. */
  query: string;
  results: SearchResult[] | null;
  error: string | null;
}
const NO_SEARCH: SearchState = { query: "", results: null, error: null };

/** Debounced server search; responses for superseded queries are dropped. */
/** Debounced search; ``folder``/``tag`` narrow it server-side, before the result limit. */
function useSearch(input: string, folder: string | null, tag: string | null): SearchState {
  const q = input.trim();
  const [state, setState] = useState<SearchState>(NO_SEARCH);
  useEffect(() => {
    if (!q) return;
    let current = true;
    const timer = window.setTimeout(() => {
      api.searchDocuments(q, { folder, tag }).then(
        (results) => current && setState({ query: q, results, error: null }),
        (e: Error) => current && setState({ query: q, results: null, error: e.message }),
      );
    }, SEARCH_DELAY_MS);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [q, folder, tag]);
  return q ? state : NO_SEARCH;
}

export function searchStatus({ query, results }: SearchState): string {
  if (!query || !results) return "";
  const n = results.length;
  if (n === 0) return `No documents match “${query}”.`;
  if (n >= SEARCH_LIMIT) {
    return `Showing the first ${n} documents that match “${query}”. Add words to narrow it down.`;
  }
  return `${n} ${n === 1 ? "document matches" : "documents match"} “${query}”.`;
}

const escapeRegExp = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Marks where the query's words (and their hyphen/dot/slash-separated parts, as the server
 * splits them) start a word, mirroring the server's word-prefix matching. React escapes every
 * piece, so a snippet can never inject markup. */
export function Highlight({ text, query }: { text: string; query: string }) {
  const words = query
    .split(/\s+/)
    .flatMap((w) => [w, ...w.split(/[-./]/)])
    .filter((w) => /[\p{L}\p{N}]/u.test(w));
  if (words.length === 0) return <>{text}</>;
  const longestFirst = [...new Set(words)].sort((x, y) => y.length - x.length);
  const alternatives = longestFirst.map(escapeRegExp).join("|");
  const pattern = new RegExp(`(?<![\\p{L}\\p{N}])(${alternatives})`, "giu");
  return (
    <>
      {text
        .split(pattern)
        .map((part, i) => (i % 2 === 1 ? <mark key={i}>{part}</mark> : part))}
    </>
  );
}

function SearchResults({
  search,
  folderNames,
}: {
  search: SearchState;
  folderNames: Map<number, string>;
}) {
  if (search.error) return <p role="alert">{search.error}</p>;
  if (!search.results?.length) return null;
  return (
    <section aria-labelledby="h-search-results">
      <h2 id="h-search-results">Search results</h2>
      <ul className="doc-list">
        {search.results.map((d) => (
          <DocRow
            key={d.id}
            doc={d}
            when="edited"
            title={<Highlight text={d.title} query={search.query} />}
            folderNames={folderNames}
          >
            {d.snippet && (
              <p className="snippet">
                <Highlight text={d.snippet} query={search.query} />
              </p>
            )}
          </DocRow>
        ))}
      </ul>
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

/** Downloads every document the user owns as one .zip (DOC-033, ADR-012). */
function ExportAllButton() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const { blob, filename, missing } = await api.exportAll();
      saveFile(blob, filename);
      if (missing > 0) {
        setError(
          `Exported, but ${missing === 1 ? "1 attachment" : `${missing} attachments`} couldn't be ` +
            "included. They're listed in index.md; try again later to include them.",
        );
      }
    } catch (e) {
      setError(`Export failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button
        type="button"
        onClick={() => void run()}
        disabled={busy}
        title="Every document you own, with attachments, as Markdown in a .zip"
      >
        {busy ? "Preparing export…" : "Export all"}
      </button>
      {error && (
        <p role="alert" className="notice notice-error export-error">
          {error}
        </p>
      )}
    </>
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
        Start with <strong>New document</strong>: a blank page or a template for POTA
        activations, satellite passes, antenna experiments or research notes. Or bring existing
        notes in with{" "}
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

/** ``?folder=<id>|unfiled&tag=<tag>`` (ADR-010). Unknown folder ids are ignored. */
export function applyFilters(
  docs: DocumentSummary[],
  folder: string | null,
  tag: string | null,
): DocumentSummary[] {
  return docs.filter(
    (d) =>
      (folder === null ||
        (folder === "unfiled" ? d.folder_id === null : d.folder_id === Number(folder))) &&
      (tag === null || d.tags.includes(tag)),
  );
}

export function DocumentList() {
  useDocumentTitle("My Documents");
  const [docs, setDocs] = useState<DocumentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useSortPreference();

  const [folders, setFolders] = useState<Folder[]>([]);
  const [foldersOpen, setFoldersOpen] = useState(false);
  const params = useSearchParams();

  const load = useCallback(() => {
    api.listDocuments().then(setDocs, (e: Error) => setError(e.message));
    api.listFolders().then(setFolders, () => setFolders([]));
  }, []);
  useEffect(load, [load]);

  const [importOpen, setImportOpen] = useState(false);
  const [query, setQuery] = useState("");
  // Filters come from the URL; a folder id the user doesn't have is ignored (ADR-010).
  const folderNames = new Map(folders.map((f) => [f.id, f.name]));
  const folderParam = params.get("folder");
  const folder =
    folderParam === "unfiled" || (folderParam !== null && folderNames.has(Number(folderParam)))
      ? folderParam
      : null;
  const tag = params.get("tag");
  const search = useSearch(query, folder, tag);
  const searchInput = useRef<HTMLInputElement>(null);
  const searching = query.trim() !== "";
  const status = searchStatus(search);

  const [newOpen, setNewOpen] = useState(false);

  if (error) return <p role="alert">{error}</p>;
  if (!docs) return <p className="loading">Loading…</p>;
  const filtering = folder !== null || tag !== null;
  const tagsInUse = [...new Set(docs.flatMap((d) => d.tags))].sort();

  const sorted = sortDocuments(applyFilters(docs, folder, tag), sort);
  const owned = sorted.filter((d) => d.permission === "owner");
  const ownsAny = docs.some((d) => d.permission === "owner");
  const recent = recentlyOpened(docs);
  const when: When = sort === "created" ? "created" : "edited";
  const clearFilters = () => setSearchParams({ folder: null, tag: null });
  const noMatch = "No documents match these filters.";
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
          {ownsAny && <ExportAllButton />}
          <button type="button" className="primary" onClick={() => setNewOpen(true)}>
            New document
          </button>
        </div>
      </div>
      <NewDocumentDialog
        open={newOpen}
        onClose={() => setNewOpen(false)}
        onCreated={(doc) => navigate(paths.doc(doc.id))}
      />
      {importOpen && (
        <Suspense fallback={<p className="loading">Loading…</p>}>
          <ImportDialog
            open={importOpen}
            onClose={() => setImportOpen(false)}
            target={{ kind: "new", onCreated: (doc) => navigate(paths.doc(doc.id)) }}
          />
        </Suspense>
      )}
      {!ownsAny && !searching && <Onboarding />}
      <div className="list-controls" role="group" aria-label="Search, filter and sort">
        {docs.length > 0 && (
          <div role="search" className="doc-search">
            <label htmlFor="doc-search">Search documents</label>
            <div className="doc-search-field">
              <input
                id="doc-search"
                ref={searchInput}
                type="search"
                value={query}
                maxLength={200}
                autoComplete="off"
                spellCheck={false}
                placeholder="Titles and text, e.g. K-4392"
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape" && query) {
                    e.preventDefault();
                    setQuery("");
                  }
                }}
              />
              {query && (
                <button
                  type="button"
                  onClick={() => {
                    setQuery("");
                    searchInput.current?.focus();
                  }}
                >
                  Clear
                </button>
              )}
            </div>
          </div>
        )}
        {docs.length > 0 && (
          <div className="control">
            {/* Explicit for/id: a <select> nested in its <label> adds its value to the name. */}
            <label htmlFor="folder-filter">Folder</label>
            <select
              id="folder-filter"
              value={folder ?? ""}
              onChange={(e) => setSearchParams({ folder: e.target.value || null })}
            >
              <option value="">All folders</option>
              <option value="unfiled">Not in a folder</option>
              {folders.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
          </div>
        )}
        {/* Always available, so a new user can set up folders before writing anything. */}
        <button type="button" className="link-button" onClick={() => setFoldersOpen(true)}>
          Manage folders
        </button>
        {docs.length > 1 && !searching && (
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
        )}
        {tagsInUse.length > 0 && (
          <div className="tag-filters" role="group" aria-label="Filter by tag">
            {tagsInUse.map((t) => (
              <button
                key={t}
                type="button"
                className="tag tag-filter"
                aria-pressed={tag === t}
                onClick={() => setSearchParams({ tag: tag === t ? null : t })}
              >
                {t}
              </button>
            ))}
          </div>
        )}
        {filtering && (
          <button type="button" className="link-button" onClick={clearFilters}>
            Clear filters
          </button>
        )}
      </div>
      {/* Always in the DOM (empty when idle) so screen readers announce each new count. */}
      <p
        role="status"
        className={search.results?.length === 0 ? "search-status empty" : "search-status"}
      >
        {status}
      </p>
      {!filtering && !searching && recent.length > 0 && (
        <Section title="Recently opened" docs={recent} when="opened" folderNames={folderNames} />
      )}
      {searching ? (
        <SearchResults search={search} folderNames={folderNames} />
      ) : (
        <>
          <Section
            title="Owned by me"
            docs={owned}
            empty={filtering ? noMatch : "No documents yet. Create one to get started."}
            when={when}
            folderNames={folder === null ? folderNames : undefined}
          />
          <Section
            title="Shared with me"
            docs={sorted.filter((d) => d.permission !== "owner")}
            empty={filtering ? noMatch : "Nothing has been shared with you yet."}
            when={when}
            folderNames={folder === null ? folderNames : undefined}
          />
          <ArchivedSection onRestored={load} />
        </>
      )}
      <FoldersDialog open={foldersOpen} onClose={() => setFoldersOpen(false)} folders={folders} onChanged={load} />
    </div>
  );
}
