# Release checklist: v1.0.0

The steps to release Solara Docs v1.0, in order. The automated gates and their evidence are in
[PRODUCTION_READINESS.md](PRODUCTION_READINESS.md); this list covers what happens around the
release itself. Tick each box with the date. The MVP checklist is archived at
[archive/RELEASE_CHECKLIST-mvp.md](archive/RELEASE_CHECKLIST-mvp.md).

## 1. Merge and let it deploy

- [ ] Merge the v1.0 release PR (squash). Note the merge commit: `__________`
- [ ] **CI** is green on the merge commit (Actions → CI).
- [ ] **Post-deploy smoke** is green on the merge commit (Actions → Post-deploy smoke). It waits
      for Render to serve the commit, then checks the public site.

## 2. Hosting and storage (dashboards)

- [ ] Render → `docworkspace-api` shows the **Starter** plan.
- [ ] Render → `docworkspace-db` → **Recovery** shows backups and point-in-time recovery.
- [ ] Cloudflare → R2 → `document-workspace-attachments` → Settings: no public `r2.dev` URL and no
      custom domain. R2 → Manage API tokens: the token the API uses is limited to this bucket.
- [ ] **Restore drill** (RUNBOOK → Restore drill), then delete the restored database.

## 3. Verify the deployed release

- [ ] Signed-in smoke: sign in on the live site, copy the `__Host-sd_session` cookie value, then
      `SMOKE_SESSION=<value> scripts/smoke_deployed.sh "" "" <merge commit>` → "All checks
      passed". Sign out afterwards to end that session.
- [ ] **Rollback rehearsal:** Render → `docworkspace-api` → Events → **Rollback** to the previous
      deploy. Wait for `/health/live` to show that commit, check the site still loads, then roll
      forward (Manual Deploy → the merge commit) and check `/health/live` again.
- [ ] Browser pass on a phone and a desktop: create from a template, edit and save, attach a
      file, file it in a folder and tag it, export it, sign out and find it again.
- [ ] Keyboard-only pass: skip link, toolbar (Tab in, arrow keys between controls), dialogs (Esc
      closes, focus returns), visible focus everywhere.
- [ ] The Solara Radio Tools Library (https://solararadio.netlify.app/tools) lists Solara Docs and
      links to https://docworkspace-web.onrender.com. The entry is in the solara-radio repo
      (`CodingProjectsWidget.jsx`, `SolaraDocsWidget.jsx`; solara-radio#2). Optional: refresh its
      description there for v1.0 (templates, folders and tags, search, export, Trash).

## 4. Cut over to real users

- [ ] Remove the demo data (RUNBOOK → Production cut-over), in the Render Shell:
      `python scripts/purge_demo_data.py`, check the list, then `--yes`.
- [ ] `python scripts/sweep_orphans.py` (dry run) reports 0 orphaned. If it lists any, run it
      again with `--yes`.
- [ ] Invite the first users: `python scripts/allow_email.py add someone@example.com`. Tell them
      to sign in once before anyone shares with them.

## 5. Publish the release

- [ ] If the release date differs from the one in [CHANGELOG.md](../CHANGELOG.md), update it in a
      small PR first.
- [ ] Create the GitHub release on the merge commit, with the changelog section as notes:
      ```bash
      git checkout main && git pull
      sed -n '/^## 1.0.0/,/^## 0.1.0/p' CHANGELOG.md | sed '1d;$d' > /tmp/v1-notes.md
      gh release create v1.0.0 --target main --title "Solara Docs 1.0.0" --notes-file /tmp/v1-notes.md
      ```
- [ ] Tick the sign-off tables here and in PRODUCTION_READINESS.

## 6. Housekeeping (optional)

- [ ] Close the MVP issues that v1.0 delivers or replaces (#1, #3, #4, #10–#12, #14–#17, #19–#22),
      and #30 (stale builds: non-editable install, plus the served-commit check that now runs
      after every deploy). Keep #26, #27, #29, #50 and #55 open as the backlog.

## Sign-off

| Step | Name | Date | Notes |
| --- | --- | --- | --- |
| 1–3 Deployed and verified | | | |
| 4 Cut over | | | |
| 5 Released | | | |
