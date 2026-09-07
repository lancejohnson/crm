<template>
  <component :is="Preview" v-if="Preview" />
  <template v-else>
    <LayoutHeader>
      <template #left-header><Breadcrumbs :items="crumbs" /></template>
      <template #right-header><span class="text-xs text-ink-gray-5">{{ caption }}</span></template>
    </LayoutHeader>

    <div v-if="!workspace.isNext" class="mx-auto max-w-xl px-5 py-10">
      <h1 class="text-lg font-semibold text-ink-gray-9">{{ __('Talk is part of the new workspace') }}</h1>
      <p class="mt-2 text-base text-ink-gray-6">{{ workspace.allowed ? __('Switch from your name menu → Try the new workspace.') : __('It is not enabled for your account yet.') }}</p>
    </div>

    <div v-else-if="!talkItem" class="mx-auto max-w-xl px-5 py-10">
      <h1 class="text-lg font-semibold text-ink-gray-9">{{ talk.channels.loading ? __('Loading…') : __('Nothing here') }}</h1>
      <p v-if="!talk.channels.loading" class="mt-2 text-base text-ink-gray-6">{{ __('That conversation does not exist, or the call already ended.') }}</p>
    </div>

    <div v-else class="talk-page">
      <!-- Live call page -->
      <section v-if="kind === 'live'" class="talk-live" :aria-label="__('Live call')">
        <span class="live-dot" :class="{ flagged: !!liveOne }" aria-hidden="true" />
        <h1>{{ liveOne ? __('Got a live one') : __('Live call') }} · {{ liveCall.lead_name || formatPhone(liveCall.number) || __('Unknown number') }}</h1>
        <p class="live-meta">{{ talk.displayName(liveCall.rep) }} · {{ formatPhone(liveCall.number) }} · {{ liveCall.started_at ? timeAgo(liveCall.started_at) : '' }}</p>
        <blockquote v-if="liveOne?.note">“{{ liveOne.note }}”</blockquote>
        <p class="live-hint">{{ compsPath ? __('Joining opens this lead’s comps map so you can price while you listen.') : __('No CRM lead on this call — you stay here.') }}</p>
        <div class="live-actions">
          <Button :variant="liveOne ? 'solid' : 'subtle'" iconLeft="headphones" :disabled="onCall" @click="joinListening">{{ __('Join listening') }}</Button>
          <Button v-if="compsPath" variant="ghost" iconLeft="external-link" @click="router.push(compsPath)">{{ __('Open comps') }}</Button>
          <Button v-if="liveOne" variant="ghost" @click="talk.dismissLiveOne(liveCall.call_log)">{{ __('Mark handled') }}</Button>
        </div>
        <p v-if="onCall" class="live-hint">{{ __('Finish your current call first.') }}</p>
      </section>

      <!-- Channel / DM / standup thread -->
      <template v-else>
        <div ref="scroller" class="talk-scroll" :aria-label="`${title} messages`" @scroll="onScroll">
          <p v-if="thread.loading && !messages.length" class="talk-empty">{{ __('Loading…') }}</p>
          <button v-else-if="hasMore" type="button" class="talk-more" @click="loadMore">{{ __('Load earlier messages') }}</button>
          <p v-if="!thread.loading && !messages.length" class="talk-empty">{{ __('No messages yet.') }}</p>
          <div v-for="m in messages" :key="m.name" class="talk-message" :class="{ mine: m.author === session.user, mm: m.origin === 'mattermost', deleted: m.deleted }">
            <Avatar :label="m.author_name || m.author" :image="getUser(m.author)?.user_image" size="lg" class="avatar" />
            <div class="talk-body">
              <b>{{ m.author_name || talk.displayName(m.author) }}</b> <small :title="m.posted_at">{{ prettyDate(m.posted_at) }}</small><small v-if="m.edited_at" class="edited">· {{ __('edited') }}</small>
              <p v-if="m.deleted" class="deleted-text">{{ __('Message deleted') }}</p>
              <p v-else v-html="renderText(m.text)" />
            </div>
          </div>
        </div>
        <!-- data-talk-composer: the ⌘⇧L / Esc target for the keyboard layer -->
        <form class="talk-compose" data-talk-composer @submit.prevent="send">
          <div class="compose-box">
            <ul v-if="mentionOptions.length" class="mention-menu" role="listbox" :aria-label="__('Mention a teammate')">
              <li v-for="(u, i) in mentionOptions" :key="u.name" role="option" :aria-selected="i === mentionIndex"><button type="button" :class="{ active: i === mentionIndex }" @mousedown.prevent="pickMention(u)">@{{ u.name.split('@')[0] }} <small>{{ u.full_name }}</small></button></li>
            </ul>
            <FormControl v-model="draft" type="textarea" :rows="2" :aria-label="`Message ${title}`" :placeholder="`Message ${title}`" @keydown="onComposerKey" />
          </div>
          <Button type="submit" icon="arrow-up" variant="solid" :disabled="!draft.trim() || posting" :aria-label="kind === 'dm' ? __('Send direct message') : __('Post to channel')" />
        </form>
      </template>
    </div>
  </template>
