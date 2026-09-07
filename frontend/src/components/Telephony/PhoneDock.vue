<template>
  <!-- Floating panel: incoming → live-one → active call → recent/conversations -->
  <aside v-if="open" ref="panel" class="phone-surface" :class="{ interruption: !!phone.incoming || !!alert }" :style="{ bottom: `${barHeight + 10}px`, maxHeight: `min(70dvh, calc(100dvh - ${barHeight + 24}px))` }" :aria-label="__('Phone')">
    <header class="phone-heading">
      <Button icon="minus" variant="ghost" :aria-label="__('Minimize phone')" @click="minimized = true" />
      <span class="phone-title">{{ __('Phone') }}</span>
      <span class="quiet-dot" :class="{ off: !ready }" :title="ready ? __('Phone ready') : __('Phone not connected')" />
      <Button v-if="isManager()" icon="settings" variant="ghost" :aria-label="__('Phone settings')" @click="router.push({ name: 'Phone Settings' })" />
    </header>

    <section v-if="phone.incoming" class="incoming-call" :aria-label="__('Incoming call')">
      <div class="incoming-symbol"><FeatherIcon name="phone-incoming" class="size-6" /></div>
      <p class="eyebrow">{{ __('Incoming') }} · {{ phone.incoming.line_label || formatPhone(phone.incoming.line) }}</p>
      <h2>{{ phone.incoming.lead_name || formatPhone(phone.incoming.from) }}</h2>
      <p class="caller-number">{{ formatPhone(phone.incoming.from) }}</p>
      <p v-if="phone.incoming.lead" class="caller-context"><router-link :to="`/leads/${phone.incoming.lead}`" class="underline">{{ __('Open lead') }}</router-link></p>
      <div class="incoming-actions">
        <button type="button" class="decline-call" @click="decline"><FeatherIcon name="phone-off" class="size-4" />{{ __('Decline') }}</button>
        <button type="button" class="answer-call" :disabled="onCall" @click="answer"><FeatherIcon name="phone" class="size-4" />{{ __('Answer') }}</button>
      </div>
    </section>

    <section v-else-if="alert" class="live-invitation" :aria-label="__('Live-one invitation')">
      <span class="invitation-label"><FeatherIcon name="zap" class="size-4" /> {{ __('Got a live one') }}</span>
      <h2>{{ talk.displayName(alert.rep) }} {{ __('needs you') }}</h2>
      <p class="invitation-lead">{{ alert.lead_name || alert.lead }}</p>
      <blockquote v-if="alert.note">“{{ alert.note }}”</blockquote>
      <Button iconLeft="headphones" class="w-full" variant="solid" :disabled="onCall" @click="joinAlert(alert)">{{ __('Join listening') }}</Button>
      <p class="pending-caption">{{ alert.lead ? __('Joining opens this lead’s comps map so you can price while you listen.') : __('No CRM lead on this call — you stay where you are.') }}</p>
      <p v-if="onCall" class="call-warning">{{ __('Finish your current call first. This invite will stay here.') }}</p>
      <div class="invitation-actions"><Button variant="ghost" @click="talk.dismissLiveOne(alert.call_log)">{{ __('Mark handled') }}</Button><Button v-if="alert.lead" variant="ghost" iconLeft="external-link" @click="router.push(`/leads/${alert.lead}/comps`)">{{ __('Open comps') }}</Button></div>
    </section>

    <template v-else>
      <PhoneDockCall v-if="onCall && tab === 'call'" />
      <template v-else>
        <div v-if="onCall" class="active-strip"><button type="button" @click="tab = 'call'"><span class="quiet-dot" /> {{ phone.peerName || formatPhone(phone.peerNumber) }} · {{ elapsed }} <span>{{ __('Return to call →') }}</span></button></div>
        <nav class="section-nav" :aria-label="__('Phone sections')">
          <button type="button" :class="{ selected: tab === 'recent' }" :aria-pressed="tab === 'recent'" @click="tab = 'recent'">{{ __('Recent calls') }}</button>
          <button type="button" :class="{ selected: tab === 'texts' }" :aria-pressed="tab === 'texts'" @click="tab = 'texts'">{{ __('Conversations') }}</button>
        </nav>
        <PhoneDockConversation v-if="conversation" :number="conversation.number" :name="conversation.name" :lead="conversation.lead" @back="conversation = null" />
        <section v-else class="call-history" :aria-label="tab === 'recent' ? __('Recent calls') : __('Conversations')">
          <p v-if="recent.loading && !rows.length" class="call-warning">{{ __('Loading…') }}</p>
          <p v-else-if="!rows.length" class="call-warning">{{ __('Nothing yet.') }}</p>
          <article v-for="item in rows" :key="item.key" class="history-row">
            <button type="button" class="history-person" :aria-label="`${__('Open conversation with')} ${item.name}`" @click="openConversation(item)">
              <FeatherIcon :name="item.kind === 'text' ? 'message-circle' : item.direction === 'Incoming' ? 'arrow-down-left' : 'arrow-up-right'" class="history-direction size-4" />
              <span class="history-content">
                <span class="history-title"><b>{{ item.name }}</b><span>{{ item.duration ? formatDuration(item.duration) : '' }}</span></span>
                <span class="history-number">{{ formatPhone(item.number) }}</span>
                <small v-if="item.kind === 'call'">{{ item.direction }} · {{ item.status }}</small>
                <small v-else class="snippet">{{ item.text }}</small>
                <small>{{ prettyDate(item.at) }}</small>
                <small v-if="item.kind === 'call'" class="recording-status" :class="{ ready: item.recording_url }">{{ item.recording_url ? __('Recording ready') : __('Not recorded') }}</small>
              </span>
            </button>
            <div class="history-actions">
              <Button icon="phone" variant="ghost" :disabled="onCall || !!phone.incoming" :aria-label="`${__('Call back')} ${item.name}`" :title="__('Call back')" @click="dial(item.number, { name: item.name, lead: item.lead })" />
              <Button icon="message-circle" variant="ghost" :aria-label="`${__('Text')} ${item.name}`" :title="__('Text')" @click="openConversation(item)" />
            </div>
          </article>
        </section>
        <form v-if="!onCall && !conversation" class="inline-dial" @submit.prevent="dialTyped">
          <FormControl v-model="number" :aria-label="__('Number to dial')" :placeholder="__('Dial a number…')" />
          <Button type="submit" icon="phone" variant="solid" :disabled="!validNumber" :aria-label="__('Dial')" />
        </form>
      </template>
    </template>
    <p v-if="phone.error" class="phone-notice" role="alert">{{ phone.error }}</p>
  </aside>

  <!-- Bottom bar: team presence + dock button -->
  <footer ref="bar" class="dock-bar" :aria-label="__('Team status and phone')">
    <div class="team-strip">
      <span class="demo-label">{{ __('TEAM') }}</span>
      <div v-for="u in teammates" :key="u.name" class="team-person">
        <button type="button" class="status-chat" :aria-label="`${__('Chat with')} ${u.full_name}`" :title="`${__('Chat with')} ${u.full_name}`" @click="chatWith(u)">
          <span class="status-dot" :class="talk.statusOf(u.name)" /><span><b>{{ u.full_name }}</b><span class="team-context">{{ contextOf(u.name) }}</span></span>
        </button>
        <Button v-if="callOf(u.name)" icon="headphones" variant="ghost" :disabled="onCall" :aria-label="`${__('Join')} ${u.full_name}${callOf(u.name).lead ? ' · opens comps' : ''}`" :title="callOf(u.name).lead ? __('Join listening · opens comps') : __('Join listening')" @click="joinCall(callOf(u.name))" />
      </div>
    </div>
    <div class="dock-strip">
      <Button class="dock-button" :variant="onCall || phone.incoming || alert ? 'solid' : 'subtle'" iconLeft="phone" :aria-expanded="open" @click="toggle">
        {{ phone.incoming ? __('Incoming call') : alert ? __('Live one') : onCall ? `${phone.peerName || formatPhone(phone.peerNumber)} · ${phone.role === 'supervisor' ? modeLabel : elapsed}` : __('Phone') }}
      </Button>
    </div>
  </footer>
