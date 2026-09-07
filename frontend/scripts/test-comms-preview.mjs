// Comms mockup checks: state rules, geometry rules, and that no surface can
// reach an API, storage, notification, audio or Mattermost. Run with node.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import {
  commsDesigns, newCommsPreview, selectCommsDesign, filteredInbox, commsUnreadCount, markCommsRead, markAllCommsRead,
  replyCommsItem, resolveCommsLiveOne, postLeadThread, postChannel, openChannel, channelUnreadTotal,
  mentionQuery, mentionCandidates, insertMention, railMode, railReservedWidth, RAIL_WIDTH, RAIL_COLLAPSED_WIDTH, inboxFilters,
  navGroups, navWidth, toggleNavGroup, navUnread, navUnreadTotal, dmUnreadTotal, openNavItem, NAV_WIDTH, NAV_COLLAPSED_WIDTH,
  talkKinds, talkSlug, talkRoute, resolveTalk, isTalkActive, STANDUP_ID,
} from '../src/utils/commsPreview.js'
import { newPhonePreview, previewCalls, previewTeamCall, previewJoinOutcome, startPreviewCall, sendPreviewChat, previewTeammates, endPreviewTeamCall } from '../src/utils/phonePreview.js'
import { talkConversations, talkIndex, nextTalk, nextUnreadTalk, matchTalk, talkPaletteSections, shortcutFor, isTypingTarget, talkShortcutList } from '../src/utils/talkShortcutsPreview.js'
import { WORKSPACE_DEFAULT_KEY, workspaceVersions, currentWorkspace, workspaceMenuLabel, applyWorkspace, toggleWorkspace, nextWorkspaceQuery, classicWorkspaceQuery, NEXT_PHONE_DESIGN, NEXT_COMMS_DESIGN } from '../src/utils/workspaceVersion.js'

// Design selection
{
  const c = newCommsPreview()
  assert.equal(c.design, null, 'comms mockup is off until chosen')
  assert.deepEqual(Object.keys(commsDesigns), ['A', 'B', 'C', 'D'])
  assert.equal(selectCommsDesign(c, 'Z'), false)
  assert.equal(selectCommsDesign(c, 'A'), true)
  assert.equal(c.open, false, 'inbox waits for the bell')
  assert.equal(selectCommsDesign(c, 'B'), true)
  assert.equal(c.open, true, 'drawer opens on selection')
  assert.equal(selectCommsDesign(c, 'C'), true)
  assert.equal(c.railCollapsed, false)
  assert.equal(selectCommsDesign(c, 'D'), true)
  assert.equal(c.open, false, 'left nav opens no overlay: conversations are pages')
  assert.equal(c.navCollapsed, false)
  assert.equal(selectCommsDesign(c, null), true)
  assert.equal(c.design, null)
}

