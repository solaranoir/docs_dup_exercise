# ADR-009: OAuth sign-in (GitHub, Google) with an invite allowlist

- **Status:** Accepted (2026-11-04). Supersedes [ADR-004](0004-seeded-demo-identities.md) once
  implemented. Addresses audit findings A1, A2, A4–A9 ([SECURITY_AUDIT.md](../SECURITY_AUDIT.md)).
- **Context:** Solara Docs moves from a demo with seeded identities to real users. The audience
  is small (Solara Radio operators and collaborators) during the v0.5 preview. We want the
  smallest security surface we can maintain alone.
- **Decision:**
  1. **Sign-in:** OAuth 2.0 authorization-code flow with GitHub and Google (OIDC), with `state`
     plus PKCE. No passwords stored, and no reset or verification email flows.
  2. **Identity:** a `user_identities` table keyed by `(provider, provider_subject)`, never by
     email, so a changed email cannot take over an account. Only verified emails are accepted
     (Google `email_verified`; the GitHub primary verified email from `/user/emails`). A second
     provider links to an existing user only when its verified email matches.
  3. **Allowlist:** sign-in succeeds only if the verified email is in `allowed_emails`, which is
     managed with a CLI (`scripts/allow_email.py add|remove|list`). Anyone else gets a neutral
     "not invited" page. Revoking an email ends that user's sessions.
  4. **Sessions:** server-side `sessions` table storing the SHA-256 of a 256-bit random token,
     with a 7-day idle timeout and a 30-day absolute limit. The cookie is
     `__Host-sd_session; HttpOnly; Secure; SameSite=Lax; Path=/`. Logout deletes the row. The
     token is never returned in a response body.
  5. **CSRF:** middleware rejects `POST/PATCH/PUT/DELETE` unless `Origin` (or `Sec-Fetch-Site:
     same-origin`) matches the app origin. Combined with SameSite=Lax this covers multipart
     uploads and future custom domains.
  6. **Same origin:** OAuth redirect URIs use the web origin
     (`https://<web>/api/auth/{provider}/callback`) through the existing `/api/*` rewrite
     (ADR-007), so the session cookie stays first-party.
  7. **Demo mode:** `/api/demo/*` and `seed_demo.py` are enabled only when
     `ENABLE_DEMO_AUTH=true` **and** `ENVIRONMENT != production`. The app refuses to start if both
     are set together. Local development and Playwright keep the fast identity switcher.
  8. **Sharing:** grants target an existing account by email. There is no user directory
     endpoint.
- **Alternatives:** email + password (we would have to own hashing, reset email and credential
  stuffing defence), magic links (needs an email provider from day one), hosted IdP such as
  Clerk or Auth0 (vendor lock-in and pricing, plus JWT verification code). Rejected for v0.5.
- **Consequences:** users need a GitHub or Google account. OAuth app credentials
  (`GITHUB_CLIENT_ID/SECRET`, `GOOGLE_CLIENT_ID/SECRET`) live in Render env vars. Existing demo
  documents are either reassigned to a real owner with a one-off script or discarded, which the
  owner decides at cut-over.
- **Revisit when:** opening public signup (needs quotas and abuse handling), or when Solara Radio
  gains its own accounts and could become the identity provider.
