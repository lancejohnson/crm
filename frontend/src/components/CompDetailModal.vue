<template>
  <Dialog
    v-model="show"
    :options="{ size: '4xl', title: comp?.address || __('Comparable property') }"
  >
    <template #body>
      <div class="flex h-[82vh] max-h-[82vh] flex-col overflow-hidden bg-surface-modal">
        <div class="flex items-start justify-between gap-4 border-b px-5 py-4 sm:px-6">
          <div class="min-w-0">
            <div class="mb-1 flex flex-wrap items-center gap-2">
              <Badge
                variant="subtle"
                :theme="comp?.status === 'Active' ? 'orange' : 'gray'"
                :label="comp?.status === 'Active' ? __('For sale') : __('Off-market')"
              />
              <Badge
                v-if="fit.total"
                variant="subtle"
                :theme="fit.theme"
                :label="__('{0}/{1} fit', [fit.matched, fit.total])"
              />
              <Badge v-if="comp?.selected" variant="subtle" theme="blue" :label="__('Using')" />
            </div>
            <h2 class="truncate text-xl font-semibold text-ink-gray-9">
              {{ comp?.address || __('Comparable property') }}
            </h2>
            <div class="mt-0.5 text-sm text-ink-gray-5">
              {{ compLocation }}
            </div>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <Button
              :variant="comp?.selected ? 'subtle' : 'solid'"
              :label="comp?.selected ? __('Remove from table') : __('Add as comp')"
              @click="$emit('use', comp.name)"
            />
            <Button variant="ghost" icon="x" @click="show = false" />
          </div>
        </div>

        <div class="grid min-h-0 flex-1 md:grid-cols-[minmax(0,1.55fr)_minmax(18rem,0.85fr)]">
          <div class="flex min-h-0 flex-col border-b bg-surface-gray-2 md:border-b-0 md:border-r">
            <div class="relative flex min-h-[16rem] flex-1 items-center justify-center overflow-hidden bg-black/90">
              <img
                v-if="photos.length"
                :src="photos[photoIndex]"
                :alt="comp?.address"
                class="size-full object-contain"
              />
              <div v-else-if="loading" class="flex flex-col items-center gap-2 text-sm text-ink-white/70">
                <FeatherIcon name="loader" class="size-5 animate-spin" />
                {{ __('Loading property photos…') }}
              </div>
              <div v-else class="flex flex-col items-center gap-2 px-6 text-center text-sm text-ink-white/70">
                <FeatherIcon name="image" class="size-7" />
                {{ __('No Zillow photos are available for this property.') }}
              </div>

              <template v-if="photos.length > 1">
                <button
                  class="absolute left-3 top-1/2 flex size-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/55 text-white hover:bg-black/75"
                  :aria-label="__('Previous photo')"
                  @click="previousPhoto"
                >
                  <FeatherIcon name="chevron-left" class="size-5" />
                </button>
                <button
                  class="absolute right-3 top-1/2 flex size-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/55 text-white hover:bg-black/75"
                  :aria-label="__('Next photo')"
                  @click="nextPhoto"
                >
                  <FeatherIcon name="chevron-right" class="size-5" />
                </button>
                <div class="absolute bottom-3 right-3 rounded-full bg-black/60 px-2.5 py-1 text-xs text-white">
                  {{ photoIndex + 1 }} / {{ photos.length }}
                </div>
              </template>
            </div>

            <div v-if="photos.length > 1" class="flex shrink-0 gap-2 overflow-x-auto p-3">
              <button
                v-for="(photo, index) in photos"
                :key="photo"
                class="h-16 w-24 shrink-0 overflow-hidden rounded-md border-2 bg-surface-gray-3"
                :class="index === photoIndex ? 'border-outline-blue-2' : 'border-transparent opacity-70 hover:opacity-100'"
                @click="photoIndex = index"
              >
                <img :src="photo" :alt="__('Photo {0}', [index + 1])" class="size-full object-cover" loading="lazy" />
              </button>
            </div>
          </div>

          <aside class="min-h-0 overflow-y-auto bg-surface-white p-5 sm:p-6">
            <div class="flex items-baseline justify-between gap-3">
              <div>
                <div class="text-2xl font-semibold text-ink-gray-9">
                  {{ formatCompMoney(displayPrice) }}
                </div>
                <div class="text-xs text-ink-gray-5">
                  {{ displayPriceLabel }}
                </div>
              </div>
              <a
                v-if="zillowLink"
                :href="zillowLink"
                target="_blank"
                rel="noopener noreferrer"
                class="flex shrink-0 items-center gap-1 text-sm font-medium text-ink-blue-3 hover:underline"
              >
                {{ __('Zillow') }}
                <FeatherIcon name="arrow-up-right" class="size-3.5" />
              </a>
            </div>

            <div class="mt-5 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
              <div v-for="fact in facts" :key="fact.label">
                <div class="text-xs text-ink-gray-5">{{ fact.label }}</div>
                <div class="mt-0.5 font-medium text-ink-gray-8">{{ fact.value }}</div>
              </div>
            </div>

            <div v-if="fit.total" class="mt-5 rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-3">
              <div class="text-sm font-medium text-ink-gray-8">
                {{ __('Similarity to the subject') }}
              </div>
              <div class="mt-2 flex flex-wrap gap-1.5">
                <span
                  v-for="dimension in fit.dimensions"
                  :key="dimension.key"
                  class="rounded px-2 py-1 text-xs"
                  :class="dimension.matches ? 'bg-surface-green-2 text-ink-green-3' : 'bg-surface-amber-1 text-ink-amber-3'"
                >
                  {{ dimension.matches ? '✓' : '△' }} {{ __(dimension.label) }}
                </span>
              </div>
              <div class="mt-2 text-xs leading-relaxed text-ink-gray-5">
                {{ __('Fit uses the same type, beds, baths, size and age tolerances as the comps filter.') }}
              </div>
            </div>

            <div v-if="timeline.length" class="mt-5">
              <div class="text-sm font-medium text-ink-gray-8">{{ __('Property history') }}</div>
              <div class="mt-2 flex flex-col gap-2 text-sm">
                <div v-for="row in timeline" :key="row.label" class="flex justify-between gap-3">
                  <span class="text-ink-gray-5">{{ row.label }}</span>
                  <span class="text-right font-medium text-ink-gray-8">{{ row.value }}</span>
                </div>
              </div>
            </div>

            <div v-if="details?.description" class="mt-5">
              <div class="text-sm font-medium text-ink-gray-8">{{ __('About this property') }}</div>
              <p class="mt-2 whitespace-pre-line text-sm leading-relaxed text-ink-gray-6">
                {{ details.description }}
              </p>
            </div>

            <div
              v-if="error || (!loading && response && !response.available)"
              class="mt-5 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3 text-sm text-ink-gray-6"
            >
              {{ error || response?.message || __('More details are unavailable right now.') }}
              <button class="ml-1 font-medium text-ink-blue-3 hover:underline" @click="load(true)">
                {{ __('Retry') }}
              </button>
            </div>
          </aside>
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { compFit, formatCompMoney } from '@/utils/comps'
import { zillowUrl } from '@/utils/propertyLinks'
import { Badge, Button, Dialog, FeatherIcon, call } from 'frappe-ui'
import { computed, ref, watch } from 'vue'

