<template>
  <div
    class="group/card relative cursor-pointer border-b border-outline-gray-1 transition-colors last:border-b-0"
    :class="[
      discarded
        ? 'bg-surface-gray-1'
        : active
          ? 'bg-surface-gray-2'
          : selected
            ? 'bg-surface-blue-1'
            : 'hover:bg-surface-gray-1',
    ]"
    @mouseenter="prefetchPhotos(); $emit('hover', comp.name)"
    @mouseleave="$emit('hover', null)"
    @click="$emit('open', comp.name)"
  >
    <!-- A discarded comp is dimmed and desaturated rather than removed: the rep
         has to be able to see what they threw out to know whether to undo it.
         Kept non-interactive so a stray click can't re-open a rejected house. -->
    <div :class="discarded ? 'pointer-events-none opacity-45 grayscale' : ''">
      <div
        class="group/photo relative aspect-[3/2] w-full overflow-hidden bg-surface-gray-2"
        @mouseenter="prefetchPhotos"
      >
        <img
          v-if="photo"
          :src="photo"
          :alt="comp.address || ''"
          loading="lazy"
          decoding="async"
          referrerpolicy="no-referrer"
          class="size-full object-cover"
          @error="broken = true"
          v-show="!broken"
        />
        <!-- No photo is the normal case for a pooled-index comp that Zillow's
             area search never matched. Say so quietly instead of showing a
             broken frame. -->
        <div
          v-if="!photo || broken"
          class="flex size-full flex-col items-center justify-center gap-1 text-ink-gray-4"
        >
          <FeatherIcon name="home" class="size-6" />
          <span class="text-2xs">{{ __('No photo') }}</span>
        </div>

        <!-- Status is the first thing that decides whether a row is evidence of a
             sale or of an ask, so it sits on the image rather than below it. -->
        <span
          class="absolute left-2 top-2 rounded px-1.5 py-0.5 text-2xs font-semibold shadow-sm"
          :style="{ background: palette.bg, color: palette.ink }"
        >
          {{ isActive ? __('For sale') : __('Off-market') }}
        </span>
        <span
          v-if="selected"
          class="absolute right-2 top-2 rounded bg-surface-blue-3 px-1.5 py-0.5 text-2xs font-semibold text-white shadow-sm"
        >
          {{ __('Using') }}
        </span>

        <!-- Hover either edge of the photo to page through the rest. Arrows
             stay hidden until the pointer is actually on that half, so a dense
             tray does not grow a forest of chevrons. Clicking an arrow must
             not open the detail modal — that's the rest of the card. -->
        <button
          v-if="photoIndex > 0"
          class="absolute bottom-0 left-0 top-9 z-20 flex w-10 items-center justify-center bg-gradient-to-r from-black/40 to-transparent text-white opacity-0 transition group-hover/photo:opacity-100"
          :aria-label="__('Previous photo')"
          @click.stop.prevent="stepPhoto(-1)"
        >
          <FeatherIcon name="chevron-left" class="size-5 drop-shadow" />
        </button>
        <button
          v-if="photoIndex < photos.length - 1"
          class="absolute bottom-0 right-0 top-9 z-20 flex w-10 items-center justify-center bg-gradient-to-l from-black/40 to-transparent text-white opacity-0 transition group-hover/photo:opacity-100"
          :aria-label="__('Next photo')"
          @click.stop.prevent="stepPhoto(1)"
        >
          <FeatherIcon name="chevron-right" class="size-5 drop-shadow" />
        </button>
        <span
          v-if="photos.length > 1"
          class="pointer-events-none absolute bottom-1.5 left-1.5 z-20 rounded bg-black/55 px-1.5 py-0.5 text-2xs text-white"
        >
          {{ photoIndex + 1 }}/{{ photos.length }}
        </span>
      </div>

      <div class="px-3 py-2">
        <div class="flex items-baseline justify-between gap-2">
          <span class="text-base font-semibold text-ink-gray-9">{{ price }}</span>
          <span class="shrink-0 text-xs tabular-nums text-ink-gray-5">
            {{ comp.distance_mi }} mi
          </span>
        </div>
        <div class="mt-0.5 text-xs text-ink-gray-7">{{ facts }}</div>

        <!-- How this comp differs from the subject, which is the actual question
             being asked of it. Without this the rep reads "1,744 sqft", then has
             to remember the subject was 1,749 and do the subtraction — for every
             card. Only non-zero differences are shown: a comp that matches on
             beds says nothing by saying "+0 bd". -->
        <div v-if="deltas.length" class="mt-1 flex flex-wrap gap-x-1.5 gap-y-0.5">
          <span
            v-for="d in deltas"
            :key="d.key"
            class="rounded bg-surface-gray-2 px-1 text-2xs font-medium tabular-nums text-ink-gray-6"
            :title="d.title"
          >{{ d.text }}</span>
        </div>

        <div class="mt-0.5 truncate text-xs font-medium text-ink-gray-8" :title="comp.address">
          {{ street }}
        </div>
        <div class="mt-1 text-2xs" :class="isActive ? 'text-ink-red-3' : 'text-ink-gray-5'">
          {{ timing }}
        </div>
      </div>
    </div>

    <!-- Undo sits ON the discarded card, not in a separate list somewhere else:
         the thing you want to undo is the thing you are looking at. -->
    <div v-if="discarded" class="absolute inset-0 flex items-center justify-center">
      <Button
        :label="__('Undo discard')"
        iconLeft="rotate-ccw"
        @click.stop="$emit('undiscard', comp.name)"
      />
    </div>

    <!-- ALWAYS visible, not hover-revealed. Use and discard are the two
         judgements this tray exists to capture, and the same view opens on a
         phone from MobileLead — where there is no hover at all, so a
         hover-only control is simply unreachable. They sit at low contrast
         over the photo and strengthen on hover, which keeps a dense tray calm
         without hiding its primary actions. -->
    <div v-else class="absolute right-2 top-2 z-30 flex gap-1">
      <button
        class="rounded bg-surface-white/80 px-1.5 py-1 shadow-sm ring-1 ring-outline-gray-2 transition hover:bg-surface-white"
        :class="selected ? 'text-ink-blue-3' : 'text-ink-gray-6 hover:text-ink-gray-9'"
        :title="__('Use as comp') + ' (U)'"
        @click.stop="$emit('use', comp.name)"
      >
        <!-- plus / check, not an unchecked-checkbox square: beside the discard
             ✕ an empty square reads as a second empty box rather than as an
             action. "+" says add it, "✓" says it is in. -->
        <FeatherIcon :name="selected ? 'check' : 'plus'" class="size-3.5" />
      </button>
      <button
        class="rounded bg-surface-white/80 px-1.5 py-1 text-ink-gray-6 shadow-sm ring-1 ring-outline-gray-2 transition hover:bg-surface-white hover:text-ink-red-3"
        :title="__('Discard this comp') + ' (H)'"
        @click.stop="$emit('discard', comp.name)"
      >
        <FeatherIcon name="x" class="size-3.5" />
      </button>
    </div>
  </div>
