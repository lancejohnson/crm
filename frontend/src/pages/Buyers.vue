<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="[{ label: __('Buyers') }]" />
    </template>
    <template #right-header>
      <Button
        variant="solid"
        :label="__('New buyer')"
        iconLeft="plus"
        @click="showModal = true"
      />
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
      <div class="flex-1" />
      <span class="text-sm text-ink-gray-5">
        {{ rows.length }} {{ __('buyers') }}
      </span>
    </div>

    <!-- list -->
    <div class="flex-1 overflow-y-auto">
      <div
        class="grid items-center gap-3 border-b px-4 py-2 text-xs font-medium uppercase text-ink-gray-5 sm:px-5"
        :style="gridCols"
      >
        <span>{{ __('Name') }}</span>
        <span>{{ __('Phone') }}</span>
        <span>{{ __('Email') }}</span>
        <span>{{ __('Type') }}</span>
        <span>{{ __('Active in') }}</span>
        <span class="text-right">{{ __('Deals') }}</span>
      </div>

      <router-link
        v-for="b in rows"
        :key="b.name"
        :to="{ name: 'Buyer', params: { buyerId: b.name } }"
        class="grid items-center gap-3 border-b border-outline-gray-1 px-4 py-2.5 text-sm text-ink-gray-8 hover:bg-surface-gray-1 sm:px-5"
        :style="gridCols"
      >
        <span class="flex min-w-0 items-center gap-1.5">
          <span class="truncate font-medium">{{ b.buyer_name || '—' }}</span>
          <BadgeCheckIcon v-if="b.verified" class="size-3.5 shrink-0 text-ink-blue-3" />
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
        <span class="truncate text-ink-gray-6">{{ b.active_in || '—' }}</span>
        <span class="text-right text-ink-gray-6">{{ b.deal_count || 0 }}</span>
      </router-link>

      <div
        v-if="!rows.length && !buyers.loading"
        class="flex flex-col items-center justify-center gap-2 py-16 text-ink-gray-4"
      >
        <UsersIcon class="size-8" />
        <span class="text-base">
          {{ search || metroFilter ? __('No buyers match.') : __('No buyers yet.') }}
        </span>
      </div>
    </div>
  </div>

  <BuyerModal v-model="showModal" @saved="buyers.reload()" />
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import BuyerModal from '@/components/Modals/BuyerModal.vue'
import SearchIcon from '~icons/lucide/search'
import UsersIcon from '~icons/lucide/users-round'
import BadgeCheckIcon from '~icons/lucide/badge-check'
import Autocomplete from '@/components/frappe-ui/Autocomplete.vue'
import { formatPhone } from '@/utils/phoneFormat'
import {
  Breadcrumbs,
  Button,
  TextInput,
  createResource,
  usePageMeta,
} from 'frappe-ui'
import { ref, computed, watch } from 'vue'

const search = ref('')
const metroFilter = ref('')
const showModal = ref(false)

const gridCols = {
  gridTemplateColumns: 'minmax(10rem,1.4fr) 9rem minmax(10rem,1.4fr) minmax(8rem,1fr) minmax(8rem,1fr) 3.5rem',
}

const buyers = createResource({
  url: 'crm.api.buyers.get_buyers',
  makeParams: () => ({
    search: search.value || null,
    metro: metroFilter.value || null,
  }),
  auto: true,
})
const rows = computed(() => buyers.data || [])

watch([search, metroFilter], () => buyers.reload())

const metros = createResource({
  url: 'crm.api.buyers.get_metro_areas',
  auto: true,
})
const metroOptions = computed(() =>
  (metros.data || []).map((m) => ({ label: m.metro_name, value: m.name })),
)

function tagList(buyer_type) {
  return (buyer_type || '')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
}

usePageMeta(() => ({ title: 'Buyers' }))
</script>
