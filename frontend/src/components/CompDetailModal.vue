<template>
  <Dialog
    v-model="show"
    :options="{ size: '4xl', title: comp?.address || __('Comparable property') }"
  >
    <template #body>
      <div
        id="comp-detail-modal"
        class="flex h-[calc(100dvh-0.5rem)] max-h-[calc(100dvh-0.5rem)] flex-col overflow-hidden bg-surface-modal sm:h-[82vh] sm:max-h-[82vh]"
      >
        <div class="flex items-start justify-between gap-3 border-b px-4 py-3 sm:gap-4 sm:px-6 sm:py-4">
          <div class="min-w-0">
            <div class="mb-1 flex flex-wrap items-center gap-2">
              <Badge
                v-if="subjectMode"
                variant="subtle"
                theme="blue"
                :label="__('This property')"
              />
              <!-- Hand-styled from the shared palette rather than a Badge:
                   frappe-ui's Badge only knows gray/blue/green/orange/red, so a
                   `theme="violet"` would silently render an unstyled chip. This
                   also means the four states look identical here, on the tray
                   card and on the map, which is the whole point of one palette. -->
              <span
                v-else
                class="rounded px-1.5 py-0.5 text-xs font-semibold"
                :style="{ background: palette.bg, color: palette.ink }"
              >
                {{ statusLabel }}
              </span>
              <!-- A comp is not similar to itself; "5/5 fit" on the subject is
                   noise where a real judgement belongs. -->
              <Badge
                v-if="fit.total && !subjectMode"
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
            <!-- A house cannot be a comp for itself, so the subject gets no
                 add-as-comp button rather than one that would corrupt the calc. -->
            <Button
              v-if="!subjectMode"
              class="hidden sm:inline-flex"
              :variant="comp?.selected ? 'subtle' : 'solid'"
              :label="comp?.selected ? __('Remove from table') : __('Add as comp')"
              @click="$emit('use', comp.name)"
            />
            <Button
              v-if="hasStreetView"
              class="hidden sm:inline-flex"
              variant="subtle"
              :label="__('Street View')"
              @click="$emit('street')"
            />
            <Button variant="ghost" icon="x" @click="show = false" />
          </div>
        </div>

        <div class="grid min-h-0 flex-1 md:grid-cols-[minmax(0,1.55fr)_minmax(18rem,0.85fr)]">
          <div class="flex min-h-0 flex-col border-b bg-surface-gray-2 md:border-b-0 md:border-r">
            <div class="relative flex min-h-[12rem] flex-1 items-center justify-center overflow-hidden bg-black/90 sm:min-h-[16rem]">
              <img
                v-if="photos.length && !photoBroken"
                :src="photoSrc"
                :alt="comp?.address"
                class="size-full object-contain"
                @error="onPhotoError"
                @load="onPhotoLoad"
              />
              <div v-else-if="loading" class="flex flex-col items-center gap-2 text-sm text-ink-white/70">
                <FeatherIcon name="loader" class="size-5 animate-spin" />
                {{ __('Loading property photos…') }}
              </div>
              <div v-else class="flex flex-col items-center gap-2 px-6 text-center text-sm text-ink-white/70">
                <FeatherIcon name="image" class="size-7" />
                <template v-if="photoBroken">
                  {{ __('This photo did not load.') }}
                  <button class="font-medium text-ink-white hover:underline" @click="retryPhoto">
                    {{ __('Retry') }}
                  </button>
                </template>
                <template v-else>
                  {{ __('No Zillow photos are available for this property.') }}
                </template>
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
              v-if="error || (!loading && response && !response.available && !photos.length)"
              class="mt-5 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3 text-sm text-ink-gray-6"
            >
              {{ error || response?.message || __('More details are unavailable right now.') }}
              <button class="ml-1 font-medium text-ink-blue-3 hover:underline" @click="load(true)">
                {{ __('Retry') }}
              </button>
            </div>
          </aside>
        </div>
        <!-- Phone: the header only has room for ✕. These three are the actions
             a rep actually takes from this screen. -->
        <div class="flex shrink-0 gap-2 border-t px-4 py-3 sm:hidden">
          <Button class="flex-1" :label="__('Close')" @click="show = false" />
          <Button
            v-if="hasStreetView"
            class="flex-1"
            variant="subtle"
            :label="__('Street View')"
            @click="$emit('street')"
          />
          <Button
            v-if="!subjectMode"
            class="flex-1"
            :variant="comp?.selected ? 'subtle' : 'solid'"
            :label="comp?.selected ? __('Remove') : __('Add as comp')"
            @click="$emit('use', comp.name)"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { compColor, compFit, compState, compStateLabel, daysToSell, formatCompMoney } from '@/utils/comps'
