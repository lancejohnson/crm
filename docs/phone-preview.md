# Native CRM phone design preview

All changes in `/Users/work/crm-worktrees/phone-preview` are **local design simulations**, not phone functionality. The real CRM lead stays behind the tools at full width. Phone calls, messages, teammates, numbers, settings, and permissions are fictional and in memory only. Other CRM controls remain real production-backed controls: do not edit records during review or publish the authenticated app publicly.

## Open / compare

The `/crm/phone-preview` launcher opens an accessible real Lead using a read-only ID lookup. Or use a real lead URL with `?phonePreview=1`.

- `&phoneDesign=A` — **Quick pocket:** compact recent-call list, understated Calls/Texts navigation, integrated dial footer. Least room taken from CRM work.
- `&phoneDesign=B` — **Conversation desk:** wide, horizontal list/thread split for messaging. Calls have a broader ledger layout. Collapses to list→thread on mobile.
- `&phoneDesign=C` — **Slim rail:** narrow icon navigation down the left and dedicated number/keypad view, then History or Texts in the same slim frame.

A tiny bottom-bar design selector switches the three while preserving in-memory conversations and calls. It updates `phoneDesign` in the URL. No recreated CRM shell, iframe, or standalone phone page.

```sh
cd frontend
CRM_DEV_TARGET=https://crm.groundworkpro.com yarn dev
# Port is frontend/.dev-port; /__crm_dev identifies root/branch/peer.
```

The current server uses port 8080 and mirrors to `mini-ts`. Standard dev authentication applies. Phone activation, launch route, and settings route are `import.meta.env.DEV`-gated; no production deployment is part of this work.

## Phone, incoming calls and invitations

Bottom **Phone** opens/minimizes the tool. Sliders opens the tucked-away **Preview controls**, not a stack of permanent scenario cards.

- **Incoming known/unknown:** sliders → Incoming, or append `&phoneIncoming=1`. Shows caller name/number, Acquisitions line, context, Answer/Decline. No sound. Answer creates an active **Inbound** mock call; Decline writes **Declined**, not Completed, to History. No claim of voicemail forwarding.
- **An active call is never replaced.** Incoming Answer is disabled while active; callback/headset/alert joins share a guard. Declining an incoming call leaves the original active call intact. Pending incoming takes precedence over live-one invites; the invite is retained and surfaces afterwards.
- **Live one:** preview controls → Receive a live-one alert; or Rep on a call → note → Got a live one. The invite remains until Join/Mark handled/call ends. The whole phone can minimize without losing it. Join starts listening. Whisper names the rep-only audience; Barge says both hear you. Closer Leave only removes the closer.
- **History (A opens here):** fictional prior connected/missed/no-answer/declined calls with time, duration, direction and an explicit **recording state** (ready · sample / pending / not recorded). Clicking the person opens their **conversation**; callback and text are sibling shortcuts. Rep End appends a `pending` row; Decline appends `Declined`, no duration, no summary.
- **Conversation (Texts tab):** one chronological timeline per number — texts as bubbles, calls as cards with direction/result/duration. Connected calls carry an expandable **AI summary · sample** (labelled as mockup text, not generated from a real call) and, when the recording is `ready`, an inline `<audio>` player. The audio is a **generated 8-second synthetic tone file** (`frontend/src/assets/phone-preview-sample.wav`, from `scripts/generate-phone-preview-audio.py`); the player shows the sample's real 0:08, never the fictional call length. No autoplay; the player tears down when the thread or phone changes, so nothing keeps playing detached. Number formatting normalizes to the same conversation; per-thread drafts survive panel and SPA navigation; refresh/Exit clears them.
- **Incoming:** Answer is solid green, Decline red-on-pink, so the two never read alike.
- **Join lands on the comps map.** A live-one raised from a lead page carries that lead; accepting **Join listening** starts the (simulated) listen, minimizes the phone to the dock (`Jordan Ellis · Listen`) and routes to `/leads/<id>/comps` — the real comps page, where Dennis prices from. The invitation says so before you click. The team-bar headset does the same: Exe's call is `linked` to a lead (tooltip “Join listening · opens comps”) and routes there; Germán's unlinked cold call (“Join listening”) stays put. In the mockup “the linked lead” is the real lead the preview last visited (`previewLead`). A blocked join (already on a call) never navigates; a call with no CRM lead stays put. Note: the comps page is real and may spend Zillow calls like any normal open.
- **Less chrome:** a single phone disclaimer carries the demo boundary. Actions are compact, repeated nested demo cards are gone, notifications/scenario switches are tucked away.

