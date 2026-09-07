<template>
  <LayoutHeader><template #left-header><Breadcrumbs :items="[{ label: __('Settings') }, { label: __('Phone') }]" /></template></LayoutHeader>
  <div class="phone-settings">
    <nav :aria-label="__('Phone settings')">
      <h2>{{ __('Phone') }}</h2>
      <button :class="{ selected: section === 'voicemail' }" @click="section = 'voicemail'">{{ __('Voicemail') }}</button>
      <button :class="{ selected: section === 'mylines' }" @click="section = 'mylines'">{{ __('My lines') }}</button>
      <template v-if="isManager()">
        <button :class="{ selected: section === 'numbers' }" @click="section = 'numbers'">{{ __('Numbers & access') }}</button>
        <button :class="{ selected: section === 'recording' }" @click="section = 'recording'">{{ __('Recording') }}</button>
      </template>
    </nav>
    <main>
      <template v-if="section === 'voicemail'">
        <h1>{{ __('Voicemail greeting') }}</h1>
        <p class="description">{{ __('Spoken to anyone who reaches your voicemail. Required before you can place a Telnyx call — sellers ring this number back.') }}</p>
        <FormControl v-model="greeting" type="textarea" :rows="4" :label="__('Greeting')" :placeholder="__('Hi, you’ve reached Groundwork. Please leave a message after the tone.')" />
        <div class="mt-4 flex items-center gap-3">
          <Button variant="solid" :disabled="greeting.trim().length < 10 || savingGreeting" @click="saveGreeting">{{ __('Save greeting') }}</Button>
          <span v-if="greetingStatus.configured" class="text-xs text-ink-gray-5">{{ __('Configured') }}</span>
          <span v-else class="text-xs text-ink-red-4">{{ __('Not set — outbound calls are blocked until you save one.') }}</span>
        </div>
      </template>
      <template v-else-if="section === 'mylines'">
        <h1>{{ __('My lines') }}</h1>
        <p class="description">{{ __('Mute a shared number to keep using it without a notification on every call or text. You will still see it in Inbox.') }}</p>
        <p v-if="!myLines.length" class="description">{{ __('No lines assigned to you yet.') }}</p>
        <label v-for="line in myLines" :key="line.name" class="setting-row">
          <span><b>{{ line.emoji }} {{ line.label || formatPhone(line.number) }}</b><small>{{ formatPhone(line.number) }}</small></span>
          <Switch :modelValue="!!line.muted" @update:modelValue="toggleMute(line, $event)" />
        </label>
      </template>
      <template v-else-if="section === 'recording'">
        <h1>{{ __('Recording') }}</h1><p class="description">{{ __('A workspace default, with an explicit override for each line.') }}</p>
        <label class="setting-row"><span><b>{{ __('Record calls by default') }}</b><small>{{ __('Applies to lines set to “Use workspace default”.') }}</small></span><Switch :modelValue="!!settingsDoc.doc?.recording_default" @update:modelValue="saveSetting('recording_default', $event ? 1 : 0)" /></label>
        <label class="setting-row"><span><b>{{ __('Ring my cell as a fallback') }}</b><small>{{ __('If the browser does not answer, incoming calls also ring the rep’s mobile.') }}</small></span><Switch :modelValue="!!settingsDoc.doc?.ring_cell_fallback" @update:modelValue="saveSetting('ring_cell_fallback', $event ? 1 : 0)" /></label>
        <p class="consent">{{ settingsDoc.doc?.consent_note || __('This toggle is not legal consent. Disclosure, access, retention and consent policy must be settled before real recording.') }}</p>
      </template>
      <template v-else>
        <div class="settings-title"><div><h1>{{ __('Numbers & access') }}</h1><p class="description">{{ __('A number has an owner. Other teammates get explicit access.') }}</p></div><Button iconLeft="plus" variant="solid" @click="showBuy = !showBuy">{{ showBuy ? __('Close') : __('Buy number') }}</Button></div>
        <div v-if="showBuy" class="buy-box">
          <p class="description">{{ __('Search a US area code, then buy. Telnyx charges the account when you confirm.') }}</p>
          <form class="buy-search" @submit.prevent="runSearch">
            <FormControl v-model="areaCode" :label="__('Area code')" placeholder="612" />
            <Button type="submit" variant="solid" :loading="searching">{{ __('Search') }}</Button>
          </form>
          <p v-if="searchError" class="description">{{ searchError }}</p>
          <div v-for="n in available" :key="n.number" class="buy-row">
            <span><b>{{ formatPhone(n.number) }}</b><small>{{ n.city }}</small></span>
            <Button size="sm" variant="solid" :loading="buying === n.number" @click="confirmBuy(n)">{{ __('Buy') }}</Button>
          </div>
        </div>
        <p v-if="lines.loading && !lines.data?.length" class="description">{{ __('Loading…') }}</p>
        <p v-else-if="!lines.data?.length" class="description">{{ __('No lines yet. Numbers are added by ops for now.') }}</p>
        <div v-else class="number-list">
          <button v-for="line in lines.data" :key="line.name" class="number-row" :class="{ selected: line.name === selected }" @click="selected = line.name"><span><b>{{ line.emoji }} {{ line.label || formatPhone(line.number) }}</b><small>{{ formatPhone(line.number) }}</small></span><span><small>{{ __('Owner') }}</small>{{ displayName(line.owner_user || line.owner) }}</span><span><small>{{ __('Recording') }}</small>{{ recordingLabel(line) }}</span></button>
        </div>
        <section v-if="current" class="number-detail">
          <h2>{{ current.emoji }} {{ current.label || formatPhone(current.number) }}</h2>
          <div class="detail-fields">
            <FormControl :modelValue="current.label" :label="__('Line name')" @update:modelValue="current.label = $event" @blur="saveLine" />
            <div>
              <p class="description" style="margin:0 0 6px">{{ __('Emoji') }}</p>
              <div class="emoji-row">
                <button v-for="e in EMOJIS" :key="e" type="button" class="emoji-btn" :class="{ on: current.emoji === e }" @click="current.emoji = e; saveLine()">{{ e }}</button>
                <button type="button" class="emoji-btn" @click="current.emoji = ''; saveLine()">{{ __('None') }}</button>
              </div>
            </div>
            <FormControl type="select" :label="__('Owner')" :options="userOptions" :modelValue="current.owner_user" @update:modelValue="current.owner_user = $event; saveLine()" />
            <FormControl type="select" :label="__('Recording')" :options="[{ label: __('Use workspace default'), value: 'inherit' }, { label: __('Always on'), value: 'on' }, { label: __('Off'), value: 'off' }]" :modelValue="current.recording || 'inherit'" @update:modelValue="current.recording = $event; saveLine()" />
          </div>
          <p class="description">{{ __('Effective recording') }}: {{ recordingLabel(current) }}</p>
          <h3>{{ __('Shared-number group') }}</h3>
          <p class="description">{{ __('View = see this line’s calls and texts. Use = place calls and send texts from it. Ring = receive its incoming calls. Mute = no ring and no notification — they can still open Inbox.') }}</p>
          <div class="access-table"><table>
            <thead><tr><th>{{ __('Teammate') }}</th><th>{{ __('View') }}</th><th>{{ __('Use') }}</th><th>{{ __('Ring') }}</th><th>{{ __('Mute') }}</th></tr></thead>
            <tbody><tr v-for="u in crmUsers" :key="u.name">
              <td>{{ u.full_name }}<small v-if="u.name === current.owner_user"> · {{ __('owner') }}</small></td>
              <td v-for="perm in ['view', 'use', 'ring', 'mute']" :key="perm"><input type="checkbox" :checked="perm === 'mute' ? !!memberOf(u.name)?.mute : (memberOf(u.name)?.[perm] === 1 || u.name === current.owner_user)" :disabled="u.name === current.owner_user && perm !== 'mute'" :aria-label="`${u.full_name} ${perm}`" @change="setMember(u.name, perm, $event.target.checked)" /></td>
            </tr></tbody>
          </table></div>
        </section>
      </template>
    </main>
  </div>
