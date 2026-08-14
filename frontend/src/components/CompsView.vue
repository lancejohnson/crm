<template>
  <div class="flex flex-col gap-3">
  <!-- Address + counts -->
  <div class="flex flex-wrap items-center justify-between gap-2">
    <div class="min-w-0">
      <div class="truncate text-sm font-medium text-ink-gray-8">
        {{ data?.address || address || __('This property') }}
      </div>
      <div class="mt-0.5 text-xs text-ink-gray-5">
        <template v-if="loading">{{ __('Finding comps…') }}</template>
        <template v-else-if="comps.length">
          {{ __('{0} comps', [data?.total_matched ?? comps.length]) }}
          <template v-if="presetLabel"> · {{ presetLabel }}</template>
          <span class="text-ink-gray-4">
            ·
            {{
              __('of {0} within {1} mi', [
                data?.total_in_radius ?? comps.length,
                data?.radius_mi,
              ])
            }}
          </span>
          <template v-if="(data?.total_matched ?? 0) > comps.length">
            · {{ __('showing the {0} nearest', [comps.length]) }}
                </template>
              </template>
              <template v-else>{{ emptyMessage }}</template>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <!-- Underwriting from the comps you picked. Enabled only once something is
     selected, and the label carries the count so "up to 4" is visible
     before the click rather than as an error after it. -->
<Button
  v-if="pageMode"
  :label="underwritingLabel"
  :variant="selectedNames.length ? 'solid' : 'subtle'"
  :disabled="!selectedNames.length || creatingSheet"
  :loading="creatingSheet"
  iconLeft="grid"
  @click="createUnderwriting"
/>

<!-- Details toggle: the pills carry beds/baths/sqft/year, but on a
                 dense board the overview is sometimes worth more than the facts.
                 A checkbox rather than a button because it reports its own state
                 — a button reading "Details off" is ambiguous about whether that
                 is the current state or what clicking will do. -->
            <label
              class="flex cursor-pointer select-none items-center gap-1.5 whitespace-nowrap text-sm text-ink-gray-7"
              :title="__('Show beds/baths/sqft/year on pills') + ' (D)'"
            >
              <FormControl type="checkbox" size="sm" v-model="showDetail" />
              {{ __('Details') }}
            </label>

            <!-- Radius stays its own control: a rural lead needs a wider net than
                 an infill lot, and the right answer is obvious once you see the
                 map. Loosening the preset ladder never touches it. -->
            <FormControl
              type="select"
              size="sm"
              :options="radiusOptions"
              v-model="radius"
            />
            <Button
              variant="ghost"
              icon="refresh-cw"
              :loading="loading"
              @click="() => load()"
            />
          </div>
        </div>

        <!-- Filters are VISIBLE, not behind a popover: they are the whole point
             of the tool, and a rep should be able to widen a beds range without
             first discovering a button. Wraps to as many rows as it needs, which
             is what keeps it usable at 390px. -->
        <div
          class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-2.5"
        >
          <div class="flex flex-wrap items-end gap-x-4 gap-y-2.5">
            <div class="flex min-w-0 flex-col gap-1">
              <span class="text-2xs font-semibold uppercase tracking-wide text-ink-gray-5">
                {{ __('Status') }}
              </span>
              <FormControl
                type="select"
                size="sm"
                :options="statusOptions"
                v-model="draft.status"
              />
            </div>
            <div class="flex min-w-0 flex-col gap-1">
              <span class="text-2xs font-semibold uppercase tracking-wide text-ink-gray-5">
                {{ __('Sold within') }}
              </span>
              <FormControl
                type="select"
                size="sm"
                :options="withinOptions"
                v-model="draft.within_days"
              />
            </div>

            <div
              v-for="r in rangeRows"
              :key="r.key"
              class="flex min-w-0 flex-col gap-1"
            >
              <span class="text-2xs font-semibold uppercase tracking-wide text-ink-gray-5">
                {{ r.label }}
              </span>
              <div class="flex items-center gap-1">
                <FormControl
                  class="w-16"
                  type="number"
                  size="sm"
                  :step="r.step"
                  :placeholder="__('min')"
                  v-model="draft[r.key + '_min']"
                />
                <span class="text-ink-gray-4">–</span>
                <FormControl
                  class="w-16"
                  type="number"
                  size="sm"
                  :step="r.step"
                  :placeholder="__('max')"
                  v-model="draft[r.key + '_max']"
                />
              </div>
            </div>

            <div class="flex min-w-0 flex-col gap-1">
              <span class="text-2xs font-semibold uppercase tracking-wide text-ink-gray-5">
                {{ __('Type') }}
              </span>
              <FormControl
                type="select"
                size="sm"
                :options="typeOptions"
                v-model="draft.property_types"
              />
            </div>

            <div class="ml-auto flex items-center gap-1.5">
              <Button
                v-if="data?.hidden_count"
                :label="
                  revealHidden
                    ? __('Hide {0} hidden', [data.hidden_count])
                    : __('{0} hidden', [data.hidden_count])
                "
                variant="ghost"
                @click="toggleRevealHidden"
              />
              <Button
                v-if="activeFilterCount"
                :label="__('Reset to suggested')"
                variant="ghost"
                @click="resetToSuggested"
              />
              <Button :label="__('Clear all')" variant="ghost" @click="clearAll" />
            </div>
          </div>
          <div class="mt-2 text-2xs text-ink-gray-5">
            {{
              __(
                '“Sold within” applies to off-market comps only — an active listing stays on the map however long it has been listed.',
              )
            }}
          </div>
        </div>

        <!-- The preset had to loosen, or nothing matched at all. Either way the
             user is told outright rather than left to wonder why a "similar"
             map is full of houses that are nothing like the subject. -->
        <div
          v-if="notice"
          class="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border px-3 py-2 text-xs"
          :class="
            notice.tone === 'warning'
              ? 'border-outline-amber-2 bg-surface-amber-1 text-ink-amber-3'
              : 'border-outline-gray-2 bg-surface-gray-1 text-ink-gray-6'
          "
        >
          <span>{{ notice.text }}</span>
          <button
            v-if="notice.action"
            class="font-medium underline underline-offset-2"
            @click="notice.action.run"
          >
            {{ notice.action.label }}
          </button>
        </div>

        <div
          ref="mapEl"
          class="w-full overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-gray-1"
          :class="pageMode ? 'h-[26rem] sm:h-[32rem]' : 'h-[20rem] sm:h-[24rem]'"
        />

        <!-- Every comp as a row, because a map answers "where" and a list answers
     "which". Hovering either one lights up the other, so a row in the table and
     a pin on the map are obviously the same property. -->
<div
  v-if="comps.length"
  class="overflow-hidden rounded-lg border border-outline-gray-2"