</template>
<script setup>
/**
 * /talk/:kind/:id — a conversation as a normal main-area page (like Leads or
 * Today). kind ∈ channel | dm | standup | live. Thread from crm.api.talk.thread
 * (older pages on scroll-up), posts via talk.post, mark_read on view, live
 * updates from the `crm_talk` event through talkStore. Live pages come from
 * telephony.active_calls and join through composables/phone.js.
 *
 * In DEV, when the workspace is classic and the phone mockup is switched on,
 * the fictional TalkPreview page takes over (kept out of production bundles).
 */
import LayoutHeader from '@/components/LayoutHeader.vue'
import { Avatar, Breadcrumbs, Button, FormControl, call, createResource } from 'frappe-ui'
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { globalStore } from '@/stores/global'
import { sessionStore } from '@/stores/session'
import { usersStore } from '@/stores/users'
import { workspaceStore } from '@/stores/workspace'
import { talkStore } from '@/stores/talk'
import { formatPhone } from '@/utils/phoneFormat'
import { prettyDate, timeAgo } from '@/utils'
import { mentionQuery, mentionCandidates, insertMention } from '@/utils/talkMentions'
import { phone, onCall, join } from '@/composables/phone'

const route = useRoute()
const router = useRouter()
const session = sessionStore()
const { getUser, users } = usersStore()
const workspace = workspaceStore()
const talk = talkStore()
const { $socket } = globalStore()

// DEV-only mockup takeover. Never imported in production builds.
const Preview = (import.meta.env.DEV && !workspace.isNext && new URLSearchParams(window.location.search).get('phonePreview') === '1')
  ? defineAsyncComponent(() => import('@/pages/TalkPreview.vue'))
  : null

const kind = computed(() => route.params.kind)
const id = computed(() => route.params.id)
const channelRow = computed(() => ['channel', 'dm', 'standup'].includes(kind.value) ? talk.byName(id.value) : null)
const liveCall = computed(() => kind.value === 'live' ? talk.calls.find((c) => c.call_log === id.value) : null)
const liveOne = computed(() => liveCall.value ? talk.liveOnes.find((a) => a.call_log === liveCall.value.call_log) : null)
const talkItem = computed(() => channelRow.value || liveCall.value)
const title = computed(() => {
  if (!talkItem.value) return __('Talk')
  if (kind.value === 'live') return __('Live')
  if (kind.value === 'dm') return talk.displayName(channelRow.value.dm_user)
  if (kind.value === 'standup') return __('Standup')
  return `#${channelRow.value.name}`
})
const crumbs = computed(() => [{ label: __('Talk'), route: { name: 'Talk', params: { kind: 'channel', id: talk.channelRows[0]?.name || 'acquisitions' } } }, { label: title.value }])
const caption = computed(() => {
  if (kind.value === 'dm' && channelRow.value) return { on_call: __('On call'), online: __('Online'), away: __('Away'), offline: __('Offline') }[talk.statusOf(channelRow.value.dm_user)] || ''
  if (kind.value === 'live' && liveCall.value) return liveCall.value.state || ''
  if (kind.value === 'standup') return __('Pinned')
  return messages.value.length ? `${messages.value.length} ${__('messages')}` : ''
})
const compsPath = computed(() => liveCall.value?.lead ? `/leads/${encodeURIComponent(liveCall.value.lead)}/comps` : null)