</template>
<script setup>
/**
 * Settings → Phone: CRM Phone Line rows (owner, recording override, member
 * view/use/ring) and the CRM Telephony Settings single (workspace recording
 * default, cell fallback, consent note). Managers only. Buying numbers is
 * deliberately disabled until a Telnyx number-order flow is approved.
 */
import LayoutHeader from '@/components/LayoutHeader.vue'
import { Breadcrumbs, Button, FormControl, Switch, call, createListResource, createDocumentResource, createResource, toast } from 'frappe-ui'
import { computed, ref, watch } from 'vue'
import { usersStore } from '@/stores/users'
import { formatPhone } from '@/utils/phoneFormat'

const { users, getUser, isManager } = usersStore()
const section = ref('voicemail')
const greeting = ref('')
const greetingStatus = ref({ configured: false, greeting: '' })
const savingGreeting = ref(false)
call('crm.integrations.telnyx.api.voicemail_status').then((r) => {
  greetingStatus.value = r || { configured: false }
  greeting.value = r?.greeting || ''
}).catch(() => {})
async function saveGreeting() {
  savingGreeting.value = true
  try {
    const r = await call('crm.integrations.telnyx.api.set_voicemail_greeting', { greeting: greeting.value.trim() })
    greetingStatus.value = { configured: true, greeting: r?.greeting }
    toast.success(__('Voicemail greeting saved'))
  } catch (e) { toast.error(e?.messages?.[0] || __('Could not save greeting')) }
  finally { savingGreeting.value = false }
}
const EMOJIS = ['📱', '🏡', '🏢', '💼', '🔥', '⭐', '🎯', '📣']
const showBuy = ref(false)
const areaCode = ref('612')
const available = ref([])
const searching = ref(false)
const searchError = ref('')
const buying = ref('')
async function runSearch() {
  searching.value = true
  searchError.value = ''
  available.value = []
  try { available.value = await call('crm.api.telephony.search_numbers', { area_code: areaCode.value, limit: 12 }) || [] }
  catch (e) { searchError.value = e?.messages?.[0] || __('Search failed') }
  finally { searching.value = false }
}
async function confirmBuy(n) {
  if (!confirm(__('Buy {0}? Telnyx will charge this account.', [formatPhone(n.number)]))) return
  buying.value = n.number
  try {
    await call('crm.api.telephony.buy_number', { number: n.number, label: n.city || '', emoji: '📱' })
    toast.success(__('Number purchased'))
    showBuy.value = false
    available.value = []
    lines.reload()
    myLineList.reload()
  } catch (e) { toast.error(e?.messages?.[0] || __('Could not buy')) }
  finally { buying.value = '' }
}
const myLineList = createResource({ url: 'crm.api.telephony.lines', auto: true, initialData: [], onError: () => {} })
const myLines = computed(() => myLineList.data || [])
async function toggleMute(line, muted) {
  try {
    await call('crm.api.telephony.set_my_mute', { line: line.name, muted: muted ? 1 : 0 })
    myLineList.reload()
  } catch (e) { toast.error(e?.messages?.[0] || __('Could not mute')) }
}
const selected = ref(null)
const lines = createListResource({
  doctype: 'CRM Phone Line', fields: ['name', 'number', 'label', 'emoji', 'owner_user', 'recording'], pageLength: 100, auto: true,
  onError: () => {},
})
const detail = createDocumentResource({ doctype: 'CRM Phone Line', name: computed(() => selected.value), auto: false })
const settingsDoc = createDocumentResource({ doctype: 'CRM Telephony Settings', name: 'CRM Telephony Settings', auto: true, onError: () => {} })
const crmUsers = computed(() => users.data?.crmUsers || [])
const userOptions = computed(() => crmUsers.value.map((u) => ({ label: u.full_name, value: u.name })))
const current = computed(() => (selected.value && detail.doc?.name === selected.value) ? detail.doc : null)
watch(selected, (name) => { if (name) { detail.name = name; detail.reload() } })
watch(() => lines.data, (rows) => { if (!selected.value && rows?.length) selected.value = rows[0].name })
function displayName(user) { return getUser(user)?.full_name || user || '—' }
function recordingLabel(line) {
  const d = settingsDoc.doc?.recording_default
  if (!line.recording || line.recording === 'inherit') return `${d ? __('On') : __('Off')} · ${__('workspace default')}`
  return `${line.recording === 'on' ? __('On') : __('Off')} · ${__('override')}`
}
function memberOf(user) { return (current.value?.members || []).find((m) => m.user === user) }
async function saveLine() {
  if (!current.value) return
  try {
    await detail.setValue.submit({ label: current.value.label, emoji: current.value.emoji || '', owner_user: current.value.owner_user, recording: current.value.recording })
    lines.reload()
  } catch (e) { toast.error(e?.messages?.[0] || __('Could not save')) }
}
async function setMember(user, perm, value) {
  if (!current.value) return
  const members = (current.value.members || []).map((m) => ({ user: m.user, view: m.view, use: m.use, ring: m.ring, mute: m.mute }))
  let row = members.find((m) => m.user === user)
  if (!row) { row = { user, view: 0, use: 0, ring: 0, mute: 0 }; members.push(row) }
  row[perm] = value ? 1 : 0
  try {
    await call('frappe.client.set_value', { doctype: 'CRM Phone Line', name: current.value.name, fieldname: { members: members.filter((m) => m.view || m.use || m.ring || m.mute) } })
    detail.reload()
  } catch (e) { toast.error(e?.messages?.[0] || __('Could not save access')) }
}
async function saveSetting(field, value) {
  try { await settingsDoc.setValue.submit({ [field]: value }) } catch (e) { toast.error(e?.messages?.[0] || __('Could not save')) }
}
</script>
<style scoped>
.phone-settings { display: grid; grid-template-columns: 200px minmax(0, 1fr); gap: 32px; padding: 20px 28px; }
nav h2 { font-size: 13px; font-weight: 600; margin: 8px 8px 12px; }
nav button { display: block; width: 100%; padding: 8px 10px; border-radius: 6px; text-align: left; font-size: 13px; color: var(--ink-gray-7, #555); }
nav button.selected { background: var(--surface-gray-2, #eee); color: var(--ink-gray-9, #222); }
main h1 { font-size: 20px; font-weight: 600; letter-spacing: -.3px; }
.description { margin-top: 6px; font-size: 12px; line-height: 1.5; color: var(--ink-gray-5, #777); }
.settings-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.setting-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 0; border-bottom: 1px solid var(--outline-gray-1, #eee); }.setting-row b { font-size: 13px; }.setting-row small { display: block; margin-top: 3px; font-size: 11px; color: var(--ink-gray-5, #777); }
.consent { margin-top: 16px; padding: 12px; border-radius: 8px; background: #fdf7e7; font-size: 12px; line-height: 1.5; color: #7a5b16; }
.number-list { margin-top: 20px; border: 1px solid var(--outline-gray-1, #eee); border-radius: 10px; overflow: hidden; }
.number-row { display: grid; grid-template-columns: 1fr 160px 200px; gap: 12px; width: 100%; padding: 14px 16px; border-bottom: 1px solid var(--outline-gray-1, #eee); text-align: left; font-size: 13px; }
.number-row:last-child { border-bottom: 0; }.number-row.selected { background: var(--surface-gray-1, #f8f8f8); }.number-row small { display: block; font-size: 11px; color: var(--ink-gray-5, #777); }
.number-detail { margin-top: 28px; }.number-detail h2 { font-size: 16px; font-weight: 600; }.number-detail h3 { margin-top: 24px; font-size: 14px; font-weight: 600; }
.detail-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }
.emoji-row { display: flex; flex-wrap: wrap; gap: 6px; }
.emoji-btn { padding: 6px 8px; border-radius: 8px; border: 1px solid var(--outline-gray-1, #eee); font-size: 16px; }
.emoji-btn.on { background: var(--surface-gray-2, #eee); }
.buy-box { margin-top: 16px; padding: 14px; border: 1px solid var(--outline-gray-1, #eee); border-radius: 10px; }
.buy-search { display: flex; align-items: flex-end; gap: 8px; margin-top: 10px; }
.buy-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--outline-gray-1, #eee); font-size: 13px; }
.buy-row small { display: block; color: var(--ink-gray-5, #777); }
.access-table { margin-top: 12px; }table { width: 100%; border-collapse: collapse; font-size: 13px; }th, td { padding: 10px 8px; border-bottom: 1px solid var(--outline-gray-1, #eee); text-align: left; }th:not(:first-child), td:not(:first-child) { width: 80px; text-align: center; }td small { color: var(--ink-gray-5, #777); }
@media (max-width: 900px) { .phone-settings { grid-template-columns: 1fr; gap: 16px; padding: 16px; }.number-row { grid-template-columns: 1fr; gap: 4px; }.detail-fields { grid-template-columns: 1fr; } }
</style>