</template>

<script setup>
/**
 * One property in the comps tray: photo, price, facts, and the two judgements a
 * rep makes about it (use it / discard it).
 *
 * Split out of CompsView because that file is already long, and because the card
 * is the unit the tray repeats — a change to how a comp reads should be one edit,
 * not a hunt through a 2,000-line template.
 */
import { Button, FeatherIcon } from 'frappe-ui'
import { computed, ref } from 'vue'
import { compColor, isActiveStatus, loadCompPhotos, streetAddress } from '@/utils/comps'

const props = defineProps({
  comp: { type: Object, required: true },
  lead: { type: String, default: '' },
  active: { type: Boolean, default: false },
  discarded: { type: Boolean, default: false },
  // The resolved subject facts from `get_lead_comps`, for the +/- comparison.
  subject: { type: Object, default: null },
})
defineEmits(['hover', 'open', 'use', 'discard', 'undiscard'])

// Shared with the map pills and the legend, so a card and its pin can never
// disagree about what "sold" looks like.
const palette = computed(() => compColor(props.comp.status))

const broken = ref(false)
const photos = ref([])
const photoIndex = ref(0)
const photo = computed(() => {
  if (photos.value.length) return photos.value[photoIndex.value] || ''
  return props.comp.photo || ''
})
const street = computed(() => streetAddress(props.comp.address) || props.comp.address || '')

