<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="[{ label: __('Buyers') }]" />
    </template>
    <template #right-header>
      <div class="flex items-center gap-2">
        <!-- bulk import lives in the "..." menu: an occasional list-drop
             action, not a daily one (same placement as Leads) -->
        <Dropdown :options="buyerListActions" placement="right">
          <Button variant="ghost" icon="more-horizontal" />
        </Dropdown>
        <Button
          variant="solid"
          :label="__('New buyer')"
          iconLeft="plus"
          @click="showModal = true"
        />
      </div>
    </template>
  </LayoutHeader>

  <div class="flex flex-1 flex-col overflow-hidden">
    <!-- toolbar -->
    <div class="flex items-center gap-2 border-b px-4 py-2.5 sm:px-5">
      <TextInput
        v-model="search"
        type="text"
        class="w-64"
        :placeholder="__('Search name, phone, email…')"
        :debounce="300"
      >
        <template #prefix>
          <SearchIcon class="size-4 text-ink-gray-5" />
        </template>
      </TextInput>
      <Autocomplete
        :options="metroOptions"
        :modelValue="metroFilter"
        :placeholder="__('All metros')"
        @update:modelValue="(v) => (metroFilter = v?.value || '')"
      >
        <template #target="{ togglePopover }">
          <Button variant="outline" iconRight="chevron-down" @click="togglePopover()">
            <span class="max-w-48 truncate">{{ metroFilter || __('All metros') }}</span>
          </Button>
        </template>
        <template #footer="{ close }">
          <Button
            v-if="metroFilter"
            variant="ghost"
            class="w-full !justify-start"
            :label="__('Clear filter')"
            iconLeft="x"
            @click="metroFilter = ''; close()"
          />
        </template>
      </Autocomplete>
      <Autocomplete
        :options="propertyOptions"
        :modelValue="propertyFilter"
        :placeholder="__('All properties')"
        @update:modelValue="(v) => (propertyFilter = v?.value || '')"
      >
        <template #target="{ togglePopover }">
          <Button variant="outline" iconRight="chevron-down" @click="togglePopover()">
            <span class="max-w-56 truncate">{{ propertyLabel || __('All properties') }}</span>
          </Button>
        </template>
        <template #footer="{ close }">
          <Button
            v-if="propertyFilter"
            variant="ghost"
            class="w-full !justify-start"
            :label="__('Clear filter')"
            iconLeft="x"
            @click="propertyFilter = ''; close()"
          />
        </template>
      </Autocomplete>
      <Autocomplete
        v-if="listOptions.length"
        :options="listOptions"
        :modelValue="listFilter"
        :placeholder="__('All lists')"
        @update:modelValue="(v) => (listFilter = v?.value || '')"
      >
        <template #target="{ togglePopover }">
          <Button variant="outline" iconRight="chevron-down" @click="togglePopover()">
            <span class="max-w-48 truncate">{{ listFilter || __('All lists') }}</span>
          </Button>
        </template>
        <template #footer="{ close }">
          <Button
            v-if="listFilter"
            variant="ghost"
            class="w-full !justify-start"
            :label="__('Clear filter')"
            iconLeft="x"
            @click="listFilter = ''; close()"
          />
        </template>
      </Autocomplete>
      <div class="flex-1" />
      <template v-if="!selectMode">
        <span class="text-sm text-ink-gray-5">
          {{ rows.length }} {{ __('buyers') }}
        </span>
        <Button
          v-if="hasFilter && rows.length"
          variant="solid"
          :label="__('Text these') + ' (' + textTheseCount + ')'"
          iconLeft="message-circle"
          @click="textThese"
        />
        <Button
          variant="ghost"
          :label="__('Select to text')"
          iconLeft="message-circle"
          @click="enterSelect"
        />
      </template>
      <template v-else>
        <span class="text-sm text-ink-gray-5">
          {{ selected.size }} {{ __('selected') }}
        </span>
        <Button variant="ghost" :label="__('Cancel')" @click="exitSelect" />
        <Button
          variant="solid"
          :label="__('Text') + ' (' + selected.size + ')'"
          iconLeft="message-circle"
          :disabled="!selected.size"
          @click="textSelected"
        />
      </template>
    </div>

    <!-- list -->
    <div class="flex-1 overflow-y-auto">
      <div
        class="grid items-center gap-3 border-b px-4 py-2 text-xs font-medium uppercase text-ink-gray-5 sm:px-5"
        :style="gridCols"
      >
        <span v-if="selectMode" />
        <span>{{ __('Name') }}</span>
        <span>{{ __('Phone') }}</span>
        <span>{{ __('Email') }}</span>
        <span>{{ __('Type') }}</span>
        <span>{{ propertyActive ? __('Status') : __('Active in') }}</span>
        <span class="text-right">{{ __('Deals') }}</span>
      </div>

      <component
        :is="selectMode ? 'div' : 'router-link'"
        v-for="b in rows"
        :key="b.name"
        :to="selectMode ? undefined : { name: 'Buyer', params: { buyerId: b.name } }"
        class="grid cursor-pointer items-center gap-3 border-b border-outline-gray-1 px-4 py-2.5 text-sm text-ink-gray-8 hover:bg-surface-gray-1 sm:px-5"
        :style="gridCols"
        @click="selectMode && toggle(b.name)"
      >
        <span v-if="selectMode" class="flex items-center">
          <input
            type="checkbox"
            class="pointer-events-none size-3.5 rounded border-outline-gray-3 accent-surface-gray-7"
            :checked="selected.has(b.name)"
          />
        </span>
        <span class="flex min-w-0 items-center gap-1.5">
          <span class="truncate font-medium">{{ b.buyer_name || '—' }}</span>
          <BadgeCheckIcon v-if="b.verified" class="size-3.5 shrink-0 text-ink-blue-3" />
          <BanIcon
            v-if="b.do_not_contact"
            class="size-3.5 shrink-0 text-ink-red-4"
            :title="__('Do not contact — this buyer asked to be removed')"
          />
        </span>
        <span class="truncate text-ink-gray-6">{{ formatPhone(b.phone) || '—' }}</span>
        <span class="truncate text-ink-gray-6">{{ b.email || '—' }}</span>
        <span class="flex min-w-0 flex-wrap gap-1">
          <span
            v-for="t in tagList(b.buyer_type)"
            :key="t"
            class="rounded bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-7"
          >
            {{ t }}
          </span>
          <span v-if="!tagList(b.buyer_type).length" class="text-ink-gray-4">—</span>
        </span>
        <span v-if="propertyActive" class="flex min-w-0 items-center gap-1.5">
          <template v-if="b.interest_stage">
            <span
              class="size-2 shrink-0 rounded-full"
              :style="{ backgroundColor: stageColor(b.interest_stage) }"
            />
            <span class="truncate text-ink-gray-7">{{ b.interest_stage }}</span>
          </template>
          <span v-else class="text-ink-gray-4">—</span>
        </span>
        <span v-else class="truncate text-ink-gray-6">{{ b.active_in || '—' }}</span>
        <span class="text-right text-ink-gray-6">{{ b.deal_count || 0 }}</span>
      </component>

      <div
        v-if="!rows.length && !buyers.loading"
        class="flex flex-col items-center justify-center gap-2 py-16 text-ink-gray-4"
      >
        <UsersIcon class="size-8" />
        <span class="text-base">
          {{ hasFilter ? __('No buyers match.') : __('No buyers yet.') }}
        </span>
      </div>
    </div>
  </div>

  <BuyerModal v-model="showModal" @saved="buyers.reload()" />
  <ImportBuyersModal
    v-if="showImportModal"
    v-model="showImportModal"
    @imported="buyers.reload(); importLists.reload()"
  />
  <BulkTextModal v-model="showBulkText" :recipients="bulkRecipients" />
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import BuyerModal from '@/components/Modals/BuyerModal.vue'
import ImportBuyersModal from '@/components/Modals/ImportBuyersModal.vue'
import BulkTextModal from '@/components/Modals/BulkTextModal.vue'
import SearchIcon from '~icons/lucide/search'
import UsersIcon from '~icons/lucide/users-round'
import BadgeCheckIcon from '~icons/lucide/badge-check'
import BanIcon from '~icons/lucide/ban'
import Autocomplete from '@/components/frappe-ui/Autocomplete.vue'
import { formatPhone } from '@/utils/phoneFormat'
import {
  Breadcrumbs,
  Button,
  Dropdown,
  TextInput,
  createResource,
  usePageMeta,
} from 'frappe-ui'
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const search = ref('')
const metroFilter = ref('')
const propertyFilter = ref('')
// import-list filter — seedable via /buyers?list=... (the import modal's
// "Open this list" lands here pre-filtered, ready for "Text these (N)")
const listFilter = ref(String(route.query.list || ''))
const showModal = ref(false)
const showImportModal = ref(false)

