<template>
  <div class="conversation" :aria-label="`${__('Conversation with')} ${name}`">
    <div class="thread-heading">
      <Button variant="ghost" icon="arrow-left" :aria-label="__('Back')" @click="$emit('back')" />
      <div class="min-w-0"><b class="block truncate">{{ name }}</b><small>{{ formatPhone(number) }}<router-link v-if="lead || info.lead" :to="`/leads/${lead || info.lead}`" class="ml-2 underline">{{ __('Open lead') }}</router-link></small></div>
      <Button icon="phone" variant="ghost" :disabled="onCall" :aria-label="`${__('Call')} ${name}`" @click="dial(number, { name, lead })" />
    </div>

    <div ref="scroller" class="timeline">
      <p v-if="history.loading && !events.length" class="empty">{{ __('Loading…') }}</p>
      <p v-else-if="!events.length" class="empty">{{ __('No calls or texts yet.') }}</p>
      <template v-for="e in events" :key="e.key">
        <div v-if="e.kind === 'text'" class="message-row" :class="{ outbound: e.direction === 'out' }">
          <div class="bubble"><p>{{ e.text }}</p><small>{{ e.direction === 'out' ? (e.sender_name || __('You')) : name }} · {{ prettyDate(e.at) }}</small></div>
        </div>
        <article v-else class="call-event" :class="{ connected: e.duration }" :aria-label="`${e.direction} call · ${e.status}`">
          <div class="call-head"><FeatherIcon :name="e.direction === 'Incoming' ? 'phone-incoming' : 'phone-outgoing'" class="size-4" /><b>{{ e.direction }} {{ __('call') }}</b><span>{{ e.status }}<template v-if="e.duration"> · {{ formatDuration(e.duration) }}</template></span></div>
          <small class="call-time">{{ prettyDate(e.at) }}<template v-if="e.rep_name"> · {{ e.rep_name }}</template></small>
          <details v-if="e.summary" class="summary"><summary><FeatherIcon name="align-left" class="size-3" /> {{ __('AI summary') }}</summary><p>{{ e.summary }}</p></details>
          <details v-if="e.transcript" class="summary"><summary><FeatherIcon name="align-left" class="size-3" /> {{ __('Transcript') }}</summary><p class="transcript">{{ e.transcript }}</p></details>
          <div v-if="e.recording_url" class="recording">
            <button v-if="playing !== e.name" type="button" class="play" @click="playing = e.name"><FeatherIcon name="play" class="size-3" /> {{ __('Play recording') }}</button>
            <audio v-else controls autoplay preload="metadata" :src="recordingSrc(e.name)" :aria-label="`${__('Recording of call with')} ${name}`" @ended="playing = null" />
          </div>
          <router-link v-if="e.lead" :to="`/leads/${e.lead}?call=${e.name}#activity`" class="open-call">{{ __('Open in lead timeline') }}</router-link>
        </article>
      </template>
    </div>

    <p v-if="info.dnc" class="dnc bar">{{ __('Do not contact — texts and calls are blocked.') }}</p>
    <button v-else-if="!lead && !info.lead && routeLead" type="button" class="link-lead" @click="linkOpenLead">{{ __('Link to this lead') }}</button>
    <form class="compose" @submit.prevent="send">
      <FormControl v-model="draft" type="textarea" :rows="2" :aria-label="`${__('Text')} ${name}`" :placeholder="__('Write a text…')" @keydown.enter.exact.prevent="send" />
      <Button type="submit" icon="arrow-up" variant="solid" :disabled="!draft.trim() || sending" :aria-label="__('Send text')" />
    </form>
  </div>
</template>
<script setup>
/**
 * One person's timeline in the dock: prior calls and texts, oldest first, from
 * crm.api.telephony.history(number). Call cards expand an AI summary when the
 * call log carries one and play the recording through the CRM's own proxy
 * (`crm.integrations.api.get_recording_url`, session-authenticated — the raw
 * provider URL never goes into an <audio> tag). Texts send via telephony.send_text.
 */
import { Button, FeatherIcon, FormControl, call, createResource, toast } from 'frappe-ui'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { formatPhone } from '@/utils/phoneFormat'
import { formatDuration, prettyDate } from '@/utils'
import { onCall, dial } from '@/composables/phone'
import { useRoute } from 'vue-router'

const route = useRoute()
const routeLead = computed(() => route.params.leadId || null)
const info = ref({ dnc: false, lead: null })