Only the bottom bar reserves workspace height. The phone floats above it, inset **36px from the right** to avoid the existing feedback tab. It does not narrow the real Lead Activity column. Minimize is sticky and left-aligned. Mobile stays within viewport with internal scrolling; real CRM modals remain above the phone.

## Chat anchored to the person

Click or keyboard-activate a teammate's **name/status**, not the headset. Chat opens directly **above that status** as its own popover, independent of the phone. Close/Escape returns focus to the status button. Drafts and messages stay isolated per person.

`PhonePreviewChat.vue` measures the live status-button rectangle, clamps the popover to the viewport (including feedback-tab clearance), and recomputes on window resize and captured scroll events, including roster scrolling. A ResizeObserver covers trigger resizing. Headset is a sibling button: chat never joins a call. Chat opening no longer minimizes/replaces the phone panel.

## Comms mockups (replacing Mattermost inside the CRM)

Four in-memory designs for carrying what Mattermost carries today — live-one alerts, the 5am standup, bot/ops alerts, @mentions, DMs — inside the CRM. Same real lead page, same activation (`?phonePreview=1`), switched with `&commsDesign=A|B|C|D` or the **Comms** selector in the bottom preview bar (“Comms · off” hides all four). State lives in `composables/commsPreview.js` (`utils/commsPreview.js` is the pure fixture/rules module). Teammate DMs are the phone preview's `chats` — one draft and one message list per person, whichever surface you type in.

