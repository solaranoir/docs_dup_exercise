import { useEffect, useState } from "react";
import { api, type User } from "../api";

export function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.demoUsers().then(setUsers, (e: Error) => setError(e.message));
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
