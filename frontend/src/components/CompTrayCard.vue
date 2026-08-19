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
    @mouseenter="$emit('hover', comp.name)"
    @mouseleave="$emit('hover', null)"
    @click="$emit('open', comp.name)"
  >
    <!-- A discarded comp is dimmed and desaturated rather than removed: the rep
         has to be able to see what they threw out to know whether to undo it.
         Kept non-interactive so a stray click can't re-open a rejected house. -->
    <div :class="discarded ? 'pointer-events-none opacity-45 grayscale' : ''">
      <div class="relative aspect-[3/2] w-full overflow-hidden bg-surface-gray-2">
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
          class="absolute left-2 top-2 rounded px-1.5 py-0.5 text-2xs font-semibold text-white shadow-sm"
          :style="{ background: isActive ? ACTIVE : OFF_MARKET }"
        >
          {{ isActive ? __('For sale') : __('Off-market') }}
        </span>
        <span
          v-if="selected"
          class="absolute right-2 top-2 rounded bg-surface-blue-3 px-1.5 py-0.5 text-2xs font-semibold text-white shadow-sm"
        >
          {{ __('Using') }}
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
        <div class="mt-0.5 truncate text-xs text-ink-gray-6" :title="comp.address">
          {{ comp.address }}
        </div>
        <div class="mt-1 text-2xs" :class="isActive ? 'text-ink-amber-3' : 'text-ink-gray-5'">
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
    <div v-else class="absolute right-2 top-2 flex gap-1">
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

const props = defineProps({
  comp: { type: Object, required: true },
  active: { type: Boolean, default: false },
  discarded: { type: Boolean, default: false },
})
defineEmits(['hover', 'open', 'use', 'discard', 'undiscard'])

// Same two colours the map pills use. Kept in JS rather than as Tailwind tokens
// because the canvas/pill code cannot read CSS variables and the two must agree.
const ACTIVE = '#d97706'
const OFF_MARKET = '#475569'

const broken = ref(false)
const photo = computed(() => props.comp.photo || '')
const selected = computed(() => !!props.comp.selected)
const isActive = computed(() =>
  String(props.comp.status || '').toLowerCase().startsWith('activ'),
)

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