>
  <div
    class="flex items-center justify-between border-b border-outline-gray-2 bg-surface-gray-1 px-3 py-2"
  >
    <span class="text-sm font-medium text-ink-gray-8">
      {{ __('{0} properties', [comps.length]) }}
    </span>
    <span class="text-xs text-ink-gray-5">
      {{ __('Hover a row to find it on the map') }}
    </span>
  </div>
  <div class="max-h-80 overflow-auto">
    <table class="w-full min-w-[560px] text-sm">
      <thead
        class="sticky top-0 z-10 bg-surface-white text-xs text-ink-gray-5 shadow-[0_1px_0_0_var(--outline-gray-2)]"
      >
        <tr>
          <th class="px-3 py-1.5 text-left font-medium">{{ __('Price') }}</th>
          <th class="px-2 py-1.5 text-left font-medium">{{ __('Bd/Ba') }}</th>
          <th class="px-2 py-1.5 text-right font-medium">{{ __('Sq ft') }}</th>
          <th class="px-2 py-1.5 text-right font-medium">{{ __('Built') }}</th>
          <th class="px-2 py-1.5 text-left font-medium">{{ __('Status') }}</th>
          <th class="px-2 py-1.5 text-right font-medium">{{ __('Dist') }}</th>
          <th class="w-20 px-2 py-1.5"></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="c in comps"
          :key="c.name"
          class="cursor-default border-t border-outline-gray-1"
          :class="
            hoveredComp === c.name
              ? 'bg-surface-gray-2'
              : c.selected
                ? 'bg-surface-blue-1'
                : ''
          "
          @mouseenter="hoveredComp = c.name"
          @mouseleave="hoveredComp = null"
        >
          <td class="whitespace-nowrap px-3 py-1.5 font-medium text-ink-gray-8">
            {{ priceShort(c.price) }}
          </td>
          <td class="whitespace-nowrap px-2 py-1.5 text-ink-gray-7">
            {{ c.bedrooms || '?' }}/{{ c.bathrooms || '?' }}
          </td>
          <td class="whitespace-nowrap px-2 py-1.5 text-right tabular-nums text-ink-gray-7">
            {{ c.square_footage ? Number(c.square_footage).toLocaleString() : '—' }}
          </td>
          <td class="whitespace-nowrap px-2 py-1.5 text-right tabular-nums text-ink-gray-7">
            {{ c.year_built || '—' }}
          </td>
          <!-- The metric that matters for THIS status, same rule as the popup. -->
          <td class="whitespace-nowrap px-2 py-1.5 text-xs">
            <span :class="isActive(c.status) ? 'text-ink-amber-3' : 'text-ink-gray-6'">
              {{
                isActive(c.status)
                  ? __('For sale · {0}', [agoLabel(c.recency_days) || '—'])
                  : __('Off-market {0}', [fmtDate(c.removed_date)])
              }}
            </span>
          </td>
          <td class="whitespace-nowrap px-2 py-1.5 text-right tabular-nums text-ink-gray-6">
            {{ c.distance_mi }} mi
          </td>
          <td class="whitespace-nowrap px-2 py-1.5 text-right">
            <!-- Photos live one click from the row as well as from the pin: the
                 list is how you work through comps in order, and having to find
                 each one's pin again to look at it is the long way round. -->
            <button
              class="rounded px-1.5 py-0.5 text-ink-gray-4 hover:text-ink-gray-7"
              :title="__('Photos & details')"
              @click="openCompDetail(c.name)"
            >
              <FeatherIcon name="image" class="size-3.5" />
            </button>
            <button
              class="ml-1 rounded px-1.5 py-0.5 text-xs font-medium"
              :class="
                c.selected
                  ? 'bg-surface-blue-2 text-ink-blue-2'
                  : 'text-ink-gray-5 hover:text-ink-gray-8'
              "
              :title="__('Use as comp')"
              @click="toggleUse(c.name)"
            >
              {{ c.selected ? '✓' : '+' }}
            </button>
            <button
              class="ml-1 rounded px-1.5 py-0.5 text-xs text-ink-gray-4 hover:text-ink-gray-7"
              :title="__('Remove from map')"
              @click="setCompState(c.name, 'hidden')"
            >
              ✕
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</div>

<!-- Legend: the map is unreadable without saying what the fade means. -->
        <div class="flex flex-wrap items-center gap-3 text-xs text-ink-gray-6">
          <span class="flex items-center gap-1.5">
            <span class="size-2.5 rounded-full" :style="{ background: SUBJECT }" />
            {{ __('This property') }}
          </span>
          <span class="flex items-center gap-1.5">
            <span class="size-2.5 rounded-full" :style="{ background: OFF_MARKET }" />
            {{ __('Sold / off-market') }}
          </span>
          <span class="flex items-center gap-1.5">
            <span class="size-2.5 rounded-full" :style="{ background: ACTIVE }" />
            {{ __('Still listed') }}
          </span>
          <span class="text-ink-gray-5">{{ __('Fainter = older') }}</span>
          <span v-if="data?.selected_count" class="flex items-center gap-1.5">
            <span
              class="size-2.5 rounded-full ring-2 ring-offset-1"
              :style="{ background: OFF_MARKET, '--tw-ring-color': SUBJECT }"
            />
            {{ __('{0} used as comps', [data.selected_count]) }}
          </span>
          <span class="text-ink-gray-4">
            {{ __('Click a pin to use or hide it') }} ·
            <b>D</b> {{ __('details') }} · <b>U</b> {{ __('use') }} ·
            <b>H</b> {{ __('hide') }}
          </span>
        </div>
  </div>

  <!-- Photos + Zillow facts for one comp. Mounted here rather than in each host
       so the map, the list and the Today modal all reach the same gallery. -->
  <CompDetailModal
    v-if="detailComp"
    v-model="showCompDetail"
    :lead="lead"
    :comp="detailComp"
    :subject="data?.subject || null"
  />
</template>

<script setup>
/**
 * A lead's comparable sales on a map.
 *
 * Ported from the LeadMarket comps view, with the one change that matters: that
 * app can only draw an ESTIMATED subject location (iSpeedToLead hides the address
 * until you buy the lead), so it plots the centroid of the comp cloud. We own
 * these leads, so this centers on the REAL geocoded parcel and the comps arrange
 * themselves around it.
 *
 * The fade is the point. A sale from last month tells you far more about today's
 * value than one from last year, so opacity carries recency and the eye lands on
 * the comps that actually count without reading a single date.
 *
 * Filters arrive PRE-SET around this property (recent + similar), because an
 * unfiltered two-mile dump is not a comp set. The server picks the tightest tier
 * that still yields a usable number and tells us whether it had to loosen; when it
 * did, we say so instead of quietly showing houses that are nothing like this one.
 * Touching any control switches to explicit mode — from then on the server runs
 * exactly what is on screen, even if that matches nothing.
 */
import { Button, FeatherIcon, FormControl, call, toast } from 'frappe-ui'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { zillowUrl } from '@/utils/propertyLinks'
import CompDetailModal from '@/components/CompDetailModal.vue'
import FilterIcon from '@/components/Icons/FilterIcon.vue'
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'

const props = defineProps({
  lead: { type: String, required: true },
  address: { type: String, default: '' },
  // Only the full page offers underwriting; it needs the room, and the action
  // belongs where the comps are actually chosen.
  pageMode: { type: Boolean, default: false },
})
// This used to be a modal driven by `defineModel()`. It is now a full page, so
// "open" is simply always true -- which keeps every existing `show.value` guard,
// watcher and keyboard-shortcut gate working exactly as before.
const emit = defineEmits(['subject'])
const show = ref(true)

// Canvas/marker colours live in JS because Leaflet can't read Tailwind tokens.
// Blue/amber rather than red/green: safe for dichromats.
const ACTIVE = '#d97706' // still listed = an ASK, not a sale
const OFF_MARKET = '#475569' // off-market = an actual transaction
const SUBJECT = '#2563c9'

const mapEl = ref(null)
const data = ref(null)
const loading = ref(false)
const radius = ref(2)
let map = null
let sizeObserver = null

const radiusOptions = [
  { label: '½ mile', value: 0.5 },
  { label: '1 mile', value: 1 },
  { label: '2 miles', value: 2 },
  { label: '5 miles', value: 5 },
]

