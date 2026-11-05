import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { api, ApiError, type User } from "./api";
import { Link } from "./components/Link";
import { SOLARA_TOOLS_URL } from "./config";
import { DocumentList } from "./pages/DocumentList";
import { Login } from "./pages/Login";
import { NotFound } from "./pages/NotFound";
import { navigate, paths, useRoute, type Route } from "./router";

// Tiptap/ProseMirror is most of the bundle; load it only when a document is opened.
const EditorPage = lazy(() => import("./pages/EditorPage").then((m) => ({ default: m.EditorPage })));

const routeKey = (route: Route) => (route.name === "doc" ? `doc:${route.id}` : route.name);

/**
 * After in-app navigation, move focus to the new page's <main> so keyboard and screen reader
 * users start at the new content instead of on a link that no longer exists (DOC-015).
 * The first render is skipped: a fresh page load keeps the browser's default focus.
 */
function useFocusOnNavigation(key: string, target: React.RefObject<HTMLElement | null>) {
  const previous = useRef(key);
  useEffect(() => {
    if (previous.current === key) return;
    previous.current = key;
    target.current?.focus();
  }, [key, target]);
}

export function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const route = useRoute();
  const mainRef = useRef<HTMLElement>(null);
  useFocusOnNavigation(routeKey(route), mainRef);

  useEffect(() => {
    // Ignore a response that arrives after cleanup (StrictMode runs this twice in dev): a late
    // /api/me answer must not sign the user back in after they have signed out.
    let current = true;
    api
      .me()
      .then((me) => current && setUser(me))
      .catch((err: unknown) => {
        if (!current) return;
        if (!(err instanceof ApiError && err.status === 401)) console.error(err);
        setUser(null);
      });
    return () => {
      current = false;
    };
  }, []);

  if (user === undefined) return <p className="loading">Loading…</p>;
  if (user === null) return <Login onLogin={setUser} />;

  const signOut = async () => {
    if (!navigate(paths.list)) return; // stayed to keep unsaved edits
    await api.logout();
    setUser(null);
  };

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <header className="app-header">
        <div className="header-start">
          <a href={SOLARA_TOOLS_URL} className="back-to-solara">
            <span aria-hidden="true">← </span>Solara Radio Tools
          </a>
          <Link to={paths.list} className="brand">
            <strong>Solara Docs</strong>
            <small>Field notes &amp; technical docs</small>
          </Link>
        </div>
        <span className="whoami">
          Signed in as <strong>{user.display_name}</strong>
          <button type="button" onClick={signOut}>
            Sign out
          </button>
        </span>
      </header>
      <main id="main" ref={mainRef} tabIndex={-1}>
        <Suspense fallback={<p className="loading">Loading editor…</p>}>
          {route.name === "doc" && <EditorPage key={route.id} id={route.id} />}
          {route.name === "list" && <DocumentList />}
          {route.name === "not-found" && <NotFound />}
        </Suspense>
      </main>
    </>
  );
}
