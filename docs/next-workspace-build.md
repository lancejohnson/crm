# Next workspace — build contract

Real implementation of the previewed design (phone dock A + left-nav comms D +
Talk pages). **Gated to an allowlist; only Lance until he widens it. Staging
first; production webhooks/numbers untouched.**

## Gating

- site_config `crm_next_users`: JSON list of CRM login emails. Default when
  missing: `["lance.johnson@groundworkpro.com"]`.
- Per-user default `crm_workspace_version` ∈ `classic|next` (Frappe user
  default, read at boot with the users store, written via
  `crm.api.workspace.set_version`). Server refuses `next` for anyone not in the
  allowlist; frontend hides the menu item unless `crm.api.workspace.get`
  returns `allowed: true`.
- `classic` renders production byte-identical. Nothing "next" mounts.
- `?phonePreview=1` stays a DEV-only override for the fictional mockup fixtures.

## API contract (backend ↔ frontend)

All under `crm.api.*`, whitelisted, session auth. Realtime via
`frappe.publish_realtime` to the user (or room) — frontend listens on `$socket`.

### workspace
- `workspace.get()` → `{ version, allowed }`
- `workspace.set_version(version)` → `{ version }` (403 if not allowed)

### talk (channels / DMs)
Doctypes (ops `scripts/setup_talk.py`, idempotent, guarded everywhere):
- `CRM Channel`: `name` (slug, e.g. `acquisitions`), `title`, `kind`
  (`channel|dm|bot`), `mm_channel_id`, `members` (child: user), `archived`.
- `CRM Message`: `channel` (Link), `author` (User), `text` (Markdown),
  `mm_post_id` (unique when set), `mm_root_id`, `origin` (`crm|mattermost`),
  `edited_at`, `deleted` (Check), `posted_at` (Datetime).
- `CRM Channel Read`: `channel`, `user`, `last_read_at`.
- `talk.list_channels()` → `[{ name, title, kind, unread, last_at, dm_user, presence }]`
  in left-column order: channels, then DMs. Standup is the `bot` channel
  `standup` (the 5am post lands here AND in Mattermost during transition).
- `talk.thread(channel, before=None, limit=50)` → `{ messages:[{ name, author, author_name, text, posted_at, origin, edited_at }], has_more }`
- `talk.post(channel, text)` → message; also mirrors to Mattermost (below).
- `talk.mark_read(channel)` → `{ unread: 0 }`
- `talk.ensure_dm(user)` → `{ name }` (creates the DM channel + MM direct channel)
- `talk.presence()` → `{ user: 'online|away|offline|on_call' }` (MM status ∪ Telnyx active calls)
- Realtime: `crm_talk` `{ channel, message }` on insert/edit/delete;
  `crm_talk_read` `{ channel, unread }`; `crm_presence` `{ user, status }`.

### Mattermost two-way sync (`crm/integrations/mattermost/`)
- Mattermost stays source of truth during transition. Sync dying loses nothing.
- **CRM → MM**: on `CRM Message` insert with `origin=crm`: POST `/posts` to
  `mm_channel_id` as the author (existing per-rep PATs in site_config
  `mattermost_user_tokens`; bot `mattermost_token` fallback prefixed
  `**Name:** `), `props: { crm_origin: 1, crm_message: name }`; store `mm_post_id`.
  Edits/deletes mirror via PUT/DELETE.
- **MM → CRM**: `crm.integrations.mattermost.webhook.event` (allow_guest, HMAC
  `X-Groundwork-Signature` over the raw body with site_config
  `mattermost_sync_secret`; fail closed). Accepts `posted`, `post_edited`,
  `post_deleted`, `status_change`. Skip when `props.crm_origin` or
  `mm_post_id` already exists (loop guard). Unknown channel → auto-create
  `CRM Channel` (`kind` from MM type `O/P`→channel, `D`→dm, membership from
  MM). Users mapped by email (both sides are Workspace accounts); unmapped
  author → text prefixed with the MM username, author = bot user.
- **Backfill**: `mattermost.sync.backfill(channel, since_days=30)` pulls posts
  for mapped channels; idempotent on `mm_post_id`.
- **Forwarder** (repo `Projects/Groundwork/mattermost/agent-listener`): the
  existing websocket listener gains a forwarder that POSTs the events above to
  `https://<crm>/api/method/crm.integrations.mattermost.webhook.event` with the
  HMAC. Env: `CRM_SYNC_URL`, `CRM_SYNC_SECRET`. Off unless both set. Not
  deployed in this pass.