const statusOptions = [
  { label: __('Sold & listed'), value: 'all' },
  { label: __('Sold / off-market'), value: 'sold' },
  { label: __('Still listed'), value: 'active' },
]

// GOTCHA — the "any" options MUST NOT use an empty-string value. frappe-ui's
// Select wraps reka-ui, which reserves '' for the placeholder and silently drops
// any item declared with it: the "Any time" row simply never rendered, leaving no
// way to lift the recency filter from the dropdown at all. A sentinel string is
// the fix; `currentFilters` maps it back to "unconstrained".
const ANY = 'any'

// Labelled "Sold within" because it no longer means the same thing for both kinds
// of pin: an active listing is exempt, however long it has been sitting there.
const withinOptions = [
  { label: __('Any time'), value: ANY },
  { label: __('Last 90 days'), value: 90 },
  { label: __('Last 6 months'), value: 180 },
  { label: __('Last 12 months'), value: 365 },
  { label: __('Last 2 years'), value: 730 },
]

// Every property_type present in the inventory (measured across all 49,769 rows).
const typeOptions = [
  { label: __('Any type'), value: ANY },
  { label: 'Single Family', value: 'Single Family' },
  { label: 'Townhouse', value: 'Townhouse' },
  { label: 'Condo', value: 'Condo' },
  { label: 'Multi-Family', value: 'Multi-Family' },
  { label: 'Manufactured', value: 'Manufactured' },
  { label: 'Land', value: 'Land' },
  { label: 'Apartment', value: 'Apartment' },
]

const rangeRows = [
  { key: 'beds', label: __('Beds'), step: 1 },
  { key: 'baths', label: __('Baths'), step: 0.5 },
  { key: 'sqft', label: __('Sq ft'), step: 50 },
  { key: 'year', label: __('Year built'), step: 1 },
  { key: 'price', label: __('Price'), step: 1000 },
]

const RANGE_KEYS = rangeRows.flatMap((r) => [`${r.key}_min`, `${r.key}_max`])

/** A control carries a real constraint (blank and the ANY sentinel do not). */
function isSet(v) {
  return v !== '' && v != null && v !== ANY
}

/** Mirrors the server's filter shape 1:1, so what is on screen is what ran. */
const draft = reactive({ status: 'all', within_days: ANY, property_types: ANY })
for (const k of RANGE_KEYS) draft[k] = ''

// `userTouched` is the whole difference between "suggest something sensible" and
// "do exactly what I said". Once the user drives a control we stop re-deriving
// presets, including on a radius change — silently rewriting someone's deliberate
// filter is how a tool stops being trusted.
const userTouched = ref(false)
let syncing = false
let applyTimer = null

// Whether pills carry beds/baths/sqft/year, or collapse to the bare price.
// Persisted per user like dispoView / activityScope — it is a view preference,
// and having to re-set it on every lead would make the shortcut pointless.
const showDetail = ref(localStorage.getItem('compsPillDetail') !== '0')
watch(showDetail, (v) => {
  localStorage.setItem('compsPillDetail', v ? '1' : '0')
  render()
})

// Which comp's popup is open — the target for the h / u shortcuts.
const focusedComp = ref(null)
const revealHidden = ref(false)

// The comp whose photos/facts are open, if any.
const detailComp = ref(null)
const showCompDetail = ref(false)

// The row/pin the pointer is over, in EITHER direction. Kept as a plain name so
// the map and the table are pointing at one shared idea of "this one".
const hoveredComp = ref(null)
const markersByName = new Map()

/**
 * Emphasise one pin without re-rendering the map.
 *
 * Deliberately a class toggle on the existing element rather than swapping the
 * icon: rebuilding a divIcon on every mouseenter would thrash 200 markers and
 * drop the popup that may be open.
 */
watch(hoveredComp, (name, prev) => {
  const off = markersByName.get(prev)
  if (off) off.getElement()?.classList.remove('comps-pill-hot')
  const on = markersByName.get(name)
  const el = on?.getElement()
  if (el) {
    el.classList.add('comps-pill-hot')
    // Lift it above its neighbours so an emphasised pin is never half-buried.
    el.style.zIndex = 900
  }
  if (off) {
    const prevEl = off.getElement()
    if (prevEl) prevEl.style.zIndex = ''
  }
})

const comps = computed(() => data.value?.comps || [])
const emptyMessage = computed(
  () => data.value?.message || __('No comps found nearby.'),
)
const presetLabel = computed(() =>
  userTouched.value ? '' : data.value?.preset?.label || '',
)

/** Counts CONSTRAINED FIELDS, not bounds, so a min+max pair reads as one filter. */
const activeFilterCount = computed(() => {
  let n = 0
  if (draft.status && draft.status !== 'all') n++
  if (isSet(draft.within_days)) n++
  if (isSet(draft.property_types)) n++
  for (const r of rangeRows) {
    if (draft[`${r.key}_min`] !== '' && draft[`${r.key}_min`] != null) n++
    else if (draft[`${r.key}_max`] !== '' && draft[`${r.key}_max`] != null) n++
  }
  return n
})

/**
 * What to tell the user about the fit of what they are looking at.
 *
 * The important case is the one Lance asked for: nothing recent and similar
 * exists, so the map is showing a wider net. That must be stated, not implied.
 */
const notice = computed(() => {
  const d = data.value
  if (!d || loading.value || !d.available || !d.subject) return null

  if ((d.total_matched ?? 0) === 0 && (d.total_in_radius ?? 0) > 0) {
    return {
      tone: 'warning',
      text: userTouched.value
        ? __('No comps match these filters. {0} properties are within {1} mi.', [
            d.total_in_radius,
            d.radius_mi,
          ])
        : __('Nothing nearby resembles this property.'),
      action: userTouched.value
        ? { label: __('Reset to suggested'), run: resetToSuggested }
        : { label: __('Show everything nearby'), run: clearAll },
    }
  }
  if (userTouched.value || !d.relaxed) return null

  // Fell all the way through the ladder: these are simply the nearest properties,
  // and calling them comparable would be a lie.
  if (d.fell_through) {
    return {
      tone: 'warning',
      text: __(
        'No recent, similar comps nearby — showing all {0} properties within {1} mi. These may not be comparable.',
        [d.total_matched, d.radius_mi],
      ),
    }
  }
  return {
    tone: 'info',
    text: __('No recent, similar comps nearby — widened to “{0}” to find {1}.', [
      d.preset?.label || '',
      d.total_matched,
    ]),
  }
})

/** Exact match — /active/i would wrongly match "Inactive". */
function isActive(status) {
  return /^active$/i.test(String(status || '').trim())
}

/**
 * Days used to fade a pill: an active listing ages by time on market, an
 * off-market one by how long ago it left. Falls back through days_old and DOM
 * when a removal date is missing, so a comp never silently reads as brand new.
 */
function stalenessDays(c) {
  if (isActive(c.status)) {
    const dom = Number(c.days_on_market)
    return Number.isFinite(dom) && dom >= 0 ? dom : 0
  }
  if (c.removed_date) {
    const ms = Date.parse(c.removed_date)
    if (Number.isFinite(ms)) return Math.max(0, (Date.now() - ms) / 86400000)
  }
  const old = Number(c.days_old)
  if (Number.isFinite(old) && old >= 0) return old
  const dom = Number(c.days_on_market)
  return Number.isFinite(dom) && dom >= 0 ? dom : 0
}

/** 0d -> 1.0 (solid); 360d+ -> ~0.32. Smoothstep keeps the first month strong. */
function pillOpacity(days) {
  const t = Math.max(0, Math.min(1, days / 360))
  const eased = t * t * (3 - 2 * t)
  return 1 - eased * 0.68
}