defineEmits(['use'])

const props = defineProps({
  lead: { type: String, required: true },
  comp: { type: Object, default: null },
  subject: { type: Object, default: null },
})

const show = defineModel({ type: Boolean })
const loading = ref(false)
const error = ref('')
const response = ref(null)
const photoIndex = ref(0)
const cache = new Map()
let requestToken = 0

const details = computed(() => response.value?.details || null)
const photos = computed(() => response.value?.photos || [])
const fit = computed(() => compFit(props.comp, props.subject))
const compLocation = computed(() =>
  [props.comp?.city, props.comp?.state, props.comp?.zip].filter(Boolean).join(', '),
)
const displayPrice = computed(() => details.value?.asking_price || props.comp?.price)
const displayPriceLabel = computed(() =>
  details.value?.asking_price ? __('Current Zillow ask') : __('Last known list price'),
)
const zillowLink = computed(() => details.value?.zillow_url || zillowUrl(props.comp?.address || ''))
const facts = computed(() => {
  const d = details.value || {}
  const c = props.comp || {}
  return [
    { label: __('Beds'), value: decimal(d.beds || c.bedrooms) },
    { label: __('Baths'), value: decimal(d.baths || c.bathrooms) },
    { label: __('Living area'), value: area(d.sqft || c.square_footage) },
    { label: __('Year built'), value: whole(d.year_built || c.year_built) },
    { label: __('Property type'), value: d.property_type || c.property_type || '—' },
    { label: __('Distance'), value: c.distance_mi ? `${Number(c.distance_mi).toFixed(1)} mi` : '—' },
    { label: __('Lot size'), value: d.lot_size || '—' },
    { label: __('Zestimate'), value: formatCompMoney(d.zestimate) },
  ]
})
const timeline = computed(() => {
  const rows = []
  if (details.value?.last_sale?.price) {
    rows.push({
      label: __('Last sold'),
      value: `${formatCompMoney(details.value.last_sale.price)} · ${dateOnly(details.value.last_sale.date)}`,
    })
  }
  if (props.comp?.listed_date) {
    rows.push({ label: __('Listed'), value: dateOnly(props.comp.listed_date) })
  }
  if (props.comp?.removed_date) {
    rows.push({ label: __('Went off market'), value: dateOnly(props.comp.removed_date) })
  } else if (props.comp?.days_on_market) {
    rows.push({ label: __('Time on market'), value: __('{0} days', [props.comp.days_on_market]) })
  }
  return rows
})