</template>
<script setup>
/**
 * Phone dock (design A) for the next workspace: a collapsed dock in the bottom
 * bar that opens a compact panel. Recent calls / conversations from
 * crm.api.telephony.history, dialing through composables/phone.js (Telnyx
 * WebRTC + telephony.dial), incoming rings from `crm_incoming`, live-one
 * invitations from `crm_live_one` (talkStore), team presence from
 * talk.presence + telephony.active_calls. Only the bar reserves height;
 * the panel floats.
 */
import { Button, FeatherIcon, FormControl, call, createResource } from 'frappe-ui'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usersStore } from '@/stores/users'
import { sessionStore } from '@/stores/session'
import { talkStore } from '@/stores/talk'
import { formatPhone, normalizeNumber } from '@/utils/phoneFormat'
import { formatDuration, prettyDate } from '@/utils'
import { phone, onCall, elapsed, dial, answer, decline, join, disconnect } from '@/composables/phone'
import PhoneDockCall from '@/components/Telephony/PhoneDockCall.vue'
import PhoneDockConversation from '@/components/Telephony/PhoneDockConversation.vue'

const emit = defineEmits(['reserve'])
const route = useRoute()
const router = useRouter()
const session = sessionStore()
const { users, isManager } = usersStore()
const talk = talkStore()