// Thread
const messages = ref([])
const hasMore = ref(false)
const scroller = ref(null)
const thread = createResource({
  url: 'crm.api.talk.thread',
  onSuccess(data) {
    const incoming = data?.messages || []
    messages.value = thread.params?.before ? [...incoming, ...messages.value] : incoming
    hasMore.value = !!data?.has_more
  },
  onError: () => {},
})
function loadThread() {
  if (!channelRow.value) return
  messages.value = []
  thread.submit({ channel: id.value, limit: 50 })
  call('crm.api.talk.mark_read', { channel: id.value }).then((r) => talk.patchUnread(id.value, r?.unread || 0)).catch(() => {})
}
function loadMore() {
  if (!messages.value.length || thread.loading) return
  thread.submit({ channel: id.value, before: messages.value[0].posted_at, limit: 50 })
}
function onScroll() { if (scroller.value && scroller.value.scrollTop < 40 && hasMore.value) loadMore() }
watch(() => [id.value, channelRow.value?.name], loadThread, { immediate: true })
watch(() => messages.value.length, async (n, prev) => {
  await nextTick()
  if (scroller.value && (!prev || !thread.params?.before)) scroller.value.scrollTop = scroller.value.scrollHeight
}, { immediate: true })

// A message for the open thread is appended and counted as read, not unread.
function onLiveMessage(data) {
  if (data?.channel !== id.value || !data?.message) return false
  const m = data.message
  const i = messages.value.findIndex((x) => x.name === m.name)
  if (i >= 0) messages.value.splice(i, 1, { ...messages.value[i], ...m })
  else messages.value.push(m)
  call('crm.api.talk.mark_read', { channel: id.value }).catch(() => {})
  return true
}
onMounted(() => $socket.on('crm_talk', onLiveMessage))
onBeforeUnmount(() => $socket.off('crm_talk', onLiveMessage))

