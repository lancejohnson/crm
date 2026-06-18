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
- `frontend/src/components/Activities/CommentArea.vue` + `Activities.vue` +
  `crm/api/comment.py` — edit your own comments inline on the Lead/Deal activity
  feed: a hover-only pencil (Comments tab + the unified Activity timeline) opens an
  inline rich-text editor with Save/Cancel. Owner-only `edit_comment` API
  (PermissionError guard; suppresses mention re-notify on edit); `Activities.vue`
  passes the activities resource via `v-model` so the feed reloads after a save.
- `frontend/src/components/Kanban/KanbanCardField.vue` + `pages/Leads.vue`
  `#fields` slot — hover-only card affordances on the Leads Kanban: copy icon
  for phone/address fields, pencil-to-edit (inline popover, `frappe.client.set_value`
  + board reload) for any non-read-only field. Nothing shows until row hover.
- **Global Kanban card settings (one editor = default for everyone)** — when
  `lance.johnson@groundworkpro.com` (the `GLOBAL_KANBAN_EDITOR` constant) edits
  the default Kanban card layout, the standard Kanban view is saved globally
  (`user=""`, which `get_views` serves to every user) and overrides each user's
  personal Kanban view. (Originally keyed off `Administrator`, but Lance runs
  the CRM as his own user, so his edits never went global — switched to his
  email.) Everyone else / other view types are unchanged (still per-user).
  Applies to any Kanban (Leads + Deals).
  `crm/fcrm/doctype/crm_view_settings/crm_view_settings.py`
  (`create_or_update_standard_view`: editor+kanban → `user=""`, promotes any
  pre-existing personal row instead of duplicating) +
  `frontend/src/stores/views.js` (a global/user-less standard view always wins
  over a personal one when resolving `standardViews`).
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
  - **MMS media (photos/videos)** — inbound texts can carry image/video
    attachments. They arrive ONLY in the Quo `message.received` webhook payload
    as `media:[{url,type}]` (the REST API omits media → already-received MMS are
    unrecoverable; capture is going-forward only). Stored as a JSON array on the
    new `Quo Message.media` Long Text field (added by ops
    `setup_quo_message_doctype.py`; populated by the `sequence-events` webhook).
    `sms.py` parses it (`_media`) and returns `media:[{url,type}]` per message;
    the inbox preview shows "📷 Attachment" for an image-only (blank-text) text.
    Rendered by `components/Activities/SMSMedia.vue` (images inline, videos with
    a player, other types as download links) in both `SMSArea.vue` and the
    unified timeline block in `Activities.vue`. Clicking an image opens
    `components/Activities/ImageLightbox.vue` — a teleported full-screen viewer
    that pages through that message's images (←/→ buttons + arrow keys, wraps,
    counter; Esc / ✕ / backdrop close). The OpenPhone API CANNOT send MMS (send
    is text-only) — test inbound media by POSTing a synthetic `message.received`
    to `/api/method/sequence-events` (see ops repo).
- **Call transcript + waveform sync** — a "conversation score" view for recorded
  calls: a dual-lane diarized waveform (rep above the axis in blue, lead below in
  amber, shared playhead), a click-anywhere-to-seek scrubber, a synced transcript
  that auto-scrolls and highlights the active line (click a line → seek), a
  talk-time balance bar (rep% vs lead%), and optional Gemini chapter ticks. No new
  npm dependency: native `<audio>` for playback + Web Audio API `decodeAudioData`
  for peaks + `<canvas>` for the waveform (single fetch reused for both decode and
  a blob-URL `<audio>` source). Speaker colors live in JS (canvas can't read
  Tailwind tokens) and are blue/amber for dichromat safety.
  - `frontend/src/components/Activities/CallTranscript.vue` — the component
  - `crm/api/call_transcript.py` — `get_call_transcript(call_log)`: normalizes
    OpenPhone's diarized segments to clean `rep`/`lead` speakers (trusts a
    pre-normalized `speaker`, else OpenPhone's `userId`, else a last-10-digit
    identifier match), computes the talk-time ratio, and returns stored chapters
  - hosts: `components/Activities/CallArea.vue` (a "Transcript" toggle badge in
    the Lead/Deal activity timeline, next to "Listen") and `pages/CallReview.vue`
    (a per-call "Transcript" expander)
  - **Transcript source = OpenPhone native only.** The diarized, timestamped
    transcript and Gemini chapters are captured server-side into two custom Long
    Text fields the OPS REPO must add to CRM Call Log:
    `custom_transcript` = `{"dialogue":[{speaker|userId|identifier,start,end,content}],"duration":n}`
    and `custom_transcript_chapters` = `{"chapters":[{title,start,end}],"highlights":[{quote,t}]}`.
    Neither field needs to exist for the app code to run — the endpoint degrades to
    "transcript still processing". Ops work (in `../frappe-crm-deploy`): add the two
    custom fields; subscribe the `call.transcript.completed` webhook
    (`/v1/webhooks/call-transcripts`, Business/Scale plan) in `setup_quo_webhooks.py`;
    capture it in `sequence_events_webhook.py` (fetch `/v1/call-transcripts/:callId`,
    store `dialogue`); generate chapters via Gemini Flash over the transcript text
    (key in Infisical); backfill historical calls.
