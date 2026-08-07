<template>
  <Dialog
    v-model="show"
    :options="{ title: __('Comparable sales'), size: '5xl' }"
  >
    <template #body-content>
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
            <!-- Same shape as the CRM's list/kanban Filter control: a labelled
                 button carrying a count badge, with a clear affordance welded to
                 its right edge. Comps have a fixed, small filter set, so the rows
                 inside are named outright instead of a field/operator builder. -->
            <Popover placement="bottom-end">
              <template #target="{ togglePopover }">
                <div class="flex items-center">
                  <Button
                    :label="__('Filters')"
                    :class="activeFilterCount ? 'rounded-r-none' : ''"
                    :iconLeft="FilterIcon"
                    @click="togglePopover"
                  >
                    <template v-if="activeFilterCount" #suffix>
                      <div
                        class="flex h-5 w-5 items-center justify-center rounded-[5px] bg-surface-white pt-px text-xs font-medium text-ink-gray-8 shadow-sm"
                      >
                        {{ activeFilterCount }}
                      </div>
                    </template>
                  </Button>
                  <Button
                    v-if="activeFilterCount"
                    :tooltip="__('Clear all filters')"
                    class="rounded-l-none border-l"
                    icon="x"
                    @click.stop="clearAll"
                  />
                </div>
              </template>
              <template #body>
                <div
                  class="my-2 rounded-lg bg-surface-modal shadow-2xl ring-1 ring-black ring-opacity-5 focus:outline-none"
                >
                  <!-- max-w is load-bearing on a phone: without it the panel took
                       its content's preferred width (480px inside a 390px screen)
                       and every "max" input, all three dropdowns and Clear all sat
                       off the right edge. Capping it makes the min-w-0 flex children
                       actually shrink. The Lead page has a mobile twin, so this
                       panel genuinely renders at 390px. -->
                  <div
                    class="min-w-72 max-w-[calc(100vw-1.5rem)] p-3 sm:min-w-[420px]"
                  >
                    <div class="mb-2.5 flex items-baseline justify-between gap-2">
                      <span class="text-base font-medium text-ink-gray-8">
                        {{ __('Filter comps') }}
                      </span>
                      <span class="text-xs text-ink-gray-5">
                        {{
                          __('{0} of {1} nearby', [
                            data?.total_matched ?? 0,
                            data?.total_in_radius ?? 0,
                          ])
                        }}
                      </span>
                    </div>

                    <div class="flex flex-col gap-2">
                      <div class="flex items-center gap-2">
                        <div class="w-20 shrink-0 text-end text-sm text-ink-gray-5">
                          {{ __('Status') }}
                        </div>
                        <FormControl
                          class="flex-1"
                          type="select"
                          size="sm"
                          :options="statusOptions"
                          v-model="draft.status"
                        />
                      </div>
                      <div class="flex items-center gap-2">
                        <div class="w-20 shrink-0 text-end text-sm text-ink-gray-5">
                          {{ __('Within') }}
                        </div>
                        <FormControl
                          class="flex-1"
                          type="select"
                          size="sm"
                          :options="withinOptions"
                          v-model="draft.within_days"
                        />
                      </div>

                      <div
                        v-for="r in rangeRows"
                        :key="r.key"
                        class="flex items-center gap-2"
                      >
                        <div class="w-20 shrink-0 text-end text-sm text-ink-gray-5">
                          {{ r.label }}
                        </div>
                        <FormControl
                          class="min-w-0 flex-1"
                          type="number"
                          size="sm"
                          :step="r.step"
                          :placeholder="__('min')"
                          v-model="draft[r.key + '_min']"
                        />
                        <span class="shrink-0 text-ink-gray-4">–</span>
                        <FormControl
                          class="min-w-0 flex-1"
                          type="number"
                          size="sm"
                          :step="r.step"
                          :placeholder="__('max')"
                          v-model="draft[r.key + '_max']"
                        />
                      </div>

                      <div class="flex items-center gap-2">
                        <div class="w-20 shrink-0 text-end text-sm text-ink-gray-5">
                          {{ __('Type') }}
                        </div>
                        <FormControl
                          class="flex-1"
                          type="select"
                          size="sm"
                          :options="typeOptions"
                          v-model="draft.property_types"
                        />
                      </div>
                    </div>

                    <div class="mt-3 flex items-center justify-between gap-2">
                      <Button
                        class="!text-ink-gray-5"
                        variant="ghost"
                        :label="__('Reset to suggested')"
                        @click="resetToSuggested"
                      />
                      <Button
                        class="!text-ink-gray-5"
                        variant="ghost"
                        :label="__('Clear all')"
                        @click="clearAll"
                      />
                    </div>
                  </div>
                </div>
              </template>
            </Popover>

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
          class="h-[26rem] w-full overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-gray-1 sm:h-[32rem]"
        />

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
          <span class="text-ink-gray-4">{{ __('Click any pin for details') }}</span>
        </div>
      </div>
    </template>
  </Dialog>
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
import { Dialog, Button, FormControl, Popover, call, toast } from 'frappe-ui'
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { zillowUrl } from '@/utils/propertyLinks'
import FilterIcon from '@/components/Icons/FilterIcon.vue'

const props = defineProps({
  lead: { type: String, required: true },
  address: { type: String, default: '' },
})
const show = defineModel()

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