const minimized = ref(true)
const tab = ref('recent')
const number = ref('')
const conversation = ref(null)
const bar = ref(null)
const panel = ref(null)
const barHeight = ref(56)
const ready = computed(() => !phone.error)
const alert = computed(() => talk.liveOnes[0] || null)
const open = computed(() => !minimized.value || !!phone.incoming || !!alert.value)
const validNumber = computed(() => !!normalizeNumber(number.value))
const modeLabel = computed(() => ({ monitor: __('Listening'), whisper: __('Whisper'), barge: __('Barge') })[phone.mode] || '')

const recent = createResource({ url: 'crm.api.telephony.history', params: { limit: 40 }, auto: true, initialData: [], onError: () => {} })
const rows = computed(() => (recent.data || []).filter((r) => tab.value === 'recent' ? r.kind === 'call' : true).map((r) => ({
  key: `${r.kind}:${r.name}`, kind: r.kind, name: r.lead_name || formatPhone(r.number) || __('Unknown'), number: r.number, lead: r.lead || null,
  direction: r.direction, status: r.status, duration: r.duration, at: r.at, recording_url: r.recording_url, text: r.text,
})))

const teammates = computed(() => (users.data?.crmUsers || []).filter((u) => u.name !== session.user))
function callOf(user) { return talk.calls.find((c) => c.rep === user && c.state !== 'ended') || null }
function contextOf(user) {
  const c = callOf(user)
  if (c) return c.lead_name || formatPhone(c.number) || __('On call')
  return { online: __('Available'), away: __('Away'), offline: __('Offline') }[talk.statusOf(user)] || ''
}
async function chatWith(u) {
  const dm = talk.dmRows.find((c) => c.dm_user === u.name)
  if (dm) return router.push({ name: 'Talk', params: { kind: 'dm', id: dm.name } })
  const created = await call('crm.api.talk.ensure_dm', { user: u.name })
  await talk.channels.reload()
  if (created?.name) router.push({ name: 'Talk', params: { kind: 'dm', id: created.name } })
}
// Joining a linked call lands on its comps map; unlinked stays put; blocked never navigates.
async function joinCall(c) {
  const ok = await join(c.call_log, 'monitor', { name: c.lead_name || formatPhone(c.number), lead: c.lead || null })
  if (ok) { minimized.value = false; tab.value = 'call'; if (c.lead) router.push(`/leads/${encodeURIComponent(c.lead)}/comps`) }
}
async function joinAlert(a) {
  const ok = await join(a.call_log, 'monitor', { name: a.lead_name || a.lead, lead: a.lead || null })
  if (ok) { talk.dismissLiveOne(a.call_log); tab.value = 'call'; if (a.lead) router.push(`/leads/${encodeURIComponent(a.lead)}/comps`) }
}
function openConversation(item) { conversation.value = { number: item.number, name: item.name, lead: item.lead }; minimized.value = false }
async function dialTyped() {
  const to = normalizeNumber(number.value)
  if (!to) return
  const ok = await dial(to, { name: '' })
  if (ok) { tab.value = 'call'; number.value = '' }
}
function toggle() { minimized.value = !minimized.value }
watch(onCall, (v) => { if (v) { tab.value = 'call'; minimized.value = false } else { tab.value = 'recent'; recent.reload() } })
watch(() => phone.incoming, (v) => { if (v) minimized.value = false })

