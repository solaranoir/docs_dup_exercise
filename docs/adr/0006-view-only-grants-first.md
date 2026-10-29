# ADR-006: View-only sharing first

- **Status:** Accepted (2026-10-29, decision #7)
- **Context:** Sharing must be demonstrable and safe; edit sharing multiplies permission cases.
- **Decision:** Owners grant/revoke **viewer** access to existing seeded users by id. Central
  policy (`backend/app/policy.py`) is deny-by-default: no access → **404** (privacy-preserving);
  viewer write → **403**; only owners manage grants or delete. The `role` column already allows
  `editor` so the extension needs no migration.
- **Alternatives:** editor grants now (more UI and tests); public links (out of scope).
- **Consequences:** Simple, fully tested matrix (Alice/Bob/Charlie). Editor role → backlog #22.
- **Revisit when:** collaborators need to edit.