import { zillowUrl } from '@/utils/propertyLinks'
import { Badge, Button, Dialog, FeatherIcon, call } from 'frappe-ui'
import { computed, ref, watch } from 'vue'

defineEmits(['use', 'street'])

const props = defineProps({
  lead: { type: String, required: true },
  comp: { type: Object, default: null },
  subject: { type: Object, default: null },
  // The same panel, showing the SUBJECT rather than a comp. Only two things
  // actually differ -- which endpoint supplies the photos, and the handful of
  // comp-only affordances below -- so this is a flag rather than a second
  // component that would drift away from this one.
  subjectMode: { type: Boolean, default: false },
})

const show = defineModel({ type: Boolean })
const loading = ref(false)
const error = ref('')
const response = ref(null)
const photoIndex = ref(0)
const cache = new Map()
let requestToken = 0

// Provider-synthesized Street View frames ride a SHARED, quota-limited Google
// key, so they fail in bursts — the classic "the photo frequently doesn't
// show". One cache-busted reload usually lands (the key does not enforce its
// URL signature); a photo that fails twice gets the placeholder, never a
// broken frame.
const photoBust = ref(0)
const photoBroken = ref(false)
const retriedPhotos = new Set()

const photoSrc = computed(() => {
  const url = photos.value[photoIndex.value] || ''
  if (!url || !photoBust.value || !retriedPhotos.has(url)) return url
  return url + (url.includes('?') ? '&' : '?') + 'cb=' + photoBust.value
})

function onPhotoError() {
  const url = photos.value[photoIndex.value] || ''
  if (!url) return
  if (url.includes('maps.googleapis.com') && !retriedPhotos.has(url)) {
    retriedPhotos.add(url)
    photoBust.value = Date.now()
    return
  }
  photoBroken.value = true
}

function onPhotoLoad() {
  photoBroken.value = false
}

function retryPhoto() {
  const url = photos.value[photoIndex.value] || ''
  retriedPhotos.add(url)
  photoBust.value = Date.now()
  photoBroken.value = false
}

// Any navigation (arrows, thumbnails, a new comp) gets a clean slate — a broken
// state left behind would show the placeholder over a perfectly good photo.
watch(photoIndex, () => {
  photoBroken.value = false
})

const details = computed(() => response.value?.details || null)
const photos = computed(() => {
  const list = response.value?.photos || []
  if (list.length) return list
  const cover =
    (props.subjectMode && props.subject?.cover_photo) ||
    details.value?.cover_photo ||
    ''
  return cover ? [cover] : []
})
const fit = computed(() => compFit(props.comp, props.subject))
const streetPoint = computed(() => {
  if (props.subjectMode) {
    const s = props.subject
    if (s?.lat != null && s?.lng != null) return s
  }
  const c = props.comp
  if (c?.lat != null && c?.lng != null) return c
  return null
})
const hasStreetView = computed(() => !!streetPoint.value)