// D: left nav groups collapse, unread rolls up, picking ROUTES to a page and reads, DMs share the phone chats
{
  const c = newCommsPreview()
  const p = newPhonePreview()
  selectCommsDesign(c, 'D')
  assert.deepEqual(navGroups, ['crm', 'live', 'channels', 'dms'])
  assert.ok(navGroups.every(group => c.navOpen[group] === true), 'every group starts open')
  assert.equal(toggleNavGroup(c, 'nope'), false)
  assert.equal(toggleNavGroup(c, 'crm'), true)
  assert.equal(c.navOpen.crm, false, 'the CRM links collapse like any channel')
  assert.equal(c.navOpen.live, true, 'other groups untouched')
  toggleNavGroup(c, 'crm')
  assert.equal(c.navOpen.crm, true)
  // Unread rollup: live = calls in progress (caller supplied), channels = badge sum, dms = fictional unread, crm = never.
  assert.equal(navUnread(c, 'crm', 5), 0)
  assert.equal(navUnread(c, 'live', 2), 2)
  assert.equal(navUnread(c, 'channels'), channelUnreadTotal(c))
  assert.equal(navUnread(c, 'dms'), 1)
  assert.equal(dmUnreadTotal(c), 1)
  assert.equal(navUnreadTotal(c, 2), 2 + 3 + 1)
  // Picking reads; nothing is stored as "open" — the route is the selection.
  assert.equal(openNavItem(c, 'channel', '#nope'), false)
  assert.equal(openNavItem(c, 'dm', 'Nobody'), false)
  assert.equal(openNavItem(c, 'live', 'ev-offer'), false, 'an offer is not joinable, so it is not a live page')
  assert.equal(openNavItem(c, 'standup', 'yesterday'), false)
  assert.equal(openNavItem(c, 'bogus', 'x'), false)
  assert.equal(openNavItem(c, 'channel', '#acquisitions'), true)
  assert.equal(c.channels['#acquisitions'].unread, 0, 'opening a channel reads it')
  assert.equal(navUnread(c, 'channels'), 1)
  assert.equal(openNavItem(c, 'dm', 'Exe'), true)
  assert.equal(c.dmUnread.Exe, 0, 'opening a DM reads it')
  assert.equal(navUnread(c, 'dms'), 0)
  assert.equal(openNavItem(c, 'live', 'ev-live'), true)
  assert.equal(openNavItem(c, 'standup', STANDUP_ID), true)
  assert.equal(c.open, false, 'D never opens an overlay')
  assert.equal(Object.hasOwn(c, 'pane'), false, 'no pane state survives')
  // Route ↔ item mapping. The route carries the preview query so a reload keeps the mockup on.
  assert.deepEqual(talkKinds, ['channel', 'dm', 'live', 'standup'])
  assert.equal(talkSlug('channel', '#acquisitions'), 'acquisitions', 'channel slug drops the #')
  assert.equal(talkSlug('dm', 'Germán'), 'Germán')
  assert.deepEqual(talkRoute('channel', '#ops-bot', { phonePreview: '1', commsDesign: 'D' }), { name: 'Talk', params: { kind: 'channel', id: 'ops-bot' }, query: { phonePreview: '1', commsDesign: 'D' } })
  assert.deepEqual(talkRoute('dm', 'Exe'), { name: 'Talk', params: { kind: 'dm', id: 'Exe' }, query: {} })
  assert.deepEqual(resolveTalk(c, { kind: 'channel', id: 'acquisitions' }), { kind: 'channel', id: '#acquisitions' })
  assert.deepEqual(resolveTalk(c, { kind: 'dm', id: 'Germán' }), { kind: 'dm', id: 'Germán' })
  assert.deepEqual(resolveTalk(c, { kind: 'live', id: 'ev-live' }), { kind: 'live', id: 'ev-live' })
  assert.deepEqual(resolveTalk(c, { kind: 'standup', id: STANDUP_ID }), { kind: 'standup', id: STANDUP_ID })
  assert.equal(resolveTalk(c, { kind: 'channel', id: 'nope' }), null, 'unknown channel resolves to nothing')
  assert.equal(resolveTalk(c, { kind: 'dm', id: 'Nobody' }), null)
  assert.equal(resolveTalk(c, { kind: 'live', id: 'ev-offer' }), null, 'an offer event is not a call')
  assert.equal(resolveTalk(c, { kind: 'live', id: 'ev-live' }, ['demo-exe']), null, 'an ended call has no page')
  assert.equal(resolveTalk(c, { kind: 'standup', id: 'yesterday' }), null)
  assert.equal(resolveTalk(c, { kind: 'bogus', id: 'x' }), null)
  assert.equal(resolveTalk(c, undefined), null)
  // Reload: resolving the route then opening it lands read, same as a click.
  const reloaded = newCommsPreview()
  const landed = resolveTalk(reloaded, { kind: 'channel', id: 'ops-bot' })
  assert.equal(reloaded.channels['#ops-bot'].unread, 1)
  openNavItem(reloaded, landed.kind, landed.id)
  assert.equal(reloaded.channels['#ops-bot'].unread, 0, 'landing on a channel page reads it')
  // Active highlight is read off the route, like SidebarLink.
  assert.equal(isTalkActive({ kind: 'channel', id: 'acquisitions' }, 'channel', '#acquisitions'), true)
  assert.equal(isTalkActive({ kind: 'channel', id: 'acquisitions' }, 'channel', '#dispo'), false)
  assert.equal(isTalkActive({ kind: 'dm', id: 'Exe' }, 'dm', 'Exe'), true)
  assert.equal(isTalkActive({ kind: 'dm', id: 'Exe' }, 'channel', 'Exe'), false, 'kind must match too')
  assert.equal(isTalkActive(undefined, 'dm', 'Exe'), false)
  // The page's DM composer IS the phone chat: a draft typed there is what the team-bar chat shows.
  const dm = resolveTalk(c, { kind: 'dm', id: 'Germán' })
  p.chats[dm.id].draft = 'typed on the talk page'
  assert.equal(p.chats['Germán'].draft, 'typed on the talk page')
  p.chatUser = dm.id
  assert.equal(sendPreviewChat(p), true)
  assert.equal(p.chats['Germán'].messages.at(-1).text, 'typed on the talk page')
  assert.equal(p.chats['Germán'].draft, '')
  assert.equal(p.chats.Exe.messages.length, 1, 'other DMs untouched')
  // Geometry: the column is 260 (48 collapsed); D reserves nothing on the right, ever.
  assert.equal(navWidth(), NAV_WIDTH)
  assert.equal(navWidth(true), NAV_COLLAPSED_WIDTH)
  assert.ok(NAV_WIDTH <= 260 && NAV_COLLAPSED_WIDTH <= 48)
  // Live join from the pane uses the same guard as everywhere else.
  const closer = newPhonePreview()
  closer.previewLead = 'CRM-LEAD-2026-00008'
  const live = c.events.find(e => e.id === 'ev-live')
  assert.equal(previewJoinOutcome(closer, previewTeamCall(closer, live.call), () => startPreviewCall(closer, 'closer', live.call), '/crm/leads/x'), '/leads/CRM-LEAD-2026-00008/comps')
}

