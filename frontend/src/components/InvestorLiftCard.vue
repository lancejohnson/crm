<template>
  <div class="border-t px-5 py-3">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2 text-base font-medium text-ink-gray-8">
        <MegaphoneIcon class="size-4 text-ink-gray-7" />
        {{ __('InvestorLift') }}
      </div>
      <div class="flex items-center gap-1">
        <Button
          v-if="linked"
          :tooltip="__('Re-sync marketing metrics')"
          :loading="marketing.loading"
          icon="rotate-ccw"
          variant="ghost"
          @click="refresh"
        />
        <Dropdown v-if="linked" :options="menuOptions">
          <Button icon="more-horizontal" variant="ghost" />
        </Dropdown>
      </div>
    </div>

    <!-- linked: marketing dashboard -->
    <div v-if="linked" class="mt-2.5 flex flex-col gap-2 text-sm">
      <div class="flex items-center gap-2">
        <Badge v-if="m.status" :theme="statusTheme(m.status)" variant="subtle">
          {{ m.status }}
        </Badge>
        <a
          :href="m.admin_url"
          target="_blank"
          class="flex items-center gap-1 text-ink-blue-3 hover:underline"
        >
          {{ __('Admin listing') }}
          <ExternalLinkIcon class="size-3" />
        </a>
      </div>

      <!-- buyer-facing marketplace listing: the link you'd actually send someone -->
      <div v-if="m.marketplace_url" class="flex items-center gap-2">
        <a
          :href="m.marketplace_url"
          target="_blank"
          class="flex items-center gap-1 text-ink-blue-3 hover:underline"
        >
          {{ __('Public listing') }}
          <ExternalLinkIcon class="size-3" />
        </a>
        <button
          class="text-ink-gray-4 hover:text-ink-gray-7"
          :title="__('Copy public link')"
          @click="copyPublicLink"
        >
          <CopyIcon class="size-3.5" />
        </button>
      </div>

      <router-link
        :to="{ name: 'Dispo', params: { leadId: lead } }"
        class="flex items-center gap-1 text-ink-blue-3 hover:underline"
      >
        <DispoIcon class="size-3.5" />
        {{ __('Open buyer board') }}
      </router-link>

      <!-- SMS funnel -->
      <div class="mt-1 grid grid-cols-3 gap-2">
        <Stat :label="__('Texts sent')" :value="formatNumber(m.sms.sent)" />
        <Stat :label="__('Delivered')" :value="formatNumber(m.sms.delivered)" />
        <Stat
          :label="__('Clicks')"
          :value="formatNumber(m.sms.clicked)"
          :sub="m.sms.ctr ? m.sms.ctr + '% CTR' : ''"
        />
      </div>
      <div class="grid grid-cols-3 gap-2">
        <Stat :label="__('Views')" :value="formatNumber(m.views)" />
        <Stat :label="__('Spend')" :value="'$' + formatNumber(m.spend)" />
        <Stat
          v-if="m.email.sent"
          :label="__('Emails')"
          :value="formatNumber(m.email.sent)"
        />
        <Stat
          v-if="m.sms.unsub"
          :label="__('Unsubs')"
          :value="formatNumber(m.sms.unsub)"
        />
      </div>

      <div v-if="m.synced_at" class="mt-1 text-xs text-ink-gray-5">
        {{ __('Synced') }} {{ formatDate(m.synced_at, '', true) }}
      </div>
    </div>

    <!-- unlinked: inline link-property search -->
    <div v-else class="mt-2 text-sm">
      <div v-if="!showLink" class="flex items-center justify-between">
        <span class="text-ink-gray-5">{{ __('Not linked to InvestorLift.') }}</span>
        <Button variant="subtle" :label="__('Link property')" @click="openLink" />
      </div>
      <div v-else class="flex flex-col gap-2">
        <div class="flex items-center gap-1.5">
          <input
            v-model="query"
            type="text"
            :placeholder="__('Search address…')"
            class="min-w-0 flex-1 rounded border border-outline-gray-2 bg-surface-white px-2 py-1 text-sm text-ink-gray-8 placeholder:text-ink-gray-4 focus:outline-none"
            @keydown.enter="runSearch"
          />
          <Button :loading="searching" icon="search" variant="subtle" @click="runSearch" />
        </div>
        <div v-if="results.length" class="flex flex-col gap-1">
          <button
            v-for="r in results"
            :key="r.il_property_id"
            class="flex items-center justify-between gap-2 rounded px-2 py-1 text-left hover:bg-surface-gray-2"
            @click="doLink(r.il_property_id)"
          >
            <span class="truncate text-ink-gray-8">{{ r.address }}</span>
            <span class="shrink-0 text-xs text-ink-gray-5">{{ r.status }}</span>
          </button>
        </div>
        <div v-else-if="searched && !searching" class="text-xs text-ink-gray-5">
          {{ __('No matching InvestorLift properties.') }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import MegaphoneIcon from '~icons/lucide/megaphone'
import ExternalLinkIcon from '~icons/lucide/external-link'
import CopyIcon from '~icons/lucide/copy'
import DispoIcon from '~icons/lucide/columns-3'
import { copyToClipboard, formatDate, formatNumber } from '@/utils'
import { globalStore } from '@/stores/global'
import { Badge, Button, Dropdown, createResource, call } from 'frappe-ui'
import { computed, h, ref, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  lead: { type: String, required: true },
  address: { type: String, default: '' },
})

