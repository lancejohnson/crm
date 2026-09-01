# Requested CRM issues — retrospective baseline audit (2026-09-01)

> **Status disclosure:** this is a retrospective audit, not a claim that the audit
> preceded implementation. The implementation shipped while the original audit
> goal was still open: app commits `75cfefe7` and `15acb9e0`, ops commit
> `103036c`, deployed as `v1.67.0-gw427`. To recover the requested pre-change
> view, every code finding below is anchored to app baseline **`de18beb9`** and,
> where the behavior lives in the companion ops repo, ops baseline **`896c11c`**.
> “Current” below means behavior at those baselines unless explicitly labelled
> post-implementation.

## Audit inputs and concurrency check

### Repository/worktree state at audit start

Command run before implementation:

```sh
git worktree list
git branch -a
git log --oneline de18beb9..<related-branch>
```

Observed:

```text
/Users/work/Projects/Groundwork/frappe-crm-app     de18beb9 [groundwork]
/Users/work/Projects/crm-worktrees/lead-desk       b61fc905 [feature/lead-desk]
/Users/work/Projects/crm-worktrees/practice-comps  6f49af27 [feature/practice-comps]
/Users/work/Projects/crm-worktrees/team-today      b7018f3d [feature/team-today]
```

- `feature/practice-comps`: no commits unique from `de18beb9`; already merged.
- `feature/team-today`: no commits unique from `de18beb9`; already merged.
- `feature/lead-desk`: one unrelated unique commit, `b61fc905 Save the v17 mockup and split the desk into named tasks.`
- Conclusion: Practice and Today work had relevant history to read, but no
  in-flight implementation to build on; lead-desk work was unrelated.

### Mattermost evidence

1. `15cfotqjx3btdym3pbdwotizjo` — Practice report. Clicking another comp without
   **Done with this one** resets/mangles the timer. Capturing the current tab
   stops when a Zillow tab is opened and then closed. Attachment
   `d7ynwq5u73r5ifb859ppf8oc3c`, `2026-08-31 12-46-38.mkv`, is a 22,114,524-byte,
   29.823-second valid bug-report screen recording; it is not a Practice backup.
2. `xssoqjah73bhig1knuxpz3x7gc` — manual refund tickets. Names David Smith
   (`CRM-LEAD-2026-00988`) and William Kellum (`CRM-LEAD-2026-01102`). The thread
   says a general support ticket must be created when the lead is missing from
   the provider refund form.
3. `pot9yjk3wtng8pwj4apac5jxaa` — Timothy Arter. He was absent from the refund
   request tab, was filed as a ticket, and later refunded; provider issue URL
   `https://app.ispeedtolead.com/issue/6a95cb9c4844105ef9ae33a3`.

Corroborating later report (not one of the original three):
`9z1xksrg6i8wmmqqb41nrn5ono` says both **Done → Sent a Text** and
**Skip → Dead lead** fail in the Today board.

### Screenshot evidence

- `/Users/work/Desktop/2026-08-31 Bug.png` — opened through Preview because the
  file tool was TCC-blocked. Denise Curry appears simultaneously in To Call and
  Done after an optimistic move; the toast says:
  `Outcome cannot be "Dead lead". It should be one of "", "Connected", "No Answer", "Left a Voicemail", "Booked an Appointment", "Other".`
- `/Users/work/Library/Application Support/CleanShot/media/media_3oxndQauzv/CleanShot 2026-08-31 at 13.50.41@2x.png`
  — Mattermost shows Star Ma ticket `153380` credited twice, five minutes apart.

## 1. Practice — browser-window recording option

### Baseline behavior

Start offered a boolean **Record screen + mic** checkbox. The capture request
was biased to the calling tab. Switching within Chrome required Chrome’s
“share this tab instead” flow, and closing the shared Zillow tab ended capture.

### Exact code path at `de18beb9`

- `frontend/src/pages/PracticeSet.vue::start()` — calls
  `startPracticeRecording()` with no capture mode.
- `frontend/src/utils/practiceRecorder.js::startPracticeRecording()` — lines
  98–103 request `getDisplayMedia({ video: VIDEO, preferCurrentTab: true,
  selfBrowserSurface: 'include' })`.
- The display video track’s `ended` listener calls `stopPracticeRecording()`.

### Root cause

The app deliberately requested a browser-tab surface and exposed no separate
window intent. Closing the chosen tab ends its display track by browser design.
A window mode needs distinct display constraints and a visible choice before
Start; silently changing all captures would remove the useful current-tab mode.

## 2. Comps — Cmd/Ctrl+F collapses the map

### Baseline behavior

Plain F, Cmd+F, and Ctrl+F all toggled the Comps full-map layout; the modified
forms also competed with browser Find.

