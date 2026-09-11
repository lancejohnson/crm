<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="[{ label: __('Properties') }]" />
      <span v-if="rows.length" class="text-base text-ink-gray-5">
        {{ rows.length }} {{ rows.length === 1 ? __('property') : __('properties') }}
      </span>
    </template>
    <template #right-header>
      <div class="flex items-center gap-2">
        <FormControl
          v-model="q"
          type="text"
          class="w-56"
          :placeholder="__('Search address, city, ZIP, note')"
        />
        <label class="flex shrink-0 items-center gap-1.5 text-sm text-ink-gray-6">
          <input v-model="mine" type="checkbox" class="rounded" />
          {{ __('Mine') }}
        </label>
        <div class="flex items-center gap-0.5 rounded-md bg-surface-gray-2 p-0.5">
          <button
            class="flex size-6 items-center justify-center rounded"
            :class="viewMode === 'board' ? 'bg-surface-white shadow-sm text-ink-gray-8' : 'text-ink-gray-5'"
            :title="__('Board view')"
            @click="setView('board')"
          >
            <BoardIcon class="size-4" />
          </button>
          <button
            class="flex size-6 items-center justify-center rounded"
            :class="viewMode === 'list' ? 'bg-surface-white shadow-sm text-ink-gray-8' : 'text-ink-gray-5'"
            :title="__('List view')"
            @click="setView('list')"
          >
            <ListIcon class="size-4" />
          </button>
        </div>
        <Button
          variant="solid"
          :label="__('Add property')"
          iconLeft="plus"
          @click="openAdd"
        />
      </div>
    </template>
  </LayoutHeader>

  <div v-if="!available && !loading" class="px-5 py-8 text-sm text-ink-gray-5">
    {{ __('Properties are not set up on this site yet.') }}
  </div>

  <!-- BOARD: one column per stage; drag a card across to move it. -->
  <div v-else-if="viewMode === 'board'" class="flex h-full overflow-x-auto">
    <div class="flex gap-2 p-3">
      <div
        v-for="col in columns"
        :key="col.name"
        class="flex w-72 min-w-72 flex-col gap-2 rounded-lg p-2.5 hover:bg-surface-gray-2"
      >
        <div class="flex items-center justify-between px-1 text-base text-ink-gray-9">
          <span class="flex items-center gap-2 font-medium">
            <span class="size-2 rounded-full" :class="stageDot(col.name)" />
            {{ __(col.name) }}
          </span>
          <span class="text-ink-gray-5">{{ col.items.length }}</span>
        </div>
        <Draggable
          :list="col.items"
          group="properties"
          item-key="name"
          class="flex min-h-[8rem] flex-1 flex-col gap-2"
          :delay="200"
          :delay-on-touch-only="true"
          @change="onChange($event, col.name)"
        >
          <template #item="{ element: p }">
            <router-link
              :to="{ name: 'Property', params: { propertyId: p.name } }"
              class="block rounded-md border border-outline-gray-1 bg-surface-white p-3 shadow-sm hover:bg-surface-gray-1"
            >
              <div class="truncate font-medium text-ink-gray-9" :title="p.property_address">
                {{ streetAddress(p.property_address) }}
              </div>
              <div class="truncate text-xs text-ink-gray-5">
                {{ restOfAddress(p.property_address) || '&nbsp;' }}
              </div>
              <div v-if="p.notes" class="mt-1 truncate text-sm text-ink-gray-6" :title="p.notes">
                {{ p.notes }}
              </div>
              <div class="mt-2 flex items-center justify-between text-xs text-ink-gray-5">
                <span v-if="p.latest_offer?.offer != null" class="text-ink-gray-8">
                  <span class="font-medium">{{ money(p.latest_offer.offer) }}</span>
                  · {{ kindLabel(p.latest_offer.kind) }}
                </span>
                <span v-else>{{ __('No calc yet') }}</span>
                <span v-if="p.picked_count" :title="__('Comps picked')">
                  {{ p.picked_count }} {{ __('comps') }}
                </span>
              </div>
              <div
                v-if="p.lead"
                class="mt-1 cursor-pointer truncate text-xs text-ink-gray-6 hover:text-ink-gray-8"
                @click.stop.prevent="openLead(p.lead)"
              >{{ p.lead_name || p.lead }}</div>
              <div class="mt-1.5 flex items-center justify-between text-xs text-ink-gray-5">
                <span class="truncate">{{ p.owner_name }}</span>
                <span class="flex items-center gap-1.5">
                  <a
                    v-if="p.listing_url"
                    :href="p.listing_url"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="hover:text-ink-gray-8"
                    :title="__('Open the listing')"
                    @click.stop
                  >
                    <FeatherIcon name="external-link" class="size-3" />
                  </a>
                  <span :title="p.creation">{{ timeAgo(p.creation) }}</span>
                </span>
              </div>
            </router-link>
          </template>
        </Draggable>
      </div>
    </div>
  </div>

  <!-- LIST -->
  <div v-else class="flex-1 overflow-y-auto px-3 pb-6 sm:px-5">
    <div v-if="rows.length" class="mt-2">
      <div class="flex border-b border-outline-gray-1 py-1.5 text-xs font-medium text-ink-gray-5">
        <span class="w-32 shrink-0">{{ __('Stage') }}</span>
        <span class="min-w-0 flex-1">{{ __('Address') }}</span>
        <span class="hidden w-40 shrink-0 sm:block">{{ __('Latest calc') }}</span>
        <span class="hidden w-16 shrink-0 text-right sm:block">{{ __('Picked') }}</span>
        <span class="w-32 shrink-0 text-right">{{ __('Added') }}</span>
      </div>
      <div
        v-for="p in rows"
        :key="p.name"
        class="flex w-full items-center border-b border-outline-gray-1 py-2 text-left text-sm hover:bg-surface-gray-1"
      >
        <span class="w-32 shrink-0" @click.stop>
          <Dropdown :options="stageOptions(p)" placement="bottom-start">
            <button
              class="flex items-center gap-1.5 rounded px-1.5 py-0.5 text-xs text-ink-gray-8 hover:bg-surface-gray-2"
              :title="__('Change stage')"
            >
              <span class="size-2 rounded-full" :class="stageDot(p.status)" />
              {{ __(p.status) }}
            </button>
          </Dropdown>
        </span>
        <router-link
          :to="{ name: 'Property', params: { propertyId: p.name } }"
          class="flex min-w-0 flex-1 items-center"
        >
          <span class="min-w-0 flex-1">
            <span class="block truncate font-medium text-ink-gray-9">
              {{ p.property_address }}
            </span>
            <span v-if="p.notes" class="block truncate text-xs text-ink-gray-5">
              {{ p.notes }}
            </span>
            <span
              v-if="p.lead"
              class="block cursor-pointer truncate text-xs text-ink-gray-6 hover:text-ink-gray-8"
              @click.stop.prevent="openLead(p.lead)"
            >{{ p.lead_name || p.lead }}</span>
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
        </router-link>
      </div>
    </div>

    <div
      v-else-if="!loading"
      class="mt-12 flex flex-col items-center gap-2 text-ink-gray-5"
    >
      <div class="text-lg font-medium text-ink-gray-7">
        {{ q || mine ? __('Nothing matches') : __('No properties yet') }}
      </div>
      <div class="text-sm">
        {{ __('Comp and price a house without making it a lead.') }}
      </div>
      <Button class="mt-2" variant="solid" :label="__('Add property')" @click="openAdd" />
    </div>
  </div>

  <!-- Add: one address line is enough. The backend's _full_address skips the
       city/state/zip already inside it, so "412 Maple Ave, Aurora, MN 55705"
       geocodes and resolves on Zillow exactly like a webhook lead's does. -->
  <Dialog v-model="addOpen" :options="{ title: __('Add property') }">
    <template #body-content>
      <form class="flex flex-col gap-3" @submit.prevent="add">
        <div>
          <FormControl
            v-model="draft.address"
            type="text"
            :label="__('Address, or a Zillow / Redfin / Realtor / Auction.com link')"
            :placeholder="__('123 Main St, City, ST 55555  ·  https://www.zillow.com/homedetails/…')"
            autocomplete="off"
          />
          <!-- What the link resolves to, before anything is created. -->
          <p v-if="preview.error" class="mt-1 text-xs text-ink-red-4">
            {{ preview.error }}
          </p>
          <p v-else-if="preview.from_url && preview.address" class="mt-1 text-xs text-ink-gray-6">
            → <span class="font-medium text-ink-gray-8">{{ preview.address }}</span>
            <span class="text-ink-gray-5"> · {{ sourceLabel(preview.source) }}</span>
          </p>
        </div>
        <FormControl
          v-model="draft.notes"
          type="text"
          :label="__('Note (optional)')"
          :placeholder="__('e.g. drive-by, buyer ask')"
        />
        <LeadPicker
          v-if="list.data?.lead_supported"
          v-model="draft.lead"
          :lead-name="draft.leadName"
          :label="__('Lead (optional)')"
          @update:lead-name="draft.leadName = $event"
        />
        <button type="submit" class="hidden" />
      </form>
    </template>
    <template #actions>
      <Button
        class="w-full"
        variant="solid"
        :label="__('Add & open comps')"
        :loading="adding"
        :disabled="!draft.address.trim() || !!preview.error"
        @click="add"
      />
    </template>
  </Dialog>