// Inbox: filters, unread, read marks, replies
{
  const c = newCommsPreview()
  assert.deepEqual(inboxFilters, ['All', 'Live ones', 'Mentions', 'DMs', 'Bots'])
  const all = filteredInbox(c)
  assert.ok(all.length >= 5)
  assert.ok(all.every((item, i) => i === 0 || item.sequence <= all[i - 1].sequence), 'newest first')
  assert.equal(commsUnreadCount(c), 3)
  c.filter = 'Live ones'
  assert.ok(filteredInbox(c).every(item => item.kind === 'live_one'))
  assert.equal(commsUnreadCount(c, 'Live ones'), 1)
  c.filter = 'Bots'
  assert.deepEqual([...new Set(filteredInbox(c).map(item => item.kind))].sort(), ['bot', 'refund', 'standup'])
  assert.equal(commsUnreadCount(c, 'Bots'), 0)
  c.filter = 'All'
  const live = c.inbox.find(item => item.kind === 'live_one')
  assert.equal(live.call, previewCalls[0], 'inbox live-one is the same team call the phone bar shows')
  assert.equal(markCommsRead(c, 'nope'), false)
  assert.equal(replyCommsItem(c, 'in-dm-exe'), false, 'blank reply refused')
  const dm = c.inbox.find(item => item.id === 'in-dm-exe')
  dm.draft = '  On it — 5 min.  '
  assert.equal(replyCommsItem(c, 'in-dm-exe'), true)
  assert.deepEqual(dm.replies.map(r => r.text), ['On it — 5 min.'])
  assert.equal(dm.draft, '')
  assert.equal(dm.read, true, 'replying reads the item')
  assert.equal(commsUnreadCount(c), 2)
  assert.equal(resolveCommsLiveOne(c, live.id), true)
  assert.ok(c.inbox.includes(live), 'handled live-one stays as a record, read')
  markAllCommsRead(c)
  assert.equal(commsUnreadCount(c), 0)
  assert.ok(c.inbox.find(item => item.kind === 'standup').digest.length === 3, 'standup carries a per-person digest')
}

// Inbox live-one join uses the phone's guard: blocked while on a call, lands on comps otherwise
{
  const c = newCommsPreview()
  const p = newPhonePreview()
  const live = c.inbox.find(item => item.kind === 'live_one')
  p.previewLead = 'CRM-LEAD-2026-00008'
  const call = previewTeamCall(p, live.call)
  assert.equal(previewJoinOutcome(p, call, () => startPreviewCall(p, 'closer', live.call), '/crm/leads/x'), '/leads/CRM-LEAD-2026-00008/comps')
  assert.equal(p.role, 'closer')
  assert.equal(p.minimized, true, 'phone tucks away so the comps page is clear')
  const busy = newPhonePreview()
  busy.previewLead = 'CRM-LEAD-2026-00008'
  startPreviewCall(busy, 'rep')
  const before = busy.call
  assert.equal(previewJoinOutcome(busy, previewTeamCall(busy, live.call), () => startPreviewCall(busy, 'closer', live.call), ''), null, 'no navigation on a blocked join')
  assert.equal(busy.call, before, 'active call untouched')
  const cold = newPhonePreview()
  assert.equal(previewJoinOutcome(cold, previewTeamCall(cold, previewCalls[1]), () => startPreviewCall(cold, 'closer', previewCalls[1]), ''), null, 'unlinked call joins but stays put')
  assert.equal(cold.call.id, 'demo-german')
}

