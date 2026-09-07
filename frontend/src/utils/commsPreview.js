// Comms design mockup fixtures: what replacing Mattermost inside the CRM could
// look like. Everything here is fictional and in memory. No API, storage,
// notification, audio or Mattermost calls. Teammate DMs deliberately reuse the
// phone preview's per-person chats so the two surfaces cannot drift.
import { previewCalls, previewTeammates } from './phonePreview.js'

export const commsDesigns = { A: 'Inbox', B: 'Talk on the house', C: 'Team rail', D: 'Left nav' }

// Rail C reserves real width only where the CRM can spare it. Below that it
// overlays, so the Lead activity column never gets crushed (measured earlier:
// a reserved rail at 1200px left Activity 130px wide).
export const RAIL_RESERVE_MIN_WIDTH = 1400
export const RAIL_WIDTH = 320
export const RAIL_COLLAPSED_WIDTH = 44
export function railMode(viewportWidth, collapsed = false) {
  if (collapsed) return 'strip'
  return viewportWidth >= RAIL_RESERVE_MIN_WIDTH ? 'reserve' : 'overlay'
}
export function railReservedWidth(viewportWidth, collapsed = false) {
  const mode = railMode(viewportWidth, collapsed)
  return mode === 'reserve' ? RAIL_WIDTH : mode === 'strip' ? RAIL_COLLAPSED_WIDTH : 0
}

// D · Left nav. The real sidebar becomes one Slack-style column: the CRM links
// are a collapsible group like any channel; Live / Channels / DMs sit beside it.
// Picking a conversation ROUTES to a full-width page in the main area (Lance:
// "open up in the middle pane just like normal"), so the lead page is never
// narrowed and nothing floats. The route is the selection: back/forward and
// reload restore the same conversation from its params.
export const NAV_WIDTH = 260
export const NAV_COLLAPSED_WIDTH = 48
export const navGroups = ['crm', 'live', 'channels', 'dms']
export const talkKinds = ['channel', 'dm', 'live', 'standup']
export const STANDUP_ID = 'today'
export function navWidth(collapsed = false) { return collapsed ? NAV_COLLAPSED_WIDTH : NAV_WIDTH }
// Route params are slugs: a channel drops its '#', everything else is its id.
import { talkSlug } from './talkShortcuts.js'
export { talkSlug }
export function talkRoute(kind, id, query = {}) {
  return { name: 'Talk', params: { kind, id: talkSlug(kind, id) }, query }
}
// Resolve a route's params back to the conversation it names, or null when the
// params name nothing (a deleted channel, a call that ended, a typo in the URL).
export function resolveTalk(state, params, endedIds = []) {
  const kind = params?.kind
  const slug = String(params?.id ?? '')
  if (kind === 'channel') { const name = `#${slug}`; return state.channels[name] ? { kind, id: name } : null }
  if (kind === 'dm') return Object.hasOwn(state.dmUnread, slug) ? { kind, id: slug } : null
  if (kind === 'live') return state.events.some(event => event.id === slug && event.call && !endedIds.includes(event.call.id)) ? { kind, id: slug } : null
  if (kind === 'standup') return slug === STANDUP_ID ? { kind, id: STANDUP_ID } : null
  return null
}
export function isTalkActive(params, kind, id) {
  return params?.kind === kind && String(params?.id ?? '') === talkSlug(kind, id)
}
export function toggleNavGroup(state, group) {
  if (!navGroups.includes(group)) return false
  state.navOpen[group] = !state.navOpen[group]
  return true
}
export function dmUnreadTotal(state) { return Object.values(state.dmUnread).reduce((sum, count) => sum + count, 0) }
// Unread rollup per group, shown on the header when the group is collapsed and
// on the icon strip when the whole column is. `liveCount` is the caller's count
// of calls still in progress (the phone owns which ones have ended).
export function navUnread(state, group, liveCount = 0) {
  if (group === 'live') return liveCount
  if (group === 'channels') return channelUnreadTotal(state)
  if (group === 'dms') return dmUnreadTotal(state)
  return 0
}
export function navUnreadTotal(state, liveCount = 0) {
  return navGroups.reduce((sum, group) => sum + navUnread(state, group, liveCount), 0)
}
// Opening a conversation reads it (channel badge / DM unread → 0). A live item
// is a call and the standup is a pinned post, so there is nothing to read. The
// page calls this on mount, so a reload or a back/forward lands read too.
export function openNavItem(state, kind, id) {
  if (kind === 'channel') { if (!openChannel(state, id)) return false }
  else if (kind === 'dm') { if (!Object.hasOwn(state.dmUnread, id)) return false; state.dm = id; state.dmUnread[id] = 0 }
  else if (kind === 'live') { if (!state.events.some(event => event.id === id && event.call)) return false }
  else if (kind === 'standup') { if (id !== STANDUP_ID) return false }
  else return false
  return true
}