function priceShort(p) {
  const n = Number(p)
  if (!Number.isFinite(n) || n <= 0) return '—'
  if (n >= 1000000) return '$' + (n / 1000000).toFixed(n >= 10000000 ? 0 : 1) + 'm'
  if (n >= 1000) return '$' + Math.round(n / 1000) + 'k'
  return '$' + Math.round(n)
}

function fmtDate(v) {
  if (!v) return '—'
  const s = String(v)
  // GOTCHA — a bare "YYYY-MM-DD" is parsed by Date.parse as UTC MIDNIGHT, which
  // then renders as the PREVIOUS DAY everywhere west of Greenwich. Every comp
  // date in this modal read a day early in Chicago (a sale on Oct 9 showed as
  // Oct 8). Date-only values are calendar dates with no timezone, so build them
  // as local; anything with a time component still goes through Date.parse.
  const ymd = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s.trim())
  const d = ymd
    ? new Date(Number(ymd[1]), Number(ymd[2]) - 1, Number(ymd[3]))
    : new Date(Date.parse(s))
  if (!Number.isFinite(d.getTime())) return s.slice(0, 10)
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function escapeHtml(s) {
  return String(s ?? '').replace(
    /[&<>"']/g,
    (m) =>
      ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      })[m],
  )
}

/**
 * The pieces of a detailed pill, split across two lines.
 *
 * Year rides on the TOP line next to the price rather than in the facts line,
 * and that is a width decision, not a cosmetic one: the pill is as wide as its
 * widest line, and "3/2 · 1,395sf · 1910" was the widest thing on it. Moving the
 * four year digits up beside the short price shortens the line that was setting
 * the width, and lengthens the one that wasn't.
 */
function pillBits(c) {
  const bb = c.bedrooms || c.bathrooms ? `${c.bedrooms || '?'}/${c.bathrooms || '?'}` : ''
  const sf = c.square_footage ? `${Number(c.square_footage).toLocaleString()}sf` : ''
  return {
    year: c.year_built ? String(c.year_built) : '',
    line2: [bb, sf].filter(Boolean).join(' · '),
  }
}

/** Everything a detailed pill says, for the title tooltip / measurement. */
function pillFacts(c) {
  const { year, line2 } = pillBits(c)
  return [line2, year].filter(Boolean).join(' · ')
}

/**
 * Design B: price bold, facts beneath in small type.
 *
 * Measured against the one-line alternative on a real 418-comp board: 115px wide
 * vs 186px, which is the difference between readable and a wall of overlapping
 * pills in a tight cluster. `showDetail` collapses it back to the bare price pill
 * (the `d` shortcut), because on a dense urban board the overview is sometimes
 * worth more than the facts.
 *
 * A SELECTED comp gets a white ring and always shows its facts — it is the one
 * someone is actually pricing off, so it should never be the pin you lose.
 */
/**
 * The hover-only ✕ that drops a comp off the map.
 *
 * Rendered into every pill but hidden until the pill is hovered (CSS at the
 * bottom of this file), so removing an obviously-wrong comp is one click on the
 * thing itself rather than click → read popup → find button. Same delegated
 * handler as the popup's Hide button, so both paths write the same state.
 */
function hideBadge(c) {
  return `<span class="comps-pill-x" data-comp-hide="${escapeHtml(c.name)}"
      title="${__('Remove from map')}"
      style="position:absolute;top:-6px;right:-6px;width:15px;height:15px;
      border-radius:50%;background:#fff;color:#44423d;border:1px solid #cfccc5;
      box-shadow:0 1px 2px rgba(0,0,0,.3);font:700 10px/13px ui-sans-serif,system-ui;
      text-align:center;cursor:pointer">✕</span>`
}

/**
 * The subject as a pill, in the same two-line shape as the comps.
 *
 * It used to be an 18px dot, which marked the spot but said nothing — you had to
 * click it to find out what you were comparing against. Rendering it like a comp
 * (bd/ba · sqft, year on the top line) means the subject's own numbers sit in the
 * same visual grammar as the numbers you are judging it by, so "is this comp
 * bigger or smaller than mine" is a glance rather than a memory test.
 *
 * Blue with a heavier white ring so it never reads as one of the comps, and it
 * keeps the centre anchor so the pill's middle still marks the real parcel.
 */
function subjectIcon(s) {
  const year = s.year_built_label || ''
  const bb =
    s.beds_label || s.baths_label ? `${s.beds_label || '?'}/${s.baths_label || '?'}` : ''
  const sf = s.sqft_label ? `${s.sqft_label}sf` : ''
  const line2 = [bb, sf].filter(Boolean).join(' · ')
  const label = __('Subject')

  // With details off (the D toggle) the comps collapse to a bare price, so the
  // subject collapses to a bare label rather than staying loud on its own.
  if (!showDetail.value || (!year && !line2)) {
    const w = Math.max(52, Math.ceil(18 + label.length * 6.6))
    return L.divIcon({
      className: 'comps-price-pill',
      html: `<div class="comps-pill-body" style="display:flex;align-items:center;
          justify-content:center;box-sizing:border-box;width:${w}px;height:24px;
          background:${SUBJECT};color:#fff;font:700 11px/1 ui-sans-serif,system-ui,sans-serif;
          border-radius:999px;border:2px solid #fff;
          box-shadow:0 1px 6px rgba(0,0,0,.5);white-space:nowrap">${label}</div>`,
      iconSize: [w, 24],
      iconAnchor: [w / 2, 12],
      popupAnchor: [0, -14],
    })
  }

  const top = label.length * 6.6 + (year ? 3 + year.length * 5.0 : 0)
  const w = Math.max(58, Math.ceil(14 + Math.max(top, line2.length * 5.05)))
  const yearHtml = year
    ? `<span style="font:500 9px/1 ui-sans-serif,system-ui,sans-serif;opacity:.8;
         margin-left:3px">${escapeHtml(year)}</span>`
    : ''
  const line2Html = line2
    ? `<div style="font:500 9px/1 ui-sans-serif,system-ui,sans-serif;opacity:.95;
         margin-top:2px">${escapeHtml(line2)}</div>`
    : ''
  return L.divIcon({
    className: 'comps-price-pill',
    html: `<div class="comps-pill-body" style="display:flex;flex-direction:column;
        align-items:center;justify-content:center;box-sizing:border-box;width:${w}px;
        height:34px;background:${SUBJECT};color:#fff;border-radius:9px;
        border:2px solid #fff;box-shadow:0 1px 6px rgba(0,0,0,.55);
        white-space:nowrap;line-height:1">
        <div style="display:flex;align-items:baseline;justify-content:center">
          <span style="font:700 11px/1 ui-sans-serif,system-ui,sans-serif">${label}</span>${yearHtml}
        </div>
        ${line2Html}
      </div>`,
    iconSize: [w, 34],
    iconAnchor: [w / 2, 17],
    popupAnchor: [0, -19],
  })
}

