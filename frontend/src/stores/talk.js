import { defineStore } from 'pinia'
import { createResource } from 'frappe-ui'
import { computed, reactive, ref } from 'vue'
import { sessionStore } from './session'
import { usersStore } from './users'

/**
 * Talk (channels / DMs / live calls / presence) for the next workspace.
 * One store so the left nav, the Talk page, the phone dock's team bar and the
 * keyboard layer all read the same lists. Everything comes from
 * `crm.api.talk.*` / `crm.api.telephony.*` per docs/next-workspace-build.md,
 * and the `crm_talk` / `crm_talk_read` / `crm_presence` / `crm_telnyx_call`
 * realtime events keep it current. Only mounted when the workspace is `next`.
 */
export const talkStore = defineStore('crm-talk', () => {
  const session = sessionStore()
  const { getUser } = usersStore()

  const channels = createResource({
    url: 'crm.api.talk.list_channels',
    cache: 'crm-talk-channels',
    initialData: [],
    auto: true,
    onError: () => {},
  })
  const presence = createResource({
    url: 'crm.api.talk.presence',
    initialData: {},
    auto: true,
    onError: () => {},
  })
  const activeCalls = createResource({
    url: 'crm.api.telephony.active_calls',
    initialData: [],
    auto: true,
    onError: () => {},
  })

  // Live-one alerts waiting on this user (from `crm_live_one`), newest first.
  const liveOnes = ref([])
  // Collapsed groups in the left column: in memory per session.
  const navOpen = reactive({ crm: true, live: true, channels: true, dms: true })
  const navCollapsed = ref(false)

  const list = computed(() => channels.data || [])
  const channelRows = computed(() => list.value.filter((c) => c.kind === 'channel'))
  const standup = computed(() => list.value.find((c) => c.kind === 'bot' && c.name === 'standup') || null)
  const botRows = computed(() => list.value.filter((c) => c.kind === 'bot' && c.name !== 'standup'))
  const dmRows = computed(() => list.value.filter((c) => c.kind === 'dm'))
  const calls = computed(() => activeCalls.data || [])

  function statusOf(user) {
    if (!user) return 'offline'
    if (calls.value.some((c) => c.rep === user && c.state !== 'ended')) return 'on_call'
    return presence.data?.[user] || 'offline'
  }
  function displayName(user) {
    return getUser(user)?.full_name || user
  }
  function byName(name) {
    return list.value.find((c) => c.name === name) || null
  }
  function unreadOf(kind) {
    const rows = kind === 'dms' ? dmRows.value : kind === 'channels' ? [...channelRows.value, ...botRows.value, ...(standup.value ? [standup.value] : [])] : []
    return rows.reduce((n, c) => n + (c.unread || 0), 0)
  }

  // Ordered conversation list (Live → Standup → channels → bots → DMs); the
  // left column, the ⌘K section and Alt+arrows all walk exactly this.
  const conversations = computed(() => [
    ...calls.value.map((c) => ({
      kind: 'live', id: c.call_log, label: `${displayName(c.rep)} · ${c.lead_name || c.number || 'Unknown'}`,
      group: 'Live', unread: 0, keywords: 'live call', call: c,
    })),
    ...(standup.value ? [{ kind: 'standup', id: standup.value.name, label: 'Standup', group: 'Channels', unread: standup.value.unread || 0, keywords: 'pinned digest today' }] : []),
    ...channelRows.value.map((c) => ({ kind: 'channel', id: c.name, label: `#${c.name}`, group: 'Channels', unread: c.unread || 0, keywords: `channel ${c.title || ''}` })),
    ...botRows.value.map((c) => ({ kind: 'channel', id: c.name, label: `#${c.name}`, group: 'Channels', unread: c.unread || 0, keywords: `bot ${c.title || ''}` })),
    ...dmRows.value.map((c) => ({ kind: 'dm', id: c.name, label: displayName(c.dm_user), group: 'Direct messages', unread: c.unread || 0, keywords: `dm direct message ${c.dm_user || ''}`, user: c.dm_user })),
  ])

  function patchUnread(channel, unread) {
    const row = byName(channel)
    if (row) row.unread = unread
  }

  // Realtime. Listeners are attached once by the shell; a message in a channel
  // we are not looking at bumps its badge, `crm_talk_read` is the server's
  // word on the count, presence and calls refetch (cheap, small).
  let bound = false
  function bind(socket, { onMessage, onIncoming, onLiveOne, onCall } = {}) {
    if (bound || !socket) return
    bound = true
    socket.on('crm_talk', (data) => {
      const row = byName(data?.channel)
      if (row && data?.message?.author !== session.user && !(onMessage && onMessage(data))) {
        row.unread = (row.unread || 0) + 1
      }
      if (row && data?.message?.posted_at) row.last_at = data.message.posted_at
    })
    socket.on('crm_talk_read', (data) => patchUnread(data?.channel, data?.unread || 0))
    socket.on('crm_presence', (data) => {
      if (!presence.data) presence.data = {}
      if (data?.user) presence.data[data.user] = data.status
    })
    socket.on('crm_telnyx_call', (data) => { activeCalls.reload(); onCall && onCall(data) })
    socket.on('crm_incoming', (data) => onIncoming && onIncoming(data))
    socket.on('crm_live_one', (data) => {
      if (!data?.call_log) return
      liveOnes.value = [data, ...liveOnes.value.filter((a) => a.call_log !== data.call_log)]
      onLiveOne && onLiveOne(data)
    })
  }
  function unbind(socket) {
    if (!bound || !socket) return
    bound = false
    for (const event of ['crm_talk', 'crm_talk_read', 'crm_presence', 'crm_telnyx_call', 'crm_incoming', 'crm_live_one']) socket.off(event)
  }
  function dismissLiveOne(callLog) {
    liveOnes.value = liveOnes.value.filter((a) => a.call_log !== callLog)
  }

  return {
    channels, presence, activeCalls, liveOnes, navOpen, navCollapsed,
    list, channelRows, botRows, standup, dmRows, calls, conversations,
    statusOf, displayName, byName, unreadOf, patchUnread, bind, unbind, dismissLiveOne,
  }
})