export const inboxFilters = ['All', 'Live ones', 'Mentions', 'DMs', 'Bots']
const filterKinds = { 'Live ones': ['live_one'], Mentions: ['mention'], DMs: ['dm'], Bots: ['standup', 'bot', 'refund'] }

export function selectCommsDesign(state, design) {
  if (design === null || design === '' || design === 'off') { Object.assign(state, { design: null, open: false }); return true }
  if (!Object.hasOwn(commsDesigns, design)) return false
  Object.assign(state, { design, open: design !== 'A' && design !== 'D', railCollapsed: false, mentionOpen: false, navCollapsed: false })
  return true
}

export function newCommsPreview() {
  return {
    design: null, open: false, railCollapsed: false, railSection: 'live', filter: 'All', expanded: null,
    thread: 'lead', channel: '#acquisitions', dm: 'Exe', mentionOpen: false, nextSequence: 100,
    // D · Left nav: which groups are open and whether the column is collapsed
    // to icons. The open conversation is the ROUTE, not state. DM unread is
    // fictional (Exe's DM is the same unread one the inbox carries).
    navOpen: { crm: true, live: true, channels: true, dms: true }, navCollapsed: false,
    dmUnread: { 'Exe': 1, 'Germán': 0, 'Dennis': 0 },
    inbox: [
      { id: 'in-live-exe', sequence: 9, kind: 'live_one', from: 'Exe', title: 'Got a live one · Jordan Ellis', body: 'Ready to talk numbers. Can you join?', time: 'Just now', read: false, call: previewCalls[0], replies: [], draft: '' },
      { id: 'in-mention-german', sequence: 8, kind: 'mention', from: 'Germán', title: 'mentioned you on 1842 Willow Bend', body: '@Dennis seller says the roof was replaced in 2019 — does that change the repair tier?', time: '12 min ago', read: false, replies: [], draft: '' },
      { id: 'in-dm-exe', sequence: 7, kind: 'dm', from: 'Exe', title: 'Direct message', body: 'Can you look at my 2pm before I call back?', time: '25 min ago', read: false, replies: [], draft: '' },
      { id: 'in-refund', sequence: 6, kind: 'refund', from: 'Refunds', title: 'ISTL refund credited', body: '1 lead moved to Complete · 4 still Waiting on them.', time: '1 hr ago', read: true, replies: [], draft: '' },
      { id: 'in-standup', sequence: 5, kind: 'standup', from: 'Standup', title: 'Yesterday · streak held (6 days)', body: 'Exe 41 done · 6 skipped. Germán 38 done · 9 skipped. 2 cards carried over. Top skip reason: Already contacted.', time: '5:00 AM', read: true, replies: [], draft: '', digest: [['Exe', '41 done', '6 skipped'], ['Germán', '38 done', '9 skipped'], ['Dennis', '3 offers', '1 signed']] },
      { id: 'in-bot-wallet', sequence: 4, kind: 'bot', from: 'Ops bot', title: 'BatchData wallet low', body: '$11.40 left · about 76 tax pulls. Auto top-up is off.', time: 'Yesterday', read: true, replies: [], draft: '' },
    ],
    // Record-anchored thread (B). The lead is whichever real lead the preview is on.
    leadThread: { draft: '', messages: [
      { sequence: 1, author: 'Exe', text: 'First call done — motivated, wants to close in 30. Price feels soft.', time: 'Today · 10:16 AM' },
      { sequence: 2, author: 'Dennis', text: 'Comps say 185 tops. Ask about the roof before we talk repairs.', time: 'Today · 10:20 AM' },
      { sequence: 3, author: 'Germán', text: '@Dennis roof replaced 2019 per seller. Windows original.', time: 'Today · 10:31 AM' },
    ] },
    standup: { title: 'Standup · today', pinned: true, lines: ['Streak held · 6 days', 'Exe 41 done · 6 skipped', 'Germán 38 done · 9 skipped', '2 cards carried over → on today\'s list', 'Spend: BatchData $11.40 · ISTL balance $1,240 (−$180 vs yesterday)'] },
    // Rail (C) channels + live event feed.
    channels: {
      '#acquisitions': { unread: 2, draft: '', messages: [
        { sequence: 1, author: 'Exe', text: 'Two live ones before lunch. Willow Bend is the real one.', time: '10:40 AM' },
        { sequence: 2, author: 'Dennis', text: 'On it. Sending 178 with a 10-day DD.', time: '10:44 AM' },
      ] },
      '#dispo': { unread: 0, draft: '', messages: [
        { sequence: 1, author: 'Dennis', text: 'Maple Ave under contract — photos Thursday.', time: 'Yesterday' },
      ] },
      '#ops-bot': { unread: 1, draft: '', messages: [
        { sequence: 1, author: 'Ops bot', text: 'Today board closed at 4:00 PM · 87/89 resolved.', time: '4:00 PM' },
        { sequence: 2, author: 'Ops bot', text: 'BatchData wallet low — $11.40 left.', time: '5:00 AM' },
      ] },
    },
    events: [
      { id: 'ev-live', sequence: 12, kind: 'live_one', text: 'Exe flagged a live one · Jordan Ellis', time: 'now', call: previewCalls[0] },
      { id: 'ev-call-german', sequence: 11, kind: 'call', text: 'Germán started a call · (202) 555-0147', time: '2 min', call: previewCalls[1] },
      { id: 'ev-offer', sequence: 10, kind: 'offer', text: 'Dennis sent an offer · $178,000 · Willow Bend', time: '14 min', lead: true },
      { id: 'ev-refund', sequence: 9, kind: 'refund', text: 'Refund credited · 1 lead → Complete', time: '1 hr' },
      { id: 'ev-text', sequence: 8, kind: 'text', text: 'Inbound text · Jordan Ellis: “Yes, after two works.”', time: '1 hr', lead: true },
    ],
  }
}

