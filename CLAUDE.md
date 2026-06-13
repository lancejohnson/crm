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
- **SMS / texting** (Quo/OpenPhone): native two-way texts on the `Quo Message`
  doctype.
  - `frontend/src/pages/TextMessages.vue` + `/texts` route + sidebar item — a
    compose-first inbox (conversations · thread · compose)
  - `frontend/src/components/Activities/SMSArea.vue`, `SMSBox.vue` — per-lead
    Text Messages tab (thread + compose); also folded into the unified Activity
    timeline (`Activities.vue`)
  - `SendTextModal.vue` + `AllModals.vue` + `ActivityHeader.vue` — "Send Text"
    quick action next to "Log a Call"
  - per-user sending number on `User.custom_quo_number`: picker
    `QuoFromSelect.vue` + `composables/quoSender.js`, admin assignment in
    `Settings/Users.vue`; no default — the sender must pick a number
  - `crm/api/sms.py` — read API (`get_sms_messages`, `get_sms_conversations`,
    `is_sms_enabled`) + `set_user_quo_number`; `crm/api/session.py` exposes
    `custom_quo_number`; `crm/hooks.py` — `Quo Message` after_insert publishes
    the `quo_message` realtime event (the server scripts can't, sandbox)
- `frontend/vite.config.js` — PWA service worker set `selfDestroying` (the
  precache served stale app bundles after deploys)

The companion server-side pieces (custom doctypes, scheduler engine, webhook
endpoints) are Server Scripts managed from the ops repo, NOT app code here. SMS
specifically: the `Quo Message` doctype, the `send-text` and `list-quo-numbers`
API server scripts, and inbound text mirroring in the `sequence-events` webhook
all live in `../frappe-crm-deploy`.

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
