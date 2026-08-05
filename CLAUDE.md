# Frappe CRM fork — Groundwork

Fork of frappe/crm (github.com/lancejohnson/crm). Working branch: **groundwork**,
based on upstream tag **v1.67.0** — the last upstream release whose published
image actually contains the crm app (their image CI is broken after it).

**This repo is the source of truth for UI/app-code changes.** Deployment,
server scripts, infra, and all operational context live in the ops repo:
`../frappe-crm-deploy` (read its CLAUDE.md first).

## Before starting a feature — check what else is in flight

Lance often runs several Claude sessions/agents at once. **Before building anything,
check that another agent isn't already on it** (this exact check surfaced an
already-merged `feature/daily-call-review` branch and avoided rebuilding it):

```bash
git worktree list      # other agents' isolated worktrees
git branch -a          # existing feature branches (incl. related-sounding ones)
```

If a related branch/worktree exists, read it first and build on it rather than
duplicating. Work substantial features in a worktree of your own.

## Our changes vs upstream (keep this list current)

- **Open Research tabs (Lead header)** — a one-click button on the Lead page
  header row (Call · Text · **Research** · ⋯ · Delete) that opens **two Zillow
  tabs + one Google Maps tab** for the lead's `property_address`. Reuses the
  same Zillow `/homes/<slug>_rb/` slug builder as More → View on Zillow and the
  same Maps `api=1&query=` URL as the address-row link (extracted into shared
  `zillowUrl`/`mapsUrl` helpers). Toasts if no address is set. Pure frontend.
  `frontend/src/pages/Lead.vue`.

