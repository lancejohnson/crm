# Next workspace — frontend

The real implementation of the previewed design (`docs/phone-preview.md`),
wired to the contract in `docs/next-workspace-build.md`. Gated: the server's
`crm.api.workspace.get` says whether this user is allowed and which version
they are on; everyone else renders production, byte-identical.

## Gate and imports

- `stores/workspace.js` — `{ version, allowed }` from the server; `isNext`
  is `allowed && version === 'next'`; `toggle()` writes `set_version`.
- `App.vue` mounts **one** dynamically imported host,
  `components/Talk/NextWorkspaceShell.vue`, only when `isNext`. Nothing under
  `components/Talk/`, `PhoneDock*`, `stores/talk.js` or `composables/phone.js`
  is statically imported anywhere — a classic session never fetches the chunk
  (`scripts/test-next-workspace.mjs` asserts this by walking `src/`).
- `UserDropdown.vue` shows *Try the new workspace / Back to classic* only when
  `allowed`. In DEV, a non-allowlisted session still gets the mockup toggle.
- `?phonePreview=1` remains the DEV-only fictional mockup; `pages/Talk.vue`
  hands over to `TalkPreview.vue` in that case (never in production).

## Pieces

- **Left column** `components/Talk/TalkNav.vue` — real CRM nav as a
  collapsible group (reuses `applySidebarConfig` + `SidebarLink`), then Live
  (`telephony.active_calls`), Channels (pinned Standup = the `bot` channel
  `standup`, then channels/bots), Direct messages with presence. Overlays the
  real sidebar; `App.vue` shifts the layout by `column − sidebar` width so
  `AppSidebar`/`MobileSidebar` are untouched. On mobile it is teleported into
  the drawer panel. Collapsed = 48px icon strip with unread dots.
- **Talk page** `pages/Talk.vue` at `/talk/:kind/:id` — thread from
  `talk.thread` (older pages on scroll-up), composer (`talk.post`, Enter /
  Shift+Enter, `@` autocomplete from the users store via
  `utils/talkMentions.js`), `mark_read` on view, live append from `crm_talk`
  (a message for the open thread is read, not unread). Live pages join with
  `telephony.join(monitor)` and route to `/leads/<lead>/comps` when linked.
- **Keyboard** `components/Talk/TalkKeys.vue` + `utils/talkShortcuts.js`
  (shared with the preview; fixtures moved to `talkShortcutsPreview.js`).
  ⌘K Talk section in the existing palette, ⌘⇧K DM switcher (also offers
  teammates with no thread → `talk.ensure_dm`), ⌥↑/↓, ⌥⇧↑/↓ unread, ⌘⇧L,
  Esc mark read, ⌘/ help.
- **Phone dock** `components/Telephony/PhoneDock.vue` — bottom bar with team
  presence (`talk.presence` ∪ active calls, headset join → comps when linked)
  and the dock button; floating panel with Recent calls / Conversations from
  `telephony.history`, inline dial, incoming Answer (green) / Decline from
  `crm_incoming`, live-one card from `crm_live_one`. `PhoneDockCall.vue`:
  mute/hold/keypad/Got a live one (`telephony.live_one`); supervisor
  Listen/Whisper/Barge via `telephony.set_mode`. `PhoneDockConversation.vue`:
  one number's calls + texts oldest-first, AI summary when the call log has
  one, recording played through `crm.integrations.api.get_recording_url`
  (never the raw provider URL), texts via `telephony.send_text`.
- **WebRTC** `composables/phone.js` — the single Telnyx leg (same token flow
  as `TelnyxCallUI.vue`, lazy SDK). `dial` calls `telephony.dial` first so the
  server owns the conference; `join` asks the server to dial our credential.
- **Settings** `pages/PhoneSettings.vue` at `/settings/phone` (managers) —
  `CRM Phone Line` rows (owner, recording override, member view/use/ring) and
  `CRM Telephony Settings` (recording default, cell fallback, consent note).
  Buy number is disabled ("coming soon").

## Shapes assumed beyond the contract (backend must match)

- `telephony.history(number=None, limit)` → flat list, newest first, rows
  `{ kind: 'call'|'text', name, number, lead, lead_name, at, direction
  ('Incoming'|'Outgoing' for calls, 'in'|'out' for texts), status, duration,
  recording_url, summary, rep_name, text, sender_name }`. With no `number` it
  returns the user's recent activity across their lines (one row per event).
- `telephony.dial` → `{ call_log, client_state }`; `telephony.decline(call_log)`.
- `telephony.active_calls` rows carry `number` alongside the contract fields.
- `crm_incoming` payload may carry `lead_name` and `line_label`.
- `talk.thread` messages may carry `deleted` (rendered as "Message deleted").

## Tests

`node scripts/test-next-workspace.mjs`: shortcut helpers over store-shaped
lists, @mentions, E.164, all 12 real modules compile, every contract endpoint
and realtime event is referenced, no embedded secrets, no fixture imports in
real code, and no classic module statically imports next-only code.
