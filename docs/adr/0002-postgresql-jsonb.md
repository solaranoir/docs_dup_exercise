# ADR-002: PostgreSQL with JSONB content

- **Status:** Accepted (2026-10-29)
- **Context:** Need durable, transactional storage for users, documents, grants and attachment
  metadata that survives Render restarts and deploys.
- **Decision:** Managed PostgreSQL 16 on Render; document body in a `JSONB` column; schema owned
  by Alembic migrations; constraints for title length, unique grants, valid roles, foreign keys.
- **Alternatives:** SQLite (ephemeral disk on Render — rejected by the proposal); a document DB
  (weaker relational guarantees for grants/ownership).
- **Consequences:** Simple transactions and constraint-backed integrity. Whole-document writes;
  unsuitable for CRDT/OT collaborative editing without redesign. Free tier DB expires after
  30 days (~2026-11-28) — upgrade before then if the demo must persist.
- **Revisit when:** real-time collaboration, version history, or full-text search are needed.
