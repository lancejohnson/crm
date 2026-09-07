<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="crumbs" />
    </template>
    <template #right-header>
      <Button v-if="activeLine" variant="ghost" size="sm" iconLeft="copy" @click="copyToClipboard(formatPhone(activeLine.number) || activeLine.number)">{{ formatPhone(activeLine.number) }}</Button>
      <span v-else class="text-xs text-ink-gray-5">{{ __('Calls and texts, including numbers with no lead') }}</span>
    </template>
  </LayoutHeader>

  <div v-if="!workspace.isNext" class="mx-auto max-w-xl px-5 py-10">
    <h1 class="text-lg font-semibold text-ink-gray-9">{{ __('Inbox is part of the new workspace') }}</h1>
    <p class="mt-2 text-base text-ink-gray-6">{{ workspace.allowed ? __('Switch from your name menu → Try the new workspace.') : __('It is not enabled for your account yet.') }}</p>
  </div>

  <div v-else class="desk">
    <aside class="desk-list" :aria-label="__('Conversations')">
      <div class="desk-tabs">
        <button type="button" :class="{ on: tab === 'inbox' }" @click="tab = 'inbox'">{{ __('Inbox') }}</button>
        <button type="button" :class="{ on: tab === 'calls' }" @click="tab = 'calls'">{{ __('Calls') }}</button>
      </div>
      <form class="desk-search" @submit.prevent="openTyped">
        <FormControl v-model="query" :placeholder="tab === 'calls' ? __('Search calls…') : __('Search or dial a number…')" :aria-label="__('Search')" />
      </form>
      <p v-if="rows.loading && !list.length" class="desk-empty">{{ __('Loading…') }}</p>
      <p v-else-if="!list.length" class="desk-empty">{{ tab === 'calls' ? __('No calls yet.') : __('No conversations yet.') }}</p>
      <button
        v-for="row in list"
        :key="row.key"
        type="button"
        class="desk-row"
        :class="{ selected: selected === row.number }"
        @click="open(row.number)"
      >
        <span class="desk-who">
          <b>{{ row.title }}</b>
          <small v-if="!row.lead">{{ __('Not linked') }}</small>
          <small v-else>{{ formatPhone(row.number) }}</small>
        </span>
        <span class="desk-meta">
          <small>{{ prettyDate(row.last_at) }}</small>
          <small class="snippet">{{ row.snippet }}</small>
        </span>
      </button>
    </aside>
    <main class="desk-thread">
      <div v-if="selected && !selectedLead" class="link-bar">
        <span>{{ __('Not on a lead') }}</span>
        <FormControl v-model="leadQuery" :placeholder="__('Search a lead to link…')" @update:modelValue="searchLeads" />
        <ul v-if="leadHits.length" class="lead-hits">
          <li v-for="hit in leadHits" :key="hit.name"><button type="button" @click="linkLead(hit.name)">{{ hit.lead_name || hit.name }}</button></li>
        </ul>
      </div>
      <PhoneDockConversation
        v-if="selected"
        :number="selected"
        :name="selectedTitle"
        :lead="selectedLead"
        :showBack="false"
      />
      <div v-else class="desk-empty pad">
        <p>{{ __('Pick a conversation, or type a number and press Enter.') }}</p>
      </div>
    </main>
  </div>
</template>
<script setup>
/**
 * Full-page Quo/Yall-style desk: every number the user has called or texted,
 * whether or not it is linked to a CRM Lead. Inbox is one row per peer;
 * Calls is the flat call feed (so a number that never texted still shows).
 */
import LayoutHeader from '@/components/LayoutHeader.vue'
import PhoneDockConversation from '@/components/Telephony/PhoneDockConversation.vue'
import { Breadcrumbs, Button, FormControl, call, createResource, toast } from 'frappe-ui'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { workspaceStore } from '@/stores/workspace'
import { formatPhone, normalizeNumber } from '@/utils/phoneFormat'
import { copyToClipboard, prettyDate } from '@/utils'

const workspace = workspaceStore()
const route = useRoute()
const router = useRouter()
const tab = ref('inbox')
const query = ref('')
const leadQuery = ref('')
const leadHits = ref([])
let searchTimer
function searchLeads(q) {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(async () => {
    const term = String(q || '').trim()
    if (term.length < 2) { leadHits.value = []; return }
    try {
      leadHits.value = await call('frappe.client.get_list', {
        doctype: 'CRM Lead', fields: ['name', 'lead_name'],
        filters: [['lead_name', 'like', `%${term}%`]], limit_page_length: 8,
      }) || []
    } catch { leadHits.value = [] }
  }, 200)
}
async function linkLead(lead) {
  try {
    await call('crm.api.telephony.link_lead', { lead, number: selected.value })
    leadHits.value = []
    leadQuery.value = ''
    loadInbox()
    history.reload()
  } catch (e) { toast.error(e?.messages?.[0] || __('Could not link')) }
}
const lineFilter = computed(() => route.query.line || '')
const lineList = createResource({ url: 'crm.api.telephony.lines', auto: true, initialData: [], onError: () => {} })
const activeLine = computed(() => (lineList.data || []).find((l) => l.name === lineFilter.value) || null)
const crumbs = computed(() => {
  const items = [{ label: __('Inbox'), route: { name: 'Phone Desk' } }]
  if (activeLine.value) items.push({ label: `${activeLine.value.emoji || ''} ${activeLine.value.label || formatPhone(activeLine.value.number)}`.trim() })
  return items
})
const inbox = createResource({ url: 'crm.api.telephony.inbox', auto: false, initialData: [], onError: () => {} })
const history = createResource({ url: 'crm.api.telephony.history', params: { limit: 200 }, auto: true, initialData: [], onError: () => {} })
function loadInbox() { inbox.submit({ limit: 200, line: lineFilter.value || undefined }) }
watch(lineFilter, loadInbox, { immediate: true })

