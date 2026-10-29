# Release checklist — MVP (for #21)

Sign-off requires someone other than the implementer to complete the **clean-room** and
**deployed** sections. Tick each box and note the date/commit.

## Automated gates (CI on the release commit)

- [ ] `backend` job green: ruff, mypy --strict, migrate + seed twice on PostgreSQL 16, boot smoke, pytest
- [ ] `frontend` job green: eslint, tsc, Vitest, production build
- [ ] `e2e` job green: Playwright critical journeys (editor persistence, imports, attachments,
      sharing permissions, invalid inputs)
- [ ] No open P0/P1 bugs (`gh issue list --label bug --state open`)

## Clean-room walkthrough (fresh clone, someone other than the implementer)

- [ ] Follow README "Local run" from scratch (mise, Postgres container, moto) without help
- [ ] `/health/ready` shows `database: ok`, `storage: ok`
- [ ] Run the three test commands in README "Tests and checks"; all pass
- [ ] Note any step that needed guessing → file an issue

## Deployed verification (Render)

- [ ] Blueprint synced on `main`; API and static site show the release commit
- [ ] `scripts/smoke_deployed.sh "" "" <release-commit>` → "All checks passed"
- [ ] Manual demo script (roadmap steps 1–10) in a browser, including:
  - [ ] Format → save → refresh keeps H1, bold, bullets
  - [ ] `.txt` and `.docx` import as new; `.md` append into a draft; warnings shown
  - [ ] Attach + download; Bob read-only; Charlie denied; revoke
  - [ ] **Restart:** Render → docworkspace-api → Manual Deploy → Restart service; reopen
        document, attachment and grant state (persistence across restart)
- [ ] Keyboard-only pass: toolbar (Tab into it, arrow keys between controls), dialogs (Esc closes,
      focus returns), visible focus everywhere, labelled controls
- [ ] README limitations reviewed; demo identities acceptable for this audience

## Sign-off

| Role | Name | Date | Commit |
| --- | --- | --- | --- |
| Reviewer (clean-room + deployed) | | | |
| Product owner | | | |
