<template>
  <LayoutHeader><template #left-header><Breadcrumbs :items="[{ label: __('Settings') }, { label: __('Phone') }]" /></template></LayoutHeader>
  <div v-if="!isManager()" class="mx-auto max-w-xl px-5 py-10">
    <h1 class="text-lg font-semibold text-ink-gray-9">{{ __('Managers only') }}</h1>
    <p class="mt-2 text-base text-ink-gray-6">{{ __('Phone numbers, access and recording are managed by a Sales Manager.') }}</p>
  </div>
  <div v-else class="phone-settings">
    <nav :aria-label="__('Phone settings')"><h2>{{ __('Phone') }}</h2><button :class="{ selected: section === 'numbers' }" @click="section = 'numbers'">{{ __('Numbers & access') }}</button><button :class="{ selected: section === 'recording' }" @click="section = 'recording'">{{ __('Recording') }}</button></nav>
    <main>
      <template v-if="section === 'recording'">
        <h1>{{ __('Recording') }}</h1><p class="description">{{ __('A workspace default, with an explicit override for each line.') }}</p>
        <label class="setting-row"><span><b>{{ __('Record calls by default') }}</b><small>{{ __('Applies to lines set to “Use workspace default”.') }}</small></span><Switch :modelValue="!!settingsDoc.doc?.recording_default" @update:modelValue="saveSetting('recording_default', $event ? 1 : 0)" /></label>
        <label class="setting-row"><span><b>{{ __('Ring my cell as a fallback') }}</b><small>{{ __('If the browser does not answer, incoming calls also ring the rep’s mobile.') }}</small></span><Switch :modelValue="!!settingsDoc.doc?.ring_cell_fallback" @update:modelValue="saveSetting('ring_cell_fallback', $event ? 1 : 0)" /></label>
        <p class="consent">{{ settingsDoc.doc?.consent_note || __('This toggle is not legal consent. Disclosure, access, retention and consent policy must be settled before real recording.') }}</p>
      </template>
      <template v-else>
        <div class="settings-title"><div><h1>{{ __('Numbers & access') }}</h1><p class="description">{{ __('A number has an owner. Other teammates get explicit access.') }}</p></div><Button iconLeft="plus" variant="solid" disabled :title="__('Coming soon')">{{ __('Buy number') }} · {{ __('coming soon') }}</Button></div>
        <p v-if="lines.loading && !lines.data?.length" class="description">{{ __('Loading…') }}</p>
        <p v-else-if="!lines.data?.length" class="description">{{ __('No lines yet. Numbers are added by ops for now.') }}</p>
        <div v-else class="number-list">
          <button v-for="line in lines.data" :key="line.name" class="number-row" :class="{ selected: line.name === selected }" @click="selected = line.name"><span><b>{{ line.label || formatPhone(line.number) }}</b><small>{{ formatPhone(line.number) }}</small></span><span><small>{{ __('Owner') }}</small>{{ displayName(line.owner) }}</span><span><small>{{ __('Recording') }}</small>{{ recordingLabel(line) }}</span></button>
        </div>
        <section v-if="current" class="number-detail">
          <h2>{{ current.label || formatPhone(current.number) }}</h2>
          <div class="detail-fields">
            <FormControl :modelValue="current.label" :label="__('Line name')" @update:modelValue="current.label = $event" @blur="saveLine" />
            <FormControl type="select" :label="__('Owner')" :options="userOptions" :modelValue="current.owner" @update:modelValue="current.owner = $event; saveLine()" />
            <FormControl type="select" :label="__('Recording')" :options="[{ label: __('Use workspace default'), value: 'inherit' }, { label: __('Always on'), value: 'on' }, { label: __('Off'), value: 'off' }]" :modelValue="current.recording || 'inherit'" @update:modelValue="current.recording = $event; saveLine()" />
          </div>
          <p class="description">{{ __('Effective recording') }}: {{ recordingLabel(current) }}</p>
          <h3>{{ __('Shared-number group') }}</h3>
          <p class="description">{{ __('View = see this line’s calls and texts. Use = place calls and send texts from it. Ring = receive its incoming calls.') }}</p>
          <div class="access-table"><table>
            <thead><tr><th>{{ __('Teammate') }}</th><th>{{ __('View') }}</th><th>{{ __('Use') }}</th><th>{{ __('Ring') }}</th></tr></thead>
            <tbody><tr v-for="u in crmUsers" :key="u.name">
              <td>{{ u.full_name }}<small v-if="u.name === current.owner"> · {{ __('owner') }}</small></td>
              <td v-for="perm in ['view', 'use', 'ring']" :key="perm"><input type="checkbox" :checked="memberOf(u.name)?.[perm] === 1 || u.name === current.owner" :disabled="u.name === current.owner" :aria-label="`${u.full_name} ${perm}`" @change="setMember(u.name, perm, $event.target.checked)" /></td>
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
import { Breadcrumbs, Button, FormControl, Switch, call, createListResource, createDocumentResource, toast } from 'frappe-ui'
import { computed, ref, watch } from 'vue'
import { usersStore } from '@/stores/users'
import { formatPhone } from '@/utils/phoneFormat'

const { users, getUser, isManager } = usersStore()
const section = ref('numbers')
const selected = ref(null)
const lines = createListResource({
  doctype: 'CRM Phone Line', fields: ['name', 'number', 'label', 'owner', 'recording'], pageLength: 100, auto: true,
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
    await detail.setValue.submit({ label: current.value.label, owner: current.value.owner, recording: current.value.recording })
    lines.reload()
  } catch (e) { toast.error(e?.messages?.[0] || __('Could not save')) }
}
async function setMember(user, perm, value) {
  if (!current.value) return
  const members = (current.value.members || []).map((m) => ({ user: m.user, view: m.view, use: m.use, ring: m.ring }))
  let row = members.find((m) => m.user === user)
  if (!row) { row = { user, view: 0, use: 0, ring: 0 }; members.push(row) }
  row[perm] = value ? 1 : 0
  try {
    await call('frappe.client.set_value', { doctype: 'CRM Phone Line', name: current.value.name, fieldname: { members: members.filter((m) => m.view || m.use || m.ring) } })
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
.detail-fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }
.access-table { margin-top: 12px; }table { width: 100%; border-collapse: collapse; font-size: 13px; }th, td { padding: 10px 8px; border-bottom: 1px solid var(--outline-gray-1, #eee); text-align: left; }th:not(:first-child), td:not(:first-child) { width: 80px; text-align: center; }td small { color: var(--ink-gray-5, #777); }
@media (max-width: 900px) { .phone-settings { grid-template-columns: 1fr; gap: 16px; padding: 16px; }.number-row { grid-template-columns: 1fr; gap: 4px; }.detail-fields { grid-template-columns: 1fr; } }
</style>
