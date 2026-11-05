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

  return (
    <main className="login">
      <h1>Solara Docs</h1>
      <p>Demo sign-in — choose a seeded identity.</p>
      {error && <p role="alert">{error}</p>}
      <ul className="login-users">
        {users.map((u) => (
          <li key={u.id}>
            <button type="button" onClick={async () => onLogin((await api.login(u.login_key)).user)}>
              {u.display_name}
            </button>
          </li>
        ))}
      </ul>
      <p className="hint">Demo identities only — not secure for public use.</p>
    </main>
  );
}