// Composer + @mentions
const draft = ref('')
const posting = ref(false)
const mentionIndex = ref(0)
const mentionOptions = computed(() => {
  const q = mentionQuery(draft.value)
  return q === null ? [] : mentionCandidates((users.data?.crmUsers || []).filter((u) => u.name !== session.user), q)
})
watch(mentionOptions, () => (mentionIndex.value = 0))
function pickMention(u) { draft.value = insertMention(draft.value, u) }
function onComposerKey(e) {
  if (mentionOptions.value.length) {
    if (e.key === 'ArrowDown') { e.preventDefault(); mentionIndex.value = (mentionIndex.value + 1) % mentionOptions.value.length; return }
    if (e.key === 'ArrowUp') { e.preventDefault(); mentionIndex.value = (mentionIndex.value - 1 + mentionOptions.value.length) % mentionOptions.value.length; return }
    if (e.key === 'Tab' || e.key === 'Enter') { e.preventDefault(); pickMention(mentionOptions.value[mentionIndex.value]); return }
  }
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
}
async function send() {
  const text = draft.value.trim()
  if (!text || posting.value || !channelRow.value) return
  posting.value = true
  try {
    const m = await call('crm.api.talk.post', { channel: id.value, text })
    if (m?.name && !messages.value.some((x) => x.name === m.name)) messages.value.push(m)
    draft.value = ''
  } finally { posting.value = false }
}
function escapeHtml(s) { return String(s || '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])) }
// Plain text with @handles highlighted and URLs linked; no HTML from the server is trusted.
function renderText(text) {
  return escapeHtml(text)
    .replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener" class="underline">$1</a>')
    .replace(/(^|\s)@([\w.-]+)/g, '$1<span class="mention">@$2</span>')
}

// Live
async function joinListening() {
  const c = liveCall.value
  if (!c || onCall.value) return
  const ok = await join(c.call_log, 'monitor', { name: c.lead_name || formatPhone(c.number), lead: c.lead || null })
  if (ok && compsPath.value) { talk.dismissLiveOne(c.call_log); router.push(compsPath.value) }
}
void phone
</script>
<style scoped>
.talk-page { display: flex; flex-direction: column; height: 100%; min-height: 0; color: var(--ink-gray-9, #222); }
.talk-scroll { flex: 1; min-height: 0; overflow-y: auto; padding: 20px 24px; }
.talk-empty { color: var(--ink-gray-5, #777); font-size: 13px; }
.talk-more { display: block; margin: 0 auto 16px; font-size: 12px; color: var(--ink-gray-5, #777); text-decoration: underline; }
.talk-message { display: flex; gap: 12px; margin-bottom: 16px; font-size: 14px; max-width: 760px; }
.talk-message .avatar { flex-shrink: 0; }
.talk-body { min-width: 0; }
.talk-message b { font-weight: 600; }
.talk-message small { margin-left: 6px; font-size: 11px; color: var(--ink-gray-5, #777); }
.talk-message p { margin-top: 2px; line-height: 1.5; white-space: pre-wrap; overflow-wrap: anywhere; }
.talk-message.mine b { color: #1f6b41; }
.talk-message.mm b::after { content: ' · Mattermost'; font-weight: 400; font-size: 10px; color: var(--ink-gray-4, #999); }
.deleted-text { color: var(--ink-gray-4, #999); font-style: italic; }
:deep(.mention) { color: #2d4f9e; background: #2d4f9e14; border-radius: 3px; padding: 0 2px; }
.talk-compose { display: flex; align-items: flex-end; gap: 8px; padding: 12px 24px; border-top: 1px solid var(--outline-gray-1, #eee); }
.compose-box { position: relative; flex: 1; min-width: 0; max-width: 760px; }
.mention-menu { position: absolute; bottom: 100%; left: 0; z-index: 5; min-width: 220px; margin-bottom: 6px; padding: 4px; list-style: none; background: var(--surface-white, #fff); border: 1px solid var(--outline-gray-2, #ddd); border-radius: 8px; box-shadow: 0 8px 24px #0002; }
.mention-menu button { display: flex; gap: 8px; align-items: baseline; width: 100%; padding: 6px 8px; border-radius: 6px; font-size: 13px; text-align: left; }
.mention-menu button.active, .mention-menu button:hover { background: var(--surface-gray-2, #eee); }
.mention-menu small { font-size: 11px; color: var(--ink-gray-5, #777); }
.talk-live { padding: 32px 24px; max-width: 640px; }
.live-dot { display: block; width: 10px; height: 10px; border-radius: 50%; background: #388452; margin-bottom: 16px; }
.live-dot.flagged { background: #d9a536; box-shadow: 0 0 0 4px #d9a53633; }
.talk-live h1 { font-size: 22px; font-weight: 600; letter-spacing: -.4px; line-height: 1.3; }
.live-meta { margin-top: 8px; font-size: 13px; color: var(--ink-gray-5, #777); }
.talk-live blockquote { margin-top: 16px; padding-left: 12px; border-left: 3px solid var(--outline-gray-2, #ddd); font-size: 15px; line-height: 1.5; color: var(--ink-gray-7, #555); }
.live-hint { margin-top: 14px; font-size: 12px; line-height: 1.5; color: var(--ink-gray-5, #777); }
.live-actions { display: flex; gap: 8px; margin-top: 18px; flex-wrap: wrap; }
@media (max-width: 640px) { .talk-scroll, .talk-compose, .talk-live { padding-inline: 14px; } }
</style>
