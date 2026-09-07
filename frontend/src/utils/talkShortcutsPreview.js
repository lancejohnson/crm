// Preview-only: the fictional conversation list for the D · Left nav mockup,
// in left-column order. Everything else (prev/next/unread, fuzzy, classifier)
// is the shared pure module in ./talkShortcuts.js.
import { previewTeammates } from './phonePreview.js'
import { STANDUP_ID } from './commsPreview.js'
export * from './talkShortcuts.js'

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
