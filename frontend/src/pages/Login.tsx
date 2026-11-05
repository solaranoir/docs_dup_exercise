import { useEffect, useState } from "react";
import { api, type AuthMethods, type DemoUser, type User } from "../api";
import { SOLARA_TOOLS_URL } from "../config";
import { useDocumentTitle } from "../useDocumentTitle";

const SIGN_IN_FAILED = "Sign-in failed. Please try again.";
/** Reasons the API puts in `?auth_error=` after a failed OAuth callback (backend app/oauth.py). */
const AUTH_ERRORS: Record<string, string> = {
  not_invited: "That account isn't invited to Solara Docs yet. Ask the owner for an invite, then try again.",
  unverified_email: "Your account needs a verified email address. Verify it with the provider, then try again.",
  cancelled: "Sign-in was cancelled.",
  expired: "The sign-in attempt expired. Please try again.",
  unavailable: "That sign-in method isn't available right now.",
  failed: SIGN_IN_FAILED,
};

/** Read and remove `?auth_error=` so a refresh doesn't show the message again. */
export function takeAuthError(): string | null {
  const url = new URL(window.location.href);
  const code = url.searchParams.get("auth_error");
  if (code === null) return null;
  url.searchParams.delete("auth_error");
  window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  return AUTH_ERRORS[code] ?? SIGN_IN_FAILED;
}

export function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [methods, setMethods] = useState<AuthMethods | null>(null);
  const [demoUsers, setDemoUsers] = useState<DemoUser[]>([]);
  const [error, setError] = useState<string | null>(() => takeAuthError());
  useDocumentTitle("Sign in");

  useEffect(() => {
    api.authMethods().then(
      (m) => {
        setMethods(m);
        if (m.demo) api.demoUsers().then(setDemoUsers, (e: Error) => setError(e.message));
      },
      (e: Error) => setError(e.message),
    );
  }, []);

  const nothingAvailable = methods !== null && methods.providers.length === 0 && !methods.demo;

  return (
    <main className="login">
      <h1>Solara Docs</h1>
      <p>Technical notes, field logs and experiments for Solara Radio.</p>
      {error && <p role="alert">{error}</p>}
      {methods === null && !error && <p className="loading">Loading…</p>}

      {methods && methods.providers.length > 0 && (
        <ul className="login-users" aria-label="Sign in with">
          {methods.providers.map((p) => (
            <li key={p.name}>
              {/* Full-page navigation: the API redirects to the provider and back. */}
              <a className="login-provider" href={api.signInUrl(p.name)}>
                Sign in with {p.label}
              </a>
            </li>
          ))}
        </ul>
      )}
      {methods && methods.providers.length > 0 && <p className="hint">Invite only during the preview.</p>}

      {nothingAvailable && <p>Sign-in is not available yet.</p>}

      {methods?.demo && demoUsers.length > 0 && (
        <section aria-labelledby="demo-heading">
          <h2 id="demo-heading">Demo identities</h2>
          <ul className="login-users">
            {demoUsers.map((u) => (
              <li key={u.id}>
                <button type="button" onClick={async () => onLogin((await api.login(u.login_key)).user)}>
                  {u.display_name}
                </button>
              </li>
            ))}
          </ul>
          <p className="hint">Local development only — never available in production.</p>
        </section>
      )}
      <a className="login-back" href={SOLARA_TOOLS_URL}>
        <span aria-hidden="true">← </span>Back to Solara Radio Tools
      </a>
    </main>
  );
}
