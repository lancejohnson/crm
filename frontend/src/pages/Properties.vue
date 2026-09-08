<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="[{ label: __('Properties') }]" />
    </template>
  </LayoutHeader>

  <div class="flex-1 overflow-y-auto px-3 pb-6 sm:px-5">
    <p class="mt-3 max-w-2xl text-sm text-ink-gray-5">
      {{ __('Comp and price a house without making it a lead. Same map, same picks, same calculator — saved here, visible to the team.') }}
    </p>

    <div v-if="!available && !loading" class="mt-8 text-sm text-ink-gray-5">
      {{ __('Properties are not set up on this site yet.') }}
    </div>

    <template v-else>
      <!-- Add: one address line is enough. The backend's _full_address skips the
           city/state/zip already inside it, so "412 Maple Ave, Aurora, MN 55705"
           geocodes and resolves on Zillow exactly like a webhook lead's does. -->
      <form
        class="mt-4 flex max-w-3xl flex-col gap-2 sm:flex-row sm:items-end"
        @submit.prevent="add"
      >
        <FormControl
          ref="addressInput"
          v-model="draft.address"
          class="min-w-0 flex-1"
          type="text"
          :label="__('Property address')"
          :placeholder="__('123 Main St, City, ST 55555')"
          autocomplete="off"
        />
        <FormControl
          v-model="draft.notes"
          class="min-w-0 sm:w-64"
          type="text"
          :label="__('Note (optional)')"
          :placeholder="__('e.g. drive-by, buyer ask')"
        />
        <Button
          variant="solid"
          type="submit"
          :label="__('Add & open comps')"
          iconLeft="plus"
          :loading="adding"
          :disabled="!draft.address.trim()"
        />
      </form>

      <div class="mt-5 flex max-w-3xl items-center gap-2">
        <FormControl
          v-model="q"
          type="text"
          class="min-w-0 flex-1"
          :placeholder="__('Search address, city, ZIP, note')"
        />
        <label class="flex shrink-0 items-center gap-1.5 text-sm text-ink-gray-6">
          <input v-model="mine" type="checkbox" class="rounded" />
          {{ __('Mine only') }}
        </label>
      </div>

      <div v-if="rows.length" class="mt-3 max-w-5xl">
        <div class="flex border-b border-outline-gray-1 py-1.5 text-xs font-medium text-ink-gray-5">
          <span class="min-w-0 flex-1">{{ __('Address') }}</span>
          <span class="hidden w-40 shrink-0 sm:block">{{ __('Latest calc') }}</span>
          <span class="hidden w-16 shrink-0 text-right sm:block">{{ __('Picked') }}</span>
          <span class="w-32 shrink-0 text-right">{{ __('Added') }}</span>
        </div>
        <button
          v-for="p in rows"
          :key="p.name"
          class="flex w-full items-center border-b border-outline-gray-1 py-2.5 text-left text-sm hover:bg-surface-gray-1"
          @click="open(p)"
        >
          <span class="min-w-0 flex-1">
            <span class="block truncate font-medium text-ink-gray-9">
              {{ p.property_address }}
            </span>
            <span v-if="p.notes" class="block truncate text-xs text-ink-gray-5">
              {{ p.notes }}
            </span>
          </span>
          <span class="hidden w-40 shrink-0 sm:block">
            <template v-if="p.latest_offer?.offer != null">
              <span class="font-medium text-ink-gray-8">{{ money(p.latest_offer.offer) }}</span>
              <span class="text-xs text-ink-gray-5"> · {{ kindLabel(p.latest_offer.kind) }}</span>
            </template>
            <span v-else class="text-ink-gray-4">—</span>
          </span>
          <span class="hidden w-16 shrink-0 text-right text-ink-gray-6 sm:block">
            {{ p.picked_count || '—' }}
          </span>
          <span
            class="w-32 shrink-0 text-right text-xs text-ink-gray-5"
            :title="`${p.owner_name} · ${p.creation}`"
          >
            {{ timeAgo(p.creation) }}
            <span class="block truncate">{{ p.owner_name }}</span>
          </span>
        </button>
      </div>

      <div
        v-else-if="!loading"
        class="mt-12 flex flex-col items-center gap-2 text-ink-gray-5"
      >
        <div class="text-lg font-medium text-ink-gray-7">
          {{ q || mine ? __('Nothing matches') : __('No properties yet') }}
        </div>
        <div class="text-sm">
          {{ __('Type an address above to comp it.') }}
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
/**
 * Scratch properties — comps + calcs on a house that is NOT a lead.
 *
 * Every earlier way to open the comps map went through a CRM Lead, which put
 * a fake seller on the Kanban, the Today board and the round-robin tally for
 * a house nobody had bought a lead on. This is the list of houses comped
 * that way; each row opens the same comps page a lead has.
 */
import LayoutHeader from '@/components/LayoutHeader.vue'
import { timeAgo } from '@/utils'
import { formatCompMoney } from '@/utils/comps'
import {
  Breadcrumbs,
  Button,
  FormControl,
  call,
  createResource,
  toast,
} from 'frappe-ui'
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const addressInput = ref(null)
const adding = ref(false)
const q = ref('')
const mine = ref(false)
const draft = reactive({ address: '', notes: '' })

const list = createResource({
  url: 'crm.api.properties.list_properties',
  params: { q: '', mine: 0 },
  auto: true,
})

let searchTimer = null
watch([q, mine], () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    list.submit({ q: q.value, mine: mine.value ? 1 : 0 })
  }, 200)
})

const available = computed(() => list.data?.available !== false)
const rows = computed(() => list.data?.properties || [])
const loading = computed(() => list.loading)

const KINDS = {
  cash: __('Cash'),
  novation: __('Novation'),
  list: __('List it'),
  rental: __('Rental'),
}
function kindLabel(kind) {
  return KINDS[kind] || KINDS.cash
}
function money(v) {
  return formatCompMoney(v)
}

function open(p) {
  router.push({ name: 'Property', params: { propertyId: p.name } })
}

async function add() {
  if (!draft.address.trim() || adding.value) return
  adding.value = true
  try {
    const res = await call('crm.api.properties.create_property', {
      address: draft.address,
      notes: draft.notes,
    })
    draft.address = ''
    draft.notes = ''
    router.push({ name: 'Property', params: { propertyId: res.name } })
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not add the property.'))
  } finally {
    adding.value = false
  }
}
</script>