### Exact code path at `de18beb9`

- `frontend/src/components/CompsView.vue:2748`:
  `{ keys: ['f', 'F'], action: () => toggleCompsFocusMap() }`.
- `frontend/src/composables/useKeyboardShortcuts.js::matchShortcut()` compares
  only `e.key`; modifiers are not rejected unless a definition supplies a guard.

### Root cause

`KeyboardEvent.key` remains `f` while Meta or Control is held, so the bare-key
shortcut matched browser shortcut chords. The F definition needed an explicit
`!metaKey && !ctrlKey && !altKey` guard.

## 3. Practice — timer switching, recording rollover, and backup files

### Baseline behavior

Clicking property chips while the prior property was saving could make the
per-listing timer jump/reset and could associate recorder state with the wrong
property. Some uploaded recordings existed on disk but had no playable result
stamp.

### Exact code path at `de18beb9`

- `frontend/src/pages/PracticeRun.vue:305–342` — async watcher on
  `current.value?.name`; each change independently awaits `persistCondition`,
  `touch_property`, and `beginPropertyRecording` with no single-flight lock or
  stale-response rejection.
- `frontend/src/utils/practiceRecorder.js::beginPropertyRecording()` — shared
  globals `recorder`, `queue`, `seq`, `propertyId`; concurrent calls both await
  the same end and then each initializes those globals.
- `crm/api/practice.py::touch_property()` — correctly row-locks and serializes
  server clock state; the client could still apply responses out of order.
- `crm/api/practice.py::upload_recording_chunk()` — writes `.webm.part` chunks.
- `crm/api/practice.py::finish_recording()` — promoted `.part` to canonical
  `.webm`, then inserted a Frappe `File` row before stamping `results`.
- `crm/api/practice.py::_file_recording_url()` — disk fallback/promotion when a
  JSON stamp is absent.

### Root cause

There were two independent races: un-serialized property transitions could
apply an older `touch_property` response last, and un-serialized recorder
transitions overwrote shared recorder/property/sequence globals. Recovery then
exposed a third failure: Frappe `File.before_insert` re-read the assembled
recording and enforced the site’s **25 MB** upload limit. Normal 40–150 MB takes
therefore failed after all chunks uploaded but before the JSON result stamp.
Playback already uses `stream_recording`, so a `File` row was unnecessary.

### Per-recording probe evidence

Attempt `4hq25i5q59` (set `qdi8g6h13g`, Exe Ortiz) had two unstamped canonical
files:

| Property | Address | Bytes | Probe result | Recovery result |
|---|---|---:|---|---|
| `ri612pe0tg` | 19111 Timber Way Dr | 45,287,440 | `ffprobe`: `EBML header parsing failed` | Not recoverable as media; preserved as `practice-4hq25i5q59-ri612pe0tg.webm.corrupt`, stamp removed |
| `rn15bm8416` | 1903 Harlan St | 90,174,031 | `ffprobe`: `duration=587.760000` | Recovered and stamped |

The recovered stream was read back through the production endpoint with
`Range: bytes=0-99`: HTTP `206`, `Content-Range: bytes 0-99/90174031`,
`Content-Type: video/webm`, first bytes `1a45dfa3` (EBML magic). Thus the audit
claims one recovered recording and one quarantined corrupt artifact—not two
recoverable recordings based on size alone.

## 4. Refundable marker for live follow-up leads

### Baseline behavior

The board already supported any status in principle, but the obvious controls
were inside the lost/refund-pool banner. A live Follow Up lead had no discoverable
lead-level refund action.

### Exact code path at `de18beb9`

- `frontend/src/pages/Refunds.vue:83` — sole inclusion predicate:
  `filters: { custom_refundable: 1 }`.
- `frontend/src/components/Activities/Activities.vue::isRefundPoolLead` and the
  lost banner — checkbox visibility follows a Lost/refund-pool status.
- `crm/api/istl_refund_nudge.py::evaluate()` — automated eligibility nudge; it
  is not a general manual marker.
- Ops `scripts/setup_refundable_field.py` — `custom_refundable` exists, but the
  generic side-panel location was not a clear workflow control.

### Root cause

Data capability and UI discoverability diverged. The status-independent board
filter was correct; the marker needed a persistent desktop/mobile lead card,
not another status rule.

## 5. Refund email reply when no auto-draft exists

### Baseline behavior

John Somerville had inbound refund email and no Pi draft. The consolidated email
thread displayed the mail but offered no per-message Reply action; only the
separate composer toggle was available without recipient/thread prefill.

### Exact code path at `de18beb9`