// B: lead thread, @mentions, DMs shared with the phone chats
{
  const c = newCommsPreview()
  const p = newPhonePreview()
  assert.equal(c.thread, 'lead')
  assert.equal(postLeadThread(c), false)
  const n = c.leadThread.messages.length
  c.leadThread.draft = 'Roof is 2019 — dropping to Paint & carpet. @Dennis'
  assert.equal(postLeadThread(c), true)
  assert.equal(c.leadThread.messages.length, n + 1)
  assert.equal(c.leadThread.messages.at(-1).author, 'You')
  assert.equal(c.leadThread.draft, '')
  assert.equal(mentionQuery('hello'), null)
  assert.equal(mentionQuery('ping @'), '')
  assert.equal(mentionQuery('ping @De'), 'De')
  assert.equal(mentionQuery('email me@x.com'), null, 'an @ inside a word is not a mention')
  assert.equal(mentionQuery('@Dennis done'), null, 'a completed mention closes the menu')
  assert.deepEqual(mentionCandidates(''), ['Exe', 'Germán', 'Dennis'])
  assert.deepEqual(mentionCandidates('ge'), ['Germán'])
  assert.deepEqual(mentionCandidates('zz'), [])
  assert.equal(insertMention('ping @De', 'Dennis'), 'ping @Dennis ')
  assert.ok(c.standup.pinned && c.standup.lines.length >= 4)
  // DM through B is the phone's chat: one source of truth per person.
  p.chatUser = 'Exe'
  p.chats.Exe.draft = 'from the drawer'
  assert.equal(sendPreviewChat(p), true)
  assert.equal(p.chats.Exe.messages.at(-1).text, 'from the drawer')
  assert.equal(p.chats['Germán'].messages.length, 1, 'other teammates untouched')
}

// C: channels, unread, event feed, rail geometry
{
  const c = newCommsPreview()
  assert.equal(channelUnreadTotal(c), 3)
  assert.equal(openChannel(c, '#nope'), false)
  assert.equal(openChannel(c, '#ops-bot'), true)
  assert.equal(c.channel, '#ops-bot')
  assert.equal(c.channels['#ops-bot'].unread, 0)
  assert.equal(channelUnreadTotal(c), 2)
  assert.equal(postChannel(c), false)
  c.channels['#ops-bot'].draft = 'ack'
  assert.equal(postChannel(c), true)
  assert.equal(c.channels['#ops-bot'].messages.at(-1).author, 'You')
  assert.ok(c.events.some(e => e.kind === 'live_one' && e.call === previewCalls[0]))
  assert.ok(c.events.some(e => e.kind === 'call' && e.call === previewCalls[1]))
  assert.ok(c.events.filter(e => !e.call).every(e => ['offer', 'refund', 'text'].includes(e.kind)), 'only calls are joinable')
  assert.equal(railMode(1600), 'reserve')
  assert.equal(railMode(1399), 'overlay')
  assert.equal(railMode(1200), 'overlay', 'a 1200px window is never narrowed by the rail')
  assert.equal(railMode(390), 'overlay')
  assert.equal(railMode(1600, true), 'strip')
  assert.equal(railReservedWidth(1600), RAIL_WIDTH)
  assert.equal(railReservedWidth(1200), 0)
  assert.equal(railReservedWidth(390, true), RAIL_COLLAPSED_WIDTH)
  assert.ok(RAIL_WIDTH <= 320 && RAIL_COLLAPSED_WIDTH <= 48)
}

// Sources: compile, and none of them can reach an API, storage, notification, audio or Mattermost.
// Workspace version switch (classic ↔ next). In-memory for the preview; the real
// thing is the per-user Frappe default named by WORKSPACE_DEFAULT_KEY.
{
  assert.equal(WORKSPACE_DEFAULT_KEY, 'crm_workspace_version')
  assert.deepEqual(Object.keys(workspaceVersions), ['classic', 'next'])
  const p = newPhonePreview(), c = newCommsPreview()
  assert.equal(p.workspace, 'classic')
  assert.equal(currentWorkspace(p), 'classic')
  assert.equal(workspaceMenuLabel(p), 'Try the new workspace')
  assert.equal(applyWorkspace(p, c, 'bogus'), false)
  assert.equal(toggleWorkspace(p, c), true)
  assert.equal(currentWorkspace(p), 'next')
  assert.equal(p.enabled, true, 'next turns the preview on')
  assert.equal(p.design, NEXT_PHONE_DESIGN, 'next = phone dock A')
  assert.equal(c.design, NEXT_COMMS_DESIGN, 'next = comms D left nav (Talk routes)')
  assert.equal(p.minimized, true, 'phone dock starts collapsed, not popped open')
  assert.equal(p.workspaceBanner, true, 'first switch shows the how-to-go-back note')
  assert.equal(workspaceMenuLabel(p), 'Back to classic')
  p.workspaceBanner = false
  c.channels['#dispo'].draft = 'unsent'
  assert.equal(toggleWorkspace(p, c), true)
  assert.equal(currentWorkspace(p), 'classic')
  assert.equal(p.enabled, false, 'classic renders no preview component')
  assert.equal(c.design, null)
  assert.equal(c.channels['#dispo'].draft, '', 'classic is a clean production layout, mockup state dropped')
  assert.equal(toggleWorkspace(p, c), true)
  assert.equal(p.workspaceBanner, false, 'banner is first-run only')
  // ?phonePreview=1 stays a dev override: any preview on reads as "next" so
  // "Back to classic" always means the real layout.
  const q = newPhonePreview(); q.enabled = true
  assert.equal(currentWorkspace(q), 'next')
  assert.equal(workspaceMenuLabel(q), 'Back to classic')
  assert.deepEqual(nextWorkspaceQuery({ view: 'x' }), { view: 'x', phonePreview: '1', phoneDesign: 'A', commsDesign: 'D' })
  assert.deepEqual(classicWorkspaceQuery({ view: 'x', phonePreview: '1', phoneDesign: 'A', commsDesign: 'D', phoneIncoming: '1' }), { view: 'x' })
}

