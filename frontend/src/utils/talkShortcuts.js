// Mattermost-style keyboard navigation for the D · Left nav comms mockup.
// Pure: conversation ordering, prev/next (incl. unread), fuzzy matching and
// the event → action classifier all live here so the DOM binding
// (`components/Telephony/TalkShortcuts.vue`) stays a thin switch statement.
//
// ⌘K is NOT bound here. The CRM's command palette already owns Ctrl/⌘+K
// (`Modals/GlobalModals.vue`), so Talk conversations are offered INSIDE it as
// a section (`talkPaletteSections`) instead of fighting the binding.
// Ctrl/⌘+Shift+K opens the same palette scoped to DMs.
import { fuzzyScore } from './fuzzy.js'
import { previewTeammates } from './phonePreview.js'
import { STANDUP_ID, talkSlug } from './commsPreview.js'

// The list in left-column order: Live (newest first, calls still in progress),
// then the pinned Standup, channels, direct messages. Alt+↑/↓ walk this order.
export function talkConversations(comms, phone) {
  const ended = phone?.endedIds || []
  const live = [...comms.events]
    .filter(event => event.call && !ended.includes(event.call.id))
    .sort((a, b) => b.sequence - a.sequence)
    .map(event => ({ kind: 'live', id: event.id, label: `${event.call.rep} · ${event.call.name}`, group: 'Live', unread: 0, keywords: `live call ${event.kind === 'live_one' ? 'live one' : ''}` }))
  const standup = [{ kind: 'standup', id: STANDUP_ID, label: 'Standup', group: 'Channels', unread: 0, keywords: 'pinned digest today' }]
  const channels = Object.entries(comms.channels).map(([name, channel]) => ({ kind: 'channel', id: name, label: name, group: 'Channels', unread: channel.unread, keywords: `channel ${name.slice(1)}` }))
  const dms = previewTeammates.map(name => ({ kind: 'dm', id: name, label: name, group: 'Direct messages', unread: comms.dmUnread[name] || 0, keywords: 'dm direct message' }))
  return [...live, ...standup, ...channels, ...dms]
}

export function talkIndex(list, current) {
  if (!current) return -1
  return list.findIndex(item => item.kind === current.kind && talkSlug(item.kind, item.id) === String(current.id ?? ''))
}

// Wraps. From nowhere (not on a Talk page) Alt+↓ goes to the first item and
// Alt+↑ to the last — the same as Mattermost from the landing view.
export function nextTalk(list, current, delta = 1) {
  if (!list.length) return null
  const index = talkIndex(list, current)
  if (index === -1) return delta > 0 ? list[0] : list[list.length - 1]
  return list[(index + delta + list.length) % list.length]
}

// Next conversation with something unread, skipping the current one. Null when
// nothing is unread — the caller should do nothing rather than move.
export function nextUnreadTalk(list, current, delta = 1) {
  if (!list.length) return null
  const n = list.length
  const start = talkIndex(list, current)
  for (let step = 1; step <= n; step++) {
    const index = (((start + step * delta) % n) + n) % n
    if (index !== start && list[index].unread > 0) return list[index]
  }
  return null
}

// Fuzzy over label + keywords, ranked; `scope: 'dm'` narrows to direct messages.
export function matchTalk(list, query = '', { scope = null } = {}) {
  const pool = scope === 'dm' ? list.filter(item => item.kind === 'dm') : list
  const q = (query || '').trim()
  if (!q) return pool.slice()
  return pool
    .map(item => ({ item, score: fuzzyScore(`${item.label} ${item.keywords}`, q) }))
    .filter(entry => entry.score !== null)
    .sort((a, b) => b.score - a.score)
    .map(entry => entry.item)
}

// Command-palette sections for the Talk entries. `scope === 'dm'` is the
// ⌘⇧K DM switcher: one section, DMs only. Otherwise one "Talk" section
// (empty query keeps left-column order; a query ranks by fuzzy score).
export function talkPaletteSections(list, query = '', scope = null) {
  const items = matchTalk(list, query, { scope })
  if (!items.length) return []
  return [{ title: scope === 'dm' ? 'Direct messages' : 'Talk', items }]
}

// Is `el` somewhere the user is typing? Element-like duck typing so it can be
// unit-tested without a DOM.
export function isTypingTarget(el) {
  if (!el) return false
  const tag = el.tagName
  return !!(el.isContentEditable || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (el.closest && el.closest('[contenteditable="true"]')))
}

export const talkShortcutList = [
  { keys: ['⌘', 'K'], label: 'Find a conversation — Talk section in the command palette' },
  { keys: ['⌘', '⇧', 'K'], label: 'Direct message switcher' },
  { keys: ['⌥', '↑'], label: 'Previous conversation' },
  { keys: ['⌥', '↓'], label: 'Next conversation' },
  { keys: ['⌥', '⇧', '↑'], label: 'Previous unread conversation' },
  { keys: ['⌥', '⇧', '↓'], label: 'Next unread conversation' },
  { keys: ['⌘', '⇧', 'L'], label: 'Focus the message box' },
  { keys: ['Esc'], label: 'Mark read and leave the message box' },
  { keys: ['⌘', '/'], label: 'This shortcuts sheet' },
]

// Classify a keydown into an action, or null. Rules: modifier combos work even
// while typing (they cannot be plain text); bare Alt+arrows do not fire inside
// a field (macOS uses them to move by word); Escape only acts on a Talk page,
// and only when focus is nowhere or in the Talk composer itself.
export function shortcutFor(event, { typing = false, onTalkPage = false, inComposer = false } = {}) {
  const key = String(event.key || '')
  const lower = key.toLowerCase()
  const primary = !!(event.metaKey || event.ctrlKey)
  if (primary && event.shiftKey && lower === 'k') return 'dm-switcher'
  if (primary && event.shiftKey && lower === 'l') return onTalkPage ? 'focus-composer' : null
  if (primary && key === '/') return 'help'
  if (event.altKey && !primary && (key === 'ArrowUp' || key === 'ArrowDown')) {
    if (typing) return null
    const dir = key === 'ArrowDown' ? 'next' : 'prev'
    return event.shiftKey ? `${dir}-unread` : dir
  }
  if (key === 'Escape' && !primary && !event.altKey && !event.shiftKey) {
    if (!onTalkPage) return null
    return !typing || inComposer ? 'escape' : null
  }
  return null
}