- **Lance-only Team Activity board** — a **Team activity** button at the bottom
  of the app sidebar (rendered only for `lance.johnson@groundworkpro.com`)
  opens a one-day manager report. Laid out as a dense report (Lance's
  preferred style): summary line → **The team** table → **The day** timeline →
  **Today board** + **Worth knowing** panels → legend. Per person: Toggl hours
  tracked, clocked-in window, Quo calls (proportional bar + out↗/in↙), talk
  time, human-sent texts, Today cards done/skipped, tasks completed (split
  on-today's-list / other), active window, and goal %. Goals persist
  cross-device in Lance's Frappe user defaults (no custom doctype).
  `crm/api/activity_progress.py` + `frontend/src/components/ActivityProgressModal.vue`
  + desktop `AppSidebar.vue` + mobile-drawer `MobileSidebar.vue` (**both entry
  points are required** — mobile renders a different sidebar).
  - **Calls are the CRM Call Log, which IS the Quo mirror** (the `call.completed`
    webhook attributes each call to the Quo `userId` who actually dialled, not
    the line owner). Do NOT try to read call counts live from the Quo API: there
    is no per-user aggregate endpoint, and counting requires
    conversations → participants → `/v1/calls` per participant — minutes of
    rate-limited work, far too slow for a page load. **Measured 2026-08-05**: a
    full live enumeration of all 5 lines for one day took **48s** and returned
    **109** calls where the mirror had **147** — it found 0 the mirror lacked and
    missed 38, because a conversation whose `updatedAt` falls outside the window
    silently drops its calls. The mirror is both faster and more complete.
  - **Calls are split lead / buyer / outside / internal**, and only the first
    three count as outreach:
    - **`reference_doctype` is NOT a link test** — it has a doctype default of
      "CRM Lead", so it is set on every row whether or not anything matched.
      Only a non-empty **`reference_docname`** means genuinely linked. Reading
      the wrong field makes unlinked calls vanish (it reported 0 outside-CRM
      calls when the true figure was 101 in two weeks).
    - **outside** = external number with no linked record: cold calls, plus
      people who only became a lead/buyer later. The webhook stamps the link
      once, at call time, and never back-fills — 22 of 58 outside numbers in a
      two-week sample exist in the CRM today (mostly a later buyer import), so
      "outside" means *was not in the CRM when called*.
    - **internal** = the other party is one of our own Quo lines. Real calls,
      but not outreach, so they are excluded from the call count and shown as a
      separate "+N internal". This is why totals dropped (Aug 4: 147 → 135 + 12).
    - The workspace line list comes from one cached live Quo `/v1/phone-numbers`
      call (6h TTL) because `User.custom_quo_number` misses shared lines like
      the Backup Number; it falls back to the per-user numbers if Quo is down.
    - The split is what makes cold calling visible: 2026-08-03, Exe ran 21
      outside calls to 21 numbers against 24 buyer calls, while German's 82 were
      all leads.
  - **Toggl** is matched to CRM users **by email** (the workspace exposes the
    same addresses), so no mapping field exists or is needed. Creds come from
    site_config `toggl_username` / `toggl_password` / `toggl_workspace_id`.
    Every Toggl call is best-effort and cached (members 1h, day 120s): an
    outage degrades to "hours unavailable", never a broken board. Toggl stamps
    carry the member's own offset (the setters are on -03:00) and are converted
    with the same helper the Quo webhook uses. A **running** timer has no `stop`
    and reports negative seconds — its band runs to now instead, or today's
    board would read 0.0 h while people are working.
  - **The board flags what it can't vouch for** rather than presenting it as
    fact: a single stretch >10h (or >12h day) is called out as a probable
    forgotten timer (Dennis, 2026-08-04: 14.5h, 7:07am–9:34pm against CRM
    activity of 9:31am–4:40pm); someone active with zero tracked time is
    flagged; unattributed resolved cards are counted out loud.
  - **Cards use `resolved_by`/`resolved_at` when present, falling back to
    `done_by`/`done_at`.** `done_*` is Done-only by design, so **Skipped cards
    before the gw292 ops script have no owner and cannot be attributed** — the
    UI says so instead of showing zero.
  - Automated sequence texts are excluded rather than credited to the owner of
    the Quo line. Quo attribution support lives in the ops repo
    (`Quo Message.sent_by` / `activity_source`).
  - **Tasks "from Today" are inferred**, not stamped: a completed task counts as
    on-list when its lead had a card that day. Measured 2026-08-04: 54 of 55
    completed tasks matched, and the task/card pairs land within a minute of
    each other, so the inference tracks reality and works retroactively. Exact
    stamping would need a schema field plus prop-threading through
    Today → Activities → AllModals, and would only work going forward.

- **Activity feed no longer auto-scrolls on every reload** — the Lead/Deal
  Activity timeline used to yank the viewport on every action (adding a
  comment/task, sending a text) and on every realtime reload from a teammate,
  because each feed resource re-ran `scroll()` in its `onSuccess`, the comment
  composer emitted `@scroll` on send, and the attachments `@reload` chained
  `scroll()`. On the Comments tab that forced the feed to the bottom; on Activity,
  to the top — and the user then had to scroll back to the To-do/quick-add at the
  top. Now auto-scroll happens **only on mount** (deep-link to a `#comment` hash,
  or no-hash → newest entry). Removed the `onSuccess` scroll from all six feed
  resources (`all_activities`, `whatsappMessages`, `smsMessages`, `taxPulls`,
  `agreements`, `underwritingWorkbooks`), the `CommunicationArea` `@scroll`
  handler, and the attachments `@reload` scroll; kept the SMS/WhatsApp chat-tab
  send-scroll (standard chat behavior) and the mount `scroll(hash)`. Pure
  frontend. `frontend/src/components/Activities/Activities.vue`. Requested by
  Lance (the feed "scrolls to the bottom" every time he did anything).

- **Lead name auto-formatting** — inbound leads (iSpeedToLead webhook, manual
  entry, imports) often arrive oddly cased ("joe cholock", "priscilla Diaz",
  "JOHN SMITH"). `crm/api/name_format.py` `format_person_name()` title-cases a
  person name but only re-cases words that look machine-mangled (all-lower /
  all-upper), preserving already-cased names (McDonald, DeAngelo, O'Brien);
  handles Mc-, the O'/D' apostrophe family, hyphenated names, Jr/Sr/Roman-numeral
  suffixes, and keeps connectors lowercase ("Carol and Charles"). Idempotent.
  Wired as a `CRM Lead` `before_validate` hook (`normalize_lead_names`) that
  re-cases `first/middle/last_name` **on creation only** (later manual edits are
  respected); `validate()` rebuilds `lead_name` from the normalized parts.
  `backfill_lead_names(dry_run=1)` is a bench-executable backfill (writes via
  `db.set_value`, `update_modified=False`, no `doc.save` → no side-effects;
  dry-run by default). Pure app code — no ops/server-script piece. Backend only
  (no `.vue`). `crm/hooks.py` + `crm/api/name_format.py`.

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
- **Shared "Today" board** (`/today`, top of the sidebar) — the surface the setters
  work the day from; the 5am DM describes it, this is where German and Exe do it.
  Three columns (**To Call / Done / Skipped**) built from the SAME cadence
  definition as the standup DM, so the morning-call list and the worked list are
  the same list. `frontend/src/pages/Today.vue` + `crm/api/today_board.py`.
  - **Cards are rows, not a live recomputation** (ops doctype `CRM Today Item`).
    "Done"/"Skipped" are judgements a person made; recomputing would lose them,
    or resurrect a dismissed card, as soon as a call got logged — and the board
    has to hold still while people work it. Division of responsibility: **the
    cadence decides what LANDS on the board; humans own the card after that.**
    Generation only ever ADDS and never retracts a card that stopped being due.
  - **The list stays current after the 5am snapshot.** Header **Sync list**
    manually re-runs the shared cadence and reports how many cards it added.
    New leads and every lead-task mutation enqueue the same add-only sync after
    commit; an every-five-minute business-day scheduler is the race/failure
    safety net. Jobs dedupe during import bursts, and structural card autonames
    make concurrent runs safe. New scheduler method
    `crm.api.today_board.run_today_sync` requires `sync_jobs` after deploy.
    Existing Done/Skipped state and manual ordering are never touched.
  - **Today report + team streak** — the flame button opens current Total/Done/
    Skipped/Remaining progress, who completed today's cards, and recent business-
    day resolved rates (Done + Skipped). A perfect streak day means every card has been resolved
    as **Done or Skipped**. An unfinished current day does not erase the streak
    earned through the previous business day.
    `frontend/src/components/TodayReportModal.vue` +
    `TodayReportMetric.vue`; `crm.api.today_board.get_today_report`.
  - **autoname `format:{for_date}-{lead}`** makes (date, lead) structurally
    unique, so generation at 5am + manual Refresh + first-page-view auto-generate
    can all race without duplicating a card (verified under a real
    clear-then-regenerate race: 0 duplicates).
  - Each card is now **one call**, not one lead: first-week leads that owe two
    calls get independently actionable **Call 1 of 2 / Call 2 of 2** cards.
    `CRM Today Item.call_number` extends the structural key to
    `(date, lead, call_number)`; the schema upgrade preserves old card state/order
    and expands an old `calls_needed=2` row on first read. If the first call was
    logged before generation, only Call 2 is materialized.
  - Cards show **address and phone on separate lines**, the soonest open task
    (click → the real Task modal), and a green **incoming-text flag** with the
    last received time. The lead status is a color-dot dropdown directly on the
    card; changing it saves the full CRM Lead (status history + hooks preserved),
    updates both call cards for that lead optimistically, and asks for the normal
    Lost Reason before a Lost-type status can be applied. Open tasks use a neutral
    empty circle. When the card is
    Done and a task was completed that board day, it shows the latest completed
    task with a green check instead of the next future task. Clicking the address
    on either the card or lead modal
    asks **Google Maps or Zillow** and opens the chosen destination; both use the
    shared `utils/propertyLinks.js` builders also used by the full Lead page.
    The message icon opens the standard Send Text modal with
    the cursor already in the composer; Today adds **Skip / Send / Send & finish**
    so the card can be judged without returning to the board.
  - **Filters** cover lead status, priority, incoming texts, and open tasks. A
    draggable **Priority order** modal saves each user's order cross-device via a
    standard Frappe user default (no custom field). Default = Never called → Task
    due → Week 1 morning → Week 1 afternoon → Weekly → Monthly. Week-one call 1/2
    are separate morning/afternoon passes; the persisted cadence phase stays
    `week1`, and `priority_key` derives the pass from `call_number` at read time.
  - A task after TODAY suppresses cadence generation (a later-today task still
    belongs today); if both an overdue task and a future appointment exist, the
    future appointment wins. Due tasks rank immediately after never-called.
  - Clicking a card now mounts the **actual Lead `Activities.vue` surface**, not
    a lookalike: the same timeline, quick comments, To-do quick-add, task edit and
    task completion behavior. `scrollOnMount=false` keeps the pinned To-do visible
    in this modal instead of the Lead page's normal mount scroll hiding it.
  - Interactions: hover **✓ Done / ⊘ Skip / ↩ put back** (fixed-size absolute
    buttons so they cannot overflow a narrow desktop card), drag across columns,
    and drag to reorder within one. Realtime `crm_today` keeps boards in step.
  - **`reorder_today` renumbers the WHOLE destination column**, not just the
    dragged names — cards are seeded at wide priority offsets, so writing
    10/20/30 onto three dragged cards once dropped
    them *behind* untouched neighbours still sitting at 3, 4, 5. Any name not
    passed keeps its relative position and is renumbered after the ones that
    were, so even a partial list can't corrupt the order.
  - **GOTCHA**: `columns` is synced from the resource with a **watcher**, not
    `board.onSuccess = ...`. The resource is `auto: true` and can resolve BEFORE
    a post-hoc onSuccess assignment lands — which rendered "All clear" over 66
    real cards. Caught only in live verification; the API was fine the whole time.
  - Ops: `scripts/setup_today_board.py` (idempotent, `--dry-run`).
  - **Not yet checked on a phone** — fixed-width columns + horizontal scroll;
    desktop is the primary surface unless Ger confirms otherwise.
- **Intraday Today pulse (every 30 min, Acq channel)** — the half-hourly
  heartbeat between the 5am standup and end of day, so pace is visible while the
  day can still be changed. Posts to the **Acq channel** (not a DM) so the whole
  acquisitions team works off the same number, via the same `pi` bot and token as
  the standup. `crm/api/today_pulse.py` (**new**).
  - **No "N cards behind pace" verdict** — an elapsed-vs-resolved over/under
    line was built and then removed the same day. The board routinely carries
    more cards than a day can hold (81-111 generated against ~87 resolved on a
    good day), so it read "behind" almost every day. That is a statement about
    board size, not about the person working it, and a warning that fires daily
    stops being read. Board overload belongs in the standup's intake-capacity
    number, not in a half-hourly nudge.
  - Carries: cards resolved **since the last pulse**, the day's rolling total as a
    Done/Skipped/left progress bar, pace vs. the hours left, and **Quo talk time**.
  - **Talk time is a first-class metric, not decoration.** Cards-per-half-hour
    alone punishes the behaviour we want: a setter in a 20-minute conversation
    with a motivated seller resolves fewer cards than one dialing voicemails, and
    a bare "+0" reads as a rebuke for doing the job right. A window with no cards
    but real talk time is rendered as *"No cards closed — but 19m on the phone,
    longest 15m. Deep in a conversation."*
  - **Skips are timestamped now** (`resolved_at`/`resolved_by`, stamped for Done
    AND Skipped; `done_at`/`done_by` stay Done-only so the Today report, activity
    pulse and card UI keep their exact meaning). ~30% of a day's cards are
    resolved by skipping, so a Done-only delta reported a working setter as idle.
    Falls back to `done_at` and says so in the message if the ops script hasn't run.
  - **The delta window is a watermark, not a fixed 30 minutes** — it runs from the
    last *successfully posted* pulse to now, so a failed or skipped slot folds its
    cards into the next message instead of dropping them. Verified by replaying a
    real day: the deltas sum to exactly the day's resolved total (87 = 87).
  - **The observed rate is measured from the first resolved card, not from 9:30.**
    The setters routinely start an hour or more after the window opens; charging
    them for that time made the pulse open every day with a false "behind" warning
    built out of hours nobody was working. A rate is withheld entirely until
    `MIN_RATE_HOURS` of actual work has elapsed.
  - **Late in the day the required rate is replaced by a projection.** "need
    ~62/hr" with 30 minutes left is arithmetically true and useless; the message
    instead says what the current pace actually lands ("at ~12/hr that's about 6
    more, ~25 carrying over"). On the 8/04 replay that projection was accurate to
    within one card.
  - **The bar is two-tone (`█` resolved / `░` still to call), not three.** It first
    shaded Done and Skipped separately; Lance read the middle shade as "in progress"
    on the very first preview. A legend on the counts line fixed the ambiguity but
    not the cost — a nudge that has to be decoded every thirty minutes is not
    glanceable. The Done/Skipped texture lives in the counts line instead.
  - **`_progress_bar` never lies in either direction** — a non-zero segment never
    rounds away to nothing, and a board with work left always keeps at least one
    empty cell (naive rounding filled every cell with 1 card left of 21+, so the
    bar read "finished" while the board was not). Invariants checked exhaustively
    over every Done/Skipped/left split for totals 1–200.
  - Call attribution reuses `activity_progress`'s exact chain (`caller` →
    `receiver` → `User.custom_quo_number`), so the pulse and the Team Activity
    report cannot disagree about whose call it was. Verified 0 unattributed on prod.
  - No self-reply loop: `agent-listener` drops posts whose `user_id` is its own,
    and the pulse posts as that same `pi` user.
  - `preview_pulse(send=0, now=..., since=...)` is the dry run and never moves the
    watermark.
  - **Ops**: needs `scripts/setup_today_board.py` (adds `resolved_*`, idempotent)
    and `bench sync_jobs` on prod — a new scheduler hook does nothing until its
    Scheduled Job Type row exists. Cron `*/30 9-17 * * 1-5` is read in the SITE
    timezone (America/Chicago); the job itself enforces the real 9:30am–5:00pm
    window so the working hours live in one readable place.
- **Daily standup list (5am CT Mattermost DM)** — the list Lance runs the morning
  call from. `crm/api/daily_standup.py` (**new**) holds ONE server-side definition
  of "what has to happen today", rendered two ways: a DM as the `pi` Mattermost
  bot, and the same lead set via `get_standup_lead_names(bucket)` for a CRM Leads
  drill-in — so the standup list and the board **cannot drift**. Replaces an
  earlier abandoned report whose lists were wrong ("the due list had 33 leads, but
  most were Dead Lead"), so every rule and exclusion is explicit.
  - **Cadence = Dennis's**, posted in the Acq channel 2026-07-31: 2x/day for a
    week → weekly for 3 weeks → monthly. Two clarifications from Lance:
    "Call/Text" means call AND text but **only calls are metered** (texts are fast
    and don't compete for the same capacity), and **"1 week" = 5 BUSINESS days**
    — the call log is flat every weekend, so calendar-day counting burned ~2 days
    of a lead's best week and overstated cost (13 calls/lead in month 1, not 17).
  - **Suppression**: an open task with a FUTURE due date means the lead is booked
    → off today's list. Due-today/overdue puts it ON. Stops the report telling a
    rep to cold-dial a seller Dennis already scheduled.
  - **Roles, not owners** — `lead_owner`/`_assign` say Dennis owns ~99% of leads,
    but German + Exe do the calling while Dennis closes. Splitting by owner would
    hand the setters an empty list, so it emits one shared **calling queue** plus
    a **closer list** (Contract Sent → Make Offer → Underwriting, closest-to-
    closing first, flagged by DD date / task due / days silent).
  - **Ordering was the hard part; two cuts were wrong.** Ranking "has a due task"
    as its own top phase made the queue ~50 identical "needs 1 — Follow up" rows
    (~45 leads carry an auto-created task literally titled "Follow up") and buried
    all 17 never-called leads — the exact failure the report exists to fix. Phase
    now comes from the **cadence alone**; a task is a *reason*, not a rank. Second
    cut: a lead called yesterday still appeared under "Monthly sweep" because a
    generic task was overdue — leads due ONLY via a leftover task now sit in their
    own group at the bottom. Never-called sorts first (it's the actual leak).
  - Groups are individually capped so the list stays finishable.
  - **Excludes** parked import leads (`import_hidden`), converted, and
    `EXCLUDE_LEAD_NAMES` (the "Lance Test" record).
  - `preview_standup(send=0, note=...)` is the dry run (whitelisted/bench);
    `send_daily_standup` is the scheduler entry, wrapped so a delivery failure
    can't take down the cron slot, and it re-checks `is_business_day()` itself.
  - **Ops**: `bench set-config mattermost_token <pi bot token>` +
    `standup_dm_user lancejohnson` (token also at
    `~/.config/mattermost/pi-agent.env`; see `Projects/Groundwork/mattermost`).
    Absent a token `send_dm` no-ops rather than erroring.
  - **GOTCHA**: cron `0 5 * * 1-5` is read in the **SITE timezone**
    (America/Chicago), NOT UTC — writing it in UTC once turned an "8am" digest
    into 1pm. And a new scheduler hook does **nothing** until `sync_jobs` creates
    its Scheduled Job Type row on prod (gw127/128) — run it via `bench execute`,
    not `bench console`.
- **Dead leads stop generating work** — a lead moved to a dead status kept its
  open follow-up tasks forever, so they sat in the Activity to-do block and in
  every "due today" list. Measured on prod 2026-08-03: **25 open tasks on Dead
  Leads** (oldest due 2026-06-22) — a quarter of the whole due-or-overdue
  backlog was chasing leads nobody should call. Same disease that made the old
  ISTL digest useless ("the due list had 33 leads, but most were Dead Lead").
  `crm/api/task_hygiene.py` (**new**) + a `CRM Lead` `on_update` hook
  (`on_lead_update`) cancels open tasks (`Backlog`/`Todo`/`In Progress`) when a
  lead moves INTO a dead status.
  - **Keyed on `CRM Lead Status.type == "Lost"`, NOT on status names** — both
    "Dead Lead" and "Lost" are type Lost, so a rename or a new dead status
    ("Not Interested") keeps working. Hardcoding a guessed status list is
    exactly what broke the previous report. `Won` is deliberately excluded (a
    won deal can still carry real closing tasks) — add to `TERMINAL_TYPES` if
    that changes.
  - Gated on `has_value_changed("status")`, so re-saving an already-dead lead
    does NOT re-cancel a task a human deliberately reopened (verified).
  - **Canceled, never deleted** (reversible; timeline keeps the struck-through
    history), via `doc.save()` rather than `db.set_value` so `CRM Task.on_update`
    fires `crm_task_update` and the kanban badge / to-do block refresh live.
  - Hook body is wrapped in try/except — hygiene can never block a status change.
  - `backfill_terminal_tasks(dry_run=1)` is the bench-executable sweep; applied
    on prod (25 tasks / 25 leads, 0 errors, due backlog **91 → 66**, and every
    remaining due task now sits on a live workable status). No ops piece.
- **Call classification badge (editable)** — each call card in the Lead/Deal
  Activity timeline (and Buyer Conversation tab, same `CallArea.vue`) shows a
  color-themed badge with the call's classification (Connected / Voicemail
  Left / Greeting Hangup / Screener - No Contact / IVR-Robot / No Answer /
  Phantom / No Transcript), written by the `classify-crm-calls` skill
  (`~/.claude/skills/classify-crm-calls/` — deterministic pull → agent reads
  transcripts → guarded write-back) onto CRM Call Log custom fields
  (`custom_call_class` / `custom_call_class_source` rule|ai|human /
  `custom_call_note` / `custom_call_side`; created idempotently by the skill's
  pull script, NOT an ops setup script). The badge is a dropdown: picking a
  class calls `crm.api.call_class.set_call_class`, which stamps
  `source=human` — the classifier's write-back never overwrites human
  verdicts. Tooltip shows the classifier's evidence note. No backend read
  changes needed: `get_call_log` returns the full doc (`as_dict`), so the
  fields ride along like `custom_ai_summary`. GOTCHA: frappe-ui `Dropdown`
  uses reka-ui `DropdownMenuTrigger as-child` — the slot ROOT must be a plain
  element (a `<button>`); wrapping the slot in `<Tooltip>` swallows the
  trigger handlers, and `@click.stop` must live on a wrapper `<div>` (Dropdown
  doesn't inherit attrs, so the card's open-modal click fires otherwise).
  Mobile (gw253): wrapped badge rows use a tighter vertical gap, and transcript
  lines switch below `sm` from the cramped 48px speaker-name column to a
  two-column grid (time | speaker-above-content); long names no longer collide
  with dialogue, and hover-only line actions hide on touch widths. Verified in
  a genuine 390px Chrome popup: 9 transcript rows, zero bounding-box overlap.
  `crm/api/call_class.py` (**new**) + `frontend/src/components/Activities/CallArea.vue` +
  `CallTranscript.vue`.
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
- **@-mention emails** — `@`-mentioning a teammate in a Lead/Deal comment already
  created an in-app `CRM Notification`; now it ALSO emails them. `crm/api/comment.py`
  `notify_mentions()` calls a new `email_mention()` per mention: `frappe.sendmail`
  with the `crm_mention` template (comment HTML + a "View comment" button) linking
  to `/crm/{leads|deals}/<reference_name>#<comment_name>` — the same route+hash the
  bell notification uses, so it lands on the record and scrolls to the comment.
  Self-mentions are skipped (mirrors `notify_user`); a send failure is caught/logged
  so it can never roll back the comment; owner full_name + record label are computed
  once before the mention loop. Pure app code, no ops piece (reuses existing SMTP).
  `crm/api/comment.py` + `crm/templates/emails/crm_mention.html` (**new**, mirrors
  the `crm_invitation` template).
- **Quick comments (customizable canned comments)** — a "Quick comment" block in
  the Lead/Deal Activity feed (directly below the To-do block, same card style):
  a row of one-tap chips that each post a canned comment to the timeline. Each
  user customizes their own list via an inline pencil editor (add/edit/remove
  rows + Save). Seeded defaults for any user who hasn't customized: "Call 3x's,
  voicemail, sent text" / "Called" / "Voicemail" / "Sent text". Persisted
  cross-device on a `User.custom_quick_comments` JSON field (mirrors the
  `custom_quo_number` per-user-setting pattern). Requested by Dennis.
  - `frontend/src/components/Activities/QuickComments.vue` — **new** (chips +
    inline editor; reads the session user's list from the users store, falls back
    to defaults when unset)
  - `frontend/src/components/Activities/AllModals.vue` — `addComment(content)`
    helper (posts via `crm.api.comment.add_comment`, wraps plain chip text in a
    `<div>`, reloads the feed) + exposed
  - `frontend/src/components/Activities/Activities.vue` — renders `<QuickComments>`
    after `<TaskTodoList>`; widened the Activity-tab `v-else-if` to `title ==
    'Activity'` so the To-do + Quick-comment blocks always show (even on an empty
    lead) instead of the EmptyState
  - `crm/api/session.py` — `custom_quick_comments` added to `get_users` fields
  - `crm/api/comment.py` — `set_user_quick_comments(comments)` (session user's
    own list only; stores a cleaned JSON array, capped at 30)
  - Ops (`../frappe-crm-deploy`): `scripts/setup_quick_comments.py` adds the
    `User.custom_quick_comments` Long Text custom field (no seeding — defaults
    live in the frontend)
- **Inline lead-name editing (sidebar header)** — hovering the lead's name in
  the Lead page sidebar shows a pencil; clicking swaps it for separate
  First/Last name inputs (Tab moves first → last, Enter or clicking away
  saves, Esc cancels). Saves `first_name`/`last_name`; the server's
  `validate()` rebuilds `lead_name`, mirrored optimistically so the header
  never flashes stale. First name required (matches the doctype). Pure
  frontend. `frontend/src/pages/Lead.vue`.
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
  - per-user sending number on `User.custom_quo_number`: when a user with no
    linked number opens a texting surface (SMS tab / `SendTextModal` / the
    `/texts` inbox thread), `Modals/SelectQuoNumberModal.vue` auto-pops with
    the Quo workspace lines (number + line name) — picking one saves to their
    profile via `set_user_quo_number` and unblocks Send (a "Select number"
    banner reopens it if dismissed). Replaced the old inline `QuoFromSelect`
    "Send from" row in the compose surfaces (gw171; the component file remains,
    now unused). Admin assignment still in `Settings/Users.vue`;
    `composables/quoSender.js` has `quoNumbers`/`myQuoNumber`/`formatPhone`
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
- **Call transcript deep-link to a timestamp** — share a link to a specific
  moment in a recorded call's transcript + audio, landing in the lead's Activity
  timeline. Link shape `/crm/leads/<leadId>?call=<callLogName>&t=<seconds>#activity`
  (Deals supported too via `linkTarget`); opening it switches to the Activity tab,
  auto-expands that call's `<CallTranscript>`, seeks the audio to `t`, and scrolls
  the card into view. Grab a link two ways: hover any transcript line → a 🔗 at the
  line's end copies a link to THAT line's start; or the 🔗 in the player bar copies
  a link to the current playhead (both via `copyToClipboard`). Pure frontend, no
  schema/server piece.
  - `components/Activities/CallTranscript.vue` — new `seekTo` + `linkTarget` props;
    `applyPendingSeek()` defers the seek until the audio has buffered far enough to
    land there (`preload='auto'` + retries on `progress`/`canplay`/`canplaythrough`)
    — seeking at `loadedmetadata` clamps to the buffered edge (apiDuration is often
    null for these); the two 🔗 copy buttons.
  - `components/Activities/CallArea.vue` — self-activates when
    `route.query.call === call.name` (expand + a scroll-retry loop that re-runs
    `scrollIntoView` until the card parks near the top, since the feed re-lays-out
    after mount); passes `:seek-to` down.
  - `pages/CallReview.vue` — passes `:link-target="{type:'leads',id:reference_name}"`
    so its copy-link points at the lead timeline.
- **Timestamped call comments + "Playback" consolidation** — reviewers annotate a
  specific moment in a recorded call ("ask a better question here") and the comment
  is pinned (a violet author-initial dot) on a time-aligned ruler under the
  waveform; a Comments list under the transcript shows each with a clickable
  time-badge (→ seek), and owners get hover edit/delete. Collaborative: every sales
  user sees all comments on a call; edit/delete is owner-only (managers may delete).
  Also **decluttered the call UI**: removed the separate **Listen** inline player
  (activity timeline) and the standalone `<audio>` player (Call Review) — hitting
  one control opens audio+waveform+transcript+comments — and **renamed that control
  "Transcript" → "Playback"** (the "Recording" raw-file link stays).
  - **Storage = new ops doctype `CRM Call Comment`** (mirrors `CRM Call Review`):
    `call_log` / `at_time` (Float secs) / `author` / `content`, autoname hash,
    Sales-roles perms. Created by `../frappe-crm-deploy/scripts/setup_crm_call_comment.py`
    (idempotent REST, `--dry-run`). No CRM Call Log custom field.
  - `crm/api/call_comments.py` — `get_call_comments` / `add_call_comment` (author =
    session user) / `edit_call_comment` (owner-only) / `delete_call_comment`
    (owner or manager); each mutation publishes `crm_call_comment` realtime
    (site-wide, `after_commit`); all guarded by `db.exists` so a pre-provision site
    returns `[]`. Reuses the `reports.py` sales-role gate.
  - `components/Activities/CallTranscript.vue` — comments resource + 💬 transport
    button → inline composer at the current playhead, plus a per-transcript-line
    hover 💬 next to the 🔗 (`startCommentAt(line.start)` → composer at that line's
    moment); waveform pins (`posOf(at_time)`, `selectComment` → seek + highlight),
    comments list with inline edit, `crm_call_comment` `$socket` listener (reload
    when `call_log` matches). Add/edit/delete via frappe-ui `call()`.
  - `components/Activities/CallArea.vue` — dropped the Listen badge + `AudioPlayer`;
    Transcript badge → **Playback** (PlayIcon). `pages/CallReview.vue` — dropped the
    `<audio>` element; toggle label → **Playback** (keeps the "No recording" span).
- **AI "Integrity Report" call-review bot** — a daily scheduler job that reviews
  every recorded call from the prior day with Gemini (2.5 Flash) and emails Lance
  one digest. Scores how well the rep got to the seller's **motivation** (0-5, or
  null on follow-ups/voicemail) and flags **integrity** issues — anything not fully
  honest or "salesy" instead of plainly clear (good: *"we're going to buy it and
  resell it to a builder or homeowner as quickly as we can — we actually work on
  getting it pre-sold right away"*; bad: *"we have multiple exit strategies like buy
  and hold, fix and flip, or wholesale"*). Each issue = verbatim quote + why +
  better phrasing. Also notes where the lead is at + what to do differently. First
  LLM call in the app code (raw `requests` to the Gemini API, key in site_config
  `gemini_api_key` — mirrored from the existing Infisical `GEMINI_API_KEY`, the same
  key the ops chapter-gen uses; JSON response schema; model config-swappable via
  `call_review_model`, e.g. `gemini-2.5-pro`). Per-call result stored in a new ops
  doctype `CRM Call AI Review`, surfaced in the Lead/Deal-adjacent **Call Review**
  tab — which is now **restricted to Lance only** (sidebar + route + backend gate).
  - `crm/api/call_review_ai.py` — **new**: `run_daily_integrity_report` (daily_long),
    `review_call_now` (whitelisted, Lance/System-Manager, on-demand + testing),
    `_review_one`/`_build_llm_input`/`_lead_context`/`_call_claude`/`_persist_review`/
    `_send_digest`. Scope = transcript + duration ≥ 60s; idempotent (one
    `CRM Call AI Review` per call); loads lead context (status/tasks/comments/prior
    AI summaries) into the prompt.
  - `crm/api/call_transcript.py` — extracted pure `_build_transcript(doc)` helper
    (endpoint is now a thin wrapper) so the bot reuses clean rep/lead dialogue.
  - `crm/templates/emails/crm_call_review_report.html` — **new** digest template.
  - `crm/hooks.py` — `run_daily_integrity_report` added to `daily_long`.
  - `crm/api/reports.py` — `validate_access` now Lance/System-Manager only
    (`CALL_REVIEW_USER`); `get_call_review` attaches `ai_review` per call from
    `CRM Call AI Review` (guarded by `db.exists`).
  - `frontend/src/utils/sidebarLinks.js` (`CALL_REVIEW_USER` + `currentUser()` +
    Call Review `condition`), `router.js` (route guard), `pages/CallReview.vue`
    (per-call AI panel: flag badge → expand → motivation, integrity issues, coaching).
  - Ops (`../frappe-crm-deploy`): `scripts/setup_call_ai_review.py` creates the
    `CRM Call AI Review` doctype (autoname by `call_log`; fields motivation_score/
    motivation_reason/integrity_issues JSON/overall_flag/lead_status/
    what_could_be_better/model/reviewed_at/reference_*); `bench set-config
    gemini_api_key <key>` on prod, value pulled from the existing Infisical
    `GEMINI_API_KEY` (same pattern as `documenso_api_token`).
  - **2026-07-10 (gw127/gw128)**: (a) the daily job had NEVER fired — the
    `daily_long` hook needs a **Scheduled Job Type row**, and `sync_jobs` never
    ran after the gw118 deploy (the seqdrain gotcha again). Fixed on prod via
    `bench execute frappe.core.…scheduled_job_type.sync_jobs` (running it from
    `bench console` did NOT persist the row; use bench execute). Any future
    scheduler-hook addition needs this. (b) Digest is now **exhaustive** — clean
    calls get full detail rows (green border) after the flagged ones, not just a
    count. (c) System prompt now enforces Lance's transparency talking points
    (from the Jun 27 email to Dennis): approved exit-strategy script, banned
    phrases ("OUR builders/partners", the three-exit-strategies menu,
    "contractors/partners" for buyers), profit + multiple-visits disclosures
    (missing-disclosure flags only on discovery/offer calls), and **novation
    guardrails** (seller must understand: we just list it with an agent — they
    could too; access for showings; they'll net LESS than listing themselves
    even after agent fees; our value = simplicity/negotiations).
  - **gw129/gw130: unknown-lead calls in the digest** — a call with no linked
    lead now shows the other party's phone number ("Unknown (+1555…)") and
    deep-links to the **Call Review page** (`/crm/reports/calls?date=&call=&t=`)
    instead of nothing. `pages/CallReview.vue` honors those query params: sets
    the date, auto-opens that call's Playback + AI panel, seeks to `t`, scrolls
    the card into view (scroll-retry loop). NOTE the route path is
    `/reports/calls` (route name "Call Review") — there is no `/call-review`
    path; gw129 shipped the wrong URL and gw130 fixed it. Verified live.
- **iSpeedToLead refund-eligibility watch — REMOVED 2026-07-28** (gw226, at
  Lance's request). Was a twice-daily digest (8am/3pm Mon-Fri) of ISTL leads at
  risk of losing the 5-double-dials-in-10-days refund, plus a matching amber/
  red/green kanban card tint. Deleted wholesale: `crm/api/istl_refund_report.py`,
  `crm/templates/emails/crm_istl_refund_report.html`, the two `cron` hooks, and
  the `_istl_card_colors` branch in `crm/api/doc.py` (`_new_lead_color` is back
  to the plain untouched-new-lead age tint from gw104, and `dueTint`/
  `TINT_URGENCY` lost their now-unreachable `green`). The two Scheduled Job Type
  rows were deleted on prod. Recoverable from git history if it's ever wanted
  back.
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
  - **Fail-safe (gw173)**: the engine catches step exceptions internally and
    leaves the enrollment Active-and-due, so a persistently failing send used to
    retry forever — when Quo ran out of prepaid credits (Jul 8–15 2026) that
    meant 275k Error Log rows and the stale backlog blasting out the moment
    credits were topped up. `drain()` now snapshots
    (current_step, next_run, modified) around `_run_core`; a due run that
    advances nothing counts as a failure: the job returns (retries once per
    drain_due tick, not 50×/job) and `fail_count` (Int on the enrollment, added
    by ops `setup_sequence_failsafe.py`) increments; at
    `MAX_CONSECUTIVE_FAILURES` (10 ≈ 10 min) the enrollment is set **Paused** +
    `FAILSAFE_NOTIFY` (Lance) is emailed (resume = set Active on the sequence's
    Enrollments list). Progress resets the counter; disabled sequences and a
    missing `fail_count` column no-op (pre-provision safe). Quo billing itself:
    auto-recharge is now ON (2026-07-15).
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
  - **Acquisition scope toggle** (gw192): a second segmented control next to
    Cohort/Flow — **Acquisition | All stages**, default Acquisition (persisted in
    `localStorage['statusReportScope']`). Acquisition shows only the 7
    acquisition-phase statuses (New → Signed Contract; `ACQ_STAGES` constant in
    `StatusChangeReport.vue`); dispo + parking/terminal stages drop out as rows
    but still appear inside a row's unfolded Came-from/Went-to flows. Pure
    client-side filter over the already-returned stages — toggling is instant,
    backend and drill-downs untouched. If a status is renamed, update
    `ACQ_STAGES` (unmatched rows just fall out of Acquisition scope; All stages
    always shows everything).
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
  - **REDESIGNED as a people-first contact ledger** (gw194+gw195, replacing both the
    original type-rows table and the short-lived gw193 "N acq" sub-numbers,
    which Lance rejected): `ActivityReport.vue` is now ONE ROW PER CONTACTED
    LEAD (name · current-status dot · calls ↗out/↙in · talk time · texts
    ↗out/↙in · Agr column only when the scoped set has agreements), scoped by
    an **Acq | Dispo | All** segmented toggle (default Acq, persisted in
    `localStorage['activityScope']`); a totals strip (Contacted / Calls /
    Talk time / Texts) sits above the table and reflects the active scope.
    Inbound is green, outbound gray (the app's direction language). Sticky
    table header in a max-h scroll; row click opens the lead; footer "Open all
    in Leads" feeds the scoped names straight into `leadDrilldown` (no server
    resolver). Backend: **`get_contacted_leads`** merges the three row fetchers
    (which select `Lead.status` through their existing joins) into per-lead
    rows with a `bucket` field — `acq` (`ACQ_STATUSES`, = the 7 acquisition
    statuses; keep in sync with `ACQ_STAGES` in `StatusChangeReport.vue`),
    `dispo` (`DISPO_STATUSES`), or `other` (dead/parked/won) — so ONE fetch
    powers all three scopes client-side (toggle = instant). Bucketing is by
    CURRENT status, not status at activity time. `get_leads_dashboard` no
    longer returns `activity`; `_activity_summary`/`get_activity_leads` remain
    in `leads_dashboard.py` but have no frontend consumer. Mobile (gw195):
    below `sm` the Status + Talk-time columns hide, the name column caps at
    7rem (≈376px total on a 390px phone), and the table wrapper is
    `overflow-auto` so narrower screens scroll inside the card. NOTE: the
    Chrome-MCP extension pins the page viewport (innerWidth stays desktop-size
    regardless of OS window size), so phone layouts can't be visually verified
    through it — verify responsive classes via DOM inspection or a real phone
    (a freshly-created MCP window sometimes DOES render narrow — worth a try).
    gw196: the Status Change Report table is wrapped in `overflow-x-auto` +
    `min-w-[520px]` — unwrapped, its width forced the WHOLE PAGE to scroll
    horizontally on phones, clipping the status names off-screen (Lance hit
    this live). Wide dashboard tables must always scroll in-card.
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

- **Acq Price (header) + Dispo fields (lead sidebar)** — deal-lifecycle fields
  on CRM Lead (this CRM runs the whole lifecycle on leads; there are zero CRM
  Deal records). **Acq Price** = `acq_price` (Currency) lives in the sidebar
  HEADER: a `$`-icon row (MoneyIcon, no label — `title` tooltip "Acq Price")
  directly under the lead name/address in `pages/Lead.vue`, per Lance ("under
  the lead name and just have the $ icon"). Custom inline editor: digits only
  (non-digits stripped on input), live thousand separators (`toLocaleString`),
  Enter/blur saves via `updateField('acq_price', n)`, Esc reverts; the
  `doc.acq_price` watcher skips overwriting the draft while focused. **Dispo**
  side-panel section = `dispo_price` (Currency, leads the section),
  `inspection_end_date`/`closing_date` (Date), buyer assigned as at-a-glance
  fields (`buyer_name`/`buyer_phone` (Phone)/`buyer_email` (Email)/
  `buyer_entity`/`buyer_em_amount` (Currency)/`buyer_inspection_end_date`
  (Date)), and `list_price` (Currency), rendered generically with inline
  editing. Custom Fields + `CRM Lead-Side Panel` layout rows created by ops
  `../frappe-crm-deploy/scripts/setup_dispo_fields.py` (idempotent, `--dry-run`;
  enforces the canonical Dispo field order, keeps UI-added extras after ours,
  and deletes retired sections via `REMOVED_SECTIONS` — the old `deal_section`
  is gone). Also **removed upstream's 300px max-height + internal scroll on
  side-panel section columns** (`SidePanelLayout.vue` CSS) — it hid fields past
  the fold (Lance couldn't see Buyer EM); the sidebar body is one scroll
  region, so sections now grow naturally.
- **InvestorLift dispo integration** — marketing dashboard on the lead
  (`InvestorLiftCard.vue`) + address auto-matcher, top-level **Dispo** nav →
  per-property buyer Kanban (`pages/Dispo.vue`) + buyer page w/ conversation
  timeline (`pages/Buyer.vue`), automated buyer scraper with SMS-webhook 2FA
  capture, auto-pull of new buyers from address-request notifications.
  Backend `crm/api/investorlift*.py`; settings page
  `Settings/InvestorLiftSettings.vue`. Full design doc:
  `docs/investorlift-integration.md` (merged from
  `feature/investorlift-dispo`, built in a parallel agent session).
- **Buyer directory + manual buyer creation + metro areas** (gw158-gw165) — a
  top-level **Buyers** nav (`/buyers`, `pages/Buyers.vue`): searchable directory
  of every CRM Buyer (search + metro filter + "Active in" = metro or engaged
  property cities + deal counts), a **New buyer** modal
  (`Modals/BuyerModal.vue`, create/edit, dedupes by email→phone→name and offers
  "Open" on a duplicate), and metro linkage: new ops doctype **CRM Metro Area**
  seeded with the **393 Census MSAs** (July 2023 OMB delineation, vendored at
  `../frappe-crm-deploy/scripts/data/us_metro_areas.txt`), plus
  `CRM Buyer.metro_area` (Link) + `buybox` (Small Text, free-form until buybox
  search is structured). Backend `crm/api/buyers.py` (get_buyers/create_buyer/
  update_buyer/get_metro_areas/create_metro_area/get_buyer_calls). Buyer page
  gained Edit (same modal), metro + buybox display. Ops:
  `scripts/setup_buyer_directory.py` (idempotent; doctype + fields + metro seed).
  - **Buyer activity parity with leads**: the buyer page's Conversation now
    renders calls from **CRM Call Log** (matched by last-10 phone against
    from/to) with the lead timeline's own `CallArea` card — recording, Playback
    (waveform + transcript + comments), AI summary — merged time-sorted with the
    live-fetched Quo texts. `get_buyer_calls` reuses `parse_call_log` and
    substitutes the buyer's name for the "Unknown" contact side;
    `get_buyer_conversation` (ingest) is texts-only now.
  - **IL buyer contact enrichment (Marcel Cohen fix)**: the address-request
    webhook now falls back to the IL admin API (property inquiries →
    `/customers/{id}`) when the paired "New buyer signed up" text isn't found,
    so buyers arrive with email/phone/verified/il_buyer_id instead of name-only;
    `_find_buyer` gained a last-resort name match against email-less+phone-less
    rows so enrichment merges instead of duplicating (`investorlift_ingest.py`).
    Cleaned the two prod duplicates (Marcel Cohen, Illinois Land Investment).
  - **Whole-dollar currency display**: `stores/meta.js` getFormattedCurrency/
    getCurrencyWithPrecision default precision 0 (docfield precision still
    wins), and `crm/api/activities.py` `strip_currency_cents()` drops the ".00"
    Version docs bake into timeline "added Acq Price as $ 2,500.00" entries.
  - **Signed agreement PDFs open inline**: `download_signed_agreement` sets
    `display_content_as="inline"` + `content_type="application/pdf"`; the
    AgreementsCard + timeline links are now "Open signed PDF" with
    `target=_blank` (opens as a browser tab; right-click still saves).
  - **Phone display formatting**: buyer surfaces (Buyer/Buyers/DispoBoard/
    CallReview) render numbers via the existing `formatPhone` → (###) ###-####.
  - **Metros are MULTI-select** (gw166): `CRM Buyer.metro_areas` (Small Text,
    JSON array — metro names contain commas) supersedes the single `metro_area`
    Link; BuyerModal uses a chips + Autocomplete picker (client-side over
    `get_metro_areas`, single-line options — the stock Link control showed
    name+title duplicated for metros — with a Create-"query" footer);
    `get_buyers(metro=)` filters via a quoted-JSON LIKE; `active_in` = metros
    joined " · " else engaged-property cities.
  - **Manually add buyers to deals** (deals = leads): `add_buyer_to_lead(lead,
    buyer, stage)` (idempotent, publishes `crm_il_buyers`) +
    `Modals/AddBuyerToDealModal.vue` — mounted on the **Dispo page** header
    ("Add buyer": pick/search a buyer or create one inline via
    `BuyerModal :redirect="false"`, pick a stage) and on the **Buyer page**
    ("Add to deal": pick a dispo property).
- **Buyer activity parity (comments / to-dos / agreements on buyers)** (gw175) —
  the Buyer page (`pages/Buyer.vue`) is now Lead-shaped: tabs on the left
  (**Activity** with the To-do quick-add block + Quick-comment chips, mirroring
  leads · **Conversation** (the bespoke live-Quo texts + phone-matched CRM Call
  Log calls panel, moved into a tab — those aren't reference-linked, so they
  stay outside Activities) · Comments · Tasks · Notes · Attachments), and a
  right Resizer sidebar (profile + Engaged properties + a new **Agreements**
  card). It mounts the SAME `<Activities doctype="CRM Buyer">` component leads
  use — comments (`Comment`), tasks (`CRM Task`), notes (`FCRM Note`) and files
  were already generically keyed by `reference_doctype`/`reference_name`, so
  the whole modal/quick-add/realtime stack (incl. `crm_task_update`) just works.
  - `crm/api/activities.py` — `get_activities` gained a CRM Buyer branch →
    **`get_buyer_activities`** (mirrors the lead version; `avoid_fields` hides
    the machine-churned `last_active`/`deal_history`/`il_buyer_id` versions).
  - `crm/api/comment.py` — @-mention notifications/emails handle CRM Buyer
    (name = `buyer_name`, deep-link route `/crm/buyers/...`).
  - **Agreements: buyer-linked only** (gw176 — Lance: a property's seller-side
    agreements must NOT appear on an engaged buyer). `CRM Esign Agreement`
    gained an optional **`buyer` Link → CRM Buyer** (ops `setup_agreement.py`
    `ensure_field(..., after="lead")`); the buyer card lists ONLY rows with
    `buyer == this buyer` (`get_buyer_agreements`, has_column-guarded), each
    still linking to its lead + `property_label` (rows shaped by the extracted
    `_shape_agreement`). `components/BuyerAgreementsCard.vue` (**new**, modeled
    on AgreementsCard: status badge, buyer link, signed-PDF link, `crm_esign`
    listener). The **＋** is a dropdown of engaged properties → fetches that
    lead's doc → the existing `CreateAgreementModal` (same prefill flow), which
    passes its new optional `buyer` prop → `create_docuseal_agreement(buyer=)`
    stamps the link, so the agreement lands on BOTH the lead's card/timeline
    and this buyer's card. Lead-page creations have no buyer (unchanged).
  - Tab state persists per-user as `lastBuyerTab` (`useActiveTabManager`).
- **Buyer ↔ Quo two-way contact sync + buyer texts/calls sync** (gw177) — every
  CRM Buyer is the peer of a Quo (OpenPhone) contact so buyer numbers show names
  on calls/texts in the Quo apps (the team had been hand-typing "Manny - Chicago
  Buyer" contacts), and buyer conversations are stored/live in the CRM.
  - **`crm/api/quo_contacts.py`** (new) — the sync engine. Push: CRM Buyer
    after_insert/on_update (or explicit `enqueue_push` from the `db.set_value`
    paths in `buyers.py` / `investorlift_ingest.py`, which fire no doc events)
    creates/updates the linked contact; on_trash tombstones `externalId`
    (`deleted-<name>`, mirrors the lead-side unlink script). Pull: `sync_all`
    (cron `*/10`, hooks.py) pages all contacts once and reconciles two-way by
    comparing `contact.updatedAt` / `buyer.modified` against the
    `quo_synced_at` watermark — adopts existing manual Quo contacts by last-10
    phone (never duplicating them), renames junk "*- *-" import rows, pulls
    team edits (name/tags/email-fill) back, creates contacts for unlinked
    buyers, and IMPORTS a Quo-only contact as a new CRM Buyer when its name or
    tag says "buyer" (word match) and its phone matches no lead. Conflict
    policy: on first link a non-junk human-typed Quo name wins (pulled in);
    both-sides-changed → Quo name wins, tags union. Link state on CRM Buyer:
    `quo_contact_id` / `quo_synced_at` / `quo_tags` (ops
    `setup_buyer_quo_sync.py`); key from site_config `quo_api_key`.
  - **Quo tags**: the workspace's "Contact" multi-select custom field (created
    by the team, renamed from "Tags" — resolved by key via
    /v1/contact-custom-fields, matched case-insensitively against
    Contact/Tags) mirrors two-way with `CRM Buyer.quo_tags` (comma-separated;
    editable in BuyerModal as "Quo tags", shown merged with the IL
    `buyer_type` chips on the buyer page). Engaged property addresses are
    pushed one-way into the Quo "Property" multi-select. API values are
    free-form (no predefined options needed).
  - **OpenPhone contact-PATCH landmine** (cost us a test contact): a
    `customFields`-only PATCH returns 200 but wipes `defaultFields` and the
    phone-less contact is then garbage-collected (all later GETs 404). Every
    PATCH must send the FULL merged `defaultFields` with item `id`s stripped.
    Recorded in the Quo Bruno QUIRKS.md.
  - **Buyer texts are stored now**: the ops `sequence-events` webhook mirrors
    texts matching a CRM Buyer phone (leads keep priority) into `Quo Message`
    with `reference_doctype: CRM Buyer`; history backfilled by ops
    `backfill_buyer_texts.py` (fetches workspace lines live).
    `get_buyer_conversation` reads those stored rows (fast, full history, MMS
    media via `SMSMedia`, sender attribution) instead of live-fetching 50/line
    from the API; `Buyer.vue` listens for `quo_message` (re-attached on every
    switch into the Conversation tab, because Activities' unmount does a
    blanket `$socket.off('quo_message')`) and `crm_buyer_update` (emitted by
    the pull sync after changing a buyer).
  - **Buyer calls**: the webhook's `call.completed` mirror stamps
    `reference_doctype: CRM Buyer` when the external number matches a buyer
    and no lead; history stamped by
    `crm.api.quo_contacts.stamp_buyer_call_references` (bench execute,
    dry_run default). The buyer page call list itself still matches by phone
    (`get_buyer_calls`).
  - **Property tags on IL-link + engagement** (gw178/gw179): when a lead gets
    `il_property_id` (manual save → `on_lead_update` hook; the auto-matcher
    links via `db.set_value`, so `investorlift._run_match` calls
    `enqueue_tag_lead_property` explicitly), the SELLER's Quo contact gets the
    property address added to the Quo "Property" multi-select — that also
    makes the tag value exist in Quo (no API to define options; a value exists
    once a contact carries it). A buyer engaging/leaving a property
    (`CRM Lead Buyer` after_insert/on_trash → `on_lead_buyer_change`)
    re-pushes their contact so its Property tags reflect current engagements
    (recomputed from live rows; wholesale replace when non-empty — a
    disengage-to-ZERO leaves the last tag, since pushing [] could wipe
    hand-set values). Backfill: `tag_all_linked_leads` (bench execute).
    gw179: `push_buyer` skips no-op PATCHes (blind PATCHes bump `updatedAt`
    and churn the reconcile) and `_upsert_buyer` only enqueues a push when an
    identity field actually changed — the IL scraper re-upserts every buyer
    each run and once flooded the short queue with 189 no-op pushes.
- **Bulk-text buyers (per-message confirm)** (gw186/gw187) — text a picked group
  of CRM Buyers, but with a **manual confirm on every message** so the rep
  eyeballs each `{{first_name}}` substitution before it sends (Lance's explicit
  ask). A `BulkTextModal.vue` stepper: **Compose** (pick recipients — a checklist,
  all pre-checked = "text all", buyers with no phone auto-excluded + counted;
  write a template with a `{{first_name}}` / `{{name}}` token; confirm the sending
  Quo number) → **Review** (walks recipients ONE at a time: buyer + phone + the
  fully-rendered message in an editable box; Send & next / Skip / Back; running
  "N of M · X sent") → **Done** (sent/skipped/failed summary). Nothing sends
  until the rep clicks — deliberately **one synchronous send per click**, no
  background blast.
  - Two entry points: the **Dispo board** header **"Text buyers"** button (seeded
    with that deal's board buyers via `get_deal_buyers`, deduped) and a
    **select-mode** on the **/buyers directory** ("Select to text" → a checkbox
    column + "Text (N)"; in select mode a row is a `<div>`, not a `router-link`,
    so a click toggles selection instead of navigating — `@click.prevent` on a
    router-link loses the race with RouterLink's own nav handler).
  - **Backend = app code** `crm/api/bulk_text.py` `send_buyer_text(buyer, content,
    from_number)` — sends ONE text to one buyer, content verbatim (the rep already
    confirmed it), buyer phone resolved server-side. Like `agreement_notify.py` it
    POSTs OpenPhone directly with site_config `quo_api_key`, and stores the text as
    a `Quo Message` referenced to **CRM Buyer** (so it threads on the buyer's
    Conversation tab + fires the `quo_message` realtime via the existing
    after_insert hook). No ops piece — reuses the `quo_api_key` already in
    site_config and the existing Quo Message doctype. Sales-roles gated; a
    first-time from-number pick is saved to the user (mirrors `send-text`).
  - `frontend`: `components/Modals/BulkTextModal.vue` (**new**), mounted in
    `pages/Dispo.vue` (button + `get_deal_buyers` resource) and `pages/Buyers.vue`
    (select-mode). `{{first_name}}` renders client-side (falls back to the first
    word of the buyer name, then "there") — and since every message is confirmed,
    a bad substitution is caught before it sends.
  - **Dispo board list view + Buyers "by property" filter** (gw188): (a) the Dispo
    board (`components/Activities/DispoBoard.vue`) gained a **Board/List** toggle
    (segmented control in the `pages/Dispo.vue` header, persisted per-user in
    `localStorage['dispoView']`, passed as a `view` prop). List = a flat,
    stage-ordered table (Stage dot + label / Name / Type / Phone / Direction /
    Last active / Msgs), same `get_deal_buyers` data + realtime as the Kanban.
    (b) The **/buyers directory** gained an **"All properties"** filter (an
    Autocomplete next to the metro filter, options from
    `investorlift_ingest.get_dispo_properties`) that narrows the list to the
    buyers engaged on that dispo property. `crm/api/buyers.py` `get_buyers` gained
    a `property` param (a CRM Lead name) → resolves the `CRM Lead Buyer` rel rows
    to buyer names and adds a `["name","in",[...]]` filter; composes with
    search + metro + select-to-text.
  - **"Text these (N)" on the filtered list** (gw189): when any filter is active
    (search / metro / property) the /buyers toolbar shows a solid **"Text these
    (N)"** button that opens `BulkTextModal` pre-loaded with the WHOLE current
    filtered list (all pre-checked) — a one-click path vs "Select to text"'s
    manual pick. Both now set a shared `bulkRecipients` ref at open time
    (`textThese` = all `rows`, `textSelected` = the checked ones); the per-message
    confirm step still applies. Gated on `hasFilter` so it never blasts all
    ~354 buyers unfiltered.
  - **Status column + status failsafe** (gw190): when filtered by property each
    buyer carries its per-property **interest_stage** (`get_buyers` returns it from
    the `CRM Lead Buyer` row when `property` is set). The property-filtered /buyers
    list swaps its "Active in" column for a **Status** column (colored dot + stage).
    `BulkTextModal` gained a **"Statuses to text"** chip row (shown whenever any
    recipient carries a `stage` — i.e. the Dispo "Text buyers" and the
    property-filtered "Text these"): one toggle chip per present stage (with a
    count), and the recipient checklist + selection are scoped to the active
    stages. **"Not Interested" is OFF by default** (`EXCLUDE_BY_DEFAULT`) so a
    blast can't accidentally hit uninterested buyers; toggling a chip re-syncs the
    selection to the now-visible set. Each checklist/review row also shows the
    buyer's stage. Recipients get `stage` from `get_deal_buyers.interest_stage`
    (Dispo) / `get_buyers.interest_stage` (property-filtered Buyers). Stage colors
    (blue/orange/red/green/purple) live in JS in both `BulkTextModal.vue` and
    `pages/Buyers.vue`. gw191: the **"Text these (N)"** button label now reflects
    the **post-failsafe** count (`textTheseCount` — phone-present and not in
    `EXCLUDE_BY_DEFAULT`), previewing what will actually be pre-selected (e.g.
    "Text these (53)" for a 58-buyer property with 5 Not Interested); the header
    "N buyers" still shows the true filtered total.
- **Filters: user pickers, no phantom queries, and a 10x faster kanban**
  (gw222/gw223) — Lance: "filters aren't really working… assigned to isn't
  working really… adding filters in the gui is pretty laggy." Three distinct
  causes, all in the list/kanban filter path.
  - **`getValueControl` checked the operator before the fieldtype.** The
    `like`/`not like`/`in`/`not in` branch sat above every fieldtype branch and
    returned a bare `FormControl type=text`, so the perfectly good `Link`
    dropdown one branch below was unreachable. Worse, `getDefaultOperator`
    returned `like` for Link too — so **every** Link field (Lead Owner, Created
    By…) and **Assigned To** opened as an empty text box. `_assign` stores
    `["dennis.szafran@groundworkpro.com"]`, so the only thing that ever matched
    was a substring of the login *email*: typing "Dennis Szafran" returned
    nothing, which is exactly what "isn't working" meant.
    Now `_assign` and any **Link → User** field render
    `Controls/UserFilterSelect.vue` — an Autocomplete over the already-loaded
    users store (`full_name` label, email as the sub-line, **zero network
    calls**). It owns the `%email%` wrap/strip, so it emits a ready-to-store
    value and Filter.vue's blanket `@change` handles it unchanged
    (`inheritAttrs: false` keeps the template's `v-model`/`placeholder` off the
    inner Autocomplete). `getDefaultOperator` now returns `equals` for
    Link/Dynamic Link so the dropdown is the default; `like` is still selectable.
  - **Picking a field immediately ran a query — with no value.** `setfilter`
    called `apply()` straight away, so an empty `like` became `%%`, and since
    `NULL LIKE '%%'` is NULL, merely *naming* a field silently dropped every
    record with nothing in it (adding "Assigned To" hid all unassigned leads —
    prod's saved kanban view was sitting in exactly that state). `filters` was
    also a **computed whose Set got mutated**, so a row could only persist if the
    server echoed it back. It's now a `ref` synced from a separate
    `appliedFilters` computed, which keeps valueless rows as client-only
    **drafts**: they show in the popover, never reach the server, and cost no
    round-trip. `hasValue()` gates `apply()`/`setfilter`/`removeFilter`/
    `updateOperator`. Also guarded `updateValue` against the `null` a cleared
    DatePicker emits (`value.target` threw) and `transformIn` against non-strings.
  - **Every filter change fetched the board twice.** `updateFilter` →
    `list.reload()` **and** `createOrUpdateStandardView()` → `reloadView()` →
    the `getView` deep watcher → `reload()` again, identical result. The view
    write is now debounced 600ms (`persistStandardView`) and the watcher skips
    the echo of our own write via `skipNextViewReload`, released on a
    `setTimeout(…, 0)` after `reloadView()` — a macrotask, so it lands after the
    microtask watcher flush. (Comparing `getParams()` to `list.params` does NOT
    work: the response's resolved `columns`/`rows` differ from the view's.)
  - **The real lag was `getCounts`: ~18 queries PER CARD.** A 104-card leads
    kanban = ~2,600 round-trips and `get_data` took **2.6s** (the list view,
    which skips it, takes 83ms). Replaced with `apply_counts(rows, doctype)` —
    one grouped query per source (`_count_by_doc`/`_max_by_doc` via `frappe.qb`,
    with a `split_field` for the direction splits), plus one `CRM Lead` fetch for
    `_first_call`/`_new_lead_color` and `istl_refund_report.prefetch_outbound_calls`
    for the ISTL tint (`refund_card_color` gained an optional `calls=` param).
    Called once over every card on the board, after the column loop. `getCounts`
    remains as a single-record wrapper. **Verified on prod against the old
    per-card code: 0 mismatches on 150 and 400 leads, 51x and 114x faster;**
    kanban `get_data` 2624ms → 253ms live.
  - Net: one filter interaction went from 2 kanban fetches (~5s) to one ~250ms
    fetch, and adding a filter field costs nothing until you fill it in.
  - `frontend/src/components/Controls/UserFilterSelect.vue` (**new**),
    `components/Filter.vue`, `components/ViewControls.vue`, `crm/api/doc.py`,
    `crm/api/istl_refund_report.py`. No ops piece, no schema change.
  - **gw224/gw225 — an unmapped operator wedged the whole popover.** On the ISTL
    LeadPack view, setting any filter did nothing: the value changed, the badge
    counted it, the list never reloaded. `oppositeOperatorMap` is keyed on the
    UPPERCASE `LIKE` that the popover itself writes, but the per-import-list
    views are generated in `lead_import.py`, which wrote lowercase `like` — so
    `convertFilters` produced `operator: undefined`, and the next `apply()` threw
    on `f.operator.includes(...)`, killing the emit before it reached
    `updateFilter`. **This was the original "filters aren't really working — I
    noticed it on the ISTL import" report**; it survived gw222/gw223 because the
    standard views all store `LIKE`. Fixed three ways: `normalizeOperator()`
    resolves any case and never returns undefined; `transformIn`/`parseFilters`
    tolerate a missing operator; and `lead_import.py` now writes `LIKE`. A prod
    sweep normalized the 2 stored views and dropped a stale
    `_assign: ["LIKE","%%"]` sitting on a personal kanban (it had been hiding
    every unassigned lead on that board).
  - **gw229 — "Save as new" + Source quick filter dropped.** The only way to
    keep an ad-hoc filtered set was "Save Changes", which writes back over the
    view you opened (destructive on a shared/public one like the LeadPack), or
    the buried views-dropdown → Create View. A **Save as new** button now sits
    in the view-controls row: it snapshots the live params into a fresh
    `CRM View Settings` via the existing `ViewModal` in `create` mode, then
    navigates to it. Shown whenever `viewUpdated` OR any filter is active —
    the second half matters because on a *standard* view
    `createOrUpdateStandardView` flips `viewUpdated` back to false within a
    second, so a `viewUpdated`-only gate would flicker. Cancel/Save Changes keep
    their original stricter gate (saved view + not public-unless-manager).
    `saveAsNewView()` + `canSaveAsNew` in `ViewControls.vue`, both toolbars.
    Also dropped **`source`** from the Leads quick-filter row (`_hidden` in
    `get_quick_filters`) — the Filter popover covers it and the row was tight.
  - **Multi-select filters** (`Controls/MultiSelectFilter.vue`, **new**) — a
    compact summary button ("Dennis Szafran" / "2 selected" / "All (6)") opening
    a searchable checkbox list with Select all / Clear. Renders as a summary
    rather than chips because it has to fit the filter row beside two selects.
    Used whenever the operator is `in`/`not in` and the field can offer options:
    **users** (`_assign` + any Link→User, from the users store), **import lists**
    (`crm.api.lead_import.get_import_lists`, with per-list lead counts — nobody
    remembers a generated name like "ISTL LeadPack — Jun 2026"), and **Select**
    fields. `_assign`/`import_lists` now default to the `in` operator.
  - Backend `crm/api/doc.py` **`expand_json_list_filters`** — `_assign` and
    `import_lists` are JSON arrays in a Text column, so "any of these" is an OR
    of LIKEs, not a SQL IN. It resolves the OR to a concrete `name in [...]`
    once, up front, because the same dict filter is reused by the kanban's
    per-column queries, per-column counts and total count, none of which take
    `or_filters`. Per-field needle shapes (`%email%` vs `%"list name"%`) live in
    `JSON_LIST_FILTER_FIELDS`. `_constrain_names` **intersects** with an
    existing `name` filter rather than overwriting it, so it composes with the
    dashboard drill-down. **Must run AFTER `apply_import_visibility`**, which
    opts a query out of the parked-lead exclusion by looking for the very
    `import_lists` key this rewrites away. Verified on prod: single-value `in` ==
    the old LIKE (256), multi-value == the union of LIKEs (698), empty == 0,
    intersection with a 5-name drill == 5, `import_lists in [pack]` == 514.
- **Lead import hardening + address repair** (gw221) — the Jun 2026 LeadPack
  (514 leads) went in with the address block scrambled on part of the batch and
  the importer said nothing: **88 leads had the whole street address sitting in
  `property_zip`** with `property_address` empty, **31 had the seller's EMAIL in
  Property Address / Property City**, and **122 had 3-4 digit ZIPs** (MA/NJ/RI
  leading zero eaten by the spreadsheet). Pattern = the pasted sheet was a
  concatenation of vendor exports with different column layouts under one header
  row; the importer wrote every cell wherever the mapping pointed and reported
  "514 created, 0 errors".
  - **Repair** — `crm/api/lead_import.py` `repair_import_addresses(list_name,
    dry_run=1)` (bench-executable, whitelisted, idempotent). `_repair_one(doc)`
    is the pure per-lead rule: rescue an email out of an address field onto
    `email` (a second one goes to `lead_summary` as "Other contact:"), drop
    vendor placeholders ("Not Provided"), then treat a **complete address as
    authoritative wherever it turns up** — `FULL_ADDR_RE` (plus a `, USA` tail
    strip) re-seeds address/city/state/ZIP in one go — and finally zero-pad the
    ZIP. **Invariant: a value is only ever cleared if it has been written
    somewhere else, or is a placeholder.** `_looks_like_street` is deliberately
    strict (house-number-led or comma-bearing) because it gates lifting a value
    out of the City column, where a bare town name legitimately lives. Ran on
    prod 2026-07-28: 222 leads changed, 0 values dropped, re-run is a no-op.
  - **Same rule now runs at import time** — `import_leads` calls `_repair_one`
    on each built row, so the address lands right whichever column it arrived
    in. A correctly-shaped row passes through untouched.
  - **Pre-flight warnings in the map step** (`ImportLeadsModal.vue` `warnings`
    computed, amber block above the mapping table — warns, never blocks): rows
    whose cell count ≠ the header's (the classic whole-batch-one-column-over
    cause); two columns mapped to the same field (`buildRows` keeps only the
    last non-empty, silently); a column whose sampled values don't match the
    field it's mapped to (email/full-address/ZIP/phone shape vs `EXPECTED`); and
    columns that have data but no field selected. Verified live against a
    synthetic sheet — all four fire.
  - **Dead aliases fixed**: `sellermotivation`/`reasonforselling` and
    `howfasttheywanttosell` pointed at `property_reason_for_sell` /
    `property_duration_to_sell`, which are **not fields on CRM Lead** (the real
    ones have no `property_` prefix). `guessField` only accepts an alias the
    field list offers, so those columns were silently dropped on *every* import
    ever run — all 514 leads have `reason_for_sell`/`duration_to_sell` null.
  - Done-screen copy no longer claims leads auto-promote when status leaves
    "New" — promotion has been manual-only since gw215.
- **Parked import leads are hidden from the dashboard too** (gw221) — the Leads
  board hid a fresh batch (`import_hidden`) but `/dashboard` still counted it,
  so 2026-07-27 read **518 new leads instead of 4**, with the LeadPack owning
  the source donut and inventing a status cohort. `crm/api/leads_dashboard.py`
  gained `live(query, Lead)` (`import_hidden IS NULL OR != 1`, `has_column`
  guarded — NULL is visible, since a lead predating the field isn't parked),
  applied at all 15 CRM Lead query sites (summary, trend, status changes, cohort
  + flow tables, every drill-down resolver, and the call/text/agreement activity
  fetchers). `crm/api/dashboard.py` `get_leads_by_source` imports it **inside
  the function** — `leads_dashboard` already imports `dashboard` at module
  level, so a top-level import would cycle.
- **Buyer import (bulk + single)** — buyers only ever arrived on their own (the
  IL scraper + the address-request webhook); a bought cash-buyer list, a county
  LLC export or a REIA spreadsheet had no way in but the one-at-a-time modal.
  Mirrors the bulk **lead** importer (`crm/api/lead_import.py` +
  `ImportLeadsModal.vue`, gw211-215) closely enough that the two read the same.
  - **Bulk**: `crm/api/buyer_import.py` + `Modals/ImportBuyersModal.vue`, in the
    "…" menu on **/buyers** and as **Import buyers** on the **Dispo** board
    header (pre-seeded with the open board). Paste rows / upload a CSV → confirm
    the auto-guessed column mapping → optionally pick a **property** and the
    **reps** to split the batch between. 200-row chunks; `assign_offset` carries
    the round-robin rotation across chunks.
  - **Property picker** = leads in **Signed Contract, Photos & Lockbox In
    Progress, Needs Listing, Marketing to Buyer, Buyer Assigned**
    (`PROPERTY_STATUSES`; confirmed with Lance — "Contract Sent" isn't ours yet,
    "Won" is done). Each buyer gets a `CRM Lead Buyer` row at the chosen stage;
    one `crm_il_buyers` emit for the whole batch, not one per buyer.
  - **Assignment = ownership** (Lance's call, over per-buyer call tasks): a
    Frappe `_assign` ToDo on the CRM Buyer. A buyer someone already owns is
    never re-assigned, and the rotation only advances on an assignment that
    actually happened, so the reps who do get buyers get an even split.
  - **Dedupe** = email → last-10 phone → name (the `_find_buyer` rule), but built
    as ONE index up front — `_find_buyer` re-queries per lookup, which would
    scan the whole buyer table once per row. A matched buyer is attached and
    assigned but **never overwritten**: blank fields get filled in, curated
    values stay. Re-import is therefore idempotent (verified on prod).
  - Metro columns are **matched** against the Census list, never created;
    unrecognised ones are reported back. Junk emails (alt numbers, "n/a") are
    dropped rather than failing an otherwise good row.
  - **Single**: `Modals/BuyerModal.vue` gained the same **Add to property +
    Board stage + Assign to** row on create (skipped via `:with-property="false"`
    from `AddBuyerToDealModal`, which attaches the buyer itself). If the buyer
    already exists, the duplicate banner now also offers **Add to property**.
  - **A dispo board no longer requires an `il_property_id`** (gw220). That was
    never the right gate — a deal needs a buyer board the moment it's ours, and
    most of ours are never posted to IL (three of the eight properties under
    contract had no board at all). `get_dispo_properties` now lists a lead if
    ANY of: its status is in **`DISPO_LEAD_STATUSES`** (the same five statuses
    the importer's picker uses) · it already has buyers on its board (so a board
    + its history survives the status moving on to Won/Dead) · it's IL-linked
    (the old rule, kept). The status tuple lives in
    `investorlift_ingest.DISPO_LEAD_STATUSES` and `buyer_import` imports it
    (the other direction would cycle), so picker and switcher can't drift.
  - **Buyer import lists** (gw247/gw248) — every bulk import tags its batch
    with a **list name** on `CRM Buyer.import_lists` (JSON array, same shape +
    `_dump`/ensure_ascii rules as the lead-side field — helpers imported from
    `lead_import`), so /buyers can filter to "the REIA list from July" and feed
    exactly that set into "Text these (N)". The import modal's **List name**
    input is prefilled ("Buyer list — Jul 30, 2026"; a CSV upload swaps in the
    filename unless the user typed their own — note the ref must be initialized
    at setup, not just in the `watch(show)` reset, because /buyers mounts the
    modal with `v-if` so it mounts with `show` already true and the watcher
    never fires); clearing it skips tagging. Matched existing buyers get the
    tag too (membership, not provenance) via side-effect-free `db.set_value`.
    /buyers gains an **"All lists"** Autocomplete (hidden until a list exists;
    options `name (count)` from `get_buyer_import_lists`), seedable via
    `/buyers?list=…` — which the done-screen's "Open this list" button uses —
    and counted into `hasFilter` so the bulk-text button lights up.
    `crm/api/buyer_import.py` (`list_name` param + `_add_to_list` +
    `get_buyer_import_lists`), `crm/api/buyers.py` (`get_buyers(import_list=)`,
    quoted-JSON LIKE like metros), `ImportBuyersModal.vue`, `pages/Buyers.vue`.
    Ops: `scripts/setup_buyer_import_lists.py` (adds the Long Text field; all
    app code has_field/has_column-guarded).
  - **Gotcha (bit the lead importer too, silently)**: `usersStore()` is a Pinia
    *setup* store, so `store.allUsers` is the UNWRAPPED array and
    `const { allUsers } = usersStore()` hands back a stale snapshot; `users` is
    the resource whose `.data` is `{allUsers, crmUsers}`, not an array. Both
    spellings render an EMPTY rep-chip row — read `usersStoreRef.allUsers`
    inside the computed. Fixed in `ImportLeadsModal.vue` as well.
  - No ops script: every field written already exists.
- **CRM-wide delete access + movable Dispo buyers + structured Buyer Buybox**
  (gw256) — every CRM sales role can delete primary records. Lead/Deal/
  Organization/Buyer permissions already allowed it; stock Contact did not, so
  ops `scripts/setup_crm_delete_permissions.py` explicitly enables delete for
  Sales User + Sales Manager (and repairs drift across Contact/CRM Lead/CRM Deal/
  CRM Organization/CRM Buyer/CRM Lead Buyer). Buyer detail now has its missing
  trash action and uses the standard linked-document delete/unlink modal.
  - Dispo cards are real cross-column `vuedraggable` items; dropping calls
    `crm.api.buyers.move_buyer_stage`, persists `CRM Lead Buyer.interest_stage`,
    and publishes the existing `crm_il_buyers` realtime event after commit.
    Every card also has an accessible **Move buyer** menu (same endpoint) for
    touch/keyboard use and as a precise alternative to drag.
  - CRM Buyer gained JSON-list `buybox_cities` (**Buying In**; legacy field
    name, now stores city/state markets, whole states, and ZIP codes) and
    `buybox_property_types` fields. Both render as searchable, create-any-value
    chip pickers in the Buyer edit modal and inline sidebar; location
    suggestions come from distinct CRM Lead cities, states, and ZIPs. Existing
    `buybox` is the free-form notes layer (price/condition/deal-size/etc.). The
    shared Autocomplete footer now reads its reactive query and clears it on
    close; the prior private-DOM `_value` lag could save `554012`, and reopening
    after adding `MN` concatenated the next entry into `MN55401`.
  - Buyer detail now mounts the standard globally-configurable
    `SidePanelLayout`: default sections are **Buybox** and **Buyer Details**;
    managers use the section pencil → Edit Field Layout to add/reorder/remove
    any CRM Buyer field. Ops `scripts/setup_buyer_directory.py` adds the two
    fields and seeds `CRM Buyer-Side Panel` once without overwriting later
    manager customization.
  - App: `crm/api/buyers.py`, `crm/api/investorlift_ingest.py`,
    `frontend/src/components/Activities/DispoBoard.vue`, `BuyerDetailPanel.vue`,
    `Controls/JsonListControl.vue`, `Modals/BuyerModal.vue`,
    `SidePanelLayout.vue`, `pages/Buyer.vue`. Ops: the two setup scripts above.
  - **IL webhook duplicate-buyer race (gw257)** — "a new Abdul appeared when I
    dragged him" was NOT the drag: OpenPhone delivers the same InvestorLift
    notification text once per Quo line it reaches, so `on_sequence_event` →
    `_handle_address_request` ran twice ~0.2s apart, both passed `_find_buyer`
    pre-commit, and both inserted (Abdul BUY-00425/426 and Shelton
    BUY-00409/410 were each created 0.2s/0.016s apart, owner=Guest). The two
    stacked duplicates only became visible when one was dragged into another
    column. Fixed with a MySQL `GET_LOCK` named lock keyed on the buyer name
    around the find+insert, plus a `frappe.db.commit()` right after acquiring
    it — REPEATABLE READ otherwise keeps the waiter's `_find_buyer` blind to
    the row the parallel handler committed. Shell duplicates were raw-deleted
    (`frappe.db.delete`, deliberately skipping `on_buyer_trash`: each shell
    SHARED the keeper's `quo_contact_id`, and the trash hook tombstones the
    contact — even with the id cleared it falls back to an externalId lookup),
    then the keepers re-pushed so the Quo contact's externalId points at the
    survivor.
- **Dispo Not Interested reasons** — moving a buyer card into **Not Interested**
  (drag or the accessible Move buyer menu) pauses the move and opens an IL-style
  multi-select: Pricing / Not buying in this location / Not currently in the
  market / Daisy chainer / Does not buy deal type / Property condition / No
  longer buying / Other, plus an optional note. Cancel reloads the board so a
  dragged card snaps back; Submit saves the stage + reasons atomically through
  `move_buyer_stage`. Reasons live on the per-property `CRM Lead Buyer`
  relationship (never on global `CRM Buyer`), are editable from the card/menu,
  and clear when the buyer leaves Not Interested so a later IL-origin stage move
  cannot surface stale CRM reasons. Orange reason symbols render on board/list
  cards; the Not Interested column header aggregates labeled counts per reason
  for that property (legacy rows with no selection count as Unspecified). The
  modal renders all eight choices without an internal scroller — the app's
  hidden-scrollbar styling made the bottom choices look absent in the first live
  verification. Reuses `crm_il_buyers` realtime. App:
  `crm/api/buyers.py`, `crm/api/investorlift_ingest.py`,
  `frontend/src/components/Activities/DispoBoard.vue`,
  `BuyerRejectionReasonBadge.vue`, `Modals/BuyerRejectionReasonModal.vue`, and
  `utils/buyerRejectionReasons.js`. Ops:
  `scripts/setup_buyer_rejection_reasons.py` adds JSON reasons / note / by / at
  fields; `setup_investorlift.py` includes them for fresh sites.
- **Lead property photos → shared Google Drive** — a **Photos** sidebar card +
  **Photos** item in the Lead header More ▾ menu open a gallery modal: drag-drop
  or pick multiple files, scroll a thumbnail grid, click through them in the
  existing `ImageLightbox`, **Download all** as one zip, or **Copy folder link**
  to hand to a listing agent. Photos live in Drive ONLY (nothing mirrored into
  Frappe's File table).
  - **Folder** = one per lead, named after the full property address (composed by
    `agreement._full_property_address`, so a street-only manual lead still gets a
    fully-qualified name), created inside **`Wholesaling > Info & Photos`**
    (`INFO_PHOTOS_FOLDER_ID`, config-overridable via `lead_photos_folder_id`) —
    directly, NOT in that folder's legacy `Photos` subfolder (Lance's call). On
    creation it gets `type=anyone, role=reader` so the link works with no Google
    login; files inherit it, so sharing is set exactly once.
  - **Adoption matches folders only.** `Info & Photos` also holds loose
    "… Property Info" Google Docs whose names contain the same addresses, so
    `_find_existing_folder` filters `mimeType=folder` and compares a normalized
    name (case/punctuation-insensitive, trailing "Photos" dropped — the folders
    already there are inconsistent about that suffix).
  - **No new Google grant was needed** — the existing `crm-underwriting@` SA is
    already a full member of the Wholesaling drive (see the Underwriting entry).
    `photos.py` reuses `underwriting._google_access_token` rather than repeating
    the JWT dance.
  - **Uploads are one HTTP request per file** (resumable Drive upload: metadata
    POST → session URI → PUT bytes). A 40-photo phone batch is hundreds of MB and
    a single giant POST is exactly what trips nginx's body limit and loses the
    whole batch instead of 39-of-40.
  - **Download-all zips server-side** because Drive has no zip-a-folder API and
    its web-UI download needs a Google session — the thing link-sharing exists to
    avoid. Capped at `MAX_ZIP_BYTES` (400 MB), over which the user is pointed at
    the Drive link. Duplicate filenames (legal in Drive, not in a zip) are
    de-duped.
  - Thumbnails render via `drive.google.com/thumbnail?id=…&sz=w400` (works
    unauthenticated precisely because of the link share); Drive's own
    `thumbnailLink` is short-lived and referrer-blocked. Videos show a play tile
    that opens Drive rather than trying to stream inline.
  - `crm/api/photos.py` (**new**: `get_lead_photos` / `ensure_photo_folder` /
    `upload_lead_photo` / `delete_lead_photo` / `download_all_photos`; realtime
    `crm_photos`, site-wide + `after_commit`), `frontend/src/components/PhotosCard.vue`
    (**new**), `frontend/src/components/Modals/PhotoGalleryModal.vue` (**new**),
    `frontend/src/pages/Lead.vue` (card + More-menu item + modal mount — mounted
    directly rather than threaded through the AllModals→Activities expose chain,
    since nothing else opens it). Deletes are `trashed=true` (recoverable), and
    only for files actually parented by that lead's folder.
  - **GOTCHA — `pages/MobileLead.vue` is a SEPARATE page**, not a responsive
    variant of `Lead.vue`: below 768px the router renders it instead, and it
    re-declares its own copy of the sidebar cards (First-Call Read / Tax Info /
    Agreements / Underwriting / InvestorLift) plus its own `AllModals` host
    (`detailModals`, since mobile tabs are mutually exclusive so `Activities`
    isn't always mounted). Adding a card to `Lead.vue` alone makes it **invisible
    on every phone** — which is exactly what shipped in gw245 and Lance caught.
    Any new sidebar card must be added in BOTH files. Note also that the header
    action row on mobile renders only Call + Text — there is no `More ▾` menu, so
    a More-menu entry is not a mobile-reachable entry point on its own.
    Mobile reaches the sidebar through a **Details** tab (first tab).
  - **Verifying phone layouts through the pi-chrome extension**: the extension
    pins the automation tab's viewport at desktop width, but
    `window.open(url, 'name', 'popup=yes,width=390,height=844')` gives a genuine
    390px viewport that `chrome_screenshot({targetId})` can capture — how the
    mobile gap above was found and the fix confirmed.
  - Ops (`../frappe-crm-deploy`): `scripts/setup_lead_photos.py` adds the CRM Lead
    `photo_folder_id` / `photo_folder_url` cache fields. They are a CACHE, not the
    source of truth — everything is `has_field`-guarded and falls back to
    resolving by address, so the feature works before the script runs; what they
    buy is that a later address edit doesn't orphan the folder.

- **DD Expiration date** (Leads) — `dd_expiration_date` (Date custom field)
  shown as a calendar-icon row in the Lead sidebar HEADER directly under the
  Acq Price row (same minimal no-label formatting): displays
  "7/16/26 (2 days left)" — a day-granular countdown, red once past / amber on
  the day (shared `ddExpiration()` helper in `frontend/src/utils/index.js`,
  reuses `dueColor`). Click opens the native date picker (hidden
  `<input type="date">` + `showPicker()`), hover ✕ clears. Also renderable as
  a **Leads Kanban card field** (selectable in KanbanSettings automatically
  since it's a real column; `dd_expiration_date` branches in `pages/Leads.vue`
  template + `parseRows` render the same countdown + color). Deliberately NOT
  in the side-panel Dispo section. `pages/Lead.vue` + `pages/Leads.vue` +
  `utils/index.js`; ops: field added via `setup_dispo_fields.py`.
- **Showing Access line** (Leads) — `showing_access` (Small Text custom field)
  rendered as a key-icon row in the Lead sidebar header directly under the DD
  expiration row: free-text access instructions ("vacant", "lockbox 4127, dogs
  in yard", …) in a borderless auto-growing textarea that wraps; Enter/blur
  saves, Esc reverts. Deliberately NOT in the side-panel Dispo section.
  `pages/Lead.vue` + `pages/MobileLead.vue`; ops: field added via
  `setup_dispo_fields.py`. Requested by Lance (Mattermost 2026-07-31).
- **Documenso "Create Purchase Agreement"** (Leads) — a header action (in the
  decluttered "More" menu next to the name) that spins up a pre-filled, editable
  Documenso e-sign draft of the wholesale purchase agreement and hands back a
  self-serve buyer signing link. A modal picks the agreement type (Standard vs
  Novation/+AIF vs Amendment) and seller count; two sellers reveals a Seller 2
  name/email (one seller drops the Seller 2 fields). Mirrors the BatchData
  Fetch-Tax-Info wiring. (E-sign moved Documenso → **DocuSeal Cloud Pro** 2026-06:
  backend is now app code `crm/api/agreement.py` `create_docuseal_agreement`,
  templates resolved by NAME, newest id wins — see the `docuseal-migration-project`
  memory.) The resolver considers ONLY the DocuSeal **"Purchase Agreements"
  folder** (`TEMPLATE_FOLDER`) — the team builds one-off templates in the UI for
  specific deals (they land in Default, with default First Party/Second Party
  roles) and a one-off named "Amendment 17199 Hamburg Detroit" once won the
  newest-name match and 422'd every CRM amendment (gw152). Keep canonical
  templates in that folder and deal one-offs out of it. Prefill "Property
  Address" is composed by `_full_property_address()` — street + city + state +
  zip, each component appended only if not already inside `property_address`
  (webhook leads carry the full string; manually-entered leads are street-only
  with separate city/state/zip fields, which used to put just "123 Main St" on
  agreements).
  - **Amendment type (2026-07-14)** — "Amendment (price / closing date)" in the
    type dropdown creates an Amendment-to-PSA envelope from the DocuSeal
    templates `Amendment - One Seller` / `- Two Sellers` (ids 4996712/4996713,
    built from Lance's Desktop DOCX via `POST /templates/docx` UNTAGGED + field
    areas computed from the rendered PDF's underscore blanks and `PUT` back —
    text-tags reflowed the layout, don't use them; area `page` is 0-indexed on
    write despite the QUIRKS note). GOTCHA (bit us again): the freshly-built
    templates 500'd on ANY `values` prefill — the known DocuSeal glitch; the fix
    is CLONE the template (clone regenerates fields cleanly, accepts values) and
    archive the original, hence the final ids. Buyer role prefills only
    `Seller Name(s)` + `Property Address`; Binding Agreement Date, amended price
    and amended closing date are left for the buyer on the signing page. Seller
    name fields (`Seller Name` / `Seller 1 Name` / `Seller 2 Name`) match the
    existing `_seller_values` superset so seller prefill just works.
    `crm/api/agreement.py` (`want_amendment` + resolver branch) +
    `CreateAgreementModal.vue` (third type option).
  - **Cancellation type (2026-07-15)** — "Cancellation / release of earnest
    money" in the type dropdown creates a Cancellation-of-Contract + Release-of-EMD
    envelope from DocuSeal templates `Cancellation - One Seller` /
    `- Two Sellers` (ids 5014844/5014850, built via `POST /templates/pdf` from
    Lance's Desktop "Cancellation of Contract - Release of EMD.pdf" UNTAGGED +
    `PUT` fields at coordinates computed from the PDF's rule lines with PyMuPDF;
    cloned + originals archived per the values-prefill-500 gotcha). Buyer role
    prefills only `Seller Name(s)` + `Property Address`; contract date, buyer
    name(s), escrow agent, EM amount and the 4 disbursement rows are buyer-filled
    on the signing page. Each signer has ONE signature + date field with areas in
    BOTH sections (Cancellation block + Release block) — sign once, lands on
    both. PDF quirk: disbursement rows 2-4 exist in the form's text layer but
    render invisibly — filled values still print there, just without visible
    $/to/Address labels (row 1 is the normal case).
    `crm/api/agreement.py` (`want_cancellation` + resolver branch) +
    `CreateAgreementModal.vue` (fourth type option).
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
  - **"Download signed PDF" once completed** — when an agreement is fully signed
    (Documenso status `COMPLETED`, or `signed_count >= total_signers` — some rows
    never flip to COMPLETED in the webhook but reach 2/2), a green **Download
    signed PDF** link shows in the sidebar card AND the Activity-timeline entry,
    streaming the signed PDF. **Backend proxy** because Documenso's `download-beta`
    returns an internal, expiring MinIO presigned URL (`http://minio:9000/…`) a
    browser can't reach: `crm/api/agreement.py` `download_signed_agreement(agreement)`
    (whitelisted, GET) permission-checks via the lead, then `requests.get` the
    Documenso `/api/v2/document/{document_id}/download?version=signed` with the API
    token and sets `frappe.local.response` (`type="download"`, `filecontent`,
    `filename=<template>_signed.pdf`). `get_agreements` now returns an `is_signed`
    flag (`_is_completed`) the UI gates the link on. **Token is in site_config**
    `documenso_api_token` (set via `bench set-config`, mirrors the underwriting
    `google_sa_json` pattern — app code can't read the server-scripts'
    `__INFISICAL:…__` placeholder). `frontend/src/components/AgreementsCard.vue` +
    `Activities/Activities.vue` (both build `/api/method/…download_signed_agreement?agreement=<name>`).
  - **Adopting hand-built DocuSeal envelopes** — the team builds one-off templates
    directly in the DocuSeal UI (deal-specific novations / amendments / AIFs) and
    sends them by SMS. Those envelopes had no `CRM Esign Agreement` row, so
    `docuseal_webhook` looked up `document_id`, found nothing and returned early —
    a contract could be **fully signed with no trace on the lead** (that's how the
    6787 N 200 E / Zurek purchase agreement went missing). DocuSeal webhooks are
    **account-wide**, so the events already reached us; we were just dropping them.
    `crm/api/agreement_adopt.py` (**new**) adds the missing branch: on an unknown
    submission it matches back to a lead by **phone** (last-10, format-insensitive —
    the primary key, since texted links mean every party has `email: None`), then
    **email**, using **address** (street number + words, from the template name /
    "Property Address" field) ONLY to break a multi-lead tie, never to link on its
    own. Internal parties (our own users by login email, `custom_quo_number`, or
    the site-config `docuseal_internal_numbers` list) are excluded first, or the
    rep who signs every envelope would match whichever lead holds their number.
    Anything not resolving to exactly one lead is **never guessed**: `_alert_unmatched`
    emails/texts Lance once per submission with the `attach_submission` command to
    link it by hand (`CRM Esign Agreement.lead` is `reqd`, so a row can't exist
    without a confident match). Adopted rows are stamped `source=adopted` +
    `match_basis` and re-owned to the lead owner. `backfill_adoptions(dry_run=1)`
    sweeps all history (`docuseal_adopt_since`, default 2026-07-01, skips the
    account's throwaway test envelopes). 5 rows adopted on prod so far.
  - **Archiving is now soft** — `archive_agreement` sets `is_archived` instead of
    `frappe.delete_doc`: deleting lost the record entirely (one click could vaporize
    a signed contract) and, with adoption live, a later webhook event would just
    recreate the row it removed. The flagged row is both recoverable and a
    tombstone. Reads filter it out via a shared `_live_filter()`; `_agreement_fields()`
    centralizes the `has_column` guards (`provider`/`source`/`match_basis`) so an
    unmigrated site still works. `AgreementsCard.vue` shows an amber **"Auto-linked
    from DocuSeal"** badge (match evidence in the `title` tooltip) so an adopted
    envelope is never mistaken for one the CRM sent, and the archive confirm now
    says the record is kept.
  - Ops (`../frappe-crm-deploy`): `scripts/setup_agreement.py` adds `source`
    (Select `crm\nadopted`), `match_basis` (Small Text) and `is_archived` (Check)
    via `ensure_field` (idempotent). All three are live on prod.
- **Signed contracts parse themselves into the lead (pi on the Mac mini)** — when
  a DocuSeal envelope goes fully signed, `docuseal_webhook` POSTs a trigger to a
  listener on the Mac mini; it fetches the signed PDF back out of the CRM, reads
  it with a one-shot `pi`, and writes `acq_price` / `dd_expiration_date` /
  `closing_date` (+ the property address if the contract corrects it) onto the
  lead. Push, not polling — the mini never sleeps (`pmset`: `sleep 0`,
  `autorestart 1`), so a startup catch-up is enough of a backstop.
  - **Transport = Tailscale Funnel**, `https://lances-mac-mini.tailc8c60d.ts.net:8443`
    → `127.0.0.1:7474`. Prod is NOT on the tailnet and doesn't need to be. Note
    the pre-existing `:8444` Serve (→ `:7373`) is tailnet-only and is NOT a
    Funnel-eligible port; this tailnet allows Funnel on **443, 8443, 10000**.
  - **The push carries an ID, not a payload.** The URL is public, so nothing
    from the request may reach the model — the listener reads one agreement id
    and re-fetches everything authoritative from the CRM with its own token. A
    forged trigger (needs the shared secret; wrong/absent → 403) can at worst
    re-read a real agreement.
  - **`pi` runs with every tool disabled** (`-xt bash,read,write,edit,ask_question`).
    Contract text is semi-untrusted input going into a prompt on a machine with a
    shell; with no tools the run is a pure text completion and the CRM write is
    done afterwards by the script, through a validating endpoint. GOTCHA: pi
    emits an OSC escape (`ESC ]9;Pi`) around stdout even when piped — strip
    escapes before parsing JSON.
  - **Writes go through `doc.save()`, not `db.set_value`** — deliberately the
    opposite of the tax-pull/first-call pattern. The Version row is the point:
    it renders as "changed Acq Price from … to …" on the activity timeline,
    which is the entire audit trail here. Attribution is whichever user's API
    key the mini holds (currently Administrator).
  - **GOTCHA — the catch-up sweep is an outage bridge, NOT an importer.** It
    first shipped at 30 days keyed on `creation`; on install that swept every
    signed contract in history and began rewriting live leads (14 queued before
    it was stopped — it got through one cancellation, which correctly wrote
    nothing). Now 2 days, keyed on **`last_event_at`** (a contract sent last
    week and signed during an outage must still be caught, so `creation` was
    the wrong clock). Backfill is opt-in via a larger `days`.
  - **GOTCHA — business-day arithmetic.** DD periods are usually "N business
    days from the effective date", and holiday handling silently moves the
    deadline a day (Labor Day did exactly this in testing). The convention is
    now pinned in the prompt (weekends **and** US federal holidays excluded;
    effective date = last signature = day 0) and the model returns a `_basis`
    explaining each date, stored in `parse_result`.
  - **Cancellations are deliberately not parsed** — the prompt returns `{}` for
    them. Clearing real fields on an LLM read of a cancellation is the one
    failure here that loses data instead of just being wrong. Verified live.
  - **GOTCHA — backfilling: preview first, and mind ASSIGNMENT documents.** An
    Assignment Agreement's price is what the BUYER pays US, not our acq price;
    on the Phoenix deal a backfill would have overwritten `acq_price`
    **180,000 → 190,000** (the assignment spread) on an active Buyer-Assigned
    lead. AIFs/POAs and novations correctly return `{}`. Also, a lead often has
    SEVERAL agreements (purchase → amendment → novation → AIF): submit oldest
    first so later terms win, or a superseded original clobbers the amended
    price. The 2026-08-01 backfill of dispo-active deals therefore ran as
    preview → human review → apply-exact-reviewed-values (no second inference),
    under a **fill-blanks-never-overwrite** rule; 7 fields across 5 leads, 4
    agreements held back because the document disagreed with the CRM (two were
    simply superseded originals the CRM already reflected).
  - `crm/api/contract_parse.py` (**new**: `PARSE_FIELDS` — the single source of
    truth, shipped to the mini on each fetch so adding a field needs no redeploy
    there — plus `notify_mini` / `get_agreement_for_parse` /
    `list_unparsed_agreements` / `write_agreement_fields` / `mark_parse_failed`)
    + the trigger call in `agreement.py::docuseal_webhook`.
  - Ops (`../frappe-crm-deploy`): `mini/contract-parser/` (listener + plist +
    README), `setup_agreement.py` gains `parsed_at` / `parse_status` /
    `parse_result` (`parsed_at` = the idempotency key, so a re-delivered webhook
    can't clobber a human's correction; an amendment is its own row and so
    correctly overwrites). site_config: `contract_parser_url` +
    `contract_parser_secret` — absent, `notify_mini` is a no-op and the feature
    lies dormant.
- **First-Call Read (2x2 lead qualification)** — after the first call a rep marks
  two yes/no reads that place the lead in a 2x2: **Motivated?** (is the seller
  motivated) x **On price?** (is their price realistic) → Motivated·On price /
  Motivated·Off price / Not motivated·On price / Not motivated·Off price; blank on
  either axis = "Not qualified yet". Drives the team to answer it on every initial
  call. Three-state (unset/Yes/No) so "not asked" is distinct from "No".
  - **Lead-page sidebar card** (top of the sidebar, above Tax Info): plain-English
    questions with big Yes/No buttons (green Yes / red No), a mini 2x2 grid that
    lights up the cell the lead lands in, and a color-coded guidance band (per-
    quadrant next-action sentence) + "Set by X · date" stamp. Tap the active
    choice again to clear it.
    `frontend/src/components/FirstCallReadCard.vue` (new), mounted in
    `pages/Lead.vue` before `<TaxInfoCard>` (`@saved="document.reload()"`).
  - **Kanban quadrant chip** (Leads) — a subtle themed Badge on each card (green/
    orange/blue/red) showing the quadrant label, only when BOTH axes are answered.
    Server pseudo-field `_first_call` ("motivated|on_price", e.g. "Yes|No") computed
    in `crm/api/doc.py` getCounts (guarded by `has_column`, CRM Lead only; excluded
    from the DB `rows` SELECT like `_next_task_due`); added to default
    `kanban_fields` in `crm_lead.py`; selectable in `Kanban/KanbanSettings.vue`;
    rendered in the `#fields` slot of `pages/Leads.vue` (`parseRows` → label/theme
    via the shared `firstCallRead()` helper in `utils/index.js`). Realtime
    `crm_first_call` (site-wide, after_commit) → `reloadKanban()` on the same
    on-board guard as `crm_task_update`. (Deals not wired — same backend extends.)
  - **Backend = app code** (not a server script): `crm/api/first_call.py`
    `set_first_call_read(lead, motivated, on_price)` — validates ''/Yes/No, writes
    all four fields via `db.set_value` (no full doc.save → no status/assign side-
    effects), stamps `first_call_by`/`first_call_at` server-side, publishes
    `crm_first_call`.
  - Ops (`../frappe-crm-deploy`): `scripts/setup_first_call_read.py` adds the four
    CRM Lead custom fields (`first_call_motivated`/`first_call_on_price` Select
    `\nYes\nNo`; `first_call_by` Link User read_only; `first_call_at` Datetime
    read_only) — kept OUT of the side-panel layout (the card renders them). The
    chip was also added to the saved Leads kanban views (CRM View Settings rows 3
    + 4, after `_next_task_due`, `label:""`) so it shows without each user re-
    adding it.
- **Underwriting workbook (Google Sheets) "Create Underwriting Sheet"** (Leads) —
  a header **More ▾** action + sidebar **Underwriting** card that copies the
  underwriting template Google Sheet into the shared "Underwriting" Shared Drive
  folder, renames it to the lead's `property_address`, pre-fills the **ARV** tab
  (B4=today's date, B5=the clicking user's full name, B9=`zillow.com/homes/<addr>_rb/`),
  records a **CRM Underwriting Workbook** row, and surfaces the link in the sidebar
  card + Activity timeline so the team can open underwriting later. **One workbook
  per lead** — re-clicking just re-opens the existing sheet. Live refresh via the
  `crm_underwriting` realtime event (site-wide, `after_commit`). Mirrors the
  tax-info/agreement card+timeline+realtime pattern.
  - **Google call lives in APP CODE, not a server script** — a Frappe server-script
    sandbox can't sign the OAuth2 JWT to mint a Google token. `crm/api/underwriting.py`
    `create_underwriting_workbook(lead)` mints a token with **PyJWT (RS256) + a
    `requests` token POST** (no Google client libs — already in the Frappe env),
    does the Drive `files.copy` (supportsAllDrives) + Sheets `values:batchUpdate`,
    inserts the doctype row, returns the URL. `get_underwriting_workbooks(lead)` is
    the read API; `on_workbook_insert` hook mirrors the URL onto the lead
    (`underwriting_url`, has_field-guarded — field not required) + publishes
    `crm_underwriting`. `crm/hooks.py` — `CRM Underwriting Workbook` `after_insert`.
  - **Credentials**: a dedicated Google service account
    `crm-underwriting@claude-code-486305.iam.gserviceaccount.com` (key in
    `~/.config/gcloud/crm-underwriting-key.json`). It is **NOT** domain-wide
    delegated. **Its actual reach is much broader than this doc long claimed**
    (measured 2026-07-29): it is a full member of **8 shared drives** — Wholesaling,
    Creative Finance, Entitlement, Hiring, Lux, RDF, Swipe, Training — with
    `canAddChildren`/`canEdit`/`canShare`/`canDeleteChildren` all true on
    Wholesaling, not "Content Manager of only the Underwriting folder". The
    Underwriting folder simply sits at the root of the Wholesaling drive. That
    breadth is what let the lead-photos feature ship with no new grant; it is also
    worth remembering that this key lives in prod's site config, so a prod
    compromise reaches all 8 drives. It **acts as itself** (no `sub` claim): `_google_access_token()` omits `sub` when `google_workspace_subject`
    is "" (present-but-empty). The key + empty subject are read from site config
    (`google_sa_json` / `google_workspace_subject`), the `frappe.conf.get` route
    `live_demo.py` uses for `demo_password`. (Legacy: an absent
    `google_workspace_subject` falls back to DWD impersonating
    `lance.johnson@groundworkpro.com` — the original broad `workspace-admin` SA.)
    Template id + folder id are module constants in `underwriting.py`
    (config-overridable: `underwriting_folder_id`). Files created in the Shared
    Drive are owned by the drive, not the SA, so the SA's zero storage quota is a
    non-issue.
  - `frontend/src/components/UnderwritingCard.vue` (sidebar) +
    `Modals/CreateUnderwritingModal.vue` (confirm → progress → success/open link;
    auto-detects an existing sheet on open) + `Activities/AllModals.vue`
    (`createUnderwriting()` + expose) + `Activities/Activities.vue` (`underwriting`
    timeline type + `underwritingWorkbooks` resource + `crm_underwriting` listener +
    icon + **forwards `createUnderwriting` through its own `defineExpose`** — easy to
    miss; the card→page→Activities→AllModals chain needs every hop) + `pages/Lead.vue`
    (card mount + More-menu item, both guarded by `property_address`).
  - Ops (`../frappe-crm-deploy`): `scripts/setup_underwriting_workbook.py` creates
    the `CRM Underwriting Workbook` doctype (fields `lead`/`address`/`sheet_id`/
    `sheet_url`/`created_by_user`/`workbook_created_at`; sales-role perms; autoname
    hash). The SA JSON was delivered into the backend `site_config` via `bench
    set-config` (not a script in the repo).

- **Agreement activity notifications (text + email to the lead owner)** — when a
  DocuSeal agreement is **viewed / started / signed**, the **lead owner** is
  notified by text (from the dedicated "Notifications" Quo line **(952) 395-3833**,
  to their own Quo number `User.custom_quo_number` by default) and by email. Fires
  on **every** DocuSeal event (no dedupe — Lance's call). Each user controls it on
  a new **Settings → User Configuration → Notifications** page: Text/Email channel
  toggles, a "Text me at" number override, and per-event checkboxes (Viewed /
  Started / Signed). Opt-out (everything on by default).
  - **Trigger = the existing DocuSeal webhook**, not a doc hook: `crm/api/agreement.py`
    `docuseal_webhook` calls `crm.api.agreement_notify.notify_event(agr, event, data)`
    after saving each row (it has the exact `event_type` + submitter `data` there).
    Wrapped in try/except so a notify failure never breaks the webhook's 200.
  - `crm/api/agreement_notify.py` — **new**: `notify_event` maps
    `form.viewed`/`form.started`/`form.completed`/`submission.completed` →
    viewed/started/signed, resolves recipient = `CRM Lead.lead_owner` (fallback the
    agreement creator), reads prefs, and sends. **Text goes straight to the
    OpenPhone API** (`requests` to `/v1/messages`, key from site_config `quo_api_key`,
    from `notifications_quo_number` default `+19523953833`) — it does NOT go through
    the ops `send-text` script (that runs as the session user / role-gated; the
    webhook is Guest) and does NOT create a `Quo Message` row (it's a rep alert, not
    a lead-thread text). Email via `frappe.sendmail` + `crm_agreement_notification`
    template.
  - `crm/api/notification_prefs.py` — **new**: `set_notification_prefs` (session
    user's own JSON, mirrors `set_user_quick_comments`) + `DEFAULT_PREFS` + `get_prefs`.
    Stored on `User.custom_notification_prefs`; surfaced via `crm/api/session.py`
    `get_users`.
  - `frontend/src/components/Settings/NotificationsSettings.vue` (**new**) +
    registered in `Settings/Settings.vue` under User Configuration.
  - Ops (`../frappe-crm-deploy`): `scripts/setup_notification_prefs.py` adds the
    `User.custom_notification_prefs` Long Text field; **`bench set-config quo_api_key
    <Infisical QUO_API_KEY>`** on prod so app code can send the texts (the DocuSeal
    webhook already subscribes to all the needed events). Verified live end-to-end
    (gw123): viewing a seller link texted Lance "Notify Test viewed the Purchase
    Agreement…" from 3833.

The companion server-side pieces (custom doctypes, scheduler engine, webhook
endpoints) are Server Scripts managed from the ops repo, NOT app code here. SMS
specifically: the `Quo Message` doctype, the `send-text` and `list-quo-numbers`
API server scripts, and inbound text mirroring in the `sequence-events` webhook
all live in `../frappe-crm-deploy`.

## Testing & verification — local first (prod-backed dev)

The full local backend/database mirror was **removed (2026-06-19)**; there is no
`dev.sh`/`docker-compose.dev.yml`, and one should not be recreated. Frontend work
is nevertheless tested **before push/deploy** through the local Vite dev server,
which serves the local source while proxying authenticated API/realtime traffic
to prod. Production must never be the first place a UI change is exercised.

- **GOTCHA — `docker cp`ing a changed `.py` onto prod does NOT change what the
  WEB path serves.** The gunicorn workers already imported the module, so an
  HTTP request keeps running the old code even after the file is replaced and
  `__pycache__` is cleared. `bench execute` forks a fresh process and therefore
  picks the change up immediately — which makes this very easy to misdiagnose:
  the bench smoke test shows new fields while the browser shows stale data.
  `docker compose restart backend` (~seconds, same window as a deploy) is what
  actually reloads it. Cost a full failed verification round on 2026-08-05.
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
- **Compile gate — before push/deploy.** Run `cd frontend && yarn build`; it must
  succeed (there are no upstream frontend tests). Worktrees need their own
  `node_modules`; no sites config stub is required. The later in-image build is
  a second gate, not the first test.
- **Visual / UI verification — MANDATORY before push/deploy for any UI change.**
  Start the prod-backed local server with
  `cd frontend && CRM_DEV_TARGET=https://crm.groundworkpro.com yarn dev`, read
  the actual port from `frontend/.dev-port`, and call π's `verify_ui` against
  `http://localhost:<port>/crm`. If the relevant device target is not already
  known, call `verify_ui` without a target first and ask Lance which target
  matters. Exercise the changed behavior (click, type, unfold, save/reload where
  safe) and verify the resulting state; merely loading the page is insufficient.
  Complete this local verification before committing/pushing or running
  `build_image.sh`. The dev page uses the real production database, so avoid or
  roll back destructive test data.
- **After deploy** — run `smoke_test.py` and make only a focused production
  spot-check for deploy/cache/auth differences. This is confirmation, not the
  initial test pass; do not push a change merely to make it testable.

## Ship a change

Do not deploy in order to test. The order is local compile + local `verify_ui`,
then commit/push, then deploy and smoke-test:

```bash
# 1. Before commit/push/deploy (for frontend/UI work)
cd frontend && yarn build
CRM_DEV_TARGET=https://crm.groundworkpro.com yarn dev
# read .dev-port and run verify_ui against http://localhost:<port>/crm

# 2. After the local checks pass, commit and push this app repo
# 3. Pull the latest deploy repo, then deploy and smoke-test
cd ../../frappe-crm-deploy && git pull
./scripts/build_image.sh && python3 scripts/smoke_test.py
# commit and push the compose pin bump in ../frappe-crm-deploy
```

`build_image.sh` is the deploy step. It also takes `FORK=/path/to/worktree` to
build+deploy straight from a worktree without merging first. Frontend has no
tests upstream; the local `yarn build` and local `verify_ui` are the initial
gates, while the in-image build and `smoke_test.py` are post-push deployment
gates. Don't run `bench run-tests` against the prod site.

**Timings (measured, per-step timing prints as it runs).** Frontend change
~75s; backend-only change ~30s, because the Dockerfile copies `crm/` BELOW
`RUN yarn build` so Python edits hit the layer cache and skip the ~50s vite
build. **User-visible downtime is ~2.4s**, the backend container swap.

Rebuilt 2026-07-28 (was: 3m27s and minutes of downtime). Four things about it
are load-bearing and easy to undo by accident:

- **The image builds `FROM ghcr.io/frappe/crm:v1.67.0`, always.** It used to be
  `docker commit` of the live prod container, which stacked a ~32 MB layer per
  deploy and never removed anything — 256 layers / 14 GB by gw228, and
  `docker commit` *pauses* the container it snapshots. Never reintroduce
  commit-based layering.
- **Layer order.** `frontend/` above `yarn build`, `crm/` below it, and
  **`ARG GIT_REV` dead last** — BuildKit invalidates everything below an ARG
  whose value changed, and GIT_REV changes every commit, so declaring it at the
  top silently voids the cache on every deploy.
- **`emptyOutDir: false`** (`frontend/vite.config.js`) plus the shared
  `crm-assets` volume. Chunks are content-hashed and a one-line component edit
  re-hashes ~124 of 127, so wiping the output dir deleted the exact files open
  tabs were still lazily importing — they 404'd, the SPA threw, and users lost
  unsaved notes. Old chunks are pruned by mtime after 7 days instead.
- **Only `backend` goes in the deploy's critical window.** websocket and the
  workers are recreated after, and the frontend container isn't recreated at
  all (it serves assets from the shared volume), so it deliberately runs an
  older image tag than the rest of the stack.

### Fast loop for iterating on UI (HMR against prod)

```bash
cd frontend && CRM_DEV_TARGET=https://crm.groundworkpro.com yarn dev
# then open http://localhost:8080/crm and log in ONCE at localhost:8080
```

Vite dev server (~1.5s start, instant HMR) serving your local `frontend/src`,
with `/api|assets|files|private|login|app|desk` proxied to prod — so you get
real prod data without deploying. `changeOrigin` is required (Frappe resolves
the site from the Host header) and `cookieDomainRewrite` scopes prod's session
cookie to localhost, hence logging in through the dev server rather than
reusing your crm.groundworkpro.com tab. Unset the env var and everything
behaves exactly as before; production builds are unaffected.

**Logging in.** Use your password at `localhost:8080` — the cookie is then
scoped to localhost and persists. **"Login with Email Link" does not work here**
and fails in two ways: the button silently does nothing if the email field is
blank (nothing is queued, nothing is logged — and it is rate-limited to 5/hour),
and even when it does send, `send_login_link` builds the URL with `get_url()`,
which reads the request `Host`. `changeOrigin` has rewritten that to
crm.groundworkpro.com, so the emailed link points at PROD and logs you into
prod, not localhost. If you want the passwordless route anyway, request the
link then hand-edit the host to `http://localhost:8080/...` before opening it —
the key is validated server-side and the Set-Cookie comes back through the
proxy with the domain rewritten.

**Caveat: you are on the real production database** — anything you create, text
or delete is real.

**The `crm-dev-boot` plugin is load-bearing — don't trim it.** Production renders
`crm.html` through jinja and injects exactly three globals: `site_name`,
`csrf_token`, `sysdefaults`. The dev server renders `index.html` itself and gets
none of them, so the plugin re-creates two:

- **`sysdefaults`** (fetched live from System Settings). `stores/meta.js`,
  `utils/index.js` and `utils/numberFormat.js` dereference it WITHOUT optional
  chaining (`window.sysdefaults.currency`, `.date_format`, `.float_precision`),
  so its absence throws mid-render. Symptom was the Lead activity feed stuck on
  "Loading…" forever while every request returned 200 — the failure surfaces
  nowhere near its cause.
- **`site_name`** — the socket.io NAMESPACE. Without it realtime silently
  connects to `/undefined` and never receives an event.

`csrf_token` is deliberately not injected: token auth skips the CSRF check and
FilesUploader already guards on the global being present.

**Realtime works in dev**, verified end-to-end: a task created via the API from
outside the browser appeared in the DOM live, and disappeared again on delete.
It needs all three of the above plus `socketio: false` on the FrappeUI plugin,
so frappe-ui's own hardcoded `:9000` socket doesn't fight the app's.

Harmless leftover: one console error, `Unexpected token '<'`, from a call to
`frappe.onboarding.get_onboarding_status` made with a RELATIVE url — it resolves
against the current route, hits vite, and gets index.html back.

### Several agents / worktrees at once

```bash
CRM_DEV_TARGET=https://crm.groundworkpro.com yarn dev    # same command in every worktree
```

- **Ports are claimed automatically — agents need no coordination.** Each
  server takes the first free port in **8080-8099** and prints
  `[crm-dev] worktree "<dir>" (<branch>) -> http://localhost:<port>/crm`.
  Run the identical command in five worktrees and you get five servers. Set
  `CRM_DEV_PORT` only if you want a fixed one; it is then honoured strictly.
- **`strictPort: true` regardless.** Vite's default is to bump a busy port,
  which is the dangerous failure: you open 8080 and get a *different
  worktree's* bundle with nothing to indicate it — the same trap as the
  Electron apps. Now it fails with `Port 8080 is already in use`.
- **How an agent learns its own port** (never assume 8080):
  ```bash
  cat frontend/.dev-port                      # this worktree's port
  curl -s localhost:<port>/__crm_dev          # {dir, branch, path, port}
  ```
  For certainty rather than trust, match on the resolved root — two worktrees
  can share a basename, and a stale `.dev-port` outlives a crashed server:
  ```bash
  ROOT=$(git rev-parse --show-toplevel)
  for p in $(seq 8080 8099); do
    curl -s --max-time 1 localhost:$p/__crm_dev | grep -q "\"path\":\"$ROOT\"" && echo $p
  done
  ```
- **Every dev page carries a corner badge** (`<dir> · <branch> · :<port>`,
  bottom-right, `pointer-events:none`). Servers can no longer overlap; the
  badge is what stops *humans* overlapping — judging a change from the wrong
  worktree's tab is the realistic mistake once several are open.
- **Put worktrees OUTSIDE Dropbox** (`~/crm-worktrees/…`, not `.worktrees/`
  inside the repo). Each needs its own `node_modules`, and ~400 MB landing in a
  synced folder sends Dropbox + Spotlight to ~50% CPU each and load average past
  10 — it silently doubled build times mid-measurement.
- **`node_modules` per worktree is now mandatory**, not optional: the fork pins
  its own vite/plugin versions, so a worktree on an older commit genuinely needs
  a different tree. Don't symlink a shared one.
- **The `sites/common_site_config.json` stub is no longer needed.** Nothing
  imports it since socket.js stopped reading `socketio_port` — a worktree builds
  with no scaffolding at all.
- **Deploys serialise safely.** `build_image.sh` takes a machine-wide lock
  (`/tmp/frappe-crm-build.lock`), the next `gwN` is read from the SERVER's pin
  so two agents can't collide on a tag, and each build ships its OWN worktree
  via `git stash create`. The shared `crm-assets` volume is additive, so one
  agent's deploy never deletes another's chunks.
- The dev API token is shared (Infisical), so every agent's dev server acts as
  the same user. Fine on one laptop; worth remembering if a session looks like
  it is "someone else's" activity.
- **PUSH BEFORE YOU DEPLOY, PULL BEFORE YOU BUILD — this is the one that bites
  ACROSS MACHINES.** The serialisation above only protects agents on the *same*
  laptop; the lock, the tag counter and the assets volume say nothing about
  whether the tree you're shipping is current. `build_image.sh` ships the
  deployer's whole tree against a fixed base image, so a deploy from a stale
  checkout doesn't merge — it **replaces** prod's app code, silently deleting
  every feature committed since that checkout. Nothing warns you: the build
  succeeds, `smoke_test.py` passes (it only asserts prod matches *your* repo,
  which it now does), and the regression surfaces days later as "feature X
  stopped working".
  - **2026-07-31, the case in point.** gw256/gw257 (buyer drag, buyboxes,
    delete access, IL duplicate-buyer race fix) were committed on the MBP but
    never pushed. Next morning an agent on the **mini**, whose checkout was at
    `8b8ea82d` (six commits behind), deployed gw258 to ship Showing Access.
    Prod lost the drag, the buyboxes, the call classification badges, buyer
    import lists, lead photos AND the duplicate-buyer race fix. Recovered by
    merging both sides and redeploying as gw259.
  - **Diagnosing it takes one command** — the image records the tree it was
    built from, and `-dirty`/an old sha is the tell:
    `docker image inspect ghcr.io/frappe/crm:<tag> --format '{{json .Config.Labels}}'`
    → `org.opencontainers.image.revision`. Compare against `git log` before
    assuming the feature's own code broke.
  - So: `git push` the moment a feature is committed (an unpushed commit is
    invisible to the other machine and *will* be clobbered), and
    `git pull` immediately before `build_image.sh`.

**Don't tune `yarn build` flags — they do nothing.** Measured on Vite 5:
baseline 42s, `--minify false` 39s, `--sourcemap false` 39s, both 41s, dropping
vite-plugin-pwa 38s. `lucideIcons: false` just fails the build. Sourcemaps are
68% of output SIZE but almost none of the TIME, so they stay on.

**The bundler is Vite 8 (Rolldown), ahead of upstream** — adopted 2026-07-28,
~40s → ~25s (36s → 18s best case). Upstream frappe/crm is still on vite ^5.4.21
and frappe-ui's develop only reached vite ^7, with no Rolldown work in flight,
so a rebase may try to drag this backwards — keep the pins.
**`vite-plugin-pwa` must stay >= 1.x.** On 0.21.x the build still *succeeds*
under Rolldown but silently drops `registerSW.js` and `manifest.webmanifest`,
so the self-destroying service worker never registers and users get stale
bundles from an old SW — the exact bug `selfDestroying` exists to prevent, and
invisible unless you diff the output.

`scripts/verify_no_drift.py` (also run by `smoke_test.py`) asserts prod matches
this repo file-for-file. It exists because the old `docker cp`-based deploy had
no delete semantics, so files removed from the repo lived on in prod for over a
year — including an abandoned module with a live whitelisted endpoint.

## Upstream sync

Upstream moves fast (v1.73+ as of 2026-06). To take upstream changes: rebase
`groundwork` onto the target tag, verify the image-tag-contents problem is
fixed (or build our own image), re-test everything in ../frappe-crm-deploy/CLAUDE.md.
