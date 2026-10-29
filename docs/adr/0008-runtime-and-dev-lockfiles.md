# ADR-008: Pinned runtime vs dev lockfiles; non-editable production install

- **Status:** Accepted (2026-10-29)
- **Context:** Render must install only runtime dependencies, reproducibly. A deploy once showed
  "live" while serving stale code; the build used an editable install (#30).
- **Decision:** `backend/requirements.lock` (runtime, used by Render) and
  `backend/requirements-dev.lock` (CI/local: pytest, moto, ruff, mypy). Render installs with
  `pip install --no-deps .` (non-editable). `/health/live` reports `RENDER_GIT_COMMIT` and
  `scripts/smoke_deployed.sh` can assert it.
- **Consequences:** Smaller, reproducible production installs; deploy verification can detect
  stale code. Lockfiles must be regenerated when `pyproject.toml` changes.
- **Revisit when:** adopting a resolver tool (uv/pip-tools) to generate both locks.