function prefetchPhotos() {
  if (photos.value.length || !props.lead) return
  loadCompPhotos(props.lead, props.comp.name).then((urls) => {
    if (!urls.length) return
    photos.value = urls
    const cover = props.comp.photo
    const i = cover ? urls.indexOf(cover) : -1
    photoIndex.value = i >= 0 ? i : 0
  })
}
function stepPhoto(dir) {
  const next = photoIndex.value + dir
  if (next < 0 || next >= photos.value.length) return
  photoIndex.value = next
  broken.value = false
}
const selected = computed(() => !!props.comp.selected)
const isActive = computed(() => isActiveStatus(props.comp.status))

const price = computed(() => {
  const p = Number(props.comp.price)
  if (!p) return '—'
  return '$' + Math.round(p).toLocaleString()
})

const facts = computed(() => {
  const c = props.comp
  const bits = []
  if (c.bedrooms) bits.push(__('{0} bd', [c.bedrooms]))
  if (c.bathrooms) bits.push(__('{0} ba', [c.bathrooms]))
  if (c.square_footage) bits.push(Number(c.square_footage).toLocaleString() + ' ' + __('sqft'))
  if (c.year_built) bits.push(__('built {0}', [c.year_built]))
  return bits.join(' · ') || __('No details')
})

/**
 * The comp minus the subject, per fact.
 *
 * Uses the subject's EXACT numbers only (`beds_exact` etc.). The lead's own
 * pick-list fields are bands -- "1000 - 2000" sqft, "3 Bedroom" -- and
 * subtracting a band midpoint would invent precision the source never had, then
 * print it as a hard "+244 sqft". When Zillow gave us a real number the delta is
 * real; otherwise there is simply no chip, which is honest.
 */
const DELTA_FIELDS = [
  { key: 'bedrooms', subj: 'beds', unit: 'bd', dp: 0 },
  { key: 'bathrooms', subj: 'baths', unit: 'ba', dp: 1 },
  { key: 'square_footage', subj: 'sqft', unit: 'sqft', dp: 0 },
  { key: 'year_built', subj: 'year_built', unit: 'yr', dp: 0 },
]

const deltas = computed(() => {
  const s = props.subject
  if (!s) return []
  const out = []
  for (const f of DELTA_FIELDS) {
    // `*_exact` marks a number that came from a real source rather than a band.
    if (f.subj !== 'year_built' && s[`${f.subj}_exact`] === false) continue
    const a = Number(props.comp[f.key])
    const b = Number(s[f.subj])
    if (!Number.isFinite(a) || !Number.isFinite(b) || !a || !b) continue
    const diff = a - b
    const r = f.dp ? Math.round(diff * 10) / 10 : Math.round(diff)
    if (!r) continue
    const n = f.unit === 'sqft' ? Math.abs(r).toLocaleString() : Math.abs(r)
    out.push({
      key: f.key,
      text: `${r > 0 ? '+' : '−'}${n} ${f.unit}`,
      title: __('{0} vs this property', [`${r > 0 ? '+' : '−'}${n} ${f.unit}`]),
    })
  }
  return out
})

/**
 * "99 days" means opposite things on the two kinds of pin, so they are never
 * rendered the same way: days ON the market for a live listing (it is not
 * selling) versus days SINCE it left for an off-market one (how current the
 * evidence is). Same rule as the map popup.
 */
const timing = computed(() => {
  const c = props.comp
  if (isActive.value) {
    const dom = c.days_on_market
    return dom ? __('Listed · {0} days on market', [dom]) : __('Listed')
  }
  const d = fmtDate(c.removed_date)
  const ago = agoLabel(c.recency_days)
  return d ? (ago ? `${__('Off-market')} ${d} · ${ago}` : `${__('Off-market')} ${d}`) : __('Off-market')
})

/**
 * GOTCHA — `Date.parse('YYYY-MM-DD')` is UTC midnight, so `toLocaleDateString`
 * renders the PREVIOUS day everywhere west of Greenwich. A date-only value is a
 * calendar date with no timezone; build it as local.
 */
function fmtDate(v) {
  if (!v) return ''
  const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})/)
  const d = m ? new Date(+m[1], +m[2] - 1, +m[3]) : new Date(v)
  if (isNaN(d)) return ''
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function agoLabel(days) {
  if (days == null) return ''
  const n = Number(days)
  if (!Number.isFinite(n)) return ''
  if (n < 45) return __('{0}d ago', [Math.round(n)])
  if (n < 365) return __('{0} mo ago', [Math.round(n / 30)])
  return __('{0}y ago', [(n / 365).toFixed(1)])
}
</script>