export function filteredInbox(state) {
  const kinds = filterKinds[state.filter]
  return [...state.inbox].sort((a, b) => b.sequence - a.sequence).filter(item => !kinds || kinds.includes(item.kind))
}
export function commsUnreadCount(state, filter = 'All') {
  const kinds = filterKinds[filter]
  return state.inbox.filter(item => !item.read && (!kinds || kinds.includes(item.kind))).length
}
export function markCommsRead(state, id, read = true) {
  const item = state.inbox.find(entry => entry.id === id)
  if (!item) return false
  item.read = read
  return true
}
export function markAllCommsRead(state) { state.inbox.forEach(item => { item.read = true }) }
export function replyCommsItem(state, id) {
  const item = state.inbox.find(entry => entry.id === id)
  if (!item?.draft.trim()) return false
  item.replies.push({ author: 'You', text: item.draft.trim(), time: 'Just now' })
  item.draft = ''
  item.read = true
  return true
}
// A live-one that ends (or is handled) leaves the inbox as read; nothing is deleted,
// so the record of the alert survives the way a Comment on the lead would.
export function resolveCommsLiveOne(state, id) { return markCommsRead(state, id, true) }

export function postLeadThread(state) {
  if (!state.leadThread.draft.trim()) return false
  state.leadThread.messages.push({ sequence: state.nextSequence++, author: 'You', text: state.leadThread.draft.trim(), time: 'Just now' })
  state.leadThread.draft = ''
  state.mentionOpen = false
  return true
}
export function postChannel(state, name = state.channel) {
  const channel = state.channels[name]
  if (!channel?.draft.trim()) return false
  channel.messages.push({ sequence: state.nextSequence++, author: 'You', text: channel.draft.trim(), time: 'Just now' })
  channel.draft = ''
  return true
}
export function openChannel(state, name) {
  if (!state.channels[name]) return false
  state.channel = name
  state.channels[name].unread = 0
  return true
}
export function channelUnreadTotal(state) { return Object.values(state.channels).reduce((sum, channel) => sum + channel.unread, 0) }

// @mention autocomplete (visual only). The query is the text after the last "@"
// that has no whitespace yet; null means no popover.
export function mentionQuery(text) {
  const match = /(?:^|\s)@([\w-]*)$/.exec(text || '')
  return match ? match[1] : null
}
export function mentionCandidates(query) {
  const q = (query || '').toLowerCase()
  return previewTeammates.filter(name => name.toLowerCase().startsWith(q))
}
export function insertMention(text, name) {
  return (text || '').replace(/@[\w-]*$/, `@${name} `)
}
