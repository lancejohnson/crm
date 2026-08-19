<template>
  <div class="border-b-2 border-outline-blue-2 bg-surface-blue-1">
    <div class="relative aspect-[3/2] w-full overflow-hidden bg-surface-gray-2">
      <img
        v-if="photo && !broken"
        :src="photo"
        :alt="address"
        loading="lazy"
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
    </div>

    <div class="px-3 py-2">
      <div class="truncate text-sm font-semibold text-ink-gray-9" :title="address">
        {{ address }}
      </div>
      <div class="mt-0.5 text-xs text-ink-gray-7">{{ facts }}</div>
      <!-- What it actually SOLD for is a verified transaction and outranks every
           other number here, so it is stated separately rather than folded in
           with the estimates. -->
      <div v-if="lastSale" class="mt-1 text-xs text-ink-gray-6">
        {{ __('Last sold') }}
        <b class="text-ink-gray-8">{{ money(lastSale.price) }}</b>
        <template v-if="lastSale.date"> · {{ fmtDate(lastSale.date) }}</template>
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
import { computed, ref } from 'vue'

const props = defineProps({
  subject: { type: Object, default: null },
  address: { type: String, default: '' },
})

const SUBJECT = '#2563c9'
const broken = ref(false)

const photo = computed(() => props.subject?.cover_photo || '')

const facts = computed(() => {
  const s = props.subject || {}
  const bits = []
  // `*_label` is the interval the SOURCE named ("1000 - 2000"), never a midpoint:
  // a vague seller answer must not be rendered as precision it does not have.
  if (s.beds_label) bits.push(s.beds_label)
  if (s.baths_label) bits.push(s.baths_label)
  if (s.sqft_label) bits.push(s.sqft_label)
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