const buyerListActions = computed(() => [
  {
    label: __('Import buyers'),
    icon: 'upload',
    onClick: () => (showImportModal.value = true),
  },
])

// bulk-text: "Select to text" (manual pick) or "Text these" (whole filtered list)
const selectMode = ref(false)
const selected = ref(new Set())
const showBulkText = ref(false)
const bulkRecipients = ref([]) // recipients handed to BulkTextModal (set on open)

const hasFilter = computed(
  () =>
    !!(search.value || metroFilter.value || propertyFilter.value || listFilter.value),
)
// when filtered by a property, each buyer carries a per-property interest_stage
const propertyActive = computed(() => !!propertyFilter.value)

const STAGE_COLOR = {
  New: '#3b82f6',
  'Attempted to Contact': '#f97316',
  'Not Interested': '#ef4444',
  Interested: '#22c55e',
  'Offer Made': '#a855f7',
}
function stageColor(s) {
  return STAGE_COLOR[s] || '#9ca3af'
}

// mirrors BulkTextModal's default: text everyone with a phone EXCEPT the
// default-excluded status(es), so the "Text these (N)" button shows the count
// that will actually be pre-selected (Not Interested is off by default).
const EXCLUDE_BY_DEFAULT = new Set(['Not Interested'])
// the post-failsafe count, so the button previews what will actually be
// pre-selected: phone on file, not a default-excluded stage, and not opted out
const textTheseCount = computed(
  () =>
    rows.value.filter(
      (r) =>
        (r.phone || '').trim() &&
        !r.do_not_contact &&
        !(r.interest_stage && EXCLUDE_BY_DEFAULT.has(r.interest_stage)),
    ).length,
)