const selected = computed(() => route.params.number ? String(route.params.number) : '')
const inboxRows = computed(() => (inbox.data || []).map((r) => ({
  key: r.number,
  number: r.number,
  title: r.lead_name || r.title || formatPhone(r.number),
  lead: r.lead,
  last_at: r.last_at,
  snippet: r.last_kind === 'call' ? (r.last_text || __('Call')) : (r.last_text || __('Text')),
})))
const callRows = computed(() => (history.data || []).filter((e) => e.kind === 'call').map((e) => ({
  key: e.name,
  number: e.number,
  title: e.lead_name || formatPhone(e.number) || __('Unknown'),
  lead: e.lead,
  last_at: e.at,
  snippet: `${e.direction || ''} ${e.status || ''}`.trim() || __('Call'),
})))
const list = computed(() => {
  const q = query.value.trim().toLowerCase()
  const rows = tab.value === 'calls' ? callRows.value : inboxRows.value
  if (!q) return rows
  return rows.filter((r) => `${r.title} ${r.number} ${r.snippet}`.toLowerCase().includes(q))
})
const selectedMeta = computed(() => inboxRows.value.find((r) => r.number === selected.value) || callRows.value.find((r) => r.number === selected.value))
const selectedTitle = computed(() => selectedMeta.value?.title || formatPhone(selected.value))
const selectedLead = computed(() => selectedMeta.value?.lead || null)

function open(number) {
  if (!number) return
  router.push({ name: 'Phone Desk', params: { number } })
}
function openTyped() {
  const n = normalizeNumber(query.value) || query.value.trim()
  if (n) open(n)
}
watch(tab, () => { if (tab.value === 'inbox') loadInbox(); else history.reload() })
</script>
<style scoped>
.desk { display: flex; height: 100%; min-height: 0; color: var(--ink-gray-9, #222); }
.desk-list { width: 320px; flex-shrink: 0; display: flex; flex-direction: column; border-right: 1px solid var(--outline-gray-1, #eee); min-height: 0; }
.desk-tabs { display: flex; gap: 4px; padding: 10px 12px 0; }
.desk-tabs button { flex: 1; padding: 7px 8px; border-radius: 8px; font-size: 12px; font-weight: 600; color: var(--ink-gray-5, #777); }
.desk-tabs button.on { background: var(--surface-gray-2, #eee); color: var(--ink-gray-9, #222); }
.desk-search { padding: 10px 12px; }
.desk-empty { padding: 16px 14px; font-size: 13px; color: var(--ink-gray-5, #777); }
.desk-empty.pad { padding: 48px 24px; }
.desk-row { display: flex; flex-direction: column; gap: 2px; width: 100%; padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--outline-gray-1, #eee); }
.desk-row:hover { background: var(--surface-gray-1, #f7f7f7); }
.desk-row.selected { background: var(--surface-gray-2, #eee); }
.desk-who { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.desk-who b { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.desk-who small { font-size: 10px; color: var(--ink-gray-5, #777); flex-shrink: 0; }
.desk-meta { display: flex; justify-content: space-between; gap: 8px; font-size: 11px; color: var(--ink-gray-5, #777); }
.desk-meta .snippet { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.desk-thread { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; }
.link-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--outline-gray-1, #eee); font-size: 12px; color: var(--ink-gray-5, #777); position: relative; }
.link-bar :deep(.form-control) { min-width: 180px; }
.lead-hits { position: absolute; top: 100%; left: 90px; z-index: 5; min-width: 220px; margin: 0; padding: 4px; list-style: none; background: var(--surface-white, #fff); border: 1px solid var(--outline-gray-2, #ddd); border-radius: 8px; box-shadow: 0 8px 24px #0002; }
.lead-hits button { display: block; width: 100%; padding: 6px 8px; text-align: left; border-radius: 6px; font-size: 13px; }
.lead-hits button:hover { background: var(--surface-gray-2, #eee); }
@media (max-width: 720px) {
  .desk { flex-direction: column; }
  .desk-list { width: 100%; max-height: 40%; border-right: 0; border-bottom: 1px solid var(--outline-gray-1, #eee); }
}
</style>
