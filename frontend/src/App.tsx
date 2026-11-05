import { lazy, Suspense, useEffect, useState } from "react";
import { api, ApiError, type User } from "./api";
import { SOLARA_TOOLS_URL } from "./config";
import { DocumentList } from "./pages/DocumentList";
import { Login } from "./pages/Login";
import { navigate, useRoute } from "./router";

// Tiptap/ProseMirror is most of the bundle; load it only when a document is opened.
const EditorPage = lazy(() => import("./pages/EditorPage").then((m) => ({ default: m.EditorPage })));

export function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const route = useRoute();

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch((err: unknown) => {
        if (!(err instanceof ApiError && err.status === 401)) console.error(err);
        setUser(null);
      });
  }, []);

  if (user === undefined) return <p className="loading">Loading…</p>;
  if (user === null) return <Login onLogin={setUser} />;

  const signOut = async () => {
    navigate("#/");
    await api.logout();
    setUser(null);
  };

  return (
    <>
      <header className="app-header">
        <div className="header-start">
          <a href={SOLARA_TOOLS_URL} className="back-to-solara">
            <span aria-hidden="true">← </span>Solara Radio Tools
          </a>
          <a href="#/" className="brand" onClick={(e) => (e.preventDefault(), navigate("#/"))}>
            <strong>Solara Docs</strong>
            <small>Field notes &amp; technical docs</small>
          </a>
        </div>
        <span className="whoami">
          Signed in as <strong>{user.display_name}</strong>
          <button type="button" onClick={signOut}>
            Sign out
          </button>
        </span>
      </header>
      <main>
        <Suspense fallback={<p className="loading">Loading editor…</p>}>
          {route.name === "doc" ? <EditorPage key={route.id} id={route.id} /> : <DocumentList />}
        </Suspense>
      </main>
    </>
  );
}
