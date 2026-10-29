# ADR-007: Same-origin `/api` via static-site rewrite, hash routing

- **Status:** Accepted (2026-10-29)
- **Context:** Static site and API live on different `*.onrender.com` subdomains. `onrender.com`
  is a public suffix, so they are cross-site and a session cookie would be third-party.
- **Decision:** The static site rewrites `/api/*` to the API, so the browser sees one origin and
  the cookie stays first-party. The SPA uses hash routes (`#/doc/:id`) so no SPA fallback rule is
  needed. Vite proxies `/api` in development.
- **Alternatives:** CORS + `SameSite=None` cookies (third-party cookie restrictions); bearer
  tokens in browser storage (XSS exposure).
- **Consequences:** Verified on Render (login, cookie, all routes). Right after the site was
  created, one path briefly returned Render's `no-server` 404 until routing propagated.
- **Revisit when:** a custom domain is added (API on a subdomain of the same site also works).