</template>

<script setup>
/**
 * Scratch properties — comps + calcs on a house that is NOT a lead.
 *
 * Every earlier way to open the comps map went through a CRM Lead, which put
 * a fake seller on the Kanban, the Today board and the round-robin tally for
 * a house nobody had bought a lead on. This is the board of houses comped
 * that way: a column per stage (drag to move, same shape as Refunds), or a
 * flat list. Each card opens the same comps page a lead has.
 */
import LayoutHeader from '@/components/LayoutHeader.vue'
import LeadPicker from '@/components/LeadPicker.vue'
import { timeAgo } from '@/utils'
import { formatCompMoney, streetAddress } from '@/utils/comps'
import { stageDot } from '@/utils/propertyStages'
import BoardIcon from '~icons/lucide/columns-3'
import ListIcon from '~icons/lucide/list'
import Draggable from 'vuedraggable'
import {
  Breadcrumbs,
  Button,
  Dialog,
  Dropdown,
  FeatherIcon,
  FormControl,
  call,
  createResource,
  toast,
} from 'frappe-ui'
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const q = ref('')
const mine = ref(false)

// board vs list (persisted per-user across visits, like dispoView)
const viewMode = ref(localStorage.getItem('propertiesView') === 'list' ? 'list' : 'board')
function setView(v) {
  viewMode.value = v
  localStorage.setItem('propertiesView', v)
}

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
const stages = computed(() => list.data?.stages || [])
const loading = computed(() => list.loading)

