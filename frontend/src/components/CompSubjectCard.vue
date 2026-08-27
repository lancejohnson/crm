<template>
  <!-- Clickable for the same reason the pin is: every comp beneath this opens a
       gallery, and the subject is the house actually being priced. Consistency
       matters more than novelty here -- a card that looks like the others and
       does not behave like them is the surprising one. -->
  <div
    class="cursor-pointer border-b-2 border-outline-blue-2 bg-surface-blue-1 transition-colors hover:bg-surface-blue-2"
    :title="__('Photos & details for this property')"
    @click="$emit('open')"
  >
    <div class="relative aspect-[3/2] w-full overflow-hidden bg-surface-gray-2">
      <!-- Deliberately NOT `loading="lazy"`: this is the first card in the tray,
           always on screen, so there was never anything to defer -- and lazy does
           not fire inside this scroller anyway (see the note in CompTrayCard),
           which is why the subject's photo only appeared after a hover. -->
      <img
        v-if="photo && !broken"
        :src="photo"
        :alt="address"
        decoding="async"
        referrerpolicy="no-referrer"
        class="size-full object-cover"
        @error="broken = true"
      />
      <div
        v-else
        class="flex size-full flex-col items-center justify-center gap-1 text-ink-gray-4"
      >
        <FeatherIcon name="home" class="size-6" />
        <span class="text-2xs">{{ __('No photo') }}</span>
      </div>
      <span
        class="absolute left-2 top-2 rounded px-1.5 py-0.5 text-2xs font-semibold text-white shadow-sm"
        :style="{ background: SUBJECT }"
      >
        {{ __('This property') }}
      </span>
      <button
        v-if="subject?.lat != null && subject?.lng != null"
        class="absolute right-2 top-2 z-30 rounded bg-surface-white/80 px-1.5 py-1 text-ink-gray-6 shadow-sm ring-1 ring-outline-gray-2 transition hover:bg-surface-white hover:text-ink-gray-9"
        :title="__('Street View')"
        @click.stop="$emit('street')"
      >
        <FeatherIcon name="navigation" class="size-3.5" />
      </button>
    </div>

    <div class="px-3 py-2">
      <div class="truncate text-sm font-semibold text-ink-gray-9" :title="address">
        {{ address }}
      </div>
      <div class="mt-0.5 text-xs text-ink-gray-7">{{ facts }}</div>
      <!-- What it actually SOLD for is a verified transaction and outranks every
           other number here, so it is stated separately rather than folded in
           with the estimates. -->
      <!-- Zillow often records that a house sold and when, without a price (a
           non-disclosure state, or simply an unpriced public record). "Last sold
           — · Jun 3, 2021" reads like a rendering fault; the date on its own is a
           real fact and is worth saying. -->
      <div v-if="lastSale && (lastSale.price || lastSale.date)" class="mt-1 text-xs text-ink-gray-6">
        {{ __('Last sold') }}
        <b v-if="lastSale.price" class="text-ink-gray-8">{{ money(lastSale.price) }}</b>
        <template v-if="lastSale.price && lastSale.date"> · </template>
        <template v-if="lastSale.date">{{ fmtDate(lastSale.date) }}</template>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * The subject, rendered in the same card grammar as the comps directly beneath
 * it — so "is this one bigger or smaller than mine" is a glance rather than a
 * memory test. Blue and heavier-bordered so it never reads as one of them.
 */
import { FeatherIcon } from 'frappe-ui'
import { computed, ref, watch } from 'vue'
import { COMP_COLORS, formatLotSize } from '@/utils/comps'

const props = defineProps({
  subject: { type: Object, default: null },
  address: { type: String, default: '' },
})
defineEmits(['open', 'street'])

const SUBJECT = COMP_COLORS.subject.bg
const broken = ref(false)

const photo = computed(() => props.subject?.cover_photo || '')
watch(photo, () => {
  broken.value = false
})

const facts = computed(() => {
  const s = props.subject || {}
  const bits = []
  // `*_label` is the interval the SOURCE named ("1000 - 2000"), never a midpoint:
  // a vague seller answer must not be rendered as precision it does not have.
  if (s.beds_label) bits.push(__('{0} bd', [s.beds_label]))
  if (s.baths_label) bits.push(__('{0} ba', [s.baths_label]))
  if (s.sqft_label) bits.push(__('{0} sqft', [s.sqft_label]))
  const lot = formatLotSize(s.lot_size, { compact: true })
  if (lot) bits.push(lot)
  // Year was missing here while every comp card beneath it showed one, so the
  // one row you compare the others against was the row you could not compare on
  // age. "built" spelled out, matching the comp cards exactly.
  if (s.year_built_label) bits.push(__('built {0}', [s.year_built_label]))
  if (s.property_type) bits.push(s.property_type)
  return bits.join(' · ') || __('No details on file')
})

const lastSale = computed(() => props.subject?.last_sale || null)

function money(v) {
  const n = Number(v)
  return n ? '$' + Math.round(n).toLocaleString() : '—'
}

function fmtDate(v) {
  if (!v) return ''
  const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})/)
  const d = m ? new Date(+m[1], +m[2] - 1, +m[3]) : new Date(v)
  if (isNaN(d)) return ''
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}
</script>