// Mattermost-style shortcuts: pure rules.
{
  const c = newCommsPreview(), p = newPhonePreview()
  const list = talkConversations(c, p)
  assert.deepEqual(list.map(item => item.kind), ['live', 'live', 'standup', 'channel', 'channel', 'channel', 'dm', 'dm', 'dm'], 'left-column order: Live, Standup, channels, DMs')
  assert.equal(list[0].id, 'ev-live', 'newest live first')
  assert.deepEqual(list.filter(i => i.kind === 'dm').map(i => i.id), previewTeammates)
  assert.equal(list.find(i => i.id === '#acquisitions').unread, 2)
  assert.equal(list.find(i => i.id === 'Exe' && i.kind === 'dm').unread, 1)
  endPreviewTeamCall(p, 'demo-exe')
  assert.equal(talkConversations(c, p).filter(i => i.kind === 'live').length, 1, 'an ended call leaves the list')
  // index/next/prev with route-shaped params (channel slug has no #)
  assert.equal(talkIndex(list, { kind: 'channel', id: 'acquisitions' }), 3)
  assert.equal(talkIndex(list, null), -1)
  assert.equal(nextTalk(list, null, 1).id, 'ev-live', 'from nowhere, next = first')
  assert.equal(nextTalk(list, null, -1).id, 'Dennis', 'from nowhere, prev = last')
  assert.equal(nextTalk(list, { kind: 'channel', id: 'acquisitions' }, 1).id, '#dispo')
  assert.equal(nextTalk(list, { kind: 'channel', id: 'acquisitions' }, -1).id, 'today')
  assert.equal(nextTalk(list, { kind: 'dm', id: 'Dennis' }, 1).id, 'ev-live', 'wraps')
  assert.equal(nextTalk([], null, 1), null)
  // unread walk: #acquisitions(2) → #ops-bot(1) → Exe(1), wraps, skips current
  assert.equal(nextUnreadTalk(list, null, 1).id, '#acquisitions')
  assert.equal(nextUnreadTalk(list, { kind: 'channel', id: 'acquisitions' }, 1).id, '#ops-bot')
  assert.equal(nextUnreadTalk(list, { kind: 'channel', id: 'ops-bot' }, 1).id, 'Exe')
  assert.equal(nextUnreadTalk(list, { kind: 'dm', id: 'Exe' }, 1).id, '#acquisitions', 'wraps')
  assert.equal(nextUnreadTalk(list, { kind: 'channel', id: 'acquisitions' }, -1).id, 'Exe', 'prev unread wraps backwards')
  const read = talkConversations(newCommsPreview(), newPhonePreview()).map(i => ({ ...i, unread: 0 }))
  assert.equal(nextUnreadTalk(read, { kind: 'channel', id: 'acquisitions' }, 1), null, 'nothing unread → no move')
  // fuzzy + scope
  assert.deepEqual(matchTalk(list, '').map(i => i.id), list.map(i => i.id), 'empty query keeps column order')
  assert.equal(matchTalk(list, 'acq')[0].id, '#acquisitions')
  assert.ok(matchTalk(list, 'ger').every(i => i.label.startsWith('Germán')), 'both Germán items (his call, his DM) and nothing else')
  assert.equal(matchTalk(list, 'ger', { scope: 'dm' })[0].id, 'Germán')
  assert.ok(matchTalk(list, 'zzzz').length === 0)
  assert.ok(matchTalk(list, 'e', { scope: 'dm' }).every(i => i.kind === 'dm'), 'dm scope never leaks a channel')
  assert.deepEqual(talkPaletteSections(list, '', 'dm').map(s => s.title), ['Direct messages'])
  assert.equal(talkPaletteSections(list, '', 'dm')[0].items.length, 3)
  assert.deepEqual(talkPaletteSections(list, 'ops').map(s => [s.title, s.items[0].id]), [['Talk', '#ops-bot']])
  assert.deepEqual(talkPaletteSections(list, 'zzzz'), [])
  // typing detection is DOM-free
  assert.equal(isTypingTarget(null), false)
  assert.equal(isTypingTarget({ tagName: 'DIV' }), false)
  assert.equal(isTypingTarget({ tagName: 'TEXTAREA' }), true)
  assert.equal(isTypingTarget({ tagName: 'DIV', isContentEditable: true }), true)
  // event → action classifier
  const ev = (key, mods = {}) => ({ key, metaKey: false, ctrlKey: false, altKey: false, shiftKey: false, ...mods })
  assert.equal(shortcutFor(ev('k', { metaKey: true })), null, '⌘K is the palette\u2019s own binding, never rebound here')
  assert.equal(shortcutFor(ev('K', { metaKey: true, shiftKey: true }), { typing: true }), 'dm-switcher', '⌘⇧K works while typing')
  assert.equal(shortcutFor(ev('K', { ctrlKey: true, shiftKey: true })), 'dm-switcher', 'Ctrl on Windows/Linux')
  assert.equal(shortcutFor(ev('L', { metaKey: true, shiftKey: true }), { onTalkPage: true, typing: true }), 'focus-composer')
  assert.equal(shortcutFor(ev('L', { metaKey: true, shiftKey: true }), { onTalkPage: false }), null, 'no composer to focus off a Talk page')
  assert.equal(shortcutFor(ev('/', { metaKey: true })), 'help')
  assert.equal(shortcutFor(ev('ArrowDown', { altKey: true })), 'next')
  assert.equal(shortcutFor(ev('ArrowUp', { altKey: true })), 'prev')
  assert.equal(shortcutFor(ev('ArrowDown', { altKey: true, shiftKey: true })), 'next-unread')
  assert.equal(shortcutFor(ev('ArrowUp', { altKey: true, shiftKey: true })), 'prev-unread')
  assert.equal(shortcutFor(ev('ArrowDown', { altKey: true }), { typing: true }), null, 'Alt+arrow stays out of text fields')
  assert.equal(shortcutFor(ev('ArrowDown', { altKey: true, metaKey: true })), null)
  assert.equal(shortcutFor(ev('ArrowDown')), null, 'bare arrows are never captured')
  assert.equal(shortcutFor(ev('Escape'), { onTalkPage: true }), 'escape')
  assert.equal(shortcutFor(ev('Escape'), { onTalkPage: true, typing: true, inComposer: true }), 'escape', 'Esc from the Talk composer')
  assert.equal(shortcutFor(ev('Escape'), { onTalkPage: true, typing: true, inComposer: false }), null, 'Esc in another field is not ours')
  assert.equal(shortcutFor(ev('Escape'), { onTalkPage: false }), null)
  assert.equal(shortcutFor(ev('a')), null)
  assert.ok(talkShortcutList.length >= 8 && talkShortcutList.every(s => s.keys.length && s.label), 'help sheet lists every shortcut')
}

