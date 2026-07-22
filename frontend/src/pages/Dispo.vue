<template>
  <LayoutHeader>
    <template #left-header>
      <div class="flex items-center gap-2">
        <Breadcrumbs :items="[{ label: __('Dispo') }]" />
        <span class="text-ink-gray-4">/</span>
        <!-- property switcher (per-property buyer board) -->
        <Dropdown :options="propertyOptions" placement="left">
          <button
            class="flex items-center gap-1.5 rounded px-2 py-1 text-base font-medium text-ink-gray-8 hover:bg-surface-gray-2"
          >
            <span class="max-w-[22rem] truncate">
              {{ current?.label || __('Select a property') }}
            </span>
            <ChevronDownIcon class="size-4 text-ink-gray-5" />
          </button>
        </Dropdown>
        <Badge
          v-if="current?.il_status"
          :theme="statusTheme(current.il_status)"
          variant="subtle"
        >
          {{ current.il_status }}
        </Badge>
      </div>
    </template>
    <template #right-header>
      <Button
        v-if="selectedLead"
        variant="ghost"
        :label="__('Text buyers')"
        iconLeft="message-circle"
        @click="openBulkText"
      />
      <Button
        v-if="selectedLead"
        variant="solid"
        :label="__('Add buyer')"
        iconLeft="plus"
        @click="showAddBuyer = true"
      />
      <router-link
        v-if="selectedLead"
        :to="{ name: 'Lead', params: { leadId: selectedLead } }"
      >
        <Button variant="ghost" :label="__('Open lead')" iconLeft="external-link" />
      </router-link>
    </template>
  </LayoutHeader>

  <div class="flex flex-1 overflow-hidden">
    <DispoBoard
      v-if="selectedLead"
      :key="selectedLead + '-' + boardKey"
      :lead="selectedLead"
      class="w-full"
    />
    <div
      v-else
      class="flex flex-1 flex-col items-center justify-center gap-2 text-ink-gray-4"
    >
      <DispoIcon class="size-8" />
      <span class="text-base">
        {{
          list.length
            ? __('Select a property to see its buyer board.')
            : __('No properties are in disposition yet. Link a lead to an InvestorLift property first.')
        }}
      </span>
    </div>
  </div>

  <AddBuyerToDealModal
    v-model="showAddBuyer"
    :lead="selectedLead || ''"
    @saved="boardKey++"
  />
  <BulkTextModal
    v-model="showBulkText"
    :recipients="bulkRecipients"
    :context-label="current?.label || ''"
  />
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import DispoBoard from '@/components/Activities/DispoBoard.vue'
import AddBuyerToDealModal from '@/components/Modals/AddBuyerToDealModal.vue'
import BulkTextModal from '@/components/Modals/BulkTextModal.vue'
import DispoIcon from '~icons/lucide/columns-3'
import ChevronDownIcon from '~icons/lucide/chevron-down'
import { Breadcrumbs, Button, Badge, Dropdown, createResource, usePageMeta } from 'frappe-ui'
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const properties = createResource({
  url: 'crm.api.investorlift_ingest.get_dispo_properties',
  auto: true,
})
const list = computed(() => properties.data || [])

const selectedLead = ref(route.params.leadId || null)
const showAddBuyer = ref(false)
const showBulkText = ref(false)
const boardKey = ref(0)

// buyers on the current deal's board — fed to the bulk-text modal. Fetched fresh
// when the button is clicked (deduped to one row per buyer).
const dealBuyers = createResource({
  url: 'crm.api.investorlift_ingest.get_deal_buyers',
  makeParams: () => ({ lead: selectedLead.value }),
})
const bulkRecipients = computed(() => {
  const seen = new Set()
  const out = []
  for (const b of dealBuyers.data || []) {
    if (b.buyer && !seen.has(b.buyer)) {
      seen.add(b.buyer)
      out.push({ name: b.buyer, buyer_name: b.buyer_name, phone: b.phone })
    }
  }
  return out
})
async function openBulkText() {
  if (!selectedLead.value) return
  await dealBuyers.reload()
  showBulkText.value = true
}

function selectProperty(p, push = true) {
  selectedLead.value = p.lead
  if (push) router.replace({ name: 'Dispo', params: { leadId: p.lead } })
}

// deep-link / nav sync
watch(
  () => route.params.leadId,
  (v) => {
    if (v) selectedLead.value = v
  },
)
// default to the most-recent property when none is chosen
watch(list, (l) => {
  if (!selectedLead.value && l.length) selectProperty(l[0], false)
})

const current = computed(() => list.value.find((p) => p.lead === selectedLead.value))

const propertyOptions = computed(() =>
  list.value.map((p) => ({
    label: p.buyer_count ? `${p.label}  ·  ${p.buyer_count}` : p.label,
    onClick: () => selectProperty(p),
  })),
)

function statusTheme(status) {
  const s = (status || '').toLowerCase()
  if (s === 'sold') return 'green'
  if (s === 'pending') return 'orange'
  if (s === 'available') return 'blue'
  return 'gray'
}

usePageMeta(() => ({ title: 'Dispo' }))
</script>
