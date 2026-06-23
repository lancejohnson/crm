# Frappe CRM fork — Groundwork

Fork of frappe/crm (github.com/lancejohnson/crm). Working branch: **groundwork**,
based on upstream tag **v1.67.0** — the last upstream release whose published
image actually contains the crm app (their image CI is broken after it).

**This repo is the source of truth for UI/app-code changes.** Deployment,
server scripts, infra, and all operational context live in the ops repo:
`../frappe-crm-deploy` (read its CLAUDE.md first).

## Our changes vs upstream (keep this list current)

- **Realtime task auto-refresh (no page reload), site-wide** — `CRM Task` now
  broadcasts a `crm_task_update` realtime event (with
  `reference_doctype`/`reference_docname`) on `after_insert`/`on_update`/`on_trash`,
  mirroring the `quo_message` pattern. The Lead/Deal **Activity feed** reloads
  `all_activities` when the event matches the open doc (To-do block +
  completed-task history update live); the **Leads & Deals Kanban** refetch the
  board (to refresh the server-computed `_next_task_due` badge) but only when on
  the Kanban view AND the affected record is currently on the board.
  SMS→Activity was already live via the existing `quo_message` listener (the
  unified timeline reads `smsMessages` reactively).
  - **Site-wide delivery is automatic, not extra work**: `frappe.publish_realtime`
    with no `room`/`user` broadcasts to the site room (`get_site_room()` → `"all"`),
    and the socketio handler (`frappe_handlers.js`) joins *every* logged-in System
    User to that room on connect. So one user's task/text update reaches all
    other users' open boards/leads. (Do NOT pass `doctype`/`docname`/`user` — that
    would *narrow* delivery to a single room.)
  - **`after_commit=True` on both publishes** (`crm_task_update` AND `quo_message`)
    — defers the emit until the DB transaction commits, so a listener's reload
    can't race ahead of the commit and read stale data (the old default
    `after_commit=False` is the likely cause of the "text doesn't show until I
    refresh" flakiness: the emit fired pre-commit, the client refetched, and the
    new row wasn't visible yet).
  - `crm/fcrm/doctype/crm_task/crm_task.py` — `notify_task_update()` +
    `on_update`/`on_trash` hooks (publish `crm_task_update`, `after_commit=True`)
  - `crm/api/sms.py` — `on_quo_message_insert` now uses `after_commit=True`
  - `frontend/src/components/Activities/Activities.vue` — `crm_task_update`
    listener → `all_activities.reload()`
  - `frontend/src/pages/Leads.vue` + `pages/Deals.vue` — `crm_task_update`
    listener → `reloadKanban()` (Deals gained a `reloadKanban` helper); on-board
    membership guard to avoid needless reloads
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
- **Lead/Deal tasks as a Trello-style to-do list** — the existing `CRM Task`
  feature (its own Tasks tab + heavyweight `TaskModal`) is now surfaced in the
  **unified Activity timeline**: a pinned **"To-do"** block at the top of the
  Activity feed lists every open task with a Trello-style **inline quick-add**
  (`Add a task…` + a `DateTimePicker` for an optional **due date/time**, Enter →
  insert defaulted to current user + `Todo`), a **hover circle →
  click-to-complete** checkbox, and a **hover trash icon** to delete a to-do
  inline; tasks sort by due date (overdue first), the relative due date is **red**
  once overdue / **amber** when due today. Completed/canceled tasks drop into the
  chronological history anchored at their completion date (`modified`),
  struck-through. Open tasks live only in the To-do block, completed only in
  history — no duplication. Creating/saving a task **stays on the Activity tab**
  (removed `TaskModal`'s `@after="redirect('tasks')"`).
  - `frontend/src/components/Activities/TaskTodoList.vue` — **new** (quick-add w/
    date picker + checkbox + per-row delete)
  - `frontend/src/components/Activities/Activities.vue` — `openTasks` computed +
    `get_task_activities()` (completed tasks → timeline entries keyed on
    `modified`), merged into the Activity feed; `task` branch in the timeline +
    `timelineIcon`; renders `<TaskTodoList>` and widened the feed's `v-if` so the
    quick-add shows on a lead with no other history
  - `frontend/src/components/Activities/AllModals.vue` — `addTask(title, due_date)`
    helper (centralized with the existing `updateTaskStatus`/`deleteTask`); no
    longer redirects to the Tasks tab after a task save
  - **Kanban next-task-due badge** (Leads **and** Deals) — each card shows the
    soonest open task's due date as **colored text** (red overdue / amber today /
    muted future). Server computes it as a pseudo-field `_next_task_due` in
    `crm/api/doc.py` `getCounts` (earliest `due_date` among non-Done/Canceled
    tasks; filtered out of the DB `rows` like `_last_comm`); added to the default
    `kanban_fields` in `crm_lead.py` + `crm_deal.py`; selectable via
    `KanbanSettings.vue`; rendered in the `#fields` slot of `pages/Leads.vue` +
    `pages/Deals.vue` (`parseRows` → `{label, value, color}`); shared `dueColor()`
    helper in `frontend/src/utils/index.js`. No schema change, no new npm dep.
  - **Kanban "Tasks due" filter** (Leads) — a dropdown (Due today / Overdue
    / Due today + overdue / Clear) filters the board to leads with a matching open
    task. `crm/api/doc.py` `get_docs_with_due_tasks(doctype, scope)` resolves the
    lead names server-side (since `_next_task_due` is computed, not a column);
    `pages/Leads.vue` injects them as the same never-persisted `name in [...]`
    default filter the dashboard drill uses. (Deals not wired yet — same backend
    would extend it.) **Lives in the view-controls row** next to the Filter
    button (not the page header): `ViewControls.vue` exposes a `#actions` slot
    just left of `<Filter>`, and `pages/Leads.vue` fills it with the Tasks-due
    `Dropdown`. To make room, `get_quick_filters` now also drops the `email` and
    `organization` quick filters for CRM Lead (alongside the existing `converted`
    strip), so the Leads search row is Full Name / Status / Source only.
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
- **Activity Report** (on the `/dashboard` landing page) — an unfoldable table of
  outreach for the selected range: **Leads called**, **Leads texted**, and
  **Agreements sent**, each shown as **unique leads** *and* **total actions**,
  split **Outbound vs Inbound** (inbound = the lead's replies, so you can see
  who's responding — inbound counts are tinted green; agreements have no inbound).
  Clicking an Outbound/Inbound number drills that set into the Leads list (same
  `leadDrilldown` mechanism as the source/status drills); unfolding a row
  (chevron) lists every lead inline with per-lead out (↗) / inbound (↙, green)
  counts, each clickable to open the lead, plus "Open all in Leads". All three
  dated by `creation`, scoped to `CRM Lead`-referenced records and (for sales
  users) the current user. Also shows **Quo talk time** (total CRM Call Log
  `duration` for the range, outbound/inbound in the tooltip) as a stat in the card
  header, with per-lead talk time in the Leads-called unfold. (Note: inbound calls
  only count if the telephony webhook logged them as `type=Incoming` and linked
  them to a lead — historically all logged calls have been Outgoing, so call
  inbound reads 0; inbound texts work via Quo `direction`.)
  - `crm/api/leads_dashboard.py` — `_activity_summary` (added to
    `get_leads_dashboard` as `activity`) + per-source row fetchers
    (`_call_rows` = CRM Call Log `type`, `_text_rows` = Quo Message `direction`,
    `_agreement_rows` = CRM Esign Agreement) + `_tally` + the `get_activity_leads`
    drill/unfold endpoint (per-lead counts + display names, `DRILL_CAP`). Quo
    Message / Esign Agreement are guarded by `frappe.db.exists` so an unprovisioned
    site just drops that row.
  - `frontend/src/components/Dashboard/ActivityReport.vue` — **new**; mounted in
    `pages/LeadsDashboard.vue` (between the summary cards and the New-leads chart),
    fed `data.activity`; lazy-fetches the per-row lead list on unfold.
- **Collapse fleeting (<60s) status changes** — a status changed by mistake and
  quickly corrected no longer leaves a fleeting intermediate behind. A run of
  consecutive status changes where each intermediate was held <60s collapses to
  the net transition (A→B→C in under a minute reads as A→C); a bounce back
  (A→B→A) disappears entirely. Applied on **both** surfaces that show status
  changes, which read different sources, so they agree:
  - **Per-lead/Deal Activity timeline** (Frappe Version history) —
    `crm/api/activities.py` `collapse_rapid_status_changes()`, a display-only
    pass wired into `get_lead_activities` + `get_deal_activities` before the sort
    (never mutates the Version audit trail).
  - **Dashboard Status Change Report** (`CRM Status Change Log` child table) —
    `crm/fcrm/doctype/crm_status_change_log/crm_status_change_log.py`
    `add_status_change_log()` rewrites the prior transition to the corrected
    status and drops the fleeting row at write time (bounce reopens the prior
    row). Threshold constant `MIN_STATUS_HELD_SECONDS` / `STATUS_COLLAPSE_SECONDS`
    = 60 in each file. The creation/initial status is never collapsed.
- **BatchData "Fetch Tax Info"** (Leads) — a $0.10/pull button on a lead that
  fetches owner, APN, and tax status from BatchData (Property Search). A confirm
  dialog ("This will charge $0.10", requested-by user, and a "last pulled by X
  on <date>" re-pull warning) precedes the charge. Each pull is a **CRM Property
  Tax Pull** row (audit trail: pulled_by/at/cost + raw record + flattened
  columns); headline fields (apn, property_owner, tax_status, annual_tax,
  assessed_value, last_tax_pull_at/by — all read_only so they auto-hide until
  filled) are written back onto the lead and show in the Property Details
  sidebar. Also: a dedicated **Tax Info** sidebar card (latest pull + pulled-by/
  when, re-pull button) and a **`tax_pull`** Activity-timeline entry. Live
  refresh via the `crm_tax_pull` realtime event (site-wide, `after_commit`,
  emitted from the app hook since the server-script sandbox can't publish — see
  the SMS/task realtime pattern).
  - **Architecture mirrors SMS**: the external BatchData call lives in the ops
    server script `pull-tax-info` (key via `__INFISICAL:BATCHDATA_API_KEY__`,
    like `send-text`); it stores the raw property record and the app-code
    `after_insert` hook does all parsing + lead writeback + realtime.
  - `crm/api/tax_info.py` — `on_tax_pull_insert` hook (parse + writeback +
    publish `crm_tax_pull`) + `get_tax_pulls(lead)` read API
  - `crm/hooks.py` — `CRM Property Tax Pull` `after_insert`
  - `frontend/src/components/Modals/FetchTaxInfoModal.vue` (charge confirm),
    `components/TaxInfoCard.vue` (sidebar object), `pages/Lead.vue` (header
    button + card + realtime doc/sidebar reload), `components/Activities/
    Activities.vue` (`tax_pull` timeline type + `taxPulls` resource + listener),
    `AllModals.vue` (`fetchTaxInfo`), `utils/index.js` (`formatNumber`)
  - **Tax-assessor caveat**: `tax.taxAmount`/`assessment.totalAssessedValue`
    only populate once the "Core Property Data (Tax Assessor)" product is enabled
    on the BatchData account; until then owner/APN/value/tax-status-flags come
    through and the assessor columns stay empty (parser already wired for them).
    BatchData has NO cumulative back-taxes-owed $ field — "taxes owed" = annual
    tax + delinquency status (`tax.taxDelinquentYear` / `quickLists.taxDefault`).
  - Ops (`../frappe-crm-deploy`): `scripts/setup_tax_info.py` (doctype + lead
    custom fields + Property side-panel layout), `site/server_scripts/
    pull_tax_info.py` + manifest entry, synced via `sync_server_scripts.py`.

- **Documenso "Create Purchase Agreement"** (Leads) — a header action (in the
  decluttered "More" menu next to the name) that spins up a pre-filled, editable
  Documenso e-sign draft of the wholesale purchase agreement and hands back a
  self-serve buyer signing link. A modal picks the agreement type (Standard vs
  Novation/+AIF) and seller count; two sellers reveals a Seller 2 name/email (one
  seller drops the Seller 2 fields). Mirrors the BatchData Fetch-Tax-Info wiring.
  - `components/Modals/CreateAgreementModal.vue` (chooser + success view: buyer
    link with copy/open + seller links), mounted in `Activities/AllModals.vue`
    (`createAgreement()` + expose), forwarded by `Activities/Activities.vue`.
  - `pages/Lead.vue` — **button row decluttered** into Call · Text · **More ▾**
    (Dropdown via a `moreActions` computed: Make-a-Call / Email / Website /
    Attach / Fetch Tax Info / Create Purchase Agreement) · Delete. (Email +
    Website moved off the row into the menu per Lance — "that area is getting
    unruly".) `MoneyIcon`/`Email2Icon`/`LinkIcon`/`AttachmentIcon` imports now
    unused but harmless.
  - **Backend = ops server script** `create_agreement_draft.py` (api_method
    `create-agreement-draft`, token via `__INFISICAL:DOCUMENSO_API_TOKEN_ACQ__`):
    resolve template by title → `/template/use` w/ prefill → delete Seller 2 for
    one-seller → `/document/distribute` distributionMethod NONE (no emails). See
    `../frappe-crm-deploy` + the `documenso-deployment` memory.
  - Modal also: asks **Seller 1 email** when the lead has none (optional); creates
    a **Contact attached to the lead** when a Seller 2 is entered (email optional).
- **E-sign agreement tracking + live status** — each draft is recorded as a
  **CRM Esign Agreement** row (ops doctype) shown in a sidebar card +
  Activity-timeline entry, with status that updates live as recipients sign
  (Documenso webhook → ops `documenso-webhook` server script → CRM Esign Agreement
  on_update APP hook → `crm_esign` realtime). Mirrors the tax-info realtime/card/
  timeline pattern exactly.
  - `crm/api/agreement.py` — `on_agreement_insert`/`on_agreement_update`
    (stamp last_event_at + publish `crm_esign`, the sandbox can't) + `get_agreements`
  - `crm/hooks.py` — CRM Esign Agreement after_insert + on_update
  - `frontend/src/components/AgreementsCard.vue` (sidebar: status badge + signed
    count + buyer/seller links), mounted in `pages/Lead.vue` after `<TaxInfoCard>`
  - `frontend/src/components/Activities/Activities.vue` — `agreement` timeline
    type (`get_agreements` resource + `crm_esign` listener + DetailsIcon)
  - Documenso webhooks are DB-managed (Webhook table, not the public API); a row
    for teamId 4 points at `/api/method/documenso-webhook?secret=…`. Details in
    `../frappe-crm-deploy` + the `documenso-deployment` memory.

The companion server-side pieces (custom doctypes, scheduler engine, webhook
endpoints) are Server Scripts managed from the ops repo, NOT app code here. SMS
specifically: the `Quo Message` doctype, the `send-text` and `list-quo-numbers`
API server scripts, and inbound text mirroring in the `sequence-events` webhook
all live in `../frappe-crm-deploy`.

## Testing & verification — prod only (no local dev mirror)

The local dev mirror was **removed (2026-06-19)** — work exclusively against
prod. There is no `dev.sh`/`docker-compose.dev.yml` anymore; don't recreate one.

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
  tests); the in-image build run by `build_image.sh` is the real gate. A host
  `yarn build` needs the `socket.js` bench-relative config import resolved: from
  the **main repo** stub `../sites/common_site_config.json` (i.e.
  `Projects/sites/common_site_config.json`) = `{"socketio_port": 9000}`; from a
  worktree symlink the main `frontend/node_modules` and stub
  `sites/common_site_config.json` (see the `frontend-yarn-build-compile-gate`
  memory).
- **Visual / UI verification — MANDATORY for any UI change.** If a change touches
  a UI component (a `.vue` file, a new screen, a button, a layout), you MUST open
  it in the live site and actually look at it after shipping — the change isn't
  "done" until you've confirmed it renders and works. Use the **Google Chrome MCP**
  (`mcp__claude-in-chrome__*`) against the live site
  `https://crm.groundworkpro.com/crm` — it rides Lance's real, logged-in Chrome
  session. **Do NOT use headless Playwright here** (this overrides the global
  browser-interaction default): the SPA needs real nginx + an authenticated
  session, which only prod has. Ship the change first (below), then open the
  live page, exercise the new component (click it, unfold it, etc.), and report
  what you saw — don't just confirm the page loaded.

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