// Columns are rebuilt from `rows` on every load; vuedraggable mutates the
// per-column arrays in place on a drag, which is fine because `onChange`
// persists the move and the arrays are thrown away on the next fetch.
const columns = computed(() =>
  stages.value.map((name) => ({
    name,
    items: rows.value.filter((p) => p.status === name),
  })),
)

const KINDS = {
  cash: __('Cash'),
  novation: __('Novation'),
  list: __('List it'),
  rental: __('Rental'),
}
function kindLabel(kind) {
  return KINDS[kind] || KINDS.cash
}
function openLead(lead) {
  if (!lead) return
  router.push({ name: 'Lead', params: { leadId: lead } })
}
function money(v) {
  return formatCompMoney(v)
}
function restOfAddress(address) {
  const s = String(address || '')
  const i = s.indexOf(',')
  return i === -1 ? '' : s.slice(i + 1).trim()
}

async function moveTo(p, status) {
  if (!p || p.status === status) return
  const before = p.status
  p.status = status
  try {
    await call('crm.api.properties.set_property_status', { name: p.name, status })
  } catch (e) {
    p.status = before
    toast.error(e.messages?.[0] || __('Could not move the property'))
    list.reload()
  }
}

function onChange(evt, toStatus) {
  const p = evt.added?.element
  if (p) moveTo(p, toStatus)
}

function stageOptions(p) {
  return stages.value.map((s) => ({
    label: __(s),
    onClick: () => moveTo(p, s),
  }))
}

// --- add ---------------------------------------------------------------------
const addOpen = ref(false)
const adding = ref(false)
const draft = reactive({ address: '', notes: '', lead: '', leadName: '' })

const SOURCES = {
  zillow: 'Zillow',
  redfin: 'Redfin',
  realtor: 'Realtor',
  auction: 'Auction.com',
}
function sourceLabel(s) {
  return SOURCES[s] || __('listing')
}

// Live "what will this become" for a pasted link. Only asked for text that
// looks like a URL; a typed address is stored as typed.
const preview = reactive({ address: '', from_url: false, source: '', error: '' })
let previewTimer = null
watch(
  () => draft.address,
  (text) => {
    clearTimeout(previewTimer)
    const t = (text || '').trim().toLowerCase()
    const isUrl =
      t.startsWith('http') || t.startsWith('www.') ||
      /^(zillow|redfin|realtor|auction)\.com/.test(t)
    if (!isUrl) {
      Object.assign(preview, { address: '', from_url: false, source: '', error: '' })
      return
    }
    previewTimer = setTimeout(async () => {
      try {
        const r = await call('crm.api.properties.preview_address', { text })
        Object.assign(preview, {
          address: r?.address || '',
          from_url: !!r?.from_url,
          source: r?.source || '',
          error: r?.error || '',
        })
      } catch (e) {
        Object.assign(preview, { address: '', from_url: true, source: '', error: '' })
      }
    }, 250)
  },
)

function openAdd() {
  draft.address = ''
  draft.notes = ''
  draft.lead = ''
  draft.leadName = ''
  Object.assign(preview, { address: '', from_url: false, source: '', error: '' })
  addOpen.value = true
  nextTick(() => {
    document.querySelector("[role=dialog] input[placeholder='123 Main St, City, ST 55555']")?.focus()
  })
}

async function add() {
  if (!draft.address.trim() || adding.value) return
  adding.value = true
  try {
    const res = await call('crm.api.properties.create_property', {
      address: draft.address,
      notes: draft.notes,
      lead: draft.lead || '',
    })
    addOpen.value = false
    router.push({ name: 'Property', params: { propertyId: res.name } })
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not add the property.'))
  } finally {
    adding.value = false
  }
}
</script>
