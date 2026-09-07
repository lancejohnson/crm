<template>
  <LayoutHeader>
    <template #left-header><Breadcrumbs :items="crumbs" /></template>
    <template #right-header><span class="text-xs text-ink-gray-5">{{ caption }}</span></template>
  </LayoutHeader>

  <div v-if="!ready" class="mx-auto max-w-xl px-5 py-10">
    <h1 class="text-lg font-semibold text-ink-gray-9">Talk preview is off</h1>
    <p class="mt-2 text-base text-ink-gray-6">This page belongs to the left-nav comms mockup. Turn the preview on to see the conversation.</p>
    <Button class="mt-4" variant="solid" @click="router.replace({ query: { ...route.query, phonePreview: '1', commsDesign: 'D' } })">Turn the preview on</Button>
  </div>

  <div v-else-if="!talk" class="mx-auto max-w-xl px-5 py-10">
    <h1 class="text-lg font-semibold text-ink-gray-9">Nothing here</h1>
    <p class="mt-2 text-base text-ink-gray-6">That conversation does not exist in the preview, or the call already ended.</p>
    <Button class="mt-4" variant="subtle" iconLeft="hash" @click="router.replace(talkRoute('channel', '#acquisitions', route.query))">Open #acquisitions</Button>
  </div>

  <div v-else class="talk-page">
    <section v-if="talk.kind === 'live' && event" class="talk-live" aria-label="Live call">
      <span class="live-dot" :class="{ flagged: event.kind === 'live_one' }" aria-hidden="true" />
      <h1>{{ event.text }}</h1>
      <p class="live-meta">{{ event.call.rep }} · {{ event.call.number }} · {{ event.time }}</p>
      <blockquote v-if="event.kind === 'live_one'">“Ready to talk numbers. Can you join?”</blockquote>
      <p class="live-hint">{{ compsPath ? 'Joining opens this lead’s comps map so you can price while you listen.' : 'No CRM lead on this call — you stay here.' }}</p>
      <div class="live-actions">
        <Button :variant="event.kind === 'live_one' ? 'solid' : 'subtle'" iconLeft="headphones" :disabled="!!p.call" @click="join">Join listening</Button>
        <Button v-if="compsPath" variant="ghost" iconLeft="external-link" @click="router.push(compsPath)">Open comps</Button>
      </div>
      <p v-if="p.call" class="live-hint">Finish your current call first.</p>
    </section>

    <section v-else-if="talk.kind === 'standup'" class="talk-standup" aria-label="Standup">
      <p class="pinned"><FeatherIcon name="bookmark" class="size-3.5" /> Pinned · posted 5:00 AM</p>
      <h1>{{ c.standup.title }}</h1>
      <ul><li v-for="line in c.standup.lines" :key="line">{{ line }}</li></ul>
      <Button variant="subtle" iconLeft="list" @click="router.push({ name: 'Today', query: route.query })">Open Today board</Button>
    </section>

    <template v-else>
      <div ref="scroller" class="talk-scroll" :aria-label="`${title} messages`">
        <p v-if="!messages.length" class="talk-empty">No messages yet.</p>
        <div v-for="(message, i) in messages" :key="message.sequence ?? i" class="talk-message" :class="{ bot: message.author === 'Ops bot', mine: message.author === 'You' }">
          <span class="avatar">{{ message.author.slice(0, 1) }}</span>
          <div><b>{{ message.author }}</b> <small>{{ message.time }}</small><p>{{ message.text }}</p></div>
        </div>
      </div>
      <!-- data-talk-composer: the ⌘⇧L / Esc target for the keyboard layer -->
      <form class="talk-compose" data-talk-composer @submit.prevent="send">
        <FormControl v-model="thread.draft" type="textarea" :rows="2" :aria-label="`Message ${title}`" :placeholder="`Message ${title}`" @keydown.enter.exact.prevent="send" />
        <Button type="submit" icon="arrow-up" variant="solid" :disabled="!thread.draft.trim()" :aria-label="talk.kind === 'dm' ? 'Send direct message' : 'Post to channel'" />
      </form>
    </template>
    <footer class="talk-foot">Design preview · fictional messages stay in this browser.</footer>
  </div>
</template>
<script setup>
/**
 * D · Left nav conversation page. The route IS the selection: /talk/:kind/:id
 * (channel | dm | live | standup). Renders in the main area like Leads or
 * Today — no floating pane, nothing reserved — so the CRM never gets narrower.
 * DEV-only (router gate); shows a switch-on notice if the preview is off after
 * a reload without its query.
 */