const { $socket } = globalStore()

// compact stat cell
const Stat = (p) =>
  h('div', { class: 'rounded-md bg-surface-gray-1 px-2 py-1.5' }, [
    h('div', { class: 'text-base font-medium text-ink-gray-8' }, p.value),
    h('div', { class: 'text-xs text-ink-gray-5' }, p.label),
    p.sub ? h('div', { class: 'text-xs text-ink-green-3' }, p.sub) : null,
  ])

const marketing = createResource({
  url: 'crm.api.investorlift.get_marketing',
  params: { lead: props.lead },
  auto: true,
})

const m = computed(() => marketing.data || {})
const linked = computed(() => !!m.value.linked)

// the buyer-facing listing is the link that actually gets sent to people, so
// make it one click to copy rather than open-then-copy-from-the-address-bar
function copyPublicLink() {
  if (m.value?.marketplace_url) copyToClipboard(m.value.marketplace_url)
}

function refresh() {
  marketing.update({ params: { lead: props.lead, refresh: 1 } })
  marketing.reload()
}

function statusTheme(status) {
  const s = (status || '').toLowerCase()
  if (s === 'sold') return 'green'
  if (s === 'pending') return 'orange'
  if (s === 'available') return 'blue'
  return 'gray'
}

const menuOptions = [
  {
    label: __('Unlink property'),
    icon: 'x',
    onClick: async () => {
      await call('crm.api.investorlift.unlink_property', { lead: props.lead })
      marketing.reload()
    },
  },
]

// --- inline link search ---
const showLink = ref(false)
const query = ref('')
const results = ref([])
const searching = ref(false)
const searched = ref(false)

function openLink() {
  showLink.value = true
  query.value = props.address || ''
  if (query.value.length >= 3) runSearch()
}

async function runSearch() {
  if (query.value.trim().length < 3) return
  searching.value = true
  searched.value = true
  try {
    results.value = await call('crm.api.investorlift.search_properties', { q: query.value })
  } finally {
    searching.value = false
  }
}

async function doLink(ilId) {
  await call('crm.api.investorlift.link_property', {
    lead: props.lead,
    il_property_id: ilId,
  })
  showLink.value = false
  marketing.update({ params: { lead: props.lead } })
  marketing.reload()
}

// live refresh when the hourly sync (or a link) fires
function onSync(data) {
  if (data.reference_doctype === 'CRM Lead' && data.reference_docname === props.lead) {
    marketing.reload()
  }
}
onMounted(() => $socket.on('crm_il_sync', onSync))
onBeforeUnmount(() => $socket.off('crm_il_sync', onSync))
</script>