- `frontend/src/components/Activities/EmailThread.vue` — props only `messages`;
  rows toggle open/closed and contain no Reply action or emit.
- `frontend/src/components/Activities/EmailArea.vue::reply()` — the older
  per-message card had working reply prefill, but consolidated threads no longer
  used it.
- `frontend/src/components/Activities/Activities.vue` refund-draft watcher —
  calls `emailBox.loadDraft(...)` only when `custom_refund_draft_json` exists.
- `frontend/src/components/CommunicationArea.vue::sendMail()` — moved status to
  Waiting on them only in the `refundDraft` branch.

### Root cause

The EmailThread consolidation dropped the interaction contract from EmailArea,
and the fallback composer path was gated on draft existence. Reply must be an
EmailThread event handled by the mounted CommunicationArea; sending a refund
reply must update workflow state whether or not Pi drafted it.

### Production readback (`CRM-LEAD-2026-00966`)

Read-only query:

```sql
SELECT name,lead_name,status,source,custom_refundable,
       custom_refund_status,custom_refund_requested,vendor_lead_id
FROM `tabCRM Lead` WHERE name='CRM-LEAD-2026-00966';

SELECT name,creation,sent_or_received,sender,recipients,subject,message_id
FROM `tabCommunication`
WHERE reference_name='CRM-LEAD-2026-00966' ORDER BY creation;
```

Observed before implementation: John Somerville, Lost, iSpeedToLead,
`refundable=1`, `Waiting on us`, `requested=1`, vendor id
`6a845d8818fa050299ed1900`, `custom_refund_draft_json=NULL`; three received
Zendesk reminders with distinct Gmail message IDs and no outbound Communication:
`sdlpbh0rcu / 1a020fa659d3f303`, `sdvplvs6g6 / 1a01e676e4926bfb`,
`secg4ot51h / 1a01bd4227414718`.

## 6. Manual refund tickets absent from the automated feed

### Baseline behavior

A manual general-support ticket had no representation. If the lead was not
already `custom_refundable=1`, it could not appear on Refunds; if it was already
there, it could remain falsely in To Request after a human submitted the ticket.

### Exact code path at `de18beb9`

- `frontend/src/pages/Refunds.vue::list` — `custom_refundable=1` only.
- `crm/api/refunds.py` — draft send/read only; no consistent manual-state setter.
- Ops `scripts/setup_refundable_field.py::FIELDS` — refundable, requested,
  requested_on, status, draft; no request-origin/manual-ticket field.
- Ops `refund_mail_poll.py::main()` — ordinary matching pool initially loads
  refundable leads; only later provider mail can reconcile status.

### Root cause

The model recorded eligibility and status but not the request path. A manual
support ticket semantically means both refundable and requested, and needs a
separate durable origin flag so one click cannot leave the board in To Request.

### Production examples/readbacks

Read-only query used:

```sql
SELECT name,lead_name,status,source,custom_refundable,
       custom_refund_requested,custom_refund_status,vendor_lead_id
FROM `tabCRM Lead`
WHERE name IN ('CRM-LEAD-2026-00988','CRM-LEAD-2026-01102','CRM-LEAD-2026-01091');
```

Captured before implementation:

| Lead | Status/source | refundable | requested | refund status | Mattermost evidence |
|---|---|---:|---:|---|---|
| David Smith `00988` | Follow Up / PropertyLeads | 0 | 0 | blank | manually submitted; absent from board |
| William Kellum `01102` | Dead Lead / iSpeedToLead | 1 | 0 | To Request | manually submitted; board falsely says not requested |
| Timothy Arter `01091` | Dead Lead / iSpeedToLead | 1 | 1 | Complete | manually submitted, later reconciled; origin unknowable |

Post-implementation readback: all three have
`custom_refund_manual_ticket=1`; David and William are Requested, Timothy remains
Complete. The Refunds DOM contained each name exactly once and three Manual
ticket badges.

## 7. Simplify scheduling a task

### Baseline behavior/screens

The lead Activity surface exposed an inline To-do composer, New → Task opened an
XL modal, and the Tasks tab had another New Task button. In the inline flow,
clicking a due chip immediately created a task (default title “Follow up” when
blank), while Enter created the typed task with no date. Clicking an existing
title renamed it; a hover-only panel icon opened schedule/details, making that
action effectively hidden on touch. The modal showed title, a 180 px rich-text
description, status, assignee, raw date/time, priority, and Call Outcome at once.

### Exact code path at `de18beb9`

- `frontend/src/components/Activities/TaskTodoList.vue::followUp()` —
  `newTitle.trim() || __('Follow up')`, then immediate `addTask(...)`.