function pillIcon(c) {
  const active = isActive(c.status)
  const opacity = pillOpacity(stalenessDays(c))
  const bg = active ? ACTIVE : OFF_MARKET
  const price = priceShort(c.price)
  const { year, line2 } = pillBits(c)
  const detailed = (showDetail.value || c.selected) && (year || line2)
  const ring = c.selected
    ? 'box-shadow:0 0 0 2px #fff,0 0 0 4px #2563c9,0 1px 3px rgba(0,0,0,.4);'
    : 'box-shadow:0 1px 3px rgba(0,0,0,.35);'
  const border = `1px solid ${active ? '#b45309' : '#334155'}`
  // A selected pill is never faded: an explicit pick outranks the recency signal.
  const op = (c.selected ? 1 : opacity).toFixed(3)

  if (!detailed) {
    const w = Math.max(40, Math.ceil(18 + price.length * 7.4))
    return L.divIcon({
      className: 'comps-price-pill',
      html: `<div class="comps-pill-body" style="position:relative;display:flex;
          align-items:center;justify-content:center;
          box-sizing:border-box;width:${w}px;height:24px;background:${bg};color:#fff;
          font:700 11px/1 ui-sans-serif,system-ui,sans-serif;border-radius:999px;
          border:${border};${ring}white-space:nowrap;
          opacity:${op}">${price}${hideBadge(c)}</div>`,
      iconSize: [w, 24],
      iconAnchor: [w / 2, 12],
      popupAnchor: [0, -14],
    })
  }
  // Line 1 = bold price + small dim year + age; line 2 = beds/baths · sqft. The
  // pill is sized to whichever line is actually wider, which is why age rides up
  // here: line 1 had slack and line 2 was the binding constraint. Measured over
  // 200 real comps, this costs 82 -> 90px average, where putting it on line 2
  // would have cost 113px and undone the whole point of the two-line layout.
  //
  // The age reads differently by status and the PILL COLOUR is what says which:
  // amber (still listed) → how long it has sat unsold; slate (off-market) → how
  // long since it left. Same rule the popup spells out in words.
  const age = agoShort(c.recency_days)
  const top =
    price.length * 7.0 +
    (year ? 3 + year.length * 5.0 : 0) +
    (age ? 3 + age.length * 5.0 : 0)
  const w = Math.max(52, Math.ceil(12 + Math.max(top, line2.length * 5.05)))
  const yearHtml = year
    ? `<span style="font:500 9px/1 ui-sans-serif,system-ui,sans-serif;opacity:.72;
         margin-left:3px">${year}</span>`
    : ''
  const ageHtml = age
    ? `<span style="font:500 9px/1 ui-sans-serif,system-ui,sans-serif;opacity:.72;
         margin-left:3px">${age}</span>`
    : ''
  const line2Html = line2
    ? `<div style="font:500 9px/1 ui-sans-serif,system-ui,sans-serif;opacity:.9;
         margin-top:2px">${escapeHtml(line2)}</div>`
    : ''
  return L.divIcon({
    className: 'comps-price-pill',
    html: `<div class="comps-pill-body" title="${escapeHtml(pillFacts(c))}"
        style="position:relative;display:flex;flex-direction:column;align-items:center;
        justify-content:center;box-sizing:border-box;width:${w}px;height:34px;
        background:${bg};color:#fff;border-radius:9px;border:${border};${ring}
        white-space:nowrap;line-height:1;opacity:${op}">
        <div style="display:flex;align-items:baseline;justify-content:center">
          <span style="font:700 11.5px/1 ui-sans-serif,system-ui,sans-serif">${price}</span>${yearHtml}${ageHtml}
        </div>
        ${line2Html}
        ${hideBadge(c)}
      </div>`,
    iconSize: [w, 34],
    iconAnchor: [w / 2, 17],
    popupAnchor: [0, -19],
  })
}

function fmtMoney(v) {
  const n = Number(v)
  if (!Number.isFinite(n) || n <= 0) return null
  return '$' + Math.round(n).toLocaleString()
}

/**
 * The subject's own card. This is the property everything else is compared to, so
 * it earns the same facts a comp shows plus what it last listed for.
 *
 * Two honesty rules, both load-bearing:
 *  - facts are labelled by SOURCE. "3 bd" off a listing record and "3 bd" typed
 *    into a web form by a motivated seller are not the same claim, and a band
 *    ("1000-2000 sqft") is shown as the band it is rather than a fake midpoint.
 *  - the price is called a LIST price, never a sale. This inventory carries the
 *    last ask, and going off-market is not a confirmed close.
 */
function subjectPopupHtml(s) {
  const addr = escapeHtml(data.value?.address || props.address || '')
  const facts = [
    s.beds_label ? `${s.beds_label} bd` : '',
    s.baths_label ? `${s.baths_label} ba` : '',
    s.sqft_label ? `${s.sqft_label} sqft` : '',
    s.year_built_label ? `built ${s.year_built_label}` : '',
  ]
    .filter(Boolean)
    .join(' · ')

  const rows = []
  if (facts) {
    rows.push(
      `<div style="margin-top:3px;color:#161614;font-weight:600">${escapeHtml(facts)}</div>`,
    )
  }
  if (s.property_type) {
    rows.push(`<div style="color:#5c5a55">${escapeHtml(s.property_type)}</div>`)
  }
  if (s.condition) {
    rows.push(`<div style="color:#5c5a55">${escapeHtml(s.condition)}</div>`)
  }
  if (!facts && !s.property_type && !s.condition) {
    rows.push(
      `<div style="margin-top:3px;color:#8a877e">${__('No property details on this lead yet.')}</div>`,
    )
  }

  // What it ACTUALLY SOLD for. Zillow's priceHistory carries Public Record `Sold`
  // rows, which is a real transaction with a date — a different and much stronger
  // claim than the comp inventory's last ask below, so it is shown separately and
  // first, and is the one thing here allowed to use the word "sold".
  const sale = s.last_sale
  if (sale && (sale.price || sale.date)) {
    const sp = fmtMoney(sale.price)
    rows.push(
      `<div style="margin-top:6px;padding-top:6px;border-top:1px solid #e5e3de">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;
          letter-spacing:.04em;color:#8a877e">${__('Last sold')}</div>
        ${sp ? `<div style="font-size:15px;font-weight:700;color:#161614">${sp}</div>` : ''}
        <div style="color:#5c5a55">${fmtDate(sale.date)}</div>
        ${
          sale.source
            ? `<div style="color:#8a877e;font-size:10px">${escapeHtml(sale.source)}</div>`
            : ''
        }
      </div>`,
    )
  }

  // Last time this house itself was on the market, when we happen to hold it.
  const ll = s.last_listing
  if (ll && (ll.price || ll.listed_date)) {
    const price = fmtMoney(ll.price)
    const live = isActive(ll.status)
    const when = live
      ? __('Listed {0} · still on the market', [fmtDate(ll.listed_date)])
      : `${__('Listed {0}', [fmtDate(ll.listed_date)])} → ${__('off-market {0}', [fmtDate(ll.removed_date)])}`
    const dom = ll.days_on_market
      ? `<div style="color:#8a877e">${Math.round(ll.days_on_market)}d ${__('on market')}</div>`
      : ''
    rows.push(
      `<div style="margin-top:6px;padding-top:6px;border-top:1px solid #e5e3de">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;
          letter-spacing:.04em;color:#8a877e">${live ? __('Currently listed') : __('Last listed')}</div>
        ${price ? `<div style="font-size:15px;font-weight:700;color:#161614">${price}</div>` : ''}
        <div style="color:#5c5a55">${when}</div>
        ${dom}
        <div style="color:#8a877e;margin-top:2px;font-style:italic">${__('Last list price (an ask) — not a verified sale.')}</div>
      </div>`,
    )
  }

  const extras = [
    fmtMoney(s.zestimate) ? `${__('Zestimate')} ${fmtMoney(s.zestimate)}` : '',
    fmtMoney(s.assessed_value) ? `${__('Assessed')} ${fmtMoney(s.assessed_value)}` : '',
    fmtMoney(s.annual_tax) ? `${__('Tax')} ${fmtMoney(s.annual_tax)}/yr` : '',
    fmtMoney(s.asking_price) ? `${__('Asking')} ${fmtMoney(s.asking_price)}` : '',
    s.lot_size ? `${__('Lot')} ${s.lot_size}` : '',
  ].filter(Boolean)
  if (extras.length) {
    rows.push(
      `<div style="margin-top:4px;color:#5c5a55">${escapeHtml(extras.join(' · '))}</div>`,
    )
  }

  const sources = Object.values(s.source || {})
  if (sources.length) {
    // Name the strongest source present. A rep reading "1,438 sqft" deserves to
    // know whether that came from Zillow, from a listing record, or from whatever
    // a motivated seller typed into a web form.
    const label = sources.includes('zillow')
      ? __('Details from Zillow')
      : sources.includes('listing')
        ? __('Details from this property’s own listing record')
        : __('Details as reported by the seller')
    rows.push(
      `<div style="margin-top:6px;font-size:10px;color:#8a877e">${label}</div>`,
    )
  }

  return `<div style="min-width:200px;max-width:260px;font:12px/1.45 system-ui,sans-serif;color:#161614">
      <div style="font-weight:700;color:${SUBJECT}">${__('This property')}</div>
      <div style="color:#5c5a55">${addr}</div>
      ${rows.join('')}
    </div>`
}