- **A · Inbox** (`CommsInbox.vue`) — the existing sidebar **bell** opens a unified inbox in the exact slot the real Notifications panel uses (350px, left of the sidebar edge; full width under 640px). The interception is the notifications store's `visible` ref flipped back with a sync watcher — `AppSidebar.vue` / `Notifications.vue` are untouched. Filter chips (All / Live ones / Mentions / DMs / Bots) with per-filter unread counts; unread dot + bold; **Mark all as read**. Rows expand in place: a live-one shows **Join listening** (the phone guard — disabled on an active call, otherwise starts listening and routes to the lead's comps) + **Open comps** + **Handled** (reads it, never deletes it); the standup row carries a per-person digest table and an **Open Today board** link; mentions, DMs and the ops bot take an inline reply. Escape / click-outside closes; the bell is ignored by click-outside so it toggles cleanly.
- **B · Talk on the house** (`CommsLeadThread.vue`) — a **bottom drawer** across the workspace (300px, collapses to a 40px strip; reserves its height like the phone bar, so nothing is covered). Tabs: **This lead** (a fictional team thread about the lead in the URL, `@Name` highlighted), **Standup** (today's digest as a pinned post with **Open Today board**), and one tab per teammate (their DM = the phone chat). The lead composer has an **@mention autocomplete**: typing `@` (or `@De`) shows the teammate list; picking inserts `@Dennis `. `me@x.com` and a finished `@Dennis ` do not open it. Message text is escaped before the mention `<mark>` is applied.
- **C · Team rail** (`CommsRail.vue`) — a Slack-like **right rail** (320px) with **Live / Channels / DMs** sections. Live is an event feed (live one flagged, call started, offer sent, refund credited, inbound text) with **Join** (phone guard; opens comps when the call is linked) and **Open lead**. Channels: `#acquisitions` `#dispo` `#ops-bot` with unread badges that clear on open, thread + composer. DMs reuse the phone chats and show On call / Available from the team-bar state. **Width rule** (`railMode`): it **docks and reserves 320px only at ≥ 1400px**; below that it **overlays** and reserves nothing, so a 1200px window's Lead Activity column is never narrowed (a docked rail at 1200px had crushed it to 130px). Collapsed it is a **44px strip** of icons with badges (always reserved). Escape collapses it in overlay mode.

- **D · Left nav** (`CommsLeftNav.vue` + `pages/TalkPreview.vue`, Lance's ask: “have it on the left nav, and just allow collapsing all the CRM nav stuff, almost as if it was a channel”; then “have the channels open up in the middle pane just like normal to keep it from being too cluttered”) — the **sidebar itself is the column** (260px). `UserDropdown` and the **Notifications bell** stay at the top (the bell drives the real panel); below them four Slack-style groups, each a `<button aria-expanded>` with a chevron: **CRM** (the real link list — `applySidebarConfig` + `SidebarLink` with the real `condition`s, plus the real Public/Pinned views — reused, never copied), **Live** (calls in progress: the flagged live-one in amber, Germán's call in green), **Channels** (a pinned **Standup** item, then `#acquisitions` `#dispo` `#ops-bot` with unread badges) and **Direct messages** (Exe/Germán/Dennis with a presence dot; DMs are the phone chats, so a draft typed here is the draft the team-bar chat shows). A collapsed group rolls its unread up onto its header.
  - **A conversation is a PAGE, not a pane.** Picking anything routes to the DEV-only **`/crm/talk/:kind/:id`** (`kind` = `channel` | `dm` | `live` | `standup`; a channel's slug drops its `#`), rendered full-width in the main area with `LayoutHeader` + `Breadcrumbs` (**Talk / #acquisitions**) like Leads or Today. Channels and DMs are a thread + composer (Enter posts); a Live page carries the call context with **Join listening** (phone guard; `previewJoinOutcome` routes to comps when the call is linked) + **Open comps**; Standup is the pinned digest with **Open Today board**. Nothing floats and nothing is reserved on the right — the width rule now belongs to C alone. **The route is the selection**: the column highlights the active item off `route.params` (`isTalkActive`, the way `SidebarLink` does), landing on a page reads it (`openNavItem` on mount — by click, back/forward, or reload), and `talkRoute` carries the preview query so a reload keeps the mockup on. A route that names nothing (typo, ended call) renders a “Nothing here” page rather than a blank; landing without the preview query shows a “Turn the preview on” button rather than a bare thread.
  - The column's own **Collapse** shrinks it to a **48px icon strip**: CRM links as icons, one icon per group with an unread dot (amber for Live); tapping a group icon widens the column and opens that group. It never writes the real `sidebarCollapsed` preference.
  - **How it sits over the real sidebar without editing it.** The column is a fixed overlay; App.vue's `reserve` channel gained a `left` value = column width − measured real-sidebar width, applied as `margin-left` (negative when the strip is narrower than the real sidebar), so the real sidebar is shifted exactly underneath and the page starts at the column's edge. `AppSidebar.vue` / `MobileSidebar.vue` are untouched; production stays byte-identical (the entry bundle has no `CommsLeftNav`/`commsDesign`). The real Notifications panel positions itself off the real sidebar's edge, so it still opens flush to the column. Real **Help / Team activity** buttons are under the overlay while D is on (residual; they are not comms).
  - **Mobile (< 640px)** the column is **teleported inside the real drawer panel** (`.bg-surface-menu-bar`) and fills it, because a fixed overlay outside the headless-ui Dialog counts as a click-outside and would close the drawer under every tap. Picking a conversation closes the drawer and the page renders full-width.

The floating phone panel offsets itself above the B drawer and left of the docked/collapsed C rail, so the mockups never stack (D reserves nothing on the right). Everything is fictional, replies/posts stay in this browser, and there is no API, storage, Notification, audio, or Mattermost reach (asserted by `scripts/test-comms-preview.mjs` over every comms SFC, the Talk page and the phone widget; D adds group collapse, unread rollup, route↔item mapping, read-on-land, active highlight and shared DM draft checks). Residual: the fixed **Report a problem** tab still overlaps the rail's right edge at its own height; the rail's actions are left-aligned so nothing interactive sits under it.

```sh
cd frontend && node scripts/test-comms-preview.mjs
```

## Workspace version switch (classic ↔ next)

Lance: “allow users to switch between the current version and the new version which will have the Telnyx phone and Mattermost replacement.” The **user menu** (top-left `UserDropdown`, the same component on desktop and in the mobile drawer) gains **Try the new workspace** / **Back to classic**.

- **next** = the phone dock (design A) + the D left-nav comms + the Talk routes. **classic** = today's layout, byte-identical — no preview component renders. `utils/workspaceVersion.js` (`applyWorkspace` / `toggleWorkspace` / `currentWorkspace`) is the single rule; `composables/workspaceSwitch.js` is the menu item.
- **Where the choice lives.** In the preview: in memory (`phone.workspace`) mirrored into the URL query (`?phonePreview=1&phoneDesign=A&commsDesign=D`), which is the only thing that survives a reload. **Real mechanism, deliberately not wired:** a per-user Frappe default **`crm_workspace_version`** (`WORKSPACE_DEFAULT_KEY`) — the same no-doctype trick the task due chips and text presets use — read at boot with the user store and set from this same item via `frappe.client.set_default`. Nothing in the preview writes to the server.
- `?phonePreview=1` stays a **dev override**: any preview on reads as “next”, so “Back to classic” always means the real layout (and clears the preview query).
- A **first-run banner** appears once after switching to next: how to get back (name menu → Back to classic) and where the shortcut sheet is (⌘/). Dismissable; not shown again that session.
- **Production stays byte-identical**: the menu item is behind `if (import.meta.env.DEV)` with a *dynamic* import of the preview composable, so the dead branch is tree-shaken — the built dist has 0 occurrences of the label or the modules (asserted by grep after `yarn build`). The `route`/`router` are captured in setup and passed in, since the composable is created after setup where `useRoute()` cannot inject.

## Keyboard shortcuts (Mattermost-style)

Only in the new workspace (preview on + comms D). Rules are pure in `utils/talkShortcuts.js` (unit-tested); `components/Telephony/TalkShortcuts.vue` is the one DOM binding (window `keydown`, capture phase) and the help sheet.

| Keys | Does |
|---|---|
| **⌘ K** | Command palette — now with a **Talk** section (Live, Standup, channels, DMs; left-column order, fuzzy-ranked when you type). |
| **⌘ ⇧ K** | **DM switcher**: the same palette scoped to direct messages. |
| **⌥ ↑ / ⌥ ↓** | Previous / next conversation in left-column order (wraps; from a non-Talk page ↓ goes to the first, ↑ to the last). |
| **⌥ ⇧ ↑ / ⌥ ⇧ ↓** | Previous / next **unread** conversation (no-op when nothing is unread). |
| **⌘ ⇧ L** | Focus the message box on a Talk page. |
| **Esc** | On a Talk page: mark it read and leave the message box. |
| **⌘ /** | This shortcuts sheet. |

⌘ is Ctrl on Windows/Linux. **⌘K decision:** the CRM palette already owns Ctrl/⌘+K globally (`Modals/GlobalModals.vue`, `ignoreTyping: false`), so rather than a second modal fighting that binding, `composables/modals.js` gained a tiny production-neutral hook — `registerPaletteExtension(provider)` returns `[{ title, items }]` sections for the current query, and `openCommandPalette(scope)` / `commandPaletteScope` let a scoped switcher reuse the one palette (a scope shows extension sections only; it resets on close). `CommandPalette.vue` renders extension sections after Commands and before record hits; with no provider registered it is inert. `TalkShortcuts.vue` registers the Talk provider on mount and removes it on unmount.

Gating: modifier combos work while typing (they cannot be plain text); bare ⌥+arrows stay out of inputs/textareas/contenteditable (macOS moves by word with them); Esc acts only on a Talk page and only when focus is nowhere or in the Talk composer (`form[data-talk-composer]`), never in some other field; everything stands down while the palette or another dialog is open. ⌘⇧K listens in the capture phase and stops propagation so the palette's own ⌘K toggle does not fire a second time.

## Phone settings preview

Sliders → **Phone settings · numbers & recording**, or `/crm/phone-settings-preview`. Native CRM shell, LayoutHeader/Breadcrumbs, quiet settings navigation and Frappe form controls.

- **Numbers & access:** two fictional lines; owner, editable line name, teammate permissions.
- **View / Use / Ring** are independent, visibly explained columns: history/thread visibility; outbound calls/texts using the line; incoming ringing. Owner selection does not silently mutate this preview's matrix. These are proposed controls, not production authorization rules.
- **Recording:** workspace default plus per-line inherit/on/off. Changing workspace default leaves explicit overrides untouched. Consent note explicitly states that the toggle is not legal consent; disclosures, access, retention and consent policy must be settled before real recording.
- **Buy number:** illustrative area-code search (202), select one fictional example, review line name/owner. Stops at **Review only — no order placed**. No availability/provider check or price claim, no purchase action, no real assignments/settings writes.

The sole API introduced by the entire preview is the launcher's read-only `frappe.client.get_list` for one lead ID. Settings, incoming calls, chat and SMS have no API clients or persistent browser storage.

## Validation

```sh
cd frontend
node scripts/test-phone-preview.mjs
node scripts/test-comms-preview.mjs
yarn build
```

Tests: three design selection/defaults; incoming answer/decline and active-call protection; invite retention; history metadata/callback; per-number draft/message routing; per-person chat isolation; bounded anchor geometry at 390/1200px; independent permission/recording fixtures; safe source checks; six Vue SFCs compile. The test separately compiles DEV-only surfaces, since a production build may omit their reachable routes.

Browser review: compare A/B/C on a real lead at 1200px and 390px; inspect B's split/thread mobile transition; incoming Answer and Decline; pending incoming while active; live-one join; anchored teammate chat and roster scrolling/resize; History→Text/send; settings recording/permissions and Buy search→review. Verify left minimize and feedback-tab clearance, and preserve real CRM width. No actual carrier/audio/reliability behavior is implemented or proven.
