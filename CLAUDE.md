# Frappe CRM fork — Groundwork

Fork of frappe/crm (github.com/lancejohnson/crm). Working branch: **groundwork**,
based on upstream tag **v1.67.0** — the last upstream release whose published
image actually contains the crm app (their image CI is broken after it).

**This repo is the source of truth for UI/app-code changes.** Deployment,
server scripts, infra, and all operational context live in the ops repo:
`../frappe-crm-deploy` (read its CLAUDE.md first).

## Our changes vs upstream (keep this list current)

- `frontend/src/pages/Sequences.vue`, `Sequence.vue` — native sequences list +
  step editor + enrollments management
- `frontend/src/router.js` — `/sequences`, `/sequences/:sequenceId` routes
- `frontend/src/components/Layouts/AppSidebar.vue` — Sequences nav item
- `frontend/src/components/SidebarLink.vue` — absolute-URL support
- `frontend/src/components/Modals/TaskModal.vue` — "Call Outcome" disposition
  dropdown (Connected / Left Voicemail / No Answer / Wrong Number / Do Not Call)
- `crm/api/activities.py` — `call_outcome` in task field lists

The companion server-side pieces (custom doctypes, scheduler engine, webhook
endpoints) are Server Scripts managed from the ops repo, NOT app code here.

## Ship a change

```bash
# edit source here, then:
cd ../frappe-crm-deploy && ./scripts/build_image.sh && python3 scripts/smoke_test.py
# commit here AND commit the compose pin bump in ../frappe-crm-deploy
```

No local dev server is set up — the build_image.sh flow (~60s build) is the
iteration loop. Frontend has no tests upstream; `yarn build` succeeding is the
gate. Don't run `bench run-tests` against the prod site.

## Upstream sync

Upstream moves fast (v1.73+ as of 2026-06). To take upstream changes: rebase
`groundwork` onto the target tag, verify the image-tag-contents problem is
fixed (or build our own image), re-test everything in ../frappe-crm-deploy/CLAUDE.md.