/**
 * The same age with no words, for the pill — "9d", "4mo", "2y".
 *
 * The pill is sized by its widest line, so " ago" is not free: it measured 103px
 * per pill against 90px without it. The popup and the list keep the wordy form,
 * where there is room and the sentence reads better.
 */
function agoShort(days) {
  const d = Number(days)
  if (!Number.isFinite(d) || d < 0) return ''
  if (d < 31) return `${Math.round(d)}d`
  if (d < 365) return `${Math.round(d / 30.44)}mo`
  const y = d / 365.25
  return `${y < 2 ? y.toFixed(1) : Math.round(y)}y`
}

/** "4 mo ago" from the server's own recency figure — the same number the fade uses. */
function agoLabel(days) {
  const d = Number(days)
  if (!Number.isFinite(d) || d < 0) return ''
  if (d < 31) return __('{0}d ago', [Math.round(d)])
  if (d < 365) return __('{0} mo ago', [Math.round(d / 30.44)])
  const y = d / 365.25
  return __('{0} yr ago', [y < 2 ? y.toFixed(1) : Math.round(y)])
}

function popupHtml(c) {
  const active = isActive(c.status)
  const ago = agoLabel(c.recency_days)
  const dom =
    c.days_on_market != null ? __('{0}d on market', [Math.round(c.days_on_market)]) : ''
  // Lead with the number that actually matters for THIS status. "99 days" means
  // opposite things on the two kinds of pin — 99 days ON the market for a live
  // listing (it is not selling), versus 99 days SINCE it left for an off-market
  // one (how current the evidence is) — so they are not rendered the same way.
  // For an off-market comp the date it left is the headline and DOM is context;
  // for a live listing it is the other way round.
  //
  // Deliberately "off-market", never "sold": this inventory carries the last ASK
  // and leaving the market is not a confirmed close.
  const headline = active
    ? `${__('For sale')}${dom ? ` · ${dom}` : ''}`
    : `${__('Off-market {0}', [fmtDate(c.removed_date)])}${ago ? ` · ${ago}` : ''}`
  const when = active
    ? __('Listed {0}', [fmtDate(c.listed_date)])
    : `${__('Listed {0}', [fmtDate(c.listed_date)])}${dom ? ` · ${dom}` : ''}`
  const facts = [
    c.bedrooms ? `${c.bedrooms} bd` : '',
    c.bathrooms ? `${c.bathrooms} ba` : '',
    c.square_footage ? `${Number(c.square_footage).toLocaleString()} sqft` : '',
    c.year_built ? `built ${c.year_built}` : '',
  ]
    .filter(Boolean)
    .join(' · ')
  // Deep-link straight to the comp on Zillow. Same slug builder the Lead page
  // uses, so a comp and a lead resolve the same way. rel=noopener because these
  // open in a new tab from injected popup HTML.
  const zurl = zillowUrl(c.address)
  const zlink = zurl
    ? `<div style="margin-top:6px"><a href="${escapeHtml(zurl)}" target="_blank" rel="noopener noreferrer"
         style="color:#2563c9;font-weight:600;text-decoration:underline">${__('Open on Zillow')} ↗</a></div>`
    : ''
  // Photos are the fastest way to know whether a comp is really comparable —
  // square footage says nothing about a gutted shell next to a renovated flip.
  // Full width and above the use/hide row because it is the thing most worth
  // doing before deciding either.
  const details = `<button data-comp-details="${escapeHtml(c.name)}" style="width:100%;
      cursor:pointer;margin-top:8px;font:600 11px/1 ui-sans-serif,system-ui;
      padding:7px 8px;border-radius:6px;border:1px solid #e5e3de;background:#fff;
      color:#2563c9">${__('Photos & details')}</button>`
  // Hide / use live in the popup rather than on the pill: a pill is 24px tall and
  // already the click target for "tell me about this one".
  const actions = `<div style="display:flex;gap:6px;margin-top:6px;padding-top:7px;
      border-top:1px solid #e5e3de">
      <button data-comp-use="${escapeHtml(c.name)}" style="flex:1;cursor:pointer;
        font:600 11px/1 ui-sans-serif,system-ui;padding:6px 8px;border-radius:6px;
        border:1px solid ${c.selected ? '#2563c9' : '#e5e3de'};
        background:${c.selected ? '#2563c9' : '#fff'};color:${c.selected ? '#fff' : '#44423d'}">
        ${c.selected ? `✓ ${__('Using')}` : __('Use as comp')}</button>
      <button data-comp-hide="${escapeHtml(c.name)}" style="cursor:pointer;
        font:600 11px/1 ui-sans-serif,system-ui;padding:6px 8px;border-radius:6px;
        border:1px solid #e5e3de;background:#fff;color:#8a877e">${__('Hide')}</button>
    </div>`
  return `<div style="min-width:190px;font:12px/1.45 system-ui,sans-serif;color:#161614">
      <div style="font-weight:700;margin-bottom:2px">${escapeHtml(c.address)}</div>
      <div style="font-size:15px;font-weight:700;margin:2px 0">${priceShort(c.price)}</div>
      <div style="color:${active ? '#b45309' : '#44423d'};font-weight:600">${headline}</div>
      <div style="color:#5c5a55">${when}</div>
      ${facts ? `<div style="color:#8a877e;margin-top:2px">${escapeHtml(facts)}</div>` : ''}
      <div style="color:#8a877e;margin-top:2px">${__('{0} mi away', [c.distance_mi])}</div>
      ${zlink}
      ${details}
      ${actions}
    </div>`
}