const props = defineProps({ number: { type: String, required: true }, name: { type: String, default: '' }, lead: { type: String, default: null } })
defineEmits(['back'])
const scroller = ref(null)
const draft = ref('')
const sending = ref(false)
const playing = ref(null)
const history = createResource({ url: 'crm.api.telephony.history', initialData: [], onError: () => {} })
const events = computed(() => (history.data || []).map((r) => ({ ...r, key: `${r.kind}:${r.name}`, direction: r.direction, at: r.at, summary: r.summary || r.custom_ai_summary || '' })).sort((a, b) => new Date(a.at) - new Date(b.at)))
function recordingSrc(callLog) { return `/api/method/crm.integrations.api.get_recording_url?call_log_name=${encodeURIComponent(callLog)}` }
function load() {
  playing.value = null
  history.submit({ number: props.number, limit: 200 })
  call('crm.api.telephony.lookup', { number: props.number }).then((r) => { info.value = r || { dnc: false } }).catch(() => {})
}
async function linkOpenLead() {
  if (!routeLead.value) return
  try {
    const r = await call('crm.api.telephony.link_lead', { lead: routeLead.value, number: props.number })
    info.value = { ...info.value, lead: r.lead, lead_name: r.lead_name, dnc: info.value.dnc }
    load()
  } catch (e) { toast.error(e?.messages?.[0] || __('Could not link')) }
}
watch(() => props.number, load, { immediate: true })
watch(() => events.value.length, async () => { await nextTick(); if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight })
async function send() {
  const text = draft.value.trim()
  if (!text || sending.value) return
  if (info.value.dnc) { toast.error(__('This number is on the do-not-contact list')); return }
  sending.value = true
  try {
    await call('crm.api.telephony.send_text', { to: props.number, text })
    draft.value = ''
    load()
  } catch (e) {
    toast.error(e?.messages?.[0] || __('Could not send the text'))
  } finally { sending.value = false }
}
onBeforeUnmount(() => { playing.value = null })
</script>
<style scoped>
.conversation { display: flex; flex-direction: column; min-height: 0; }
.thread-heading { display: flex; align-items: center; gap: 8px; border-bottom: 1px solid var(--outline-gray-1, #eee); padding: 8px 10px; }
.thread-heading > div { flex: 1; }
.thread-heading b { font-size: 13px; font-weight: 600; }.thread-heading small { display: block; margin-top: 2px; font-size: 10px; color: var(--ink-gray-5, #777); }
.timeline { max-height: 320px; overflow-y: auto; padding: 14px 12px 0; }
.empty { padding: 20px 4px; font-size: 12px; color: var(--ink-gray-5, #777); }
.message-row { display: flex; margin-bottom: 12px; }.message-row.outbound { justify-content: flex-end; }
.bubble { max-width: 90%; padding: 9px 11px; border-radius: 10px; background: var(--surface-gray-1, #f8f8f8); overflow-wrap: anywhere; }.outbound .bubble { background: var(--surface-gray-2, #eee); }
.bubble p { white-space: pre-wrap; font-size: 13px; line-height: 1.5; }.bubble small { display: block; margin-top: 5px; font-size: 10px; color: var(--ink-gray-5, #777); }
.call-event { margin: 0 0 12px; padding: 10px 12px; border: 1px solid var(--outline-gray-1, #eee); border-radius: 10px; }.call-event.connected { border-left: 3px solid #388452; }
.call-head { display: flex; align-items: center; gap: 7px; font-size: 12px; }.call-head b { font-weight: 600; }.call-head span { margin-left: auto; color: var(--ink-gray-5, #777); font-variant-numeric: tabular-nums; }
.call-time { display: block; margin-top: 5px; font-size: 10px; color: var(--ink-gray-5, #777); }
.summary { margin-top: 9px; font-size: 12px; }.summary summary { display: flex; align-items: center; gap: 5px; cursor: pointer; font-size: 11px; font-weight: 600; color: var(--ink-gray-7, #555); list-style: none; }.summary summary::-webkit-details-marker { display: none; }.summary p { margin-top: 7px; line-height: 1.55; }
.recording { margin-top: 10px; }.play { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600; color: #167645; }.recording audio { display: block; width: 100%; height: 36px; }
.open-call { display: block; margin-top: 8px; font-size: 10px; color: var(--ink-gray-5, #777); text-decoration: underline; }
.dnc { margin-top: 8px; font-size: 11px; font-weight: 600; color: #a32e2e; }.dnc.bar { padding: 8px 12px; border-top: 1px solid var(--outline-gray-1, #eee); }
.transcript { white-space: pre-wrap; max-height: 160px; overflow: auto; }
.link-lead { padding: 8px 12px; font-size: 11px; font-weight: 600; text-align: left; color: #167645; text-decoration: underline; }
.compose { display: flex; align-items: flex-end; gap: 7px; padding: 10px 12px 14px; border-top: 1px solid var(--outline-gray-1, #eee); }.compose > :first-child { flex: 1; min-width: 0; }
</style>