- `TaskTodoList.vue::submit()` — Enter path with optional `newDue`.
- `TaskTodoList.vue::startTitleEdit()` and title `@click` — inline rename.
- Hover-only `LucidePanelRight` button — `modalRef.showTask(task)`.
- `frontend/src/components/Activities/ActivityHeader.vue::activityActions` and
  Tasks-tab branch — two full-modal create entry points alongside quick-add.
- `frontend/src/components/Modals/TaskModal.vue` — all advanced controls visible;
  Call Outcome shown on every task.
- `frontend/src/components/Activities/AllModals.vue::showTask()` defaults new
  modal tasks to `Backlog`; `AllModals.vue::addTask()` defaults quick tasks to
  `Todo`.

### Root cause

One record type had competing creation semantics and hidden interaction targets.
The common scheduling decision is “what?” then “when?” then explicit Add; due
chips should select state, not submit. Advanced fields belong behind progressive
disclosure, and title click should consistently open the editable schedule on
both pointer and touch devices.

## 8. Denise Curry — Skip + Dead lead validation error

### Baseline behavior

Lead status changed to Dead Lead, but resolving the Today card with skip reason
Dead lead raised the screenshot’s Select validation toast. The optimistic client
move could leave the card visually duplicated until reload.

### Exact code path at baselines

- App `de18beb9`, `crm/api/today_board.py::set_today_state()` — correctly
  validates `state == 'Skipped'` against `SKIP_OUTCOMES`, which includes
  `Dead lead`.
- App `frontend/src/components/Modals/TodayOutcomeModal.vue::SKIP_OUTCOMES` —
  also includes Dead lead.
- Ops `896c11c`, `scripts/setup_today_board.py::DOCTYPE` — `outcome` is a Select
  containing only blank, Connected, No Answer, Left a Voicemail, Booked an
  Appointment, Other. The idempotent updater changed only missing fields and
  autoname; it did not repair existing field options.

### Root cause

App validation and storage validation disagreed. `doc.save()` reaches Frappe’s
Select validator after the app accepts the skip, so a valid skip reason was
rejected by schema. The durable fix is the union of Done + Skip options plus an
idempotent options migration—not weakening validation or storing reasons only
in free text.

### Production evidence

Before correction, Denise Curry `CRM-LEAD-2026-01109` on 2026-08-31 had call 1
Done/No Answer and call 2 Skipped/Other with note “Dead lead”; the workaround
preserved the human intent but not the structured reason. Post-migration,
`set_today_state(... state='Skipped', outcome='Dead lead')` returned OK; readback
is `Skipped / Dead lead / ''`, and `resolved_at` remained
`2026-08-31 12:18:39.589272` (correction did not restamp activity time).

## 9. Same lead credited twice

### Baseline behavior

Mattermost posted two credit notices for Star Ma, ticket `153380`, five minutes
apart.

### Exact code path at ops baseline `896c11c`

- `refund_mail_poll.py::classify()` — both “New money was added” and “ticket has
  been refunded” classify as `complete`.
- `refund_mail_poll.py::next_status()` — returns Complete only when a transition
  is needed; returns `None` when already Complete.
- `refund_mail_poll.py::main()` — after applying `nxt`, unconditionally calls
  `notify_owner` for every `kind in ('complete','needs_reply')`; `pinged` is only
  process-local and Gmail dedupe keys individual message IDs.

### Root cause

Two different Gmail messages describe one semantic completion. Message-ID
dedupe cannot collapse them. Credit notification must be gated on the actual
transition (`kind == complete && nxt == Complete`); needs-reply notices remain
message-driven.

### Production readback

`CRM-LEAD-2026-01141` Star Ma has ticket 153380 mail at 13:45 (“New money was
added”) and 13:50 (“Your ticket 153380 … has been refunded”), plus associated
provider notifications. Both Mattermost credit posts point to the same lead and
ticket, not two legitimate credits. Post-implementation host assertion verifies
`should_notify('complete','Complete') == True` and
`should_notify('complete',None) == False`.

## Reproducible verification commands

All database inspection was read-only unless a post-implementation correction is
explicitly labelled above:

```sh
# Baseline source
git grep -n '<anchor>' de18beb9 -- <path>
git -C ../frappe-crm-deploy show 896c11c:<path>

# Production reads
ssh groundwork-apps "cd /opt/frappe-crm && docker compose exec -T backend \
  bench --site crm.groundworkpro.com mariadb -N -e '<SELECT only>'"

# Recording validity
ssh groundwork-apps "cd /opt/frappe-crm && docker compose exec -T backend \
  ffprobe -v error -show_entries format=duration -of default=nw=1 <file>"
```

This document is the requested baseline audit reconstructed after implementation.
It does not represent itself as contemporaneous pre-implementation evidence.