function render() {
  if (!mapEl.value) return
  if (map) {
    map.remove()
    map = null
  }
  // Markers are rebuilt below; stale entries would otherwise leak and the hover
  // watcher would try to light up an element no longer on the map.
  markersByName.clear()
  const s = data.value?.subject
  if (!s?.lat) return

  // scrollWheelZoom OFF deliberately. The map sits above the property list on a
  // full page, so a wheel over the map used to be swallowed by Leaflet and the
  // list below was unreachable on a laptop-height window (caught in review).
  // Zoom is still available via the +/- control and pinch on a trackpad.
  map = L.map(mapEl.value, { center: [s.lat, s.lng], zoom: 14, scrollWheelZoom: false })
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap',
  }).addTo(map)

  const bounds = [[s.lat, s.lng]]

  // Distance rings give instant scale. L.circle is metres on the ground, so the
  // rings stay true at any latitude (L.circleMarker would be pixels and lie).
  for (const [mi, label] of [
    [0.5, '½ mi'],
    [1, '1 mi'],
    [2, '2 mi'],
  ]) {
    if (mi > (data.value?.radius_mi || 2)) continue
    L.circle([s.lat, s.lng], {
      radius: mi * 1609.344,
      color: '#161614',
      weight: 1,
      opacity: 0.3,
      dashArray: '4 4',
      fill: false,
      interactive: false,
    }).addTo(map)
    L.marker([s.lat + mi / 69, s.lng], {
      icon: L.divIcon({
        className: '',
        // display:inline-block is load-bearing: iconSize [0,0] gives the icon
        // container zero width, and translate(-50%) of a BLOCK child inside it
        // resolves to 0px — so the label was never actually centred, it just
        // started at the ring point and ran right. Shrink-to-fit gives the
        // transform a real width to halve.
        html: `<div style="display:inline-block;transform:translate(-50%,-50%);
            background:rgba(255,255,255,.85);padding:0 4px;border-radius:4px;
            font:600 9px/14px system-ui,sans-serif;color:#44423d;white-space:nowrap">${label}</div>`,
        iconSize: [0, 0],
      }),
      interactive: false,
    }).addTo(map)
  }

  for (const c of comps.value) {
    if (c.lat == null || c.lng == null) continue
    // Fresher pills stack above faded ones where markers overlap, so the comp
    // that matters is the one you can actually click in a tight cluster.
    const fresh = Math.round(pillOpacity(stalenessDays(c)) * 100)
    const marker = L.marker([c.lat, c.lng], {
      icon: pillIcon(c),
      // A selected comp sits above everything so it stays clickable in a cluster.
      zIndexOffset: (c.selected ? 600 : isActive(c.status) ? 200 : 100) + fresh,
      opacity: c.hidden ? 0.45 : 1,
    })
      .addTo(map)
      .bindPopup(popupHtml(c), { maxWidth: 280 })
    // Remember which comp is open so h / u know what they act on.
    marker.on('popupopen', () => (focusedComp.value = c.name))
    marker.on('popupclose', () => {
      if (focusedComp.value === c.name) focusedComp.value = null
    })
    // Hover the pin -> highlight its row, and vice versa via `hoveredComp`.
    marker.on('mouseover', () => (hoveredComp.value = c.name))
    marker.on('mouseout', () => {
      if (hoveredComp.value === c.name) hoveredComp.value = null
    })
    markersByName.set(c.name, marker)
    bounds.push([c.lat, c.lng])
  }

  // The subject goes on LAST so it is never buried under a comp pill.
  L.marker([s.lat, s.lng], {
    zIndexOffset: 1000,
    // A real iconSize + centre anchor, NOT the 0x0-plus-transform trick the rings
    // use. With a zero-width container the horizontal translate(-50%) collapsed to
    // 0, so the marker for "the real parcel" was drawn ~9px to the RIGHT of the
    // coordinate it claims to mark — and its hit area sat off it too, on the one
    // pin that is expected to be clicked for the subject's details.
    icon: subjectIcon(s),
  })
    .addTo(map)
    .bindPopup(subjectPopupHtml(s), { maxWidth: 300 })

  if (bounds.length > 1) {
    try {
      map.fitBounds(bounds, { padding: [30, 30], maxZoom: 16 })
    } catch {
      /* single point / degenerate bounds — keep the default view */
    }
  }
  // Popup HTML is injected, so its buttons cannot carry Vue handlers. One
  // delegated listener on the map container covers every popup instead.
  map.getContainer().addEventListener('click', onPopupClick)

  // Leaflet mis-measures a container that was display:none when it mounted,
  // which is exactly what a modal is until the moment it opens.
  setTimeout(() => map && map.invalidateSize(), 120)
}

function onPopupClick(e) {
  const use = e.target?.closest?.('[data-comp-use]')
  if (use) {
    e.preventDefault()
    toggleUse(use.getAttribute('data-comp-use'))
    return
  }
  const detail = e.target?.closest?.('[data-comp-details]')
  if (detail) {
    e.preventDefault()
    openCompDetail(detail.getAttribute('data-comp-details'))
    return
  }
  const hide = e.target?.closest?.('[data-comp-hide]')
  if (hide) {
    e.preventDefault()
    setCompState(hide.getAttribute('data-comp-hide'), 'hidden')
  }
}

/**
 * Open one comp's photo gallery + Zillow facts.
 *
 * Resolved from `comps` by name rather than passed by reference so the popup
 * (whose HTML is injected and therefore holds only strings) and the list row
 * reach the identical object -- and so a reload cannot leave the modal showing a
 * comp that is no longer on the map.
 */
function openCompDetail(name) {
  const comp = comps.value.find((c) => c.name === name)
  if (!comp) return
  detailComp.value = comp
  showCompDetail.value = true
}

/** Draft -> the server's filter shape. Blank means "unconstrained", not zero. */
function currentFilters() {
  const f = { status: draft.status || 'all', radius_mi: radius.value }
  if (isSet(draft.within_days)) f.within_days = Number(draft.within_days)
  if (isSet(draft.property_types)) f.property_types = [draft.property_types]
  for (const k of RANGE_KEYS) {
    const v = draft[k]
    if (v !== '' && v != null && Number.isFinite(Number(v))) f[k] = Number(v)
  }
  return f
}

/** Server -> draft, so the controls always show what actually ran. */
function syncDraft(f) {
  syncing = true
  draft.status = f?.status || 'all'
  draft.within_days = f?.within_days ?? ANY
  const types = f?.property_types
  const type = Array.isArray(types) ? types[0] : types
  draft.property_types = type || ANY
  for (const k of RANGE_KEYS) {
    const v = f?.[k]
    draft[k] = v == null ? '' : v
  }
  // Watchers flush before nextTick callbacks, so this releases only after the
  // deep watcher has seen (and ignored) our own programmatic write.
  nextTick(() => {
    syncing = false
  })
}

/**
 * Mark a comp as one we are pricing off, or hide it. Team-wide by design.
 *
 * Optimistic on the pill, then reloaded: hiding removes a pin, which changes the
 * counts and can change which preset tier applies, and re-deriving that on the
 * client would be a second, divergent copy of the ladder.
 */
async function setCompState(comp, state) {
  if (!props.lead || !comp) return
  try {
    const res = await call('crm.api.comps.set_comp_state', {
      lead: props.lead,
      comp,
      state,
    })
    if (res?.ok === false) {
      toast.error(__('Comp selection is not set up on this site yet.'))
      return
    }
    if (state === 'hidden') toast.success(__('Comp hidden'))
    await load()
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not update that comp.'))
  }
}

function toggleUse(name) {
  const c = comps.value.find((x) => x.name === name)
  setCompState(name, c?.selected ? 'none' : 'selected')
}

async function load({ explicit = userTouched.value } = {}) {
  if (!props.lead) return
  loading.value = true
  try {
    const payload = { lead: props.lead, radius_mi: radius.value }
    if (revealHidden.value) payload.include_hidden = 1
    if (explicit) {
      payload.filters = JSON.stringify(currentFilters())
      payload.auto = 0
    } else {
      payload.auto = 1
    }
    data.value = await call('crm.api.comps.get_lead_comps', payload)
    // Hand the resolved subject facts to whoever is hosting us. `get_lead_comps`
    // is the only place that merges them best-first and labels each with its
    // source (Zillow > the property's own comp row > the lead's pick-list bands
    // > the tax pull), so a host that read CRM Lead directly would show the
    // vague band -- "1900-1950" -- next to a map pill already saying 1930.
    // Emitting costs the host nothing and avoids a second call to a function
    // that geocodes and can hit a paid Zillow lookup.
    emit('subject', data.value?.subject || null)
    syncDraft(data.value?.filters)
    await nextTick()
    render()
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not load comps.'))
  } finally {
    loading.value = false
  }
}