watch(
  () => [show.value, props.comp?.name],
  ([open]) => {
    if (!open || !props.comp?.name) return
    photoIndex.value = 0
    load()
  },
  // CompsView mounts this with v-if on the chosen comp, which is set in the same
  // tick as `show` — so the component's first render already has show=true. A
  // non-immediate watcher would never see a transition and the gallery would
  // sit forever on its empty fallback despite the endpoint returning photos.
  { immediate: true },
)

async function load(force = false) {
  if (!props.comp?.name) return
  const name = props.comp.name
  if (!force && cache.has(name)) {
    response.value = cache.get(name)
    return
  }
  const token = ++requestToken
  loading.value = true
  error.value = ''
  response.value = null
  try {
    const result = await call('crm.api.comps.get_comp_details', {
      lead: props.lead,
      comp: name,
    })
    if (token !== requestToken) return
    response.value = result
    cache.set(name, result)
  } catch (e) {
    if (token !== requestToken) return
    error.value = e?.messages?.[0] || e?.message || __('Could not load this property.')
  } finally {
    if (token === requestToken) loading.value = false
  }
}

function previousPhoto() {
  photoIndex.value = (photoIndex.value - 1 + photos.value.length) % photos.value.length
}

function nextPhoto() {
  photoIndex.value = (photoIndex.value + 1) % photos.value.length
}

function decimal(value) {
  const n = Number(value)
  if (!Number.isFinite(n) || n <= 0) return '—'
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, '')
}

function whole(value) {
  const n = Number(value)
  return Number.isFinite(n) && n > 0 ? Math.round(n).toLocaleString() : '—'
}

function area(value) {
  const n = Number(value)
  return Number.isFinite(n) && n > 0 ? `${Math.round(n).toLocaleString()} sf` : '—'
}

function dateOnly(value) {
  if (!value) return '—'
  const [y, m, d] = String(value).slice(0, 10).split('-').map(Number)
  if (!y || !m || !d) return String(value)
  return new Date(y, m - 1, d).toLocaleDateString()
}
</script>
