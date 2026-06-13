---
name: ship
description: Commit, push, build, deploy, and smoke-test a UI/app change for this Groundwork Frappe CRM fork. Runs the full ship loop — commit + push the fork (this repo, branch `groundwork`), build & deploy the image via the ops repo's build_image.sh, run the smoke test, then commit + push the compose pin bump in ../frappe-crm-deploy. Triggers on "commit push deploy", "ship this", "deploy this change", "ship it", "push and deploy".
---

# Ship a change (commit → push → deploy)

End-to-end release of a source change in this fork (`frappe-crm-app`, branch
`groundwork`) to the live site **https://crm.groundworkpro.com**. The deploy
machinery lives in the sibling ops repo `../frappe-crm-deploy`.

## How deploy actually works (so you know what each step does)

`../frappe-crm-deploy/scripts/build_image.sh` rsyncs this fork's **working-tree**
`frontend/src/` and `crm/` into the running backend container, runs `yarn build`
inside it, `docker commit`s the result as the next `v1.67.0-gwN` image tag, bumps
the compose pin on the **server**, brings the stack up, clears the website cache,
and bounces the frontend container. It then bumps the **local** `docker-compose.yml`
pin in the ops repo — that bump is an uncommitted change you must commit afterward.

Because it ships the working tree (not a git ref), committing first isn't strictly
required for the deploy to pick up the change — but we always commit first so the
deployed bundle is traceable to a commit.

## Steps

Run these in order. Stop and report if any step fails — do not push the compose
pin if the smoke test fails.

### 1. Pre-flight
- Confirm cwd is this repo and the branch is `groundwork`:
  `git -C /Users/work/Dropbox/Projects/Groundwork/frappe-crm-app rev-parse --abbrev-ref HEAD`
- Show `git status` + `git diff --stat`. If there are no changes to ship, say so and stop.
- If the user didn't supply a commit message, derive a concise one from the diff
  (and confirm it if non-trivial).

### 2. Commit + push the fork
```bash
cd /Users/work/Dropbox/Projects/Groundwork/frappe-crm-app
git add <the files you changed>   # don't blindly `git add -A` — stage intentionally
git commit -F - <<'EOF'
<subject>

<body>

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
git push origin groundwork
```

### 3. Build + deploy (ops repo)
```bash
cd /Users/work/Dropbox/Projects/Groundwork/frappe-crm-deploy
./scripts/build_image.sh
```
- ~60s. It auto-increments the `gwN` tag. Watch for `deployed v1.67.0-gwN` at the end.
- If it says another build is running (`/tmp/frappe-crm-build.lock`), don't force —
  report it; only `rmdir` the lock if you've confirmed nothing else is building.

### 4. Smoke test
```bash
cd /Users/work/Dropbox/Projects/Groundwork/frappe-crm-deploy
python3 scripts/smoke_test.py
```
- Must pass before committing the pin bump. If it fails, stop and report output.
- Never run `bench run-tests` against the prod site.

### 5. Commit + push the compose pin bump (ops repo)
`build_image.sh` edited `../frappe-crm-deploy/docker-compose.yml` to the new tag.
```bash
cd /Users/work/Dropbox/Projects/Groundwork/frappe-crm-deploy
git add docker-compose.yml
git commit -m "Bump CRM image pin to v1.67.0-gwN

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push     # check its branch first; push to its current upstream
```
(Use the actual `gwN` from step 3. If build_image.sh changed other tracked files,
review them — only commit the intended pin bump.)

### 6. Report
Summarize: fork commit pushed, image tag deployed, smoke test result, pin-bump
commit pushed, and the live URL on its own line:

https://crm.groundworkpro.com

## Notes
- This is the explicit user request to commit — fine to commit here despite the
  usual "don't commit unless asked" rule.
- Keep fork commits atomic; if there are unrelated working-tree changes, don't
  sweep them into the ship commit.