function resetToSuggested() {
  userTouched.value = false
  load({ explicit: false })
}

function toggleRevealHidden() {
  revealHidden.value = !revealHidden.value
  load()
}

const MAX_SHEET_COMPS = 4
const creatingSheet = ref(false)
const selectedNames = computed(() => comps.value.filter((c) => c.selected).map((c) => c.name))

const underwritingLabel = computed(() => {
  const n = selectedNames.value.length
  if (!n) return __('Select comps to underwrite')
  return __('Underwrite with {0} of {1} comps', [Math.min(n, MAX_SHEET_COMPS), MAX_SHEET_COMPS])
})

/**
 * Send the chosen comps to a NEW underwriting sheet.
 *
 * Always a new sheet, never an edit of an existing one: a colleague may already
 * have comps in theirs, and silently overwriting their work is the one outcome
 * worth a few cents of Drive storage to avoid.
 */
async function createUnderwriting() {
  const picked = selectedNames.value
  if (!picked.length) return
  if (picked.length > MAX_SHEET_COMPS) {
    toast.error(
      __('Pick at most {0} comps — you have {1} selected.', [MAX_SHEET_COMPS, picked.length]),
    )
    return
  }
  creatingSheet.value = true
  try {
    const res = await call('crm.api.underwriting.create_underwriting_from_comps', {
      lead: props.lead,
      comps: JSON.stringify(picked),
    })
    // Name the shortfall rather than opening a sheet with quietly missing rows:
    // the sheet's formulas need a Zillow homedetails URL and not every address
    // resolves to one.
    if (res?.unresolved?.length) {
      toast.warning(
        __("{0} comp(s) couldn't be linked to Zillow and were left out", [
          res.unresolved.length,
        ]),
      )
    }
    toast.success(
      res?.sheet_number > 1
        ? __('Created underwriting sheet #{0} with {1} comps', [
            res.sheet_number,
            res.comps_written,
          ])
        : __('Created underwriting sheet with {0} comps', [res?.comps_written ?? 0]),
    )
    if (res?.sheet_url) window.open(res.sheet_url, '_blank', 'noopener')
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not create the underwriting sheet.'))
  } finally {
    creatingSheet.value = false
  }
}

function clearAll() {
  syncing = true
  draft.status = 'all'
  draft.within_days = ANY
  draft.property_types = ANY
  for (const k of RANGE_KEYS) draft[k] = ''
  nextTick(() => {
    syncing = false
  })
  // Deliberately explicit: "clear" means show everything, not "go back to the
  // suggestion", which is what the neighbouring Reset button is for.
  userTouched.value = true
  load({ explicit: true })
}

// Watch the value rather than binding @change on the control: frappe-ui renders
// `type="select"` as a button-driven dropdown, not a native <select>, so a
// `change` event is not guaranteed to reach us. Watching v-model works whichever
// way the control chooses to emit.
watch(draft, () => {
  if (syncing || !show.value) return
  userTouched.value = true
  clearTimeout(applyTimer)
  // Debounced: typing "1400" into a min box is four keystrokes, not four queries.
  applyTimer = setTimeout(() => load({ explicit: true }), 300)
}, { deep: true })

watch(radius, () => {
  if (show.value) load()
})

watch(show, (v) => {
  if (v) {
    // Every open starts from the suggestion again: the filters describe THIS
    // property, and a stale set carried over from the last lead would be wrong.
    userTouched.value = false
    nextTick(() => load({ explicit: false }))
  } else if (map) {
    map.remove()
    map = null
  }
})

// GOTCHA — useKeyboardShortcuts defaults to skipWhenDialogOpen:true, and this IS
// a Dialog, so the shortcuts would silently never fire. It is turned off here and
// the modal's own `show` gates them instead. `ignoreTyping` (on by default) is
// what stops "d" toggling pills while someone types in a filter box.
//
// Because that opt-out is blanket, the photo gallery has to be excluded by hand:
// it is a Dialog stacked on top of this one, and without the guard `h` would hide
// the very comp whose photos the user is looking at.
useKeyboardShortcuts({
  active: () => !!show.value && !showCompDetail.value,
  skipWhenDialogOpen: false,
  shortcuts: [
    { keys: ['d', 'D'], action: () => (showDetail.value = !showDetail.value) },
    {
      keys: ['h', 'H'],
      action: () => focusedComp.value && setCompState(focusedComp.value, 'hidden'),
    },
    { keys: ['u', 'U'], action: () => focusedComp.value && toggleUse(focusedComp.value) },
  ],
})

// If this ever mounts with `show` already true (a v-if host, or a hot reload),
// the watcher above never fires and the map would sit empty claiming "no comps".
onMounted(() => {
  if (show.value) nextTick(() => load({ explicit: false }))
  observeMapSize()
})

onBeforeUnmount(() => {
  sizeObserver?.disconnect()
  sizeObserver = null
  if (map) {
    map.remove()
    map = null
  }
})

/**
 * Re-measure the map whenever its container changes size.
 *
 * Leaflet measures once, at init, and a container that was display:none measures
 * 0x0 -- so a host that keeps this mounted behind a hidden tab (the Today lead
 * modal) gets tiles crammed into the corner the first time the tab is opened.
 * The one-shot `invalidateSize` after render() only covers the case where the
 * container becomes visible within 120ms of loading, which a tab does not.
 *
 * Observing the element means every show, hide and window resize fixes itself
 * and no host has to remember to tell us it revealed the map.
 */
function observeMapSize() {
  if (!mapEl.value || typeof ResizeObserver === 'undefined') return
  sizeObserver = new ResizeObserver(() => {
    // Deferred a frame: calling back into layout from inside the callback is what
    // produces "ResizeObserver loop completed with undelivered notifications".
    requestAnimationFrame(() => map && map.invalidateSize())
  })
  sizeObserver.observe(mapEl.value)
}
</script>

<style>
/* Kill Leaflet's default white chrome on divIcons so the pills sit clean. */
.comps-price-pill {
  background: transparent;
  border: 0;
}

/* The remove-✕ is hover-only: 200 pins each wearing a permanent ✕ would be
   louder than the prices they exist to show. */
.comps-pill-x {
  display: none;
}
.comps-price-pill:hover .comps-pill-x {
  display: block;
}

/* Hovering the row (or the pin) outlines the matching pill and brings it to full
   strength; the JS also lifts its z-index so it is never half-buried.

   NOTE: a `transform: scale()` was tried here first and is deliberately gone --
   it silently does nothing on a Leaflet divIcon child. Verified directly: with
   the rule matching (its `outline` applied fine) the computed transform stayed
   `matrix(1,0,0,1,0,0)` at 600ms, and even setting `style.transform` inline on
   the element did not take. Outline + opacity are what actually render, so they
   are what the highlight is built from. */
.comps-price-pill.comps-pill-hot .comps-pill-body {
  opacity: 1 !important;
  outline: 3px solid #161614;
  outline-offset: 2px;
}
.comps-pill-body {
  transition: opacity 90ms ease-out;
}
</style>