const withinOptions = [
  { label: __('Any time'), value: ANY },
  { label: __('Last 90 days'), value: 90 },
  { label: __('Last 6 months'), value: 180 },
  { label: __('Last year'), value: 365 },
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

function pillIcon(c) {
  const active = isActive(c.status)
  const label = priceShort(c.price)
  const opacity = pillOpacity(stalenessDays(c))
  const bg = active ? ACTIVE : OFF_MARKET
  const w = Math.max(40, Math.ceil(18 + label.length * 7.4))
  return L.divIcon({
    className: 'comps-price-pill',
    html: `<div style="display:flex;align-items:center;justify-content:center;
        box-sizing:border-box;width:${w}px;height:24px;background:${bg};color:#fff;
        font:700 11px/1 ui-sans-serif,system-ui,sans-serif;border-radius:999px;
        border:1px solid ${active ? '#b45309' : '#334155'};
        box-shadow:0 1px 3px rgba(0,0,0,.35);white-space:nowrap;
        opacity:${opacity.toFixed(3)}">${label}</div>`,
    iconSize: [w, 24],
    iconAnchor: [w / 2, 12],
    popupAnchor: [0, -14],
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
    fmtMoney(s.assessed_value) ? `${__('Assessed')} ${fmtMoney(s.assessed_value)}` : '',
    fmtMoney(s.annual_tax) ? `${__('Tax')} ${fmtMoney(s.annual_tax)}/yr` : '',
    fmtMoney(s.asking_price) ? `${__('Asking')} ${fmtMoney(s.asking_price)}` : '',
  ].filter(Boolean)
  if (extras.length) {
    rows.push(
      `<div style="margin-top:4px;color:#5c5a55">${escapeHtml(extras.join(' · '))}</div>`,
    )
  }

  const sources = Object.values(s.source || {})
  if (sources.length) {
    const label = sources.includes('listing')
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
  const when = active
    ? __('Listed {0}', [fmtDate(c.listed_date)])
    : `${__('Listed {0}', [fmtDate(c.listed_date)])} → ${__('removed {0}', [fmtDate(c.removed_date)])}`
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
  return `<div style="min-width:190px;font:12px/1.45 system-ui,sans-serif;color:#161614">
      <div style="font-weight:700;margin-bottom:2px">${escapeHtml(c.address)}</div>
      <div style="font-size:15px;font-weight:700;margin:2px 0">${priceShort(c.price)}</div>
      <div style="color:#5c5a55">${active ? __('Active (still listed)') : __('Off-market')}${
        c.days_on_market != null ? ` · ${Math.round(c.days_on_market)}d DOM` : ''
      }</div>
      <div style="color:#5c5a55">${when}</div>
      ${facts ? `<div style="color:#8a877e;margin-top:2px">${escapeHtml(facts)}</div>` : ''}
      <div style="color:#8a877e;margin-top:2px">${__('{0} mi away', [c.distance_mi])}${
        ago ? ` · ${ago}` : ''
      }</div>
      ${zlink}
    </div>`
}

function render() {
  if (!mapEl.value) return
  if (map) {
    map.remove()
    map = null
  }
  const s = data.value?.subject
  if (!s?.lat) return

  map = L.map(mapEl.value, { center: [s.lat, s.lng], zoom: 14, scrollWheelZoom: true })
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
    L.marker([c.lat, c.lng], {
      icon: pillIcon(c),
      zIndexOffset: (isActive(c.status) ? 200 : 100) + fresh,
    })
      .addTo(map)
      .bindPopup(popupHtml(c), { maxWidth: 280 })
    bounds.push([c.lat, c.lng])
  }

  // The subject goes on LAST so it is never buried under a comp pill.
  L.marker([s.lat, s.lng], {
    zIndexOffset: 1000,
    // A real iconSize + centre anchor, NOT the 0x0-plus-transform trick the rings
    // use. With a zero-width container the horizontal translate(-50%) collapsed to
    // 0, so the dot marking "the real parcel" was drawn ~9px to the RIGHT of the
    // coordinate it claims to mark — and its hit area sat off the dot too, on the
    // one pin that is now expected to be clicked for the subject's details.
    icon: L.divIcon({
      className: '',
      html: `<div style="width:18px;height:18px;border-radius:50%;background:${SUBJECT};
          border:3px solid #fff;box-shadow:0 1px 6px rgba(0,0,0,.5);box-sizing:border-box"></div>`,
      iconSize: [18, 18],
      iconAnchor: [9, 9],
      popupAnchor: [0, -10],
    }),
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
  // Leaflet mis-measures a container that was display:none when it mounted,
  // which is exactly what a modal is until the moment it opens.
  setTimeout(() => map && map.invalidateSize(), 120)
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

async function load({ explicit = userTouched.value } = {}) {
  if (!props.lead) return
  loading.value = true
  try {
    const payload = { lead: props.lead, radius_mi: radius.value }
    if (explicit) {
      payload.filters = JSON.stringify(currentFilters())
      payload.auto = 0
    } else {
      payload.auto = 1
    }
    data.value = await call('crm.api.comps.get_lead_comps', payload)
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

// If this ever mounts with `show` already true (a v-if host, or a hot reload),
// the watcher above never fires and the map would sit empty claiming "no comps".
onMounted(() => {
  if (show.value) nextTick(() => load({ explicit: false }))
})
</script>

<style>
/* Kill Leaflet's default white chrome on divIcons so the pills sit clean. */
.comps-price-pill {
  background: transparent;
  border: 0;
}
</style>