// Production files touched for the switch + palette hook: gated, no preview
// imports in the static graph, hook is inert without a registered provider.
{
  const modals = readFileSync(new URL('../src/composables/modals.js', import.meta.url), 'utf8')
  assert.match(modals, /export const commandPaletteScope = ref\(null\)/)
  assert.match(modals, /export function registerPaletteExtension\(provider\)/)
  assert.match(modals, /export function openCommandPalette\(scope = null\)/)
  assert.doesNotMatch(modals, /Preview|talk/i, 'the hook knows nothing about the preview')
  const palette = readFileSync(new URL('../src/components/CommandPalette.vue', import.meta.url), 'utf8')
  assert.match(palette, /paletteExtensions\.value\.flatMap/, 'palette renders registered extension sections')
  assert.match(palette, /if \(scope\.value\) return extensionSections\.value/, 'a scope narrows to extension sections only (⌘⇧K DM switcher)')
  assert.match(palette, /onBeforeUnmount\(\(\) => \{ commandPaletteScope\.value = null \}\)/, 'scope resets on close')
  assert.doesNotMatch(palette, /talkShortcuts|commsPreview|phonePreview/, 'palette does not import the preview')
  const dropdown = readFileSync(new URL('../src/components/UserDropdown.vue', import.meta.url), 'utf8')
  assert.match(dropdown, /if \(import\.meta\.env\.DEV\) \{[\s\S]*?import\('@\/composables\/workspaceSwitch'\)/, 'switch item is DEV-gated behind a dynamic import')
  assert.doesNotMatch(dropdown, /^import .*(workspaceVersion|phonePreview|commsPreview)/m, 'no static preview import in a production component')
  assert.match(dropdown, /crm_workspace_version/, 'the real per-user default is named in the code comment')
  for (const file of ['components/CommandPalette.vue', 'components/UserDropdown.vue']) {
    const source = readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8')
    const { descriptor, errors } = parse(source, { filename: file })
    assert.deepEqual(errors, [])
    const script = compileScript(descriptor, { id: file })
    const template = compileTemplate({ source: descriptor.template.content, filename: file, id: file, compilerOptions: { bindingMetadata: script.bindings } })
    assert.deepEqual(template.errors, [], `${file} compiles`)
  }
  const sw = readFileSync(new URL('../src/composables/workspaceSwitch.js', import.meta.url), 'utf8')
  assert.doesNotMatch(sw, /^import .*vue-router/m, 'created after setup: route/router are passed in, never injected')
  assert.match(sw, /useWorkspaceSwitch\(\{ route, router \}\)/)
  assert.doesNotMatch(sw, /\b(fetch|createResource|set_default|localStorage)\b|\bcall\(/, 'the switch writes nothing to the server yet')
}

for (const file of ['components/Telephony/CommsPreviewWidget.vue', 'components/Telephony/CommsInbox.vue', 'components/Telephony/CommsLeadThread.vue', 'components/Telephony/CommsRail.vue', 'components/Telephony/CommsLeftNav.vue', 'pages/TalkPreview.vue', 'components/Telephony/PhonePreviewWidget.vue', 'components/Telephony/TalkShortcuts.vue']) {
  const source = readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8')
  const { descriptor, errors } = parse(source, { filename: file })
  assert.deepEqual(errors, [], file)
  const script = compileScript(descriptor, { id: file })
  const template = compileTemplate({ source: descriptor.template.content, filename: file, id: file, compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(template.errors, [], file)
  assert.doesNotMatch(source, /\b(fetch|createResource|createDocumentResource|localStorage|sessionStorage|Notification|AudioContext)\b|crm\.integrations|@telnyx|requestPermission|mattermost_(token|base|user)|api\/v4\/|mmctl|live_one\.alert|\bcall\(/, `${file} has no API/notification/audio/Mattermost reach`)
  for (const button of source.matchAll(/<button\b[^>]*>([\s\S]*?)<\/button>/g)) {
    assert.doesNotMatch(button[1], /<(button|Button)\b/, `${file}: no nested buttons`)
  }
  if (file.endsWith('CommsPreviewWidget.vue')) {
    assert.match(source, /realNotificationsVisible\.value = false/, 'A intercepts the real bell instead of editing AppSidebar')
    assert.match(source, /flush: 'sync'/, 'intercept before the real panel paints')
    assert.match(source, /key !== 'Escape'/, 'Escape closes overlays')
    assert.match(source, /emit\('reserve'/)
    assert.doesNotMatch(source, /CommsNavPane|paneReservedWidth|closeNavPane/, 'D has no right pane and reserves nothing on the right')
    assert.match(source, /left: navShift\.value/, 'D shifts the real sidebar under the column via reserve, never by editing it')
    assert.match(source, /<Teleport v-else-if="mobileNavTarget"/, 'mobile nav lives inside the real drawer panel')
  }
  if (file.endsWith('CommsLeftNav.vue')) {
    assert.match(source, /applySidebarConfig\(settings\.value\?\.custom_sidebar_items\)/, 'the CRM group is the real link list')
    assert.match(source, /link\.condition\(\)/, 'real link conditions still apply')
    assert.match(source, /getPublicViews\(\)/)
    assert.match(source, /:aria-expanded="c\.navOpen\[group\.id\]"/, 'groups are buttons with aria-expanded')
    assert.match(source, /navUnread\(c, 'live'/)
    assert.match(source, /openNavItem\(c, kind, id\)/)
    assert.match(source, /router\.push\(talkRoute\(kind, id, route\.query\)\)/, 'picking routes to the page and carries the preview query')
    assert.match(source, /isTalkActive\(route\.params, kind, id\)/, 'active item is read off the route')
    assert.match(source, /pick\('standup', STANDUP_ID\)/, 'Standup is a pinned item under Channels')
    assert.doesNotMatch(source, /c\.pane|c\.open/, 'no pane state')
    assert.match(source, /<UserDropdown /, 'workspace header stays')
    assert.match(source, /toggleNotificationPanel\(\)/, 'the bell stays and drives the real panel')
    assert.doesNotMatch(source, /sidebarCollapsed\b/, 'never writes the real collapse preference')
  }
  if (file.endsWith('TalkPreview.vue')) {
    assert.match(source, /<LayoutHeader>/, 'a normal CRM page: LayoutHeader + Breadcrumbs')
    assert.match(source, /<Breadcrumbs :items="crumbs"/)
    assert.match(source, /resolveTalk\(c, route\.params, p\.endedIds\)/, 'the route is the selection')
    assert.match(source, /watch\(talk, value => \{ if \(value\) openNavItem\(c, value\.kind, value\.id\) \}, \{ immediate: true \}\)/, 'landing reads the conversation (click, back/forward, reload)')
    assert.match(source, /previewJoinOutcome/)
    assert.match(source, /sendPreviewChat/, 'DMs reuse the phone chats')
    assert.match(source, /p\.enabled && c\.design === 'D'/, 'page gates on the preview being on')
    assert.doesNotMatch(source, /position: fixed|railMode|emit\('reserve'|ReservedWidth/, 'nothing floats, nothing reserved')
  }
  if (file.endsWith('CommsInbox.vue')) {
    assert.match(source, /previewJoinOutcome/, 'inbox join shares the phone guard')
    assert.match(source, /inboxFilters/)
    assert.match(source, /onClickOutside/)
  }
  if (file.endsWith('CommsLeadThread.vue')) {
    assert.match(source, /mentionCandidates/)
    assert.match(source, /sendPreviewChat/, 'DMs reuse the phone chats')
    assert.match(source, /replace\(\/\[&<>"'\]\/g/, 'mention highlight escapes before v-html')
  }
  if (file.endsWith('CommsRail.vue')) {
    assert.match(source, /railMode\(/)
    assert.match(source, /previewJoinOutcome/)
    assert.match(source, /mode === 'strip'/, 'collapsed rail is a thin strip')
  }
  if (file.endsWith('PhonePreviewWidget.vue')) {
    assert.match(source, /id="comms-design"/, 'comms selector lives in the existing bottom bar')
    assert.match(source, /previewJoinOutcome\(p, call, start, route\.path\)/, 'team-bar join uses the shared helper')
  }
  if (file.endsWith('CommsPreviewWidget.vue')) {
    assert.match(source, /<TalkShortcuts \/>/, 'the keyboard layer mounts with D')
    assert.match(source, /v-if="p\.workspaceBanner"/, 'first-run banner says how to switch back')
    assert.match(source, /Back to classic/)
  }
  if (file.endsWith('TalkShortcuts.vue')) {
    assert.match(source, /registerPaletteExtension\(/, 'Talk section goes INTO the existing ⌘K palette')
    assert.match(source, /openCommandPalette\('dm'\)/, '⌘⇧K = same palette, DM scope')
    assert.doesNotMatch(source, /=== 'k'|key\.toLowerCase\(\) === 'k'/, 'no second ⌘K binding')
    assert.match(source, /addEventListener\('keydown', onKey, true\)/, 'capture phase, one listener')
    assert.match(source, /shortcutFor\(event, \{ typing: isTypingTarget\(target\), onTalkPage, inComposer \}\)/, 'DOM binding defers every rule to the pure helper')
    assert.match(source, /form\[data-talk-composer\] textarea/, 'composer focus/blur target')
    assert.match(source, /if \(paletteOpen && action !== 'dm-switcher'\) return/, 'stands down while the palette is open')
    assert.match(source, /talkShortcutList/, 'help sheet lists the shortcuts')
    assert.match(source, /unregister\(\)/, 'palette provider is removed on unmount')
  }
  if (file.endsWith('TalkPreview.vue')) assert.match(source, /data-talk-composer/, 'composer is tagged for ⌘⇧L / Esc')
}
console.log('Comms preview: A inbox (filters/unread/reply/live-one guard), B lead thread (@mentions, shared DMs, pinned standup), C rail (channels/events/geometry), D left nav (group collapse/unread rollup/route↔item mapping/read-on-land/active highlight/shared DM drafts/no right pane), workspace switch (classic↔next, first-run banner, dev-override query), Talk shortcuts (column order, prev/next/unread, fuzzy + DM scope, event classifier, palette hook), ten Vue SFCs compile, no API/notification/audio/Mattermost reach.')