let observer, frame
function measure() {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(() => {
    barHeight.value = Math.ceil(bar.value?.getBoundingClientRect().height || 56)
    emit('reserve', barHeight.value)
  })
}
watch(open, async () => { await nextTick(); if (panel.value) observer?.observe(panel.value); measure() })
onMounted(() => { observer = new ResizeObserver(measure); if (bar.value) observer.observe(bar.value); window.addEventListener('resize', measure); measure() })
onBeforeUnmount(() => { observer?.disconnect(); cancelAnimationFrame(frame); window.removeEventListener('resize', measure); emit('reserve', 0); disconnect() })
void route
</script>
<style scoped>
.dock-bar { position: fixed; z-index: 40; bottom: 0; left: 0; right: 0; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 16px; background: var(--surface-white, white); border-top: 1px solid var(--outline-gray-2, #dedede); box-shadow: 0 -3px 14px #00000006; }
.team-strip, .dock-strip { display: flex; align-items: center; gap: 8px; min-width: 0; }
.team-strip { overflow-x: auto; }.dock-strip { flex-shrink: 0; }
.demo-label { font-size: 10px; letter-spacing: .08em; color: var(--ink-gray-5, #777); }
.team-person { display: flex; align-items: center; gap: 2px; font-size: 12px; color: var(--ink-gray-8, #333); white-space: nowrap; padding-right: 8px; }
.status-chat { display: flex; align-items: center; gap: 7px; text-align: left; border-radius: 5px; padding: 4px; }.status-chat:hover { background: var(--surface-gray-1, #f5f5f5); }
.status-chat:focus-visible, .section-nav button:focus-visible { outline: 2px solid var(--ink-gray-7, #555); outline-offset: -2px; }
.team-context { display: block; margin-top: 3px; font-size: 10px; color: var(--ink-gray-5, #777); }
.status-dot, .quiet-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; display: inline-block; background: var(--surface-gray-4, #ccc); }
.status-dot.online, .quiet-dot { background: #388452; }.status-dot.on_call { background: #bc8e37; }.status-dot.away { background: #d9a536; }.quiet-dot.off { background: #b33; }
.dock-button { max-width: 220px; }
.phone-surface { position: fixed; z-index: 40; right: 36px; width: 328px; display: flex; flex-direction: column; overflow-y: auto; background: var(--surface-white, white); border: 1px solid var(--outline-gray-2, #ddd); border-radius: 12px; box-shadow: 0 10px 40px #0002; color: var(--ink-gray-8, #333); }
.phone-heading { position: sticky; top: 0; z-index: 2; display: flex; align-items: center; gap: 7px; padding: 9px 10px; border-bottom: 1px solid var(--outline-gray-1, #eee); background: var(--surface-white, white); }
.phone-title { font-size: 14px; font-weight: 600; flex: 1; }.phone-heading .quiet-dot { margin-right: 4px; }
.section-nav { display: flex; gap: 22px; padding: 0 16px; border-bottom: 1px solid var(--outline-gray-1, #eee); }.section-nav button { padding: 12px 0 10px; font-size: 12px; color: var(--ink-gray-5, #777); border-bottom: 2px solid transparent; }.section-nav button.selected { border-bottom-color: var(--ink-gray-8, #333); color: var(--ink-gray-9, #222); font-weight: 600; }
.history-row { display: flex; gap: 9px; padding: 14px 14px; border-bottom: 1px solid var(--outline-gray-1, #eee); }.history-direction { flex-shrink: 0; margin-top: 2px; color: var(--ink-gray-5, #777); }.history-content { flex: 1; min-width: 0; }.history-title { display: flex; gap: 8px; align-items: center; justify-content: space-between; }.history-title b { font-weight: 550; font-size: 13px; }.history-title span { font-size: 10px; color: var(--ink-gray-5, #777); font-variant-numeric: tabular-nums; }.history-number { display: block; margin-top: 3px; font-size: 11px; color: var(--ink-gray-5, #777); }.history-content small { display: block; margin-top: 4px; font-size: 10px; color: var(--ink-gray-5, #777); }.history-actions { display: flex; flex-direction: column; gap: 1px; }
.snippet { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-person { display: flex; gap: 9px; min-width: 0; flex: 1; text-align: left; border-radius: 5px; }.history-person:hover { background: var(--surface-gray-1, #fafafa); }.history-person:focus-visible { outline: 2px solid var(--ink-gray-7, #555); outline-offset: 3px; }
.history-content .recording-status.ready { color: #167645; }
.incoming-actions button { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 11px 12px; border-radius: 8px; font-size: 13px; font-weight: 600; }
.incoming-actions .answer-call { background: #167645; color: #fff; border: 1px solid #12613a; }.incoming-actions .answer-call:hover:not(:disabled) { background: #12613a; }.incoming-actions .answer-call:disabled { opacity: .45; cursor: not-allowed; }
.incoming-actions .decline-call { background: #fff1f0; color: #a32e2e; border: 1px solid #e9c4c1; }
.incoming-actions button:focus-visible { outline: 2px solid var(--ink-gray-8, #333); outline-offset: 3px; }
.inline-dial { display: flex; gap: 8px; padding: 14px; background: var(--surface-gray-1, #fafafa); }.inline-dial > :first-child { min-width: 0; flex: 1; }
.phone-notice { margin: 0; padding: 10px 14px; font-size: 11px; line-height: 1.5; color: #a32e2e; }
.active-strip { border-bottom: 1px solid var(--outline-gray-1, #eee); padding: 9px 14px; font-size: 11px; }.active-strip button { width: 100%; text-align: left; }.active-strip span:last-child { float: right; }
.interruption { width: 344px; }.incoming-call { padding: 24px 20px 20px; text-align: center; }.incoming-symbol { width: 48px; height: 48px; border-radius: 50%; display: grid; place-items: center; margin: 0 auto 16px; background: var(--surface-gray-1, #f7f7f7); color: #388452; }.eyebrow { font-size: 10px; letter-spacing: .08em; text-transform: uppercase; color: var(--ink-gray-5, #777); }.incoming-call h2 { font-size: 25px; font-weight: 600; letter-spacing: -.6px; margin: 12px 0 6px; }.caller-number { font-size: 14px; }.caller-context { margin-top: 10px; font-size: 11px; line-height: 1.5; color: var(--ink-gray-5, #777); }.incoming-actions { display: flex; gap: 10px; margin-top: 22px; }.incoming-actions > * { flex: 1; }
.live-invitation { padding: 18px; }.invitation-label { display: flex; gap: 7px; align-items: center; color: #9b772e; font-size: 12px; }.live-invitation h2 { margin-top: 18px; font-size: 22px; font-weight: 550; letter-spacing: -.5px; }.invitation-lead { margin-top: 7px; font-size: 13px; }.live-invitation blockquote { padding: 14px 0 20px; font-size: 14px; line-height: 1.6; color: var(--ink-gray-6, #666); }.invitation-actions { display: flex; justify-content: space-between; gap: 4px; margin-top: 10px; }.pending-caption, .call-warning { padding: 10px 14px; font-size: 11px; line-height: 1.5; color: var(--ink-gray-5, #777); }
@media (max-width: 999px) { .dock-bar { flex-direction: column; align-items: stretch; padding: 8px 12px; gap: 7px; }.dock-strip { justify-content: flex-end; flex-wrap: wrap; }.phone-surface { max-width: calc(100vw - 48px); right: 36px; max-height: 62dvh !important; }.dock-button { max-width: 160px; } }
</style>