- `frontend/vite.config.js` — PWA service worker set `selfDestroying` (the
  precache served stale app bundles after deploys)
- **Sequence real-time drainer** — `crm/api/sequence_drain.py` + `crm/hooks.py`
  (CRM Lead doc-event `enqueue_for_lead` + 1-min `drain_due` scheduler). Makes
  sub-minute sequence-step waits actually honor seconds (the sandboxed engine
  can't `time.sleep`/delay-enqueue, so the old cron rounded every wait up to
  ~60s). Single-driver model on a dedicated `seqdrain` worker; the old
  "CRM Sequence Runner" cron is disabled. Full design + the two deploy gotchas
  (register the `seqdrain` queue in common_site_config; `migrate`/`sync_jobs` to
  register `drain_due`) live in `../frappe-crm-deploy/CLAUDE.md` → Sequences.
- **Status Change Report** (on the `/dashboard` landing page) — a drill-downable
  table of how leads move between statuses, replacing the old status-changes bar
  chart. Two lenses via a Cohort/Flow toggle: **Cohort** (default) = the leads
  *created* in the range and where each went; **Flow** = every transition that
  *happened* in the range (Started/Ended are population snapshots at the window
  edges). Per-status columns Entered/Left/Started→Ended/Net; an unfold arrow
  reveals each status's inflow/outflow flow (a synthetic "Created" node feeds
  newly-created leads). Clicking any flow drills into the CRM Leads list filtered
  to exactly those leads. All derived from the `CRM Status Change Log` child
  table + each lead's `status`/`creation`; both lenses satisfy
  `Ended = Started + Entered − Left`.
  - `crm/api/leads_dashboard.py` — `get_status_change_report` (table + per-stage
    inflow/outflow) and `get_status_transition_leads` (drill-down name resolver)
  - `frontend/src/components/Dashboard/StatusChangeReport.vue` + `FlowEdge.vue`;
    integrated in `pages/LeadsDashboard.vue`
  - drill-down: `frontend/src/stores/leadDrilldown.js` holds an ad-hoc lead-name
    set; `pages/Leads.vue` injects it as a never-persisted `name in […]`
    default-filter (+ a dismissible banner); `components/ViewControls.vue` now
    exposes `reload()` so clearing the drill refreshes the list

The companion server-side pieces (custom doctypes, scheduler engine, webhook
endpoints) are Server Scripts managed from the ops repo, NOT app code here. SMS
specifically: the `Quo Message` doctype, the `send-text` and `list-quo-numbers`
API server scripts, and inbound text mirroring in the `sequence-events` webhook
all live in `../frappe-crm-deploy`.

## Testing & verification — use prod, not the local dev mirror

Lance's standing preference: **do NOT use the local dev mirror — work against
prod.** (A dev mirror still exists under `../frappe-crm-deploy`, but it's
deprecated for this workflow; don't `dev.sh up` it.)

- **Backend logic** — validate read-only against the live DB with `bench
  execute` / `bench console` on the prod backend; roll back anything that writes:

  ```bash
  ssh groundwork-apps "cd /opt/frappe-crm && docker compose exec -T backend \
    bench --site crm.groundworkpro.com execute <dotted.path.func> --kwargs '{...}'"
  ```

  Read-only queries (SELECTs / report builders) are safe to run as-is. To probe
  unmerged code without deploying, `docker cp` the module into the backend
  container under a throwaway name, `execute` it, then remove it. Any snippet
  that writes must end in `frappe.db.rollback()`.
- **Compile gate** — `cd frontend && yarn build` must succeed (no upstream
  tests). From a worktree, symlink the main `frontend/node_modules` and add a
  stub `sites/common_site_config.json` = `{"socketio_port": 9000}` first
  (see the `dev-isolated-backend-for-worktree` memory).
- **Visual / UI verification** — use the **Google Chrome MCP**
  (`mcp__claude-in-chrome__*`) against the live site
  `https://crm.groundworkpro.com/crm` — it rides Lance's real, logged-in Chrome
  session. **Do NOT use headless Playwright here** (this overrides the global
  browser-interaction default): the SPA needs real nginx + an authenticated
  session, which prod has and the mirror does not. Ship the change first (below),
  then open the live page to look at it.

## Ship a change

```bash
# edit source here, then:
cd ../frappe-crm-deploy && ./scripts/build_image.sh && python3 scripts/smoke_test.py
# commit here AND commit the compose pin bump in ../frappe-crm-deploy
```

`build_image.sh` (~60s build) is the deploy step. It also takes
`FORK=/path/to/worktree` to build+deploy straight from a worktree without
merging first. Frontend has no tests upstream; `yarn build` succeeding is the
gate. Don't run `bench run-tests` against the prod site.

## Upstream sync

Upstream moves fast (v1.73+ as of 2026-06). To take upstream changes: rebase
`groundwork` onto the target tag, verify the image-tag-contents problem is
fixed (or build our own image), re-test everything in ../frappe-crm-deploy/CLAUDE.md.
