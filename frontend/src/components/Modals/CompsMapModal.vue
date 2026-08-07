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
                {{
                  __('{0} comps within {1} mi', [
                    data?.total_in_radius ?? comps.length,
                    data?.radius_mi,
                  ])
                }}
                <template v-if="data?.total_in_radius > comps.length">
                  · {{ __('showing the {0} nearest', [comps.length]) }}
                </template>
              </template>
              <template v-else>{{ emptyMessage }}</template>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <!-- Radius is the one control that matters: a rural lead needs a
                 wider net than an infill lot, and the right answer is obvious
                 the moment you see the map. -->
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
              @click="load"
            />
          </div>
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
 */
import { Dialog, Button, FormControl, call, toast } from 'frappe-ui'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

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

const comps = computed(() => data.value?.comps || [])
const emptyMessage = computed(
  () => data.value?.message || __('No comps found nearby.'),
)

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
  const ms = Date.parse(v)
  if (!Number.isFinite(ms)) return String(v).slice(0, 10)
  return new Date(ms).toLocaleDateString('en-US', {
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

function popupHtml(c) {
  const active = isActive(c.status)
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
  return `<div style="min-width:190px;font:12px/1.45 system-ui,sans-serif;color:#161614">
      <div style="font-weight:700;margin-bottom:2px">${escapeHtml(c.address)}</div>
      <div style="font-size:15px;font-weight:700;margin:2px 0">${priceShort(c.price)}</div>
      <div style="color:#5c5a55">${active ? __('Active (still listed)') : __('Off-market')}${
        c.days_on_market != null ? ` · ${Math.round(c.days_on_market)}d DOM` : ''
      }</div>
      <div style="color:#5c5a55">${when}</div>
      ${facts ? `<div style="color:#8a877e;margin-top:2px">${escapeHtml(facts)}</div>` : ''}
      <div style="color:#8a877e;margin-top:2px">${__('{0} mi away', [c.distance_mi])}</div>
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
        html: `<div style="transform:translate(-50%,-50%);background:rgba(255,255,255,.85);
            padding:0 4px;border-radius:4px;font:600 9px/14px system-ui,sans-serif;
            color:#44423d;white-space:nowrap">${label}</div>`,
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
    icon: L.divIcon({
      className: '',
      html: `<div style="transform:translate(-50%,-50%)">
          <div style="width:18px;height:18px;border-radius:50%;background:${SUBJECT};
            border:3px solid #fff;box-shadow:0 1px 6px rgba(0,0,0,.5)"></div>
        </div>`,
      iconSize: [0, 0],
    }),
  })
    .addTo(map)
    .bindPopup(
      `<div style="font:12px/1.45 system-ui,sans-serif">
        <div style="font-weight:700;color:${SUBJECT}">${__('This property')}</div>
        <div style="color:#5c5a55">${escapeHtml(data.value?.address || '')}</div>
      </div>`,
    )

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

async function load() {
  if (!props.lead) return
  loading.value = true
  try {
    data.value = await call('crm.api.comps.get_lead_comps', {
      lead: props.lead,
      radius_mi: radius.value,
    })
    await nextTick()
    render()
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not load comps.'))
  } finally {
    loading.value = false
  }
}

// Watch the value rather than binding @change on the control: frappe-ui renders
// `type="select"` as a button-driven dropdown, not a native <select>, so a
// `change` event is not guaranteed to reach us. Watching v-model works whichever
// way the control chooses to emit.
watch(radius, () => {
  if (show.value) load()
})

watch(show, (v) => {
  if (v) {
    nextTick(load)
  } else if (map) {
    map.remove()
    map = null
  }
})

// If this ever mounts with `show` already true (a v-if host, or a hot reload),
// the watcher above never fires and the map would sit empty claiming "no comps".
onMounted(() => {
  if (show.value) nextTick(load)
})
</script>

<style>
/* Kill Leaflet's default white chrome on divIcons so the pills sit clean. */
.comps-price-pill {
  background: transparent;
  border: 0;
}
</style>