const gridCols = computed(() => ({
  gridTemplateColumns:
    (selectMode.value ? '1.5rem ' : '') +
    'minmax(10rem,1.4fr) 9rem minmax(10rem,1.4fr) minmax(8rem,1fr) minmax(8rem,1fr) 3.5rem',
}))

function enterSelect() {
  selectMode.value = true
  selected.value = new Set()
}
function exitSelect() {
  selectMode.value = false
  selected.value = new Set()
}
function toggle(name) {
  const s = new Set(selected.value)
  s.has(name) ? s.delete(name) : s.add(name)
  selected.value = s
}

function toRecipient(r) {
  return {
    name: r.name,
    buyer_name: r.buyer_name,
    phone: r.phone,
    first_name: r.first_name,
    stage: r.interest_stage, // per-property status (only when property-filtered)
    do_not_contact: r.do_not_contact, // asked to be removed — modal drops them
  }
}
// text everyone currently in the (filtered) list
function textThese() {
  bulkRecipients.value = rows.value.map(toRecipient)
  showBulkText.value = true
}
// text the manually-checked buyers (select mode)
function textSelected() {
  bulkRecipients.value = rows.value
    .filter((r) => selected.value.has(r.name))
    .map(toRecipient)
  showBulkText.value = true
}

const buyers = createResource({
  url: 'crm.api.buyers.get_buyers',
  makeParams: () => ({
    search: search.value || null,
    metro: metroFilter.value || null,
    property: propertyFilter.value || null,
    import_list: listFilter.value || null,
  }),
  auto: true,
})
const rows = computed(() => buyers.data || [])

watch([search, metroFilter, propertyFilter, listFilter], () => buyers.reload())

const metros = createResource({
  url: 'crm.api.buyers.get_metro_areas',
  auto: true,
})
const metroOptions = computed(() =>
  (metros.data || []).map((m) => ({ label: m.metro_name, value: m.name })),
)

// dispo properties (leads linked to an IL property) for the Property filter
const properties = createResource({
  url: 'crm.api.investorlift_ingest.get_dispo_properties',
  auto: true,
})
const propertyOptions = computed(() =>
  (properties.data || []).map((p) => ({ label: p.label, value: p.lead })),
)
const propertyLabel = computed(
  () => propertyOptions.value.find((p) => p.value === propertyFilter.value)?.label || '',
)

// buyer import lists for the "All lists" filter (hidden until one exists)
const importLists = createResource({
  url: 'crm.api.buyer_import.get_buyer_import_lists',
  auto: true,
})
const listOptions = computed(() =>
  (importLists.data || []).map((l) => ({
    label: `${l.list_name} (${l.total})`,
    value: l.list_name,
  })),
)

function tagList(buyer_type) {
  return (buyer_type || '')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
}

usePageMeta(() => ({ title: 'Buyers' }))
</script>
