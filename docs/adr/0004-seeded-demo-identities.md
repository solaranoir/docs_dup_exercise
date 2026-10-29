# ADR-004: Seeded demo identities with a signed session

- **Status:** Accepted for MVP (2026-10-29) — **must be replaced before any public release**
- **Context:** The demo needs fast, repeatable identity switching (Alice/Bob/Charlie) without an
  identity provider.
- **Decision:** Idempotent seed on every API start (user decision). `POST /api/demo/login`
  issues an `itsdangerous`-signed token (httpOnly, SameSite=Lax, Secure in production) also
  usable as a bearer token for tests. The principal is always derived server-side; no route trusts
  a client-supplied user id. Login is rate limited per IP.
- **Alternatives:** OIDC/SSO (out of scope for 90 minutes); unsigned user switcher (insecure).
- **Consequences:** Anyone who can reach the site can sign in as any demo user. Acceptable only
  for a restricted demo environment.
- **Revisit when:** any real users or real data — replace with OIDC (backlog #22).