// Status, in the same four-state grammar as the pills and the tray cards.
const state = computed(() => compState(props.comp))
const statusLabel = computed(() => compStateLabel(state.value))
const palette = computed(() => compColor(props.comp))
const compLocation = computed(() =>
  [props.comp?.city, props.comp?.state, props.comp?.zip].filter(Boolean).join(', '),
)
const displayPrice = computed(
  () => details.value?.asking_price || props.comp?.price || details.value?.zestimate,
)
const displayPriceLabel = computed(() => {
  // Name the number honestly: an agreed contract price, a live ask, a verified
  // sale, an estimate and a stale last-ask are five different claims, and only
  // some of them are prices anybody ever committed to.
  if (details.value?.asking_price) return __('Current Zillow ask')
  if (state.value === 'pending') return __('Agreed price · under contract')
  // The subject is not on the market, so its headline number is whatever it last
  // SOLD for -- which is a recorded transaction and must not inherit the comps'
  // "last known list price", the exact confusion the pin popup exists to avoid.
  if (props.subjectMode && props.comp?.price) {
    const when = details.value?.last_sale?.date
    return when ? __('Last sold · {0}', [dateOnly(when)]) : __('Last sold')
  }
  if (props.comp?.price) return __('Last known list price')
  return details.value?.zestimate ? __('Zestimate — no listing price on record') : ''
})
const zillowLink = computed(() => details.value?.zillow_url || zillowUrl(props.comp?.address || ''))
const facts = computed(() => {
  const d = details.value || {}
  const c = props.comp || {}
  return [
    { label: __('Beds'), value: decimal(d.beds || c.bedrooms) },
    { label: __('Baths'), value: decimal(d.baths || c.bathrooms) },
    { label: __('Living area'), value: area(d.sqft || c.square_footage) },
    {
      label: __('Lot size'),
      value:
        d.lot_size ||
        c.lot_size ||
        (props.subjectMode && props.subject?.lot_size) ||
        '—',
    },
    { label: __('Year built'), value: whole(d.year_built || c.year_built) },
    { label: __('Property type'), value: d.property_type || c.property_type || '—' },
    // "0.0 mi from itself" is not a fact about the subject.
    ...(props.subjectMode
      ? []
      : [
          {
            label: __('Distance'),
            value: c.distance_mi ? `${Number(c.distance_mi).toFixed(1)} mi` : '—',
          },
        ]),
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
  // Time to sell is a FINISHED measurement off the listing chain, so it is named
  // differently from "time on market" above, which on a live listing is a clock
  // still running. Price cuts ride with it because "sold in 169 days after 3 cuts"
  // and "sold in 169 days at the asking price" are opposite stories about a price.
  const sh = props.comp?.sale_history
  const took = daysToSell(props.comp)
  if (took != null) {
    const cuts = Number(sh?.price_cuts) || 0
    rows.push({
      label: __('Took to sell'),
      value:
        __('{0} days', [Math.round(took)]) +
        (cuts > 0 ? ` · ${cuts === 1 ? __('1 price cut') : __('{0} price cuts', [cuts])}` : ''),
    })
  }
  // The purchase that makes this a possible flip. Shown as its own row rather than
  // folded into "Last sold", because the point is the PAIR of transactions.
  const f = sh?.flip
  if (f) {
    rows.push({
      label: f.kind === 'relist' ? __('Bought before relisting') : __('Bought before resale'),
      value: __('{0} on {1} · held {2} · {3}% more', [
        formatCompMoney(f.bought_price),
        dateOnly(f.bought_date),
        __('{0} days', [Math.round(f.hold_days)]),
        Math.round((f.pct || 0) * 100),
      ]),
    })
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
    const result = props.subjectMode
      ? await call('crm.api.comps.get_subject_details', { lead: props.lead })
      : await call('crm.api.comps.get_comp_details', {
          lead: props.lead,
          comp: name,
          // Lets the server fall back to an address lookup (Zillow, then Realtor
          // photos) when the zpid /property call returns an empty shell.
          address: props.comp.address || '',
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
  // NO thousand separator: the only thing rendered through this is the year
  // built, and `toLocaleString` was printing a house built in 1910 as "1,910".
  return Number.isFinite(n) && n > 0 ? String(Math.round(n)) : '—'
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

<!-- Unscoped: Dialog teleports to <body>. On a phone this is a full-screen
     gallery, not a 4xl card with desktop padding. -->
<style>
.dialog-overlay:has(#comp-detail-modal) > div {
  padding: 0.25rem !important;
}
.dialog-content:has(#comp-detail-modal) {
  max-width: calc(100vw - 0.5rem) !important;
  width: calc(100vw - 0.5rem);
  margin-top: 0 !important;
  margin-bottom: 0 !important;
}
@media (min-width: 640px) {
  .dialog-overlay:has(#comp-detail-modal) > div {
    padding: 2rem !important;
  }
  .dialog-content:has(#comp-detail-modal) {
    max-width: 56rem !important;
    width: auto;
  }
}
</style>