import LayoutHeader from '@/components/LayoutHeader.vue'
import { Breadcrumbs, Button, FeatherIcon, FormControl } from 'frappe-ui'
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { commsPreview as c } from '@/composables/commsPreview'
import { phonePreview as p } from '@/composables/phonePreview'
import { resolveTalk, openNavItem, postChannel, talkRoute } from '@/utils/commsPreview'
import { previewTeamCall, previewJoinDestination, previewJoinOutcome, startPreviewCall, sendPreviewChat, previewCalls } from '@/utils/phonePreview'
const route = useRoute()
const router = useRouter()
const scroller = ref(null)
const ready = computed(() => p.enabled && c.design === 'D')
const talk = computed(() => resolveTalk(c, route.params, p.endedIds))
const event = computed(() => talk.value?.kind === 'live' ? c.events.find(item => item.id === talk.value.id) : null)
const thread = computed(() => talk.value?.kind === 'channel' ? c.channels[talk.value.id] : talk.value?.kind === 'dm' ? p.chats[talk.value.id] : null)
const messages = computed(() => thread.value?.messages || [])
const title = computed(() => {
  if (!talk.value) return 'Talk'
  if (talk.value.kind === 'live') return event.value?.kind === 'live_one' ? 'Live one' : 'Live call'
  if (talk.value.kind === 'standup') return 'Standup'
  return talk.value.id
})
const crumbs = computed(() => [{ label: 'Talk', route: talkRoute('channel', '#acquisitions', route.query) }, { label: title.value }])
const caption = computed(() => {
  if (!talk.value) return ''
  if (talk.value.kind === 'dm') return previewCalls.some(call => call.rep === talk.value.id && !p.endedIds.includes(call.id)) ? 'On call' : 'Available'
  if (talk.value.kind === 'channel') return `${messages.value.length} messages`
  if (talk.value.kind === 'live') return event.value?.time || ''
  return 'Pinned'
})
const compsPath = computed(() => event.value ? previewJoinDestination(previewTeamCall(p, event.value.call)) : null)
// Landing on a conversation reads it — by click, by back/forward, or by reload.
watch(talk, value => { if (value) openNavItem(c, value.kind, value.id) }, { immediate: true })
watch(() => [talk.value?.id, messages.value.length], async () => {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
}, { immediate: true })
function send() {
  if (!talk.value || !thread.value) return
  if (talk.value.kind === 'channel') postChannel(c, talk.value.id)
  else { p.chatUser = talk.value.id; sendPreviewChat(p) }
}
function join() {
  const call = previewTeamCall(p, event.value.call)
  const destination = previewJoinOutcome(p, call, () => startPreviewCall(p, 'closer', event.value.call), route.path)
  if (destination) router.push(destination)
}
</script>
<style scoped>
.talk-page { display: flex; flex-direction: column; height: 100%; min-height: 0; color: var(--ink-gray-9, #222); }
.talk-scroll { flex: 1; min-height: 0; overflow-y: auto; padding: 20px 24px; }
.talk-empty { color: var(--ink-gray-5, #777); font-size: 13px; }
.talk-message { display: flex; gap: 12px; margin-bottom: 16px; font-size: 14px; max-width: 760px; }
.avatar { display: grid; place-items: center; flex-shrink: 0; width: 32px; height: 32px; border-radius: 8px; font-size: 13px; font-weight: 600; background: var(--surface-gray-2, #eee); color: var(--ink-gray-7, #555); }
.talk-message b { font-weight: 600; }
.talk-message small { margin-left: 6px; font-size: 11px; color: var(--ink-gray-5, #777); }
.talk-message p { margin-top: 2px; line-height: 1.5; white-space: pre-wrap; overflow-wrap: anywhere; }
.talk-message.bot b { color: #2d4f9e; }
.talk-message.mine b { color: #1f6b41; }
.talk-compose { display: flex; align-items: flex-end; gap: 8px; padding: 12px 24px; border-top: 1px solid var(--outline-gray-1, #eee); }
.talk-compose > :first-child { flex: 1; min-width: 0; max-width: 760px; }
.talk-foot { padding: 8px 24px; font-size: 10px; color: var(--ink-gray-5, #777); }
.talk-live, .talk-standup { padding: 32px 24px; max-width: 640px; }
.live-dot { display: block; width: 10px; height: 10px; border-radius: 50%; background: #388452; margin-bottom: 16px; }
.live-dot.flagged { background: #d9a536; box-shadow: 0 0 0 4px #d9a53633; }
.talk-live h1, .talk-standup h1 { font-size: 22px; font-weight: 600; letter-spacing: -.4px; line-height: 1.3; }
.live-meta { margin-top: 8px; font-size: 13px; color: var(--ink-gray-5, #777); }
.talk-live blockquote { margin-top: 16px; padding-left: 12px; border-left: 3px solid var(--outline-gray-2, #ddd); font-size: 15px; line-height: 1.5; color: var(--ink-gray-7, #555); }
.live-hint { margin-top: 14px; font-size: 12px; line-height: 1.5; color: var(--ink-gray-5, #777); }
.live-actions { display: flex; gap: 8px; margin-top: 18px; flex-wrap: wrap; }
.pinned { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--ink-gray-5, #777); margin-bottom: 10px; }
.talk-standup ul { margin: 16px 0 20px; padding-left: 18px; font-size: 14px; line-height: 1.8; }
@media (max-width: 640px) { .talk-scroll, .talk-compose, .talk-live, .talk-standup { padding-inline: 14px; } }
</style>
