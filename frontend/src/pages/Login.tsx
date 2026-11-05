import { useEffect, useState } from "react";
import { api, ApiError, type DemoUser, type User } from "../api";

export function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [users, setUsers] = useState<DemoUser[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.demoUsers().then(setUsers, (e: Error) =>
      // 404 = demo sign-in is switched off (always, in production) until OAuth sign-in ships.
      setError(e instanceof ApiError && e.status === 404 ? "Sign-in is not available yet." : e.message),
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
    </main>
  );
}