### telephony (extends `crm/integrations/telnyx/`)
Doctype `CRM Phone Line` (ops `scripts/setup_phone_lines.py`): `number`
(E.164), `label`, `owner` (User), `recording` (`inherit|on|off`),
`members` (child: user, view, use, ring). Settings doctype
`CRM Telephony Settings` (Single): `recording_default` (Check),
`consent_note` (read-only text), `ring_cell_fallback` (Check).
- `telephony.lines()` → lines the user can view/use/ring.
- `telephony.dial(to, line)` → `{ call_control_id }` — **conference-first**:
  rep leg + callee joined to conference `crm-<call_log>`; CRM Call Log row is
  written by the webhook (existing rule).
- `telephony.active_calls()` → `[{ call_log, rep, lead, lead_name, state, started_at, conference }]`
- `telephony.join(call_log, mode)` mode ∈ `monitor|whisper|barge` → joins the
  caller's WebRTC leg as supervisor (`supervisor_role`, `whisper_call_control_ids`),
  `beep_enabled: never`, then `conferences/{id}/actions/play` a short tone to
  the **rep leg only**. `telephony.set_mode(call_log, mode)` → `actions/update`.
- `telephony.live_one(lead, note)` → creates `CRM Notification` (type
  `Live one`) for the closer + posts to the closer's DM in Talk (and Mattermost
  during transition, via existing `live_one.alert`), realtime `crm_live_one`
  `{ lead, rep, note, call_log }`.
- `telephony.history(number)` → chronological calls (CRM Call Log incl.
  recording_url, custom_transcript/summary) + texts (Quo Message, any provider)
  for the normalized number.
- `telephony.send_text(to, text, line)` → Quo Message row provider=Telnyx (existing `api.send_sms`).
- Incoming: `call.initiated` on a line → ring every `ring` member's WebRTC
  credential + (if `ring_cell_fallback`) their mobile; first answer bridges
  into the conference, others cancel. Realtime `crm_incoming`
  `{ call_log, from, lead, line }` to ring members.
- Recording: start at bridge time when `line.recording` resolves on
  (inherit → settings default). Consent note shown in settings; toggle is not
  legal consent.

## Frontend wiring

- `stores/workspace.js`: version + allowed from `workspace.get`; user menu item
  only when allowed; `next` mounts `PhoneDock` (design A), `TalkNav` (design
  D left column), Talk routes `/crm/talk/:kind/:id`.
- Replace fixtures with resources: channels (`talk.list_channels` + `crm_talk*`
  realtime), thread (`talk.thread`, `talk.post`), presence, history
  (`telephony.history`), lines/settings, active calls (`telephony.active_calls`
  + `crm_telnyx_call`), incoming (`crm_incoming` → Answer/Decline via
  `TelnyxRTC`), live-one (`crm_live_one` → alert card with Join → `telephony.join`
  then route to `/leads/<lead>/comps` when linked).
- Keyboard shortcuts and ⌘K Talk section as previewed.
- Phone settings page bound to `CRM Phone Line` / `CRM Telephony Settings`
  (admin only). Buy-number stays disabled with "coming soon" until a Telnyx
  number-order flow is approved.

## Lanes

1. `backend` — talk API + doctypes (ops scripts) + Mattermost sync + workspace
   gating; then telephony extensions. Tests: `bench --site … run-tests --module crm.tests.test_talk` style or pytest-less unit tests under `crm/tests/`.
2. `frontend` — wire preview components to the contract; DEV fixtures stay
   behind `?phonePreview=1`.
3. `listener` — forwarder in `Projects/Groundwork/mattermost/agent-listener`.
4. `integrate` — merge lanes, run both test suites, `yarn build`, then
   **staging only**: `ALLOW_WORKTREE=1 scripts/build_image.sh` + staging
   deploy per ops CLAUDE.md, run ops setup scripts on staging, set staging
   site_config (`crm_next_users`, `mattermost_sync_secret`). Telnyx: staging
   number +1 651 382 0252 only. Never touch prod webhooks or Quo.

## Must stay true
- Classic layout byte-identical for everyone not on the allowlist.
- No production deploy, no prod site_config, no Telnyx changes outside the
  "Groundwork CRM (test)" resources, no Mattermost writes from a laptop.
- Every allow_guest endpoint verifies a signature and fails closed.
