<template>
  <span v-if="badges.length" class="inline-flex flex-wrap items-center gap-1">
    <span
      v-for="b in badges"
      :key="b.buyer"
      :title="tooltip(b)"
      class="inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold leading-none"
      :class="chipClass(b)"
    >
      <component :is="b.buyer === 'nw' ? NewWesternMark : KeyGleeMark" class="h-2.5 w-auto" />
      <span class="max-w-20 truncate">{{ label(b) }}</span>
    </span>
  </span>
</template>

<script setup>
import NewWesternMark from '@/components/Icons/NewWesternMark.vue'
import KeyGleeMark from '@/components/Icons/KeyGleeMark.vue'
import { computed } from 'vue'

const props = defineProps({
  // The server's `_dispo_buyers` pseudo-field: null when neither buyer covers
  // this lead's area, so most cards render nothing at all.
  value: { type: [Array, Object, String], default: null },
})

const badges = computed(() => {
  const v = props.value
  if (!v) return []
  if (Array.isArray(v)) return v
  // Kanban rows arrive through parseRows, which can stringify a value on the
  // way. Tolerate both rather than depending on which path fed us.
  if (typeof v === 'string') {
    try {
      const parsed = JSON.parse(v)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }
  return []
})

// FILLED = the company's own claim about where it buys. OUTLINED = ours.
//
// The two levels stay visually distinct on purpose, which is the same rule the
// source data keeps: New Western publishes a city list, and a lead merely in the
// same county as a listed city is us guessing at their metro buy box. One badge
// for both would quietly promote a guess to a fact.
function chipClass(b) {
  if (!b.strong) return 'border border-outline-gray-2 text-ink-gray-5'
  return b.buyer === 'nw'
    ? 'bg-[#fbf6ec] text-[#8a6a33]'
    : 'bg-[#ecf7fa] text-[#0f6f87]'
}

function label(b) {
  if (b.buyer === 'kg' && !b.strong) return `${b.market} sold out`
  if (b.buyer === 'nw' && !b.strong) return `${b.market} area`
  return b.market
}

// Say which kind of claim this is, in words, because the colour alone cannot.
function tooltip(b) {
  const market = b.market || ''
  if (b.buyer === 'nw') {
    if (b.status === 'Yes - NW city')
      return __('New Western lists this city in their {0} market.', [market])
    if (b.status === 'Yes - NW market')
      return __(
        'New Western runs a {0} office covering this area, though this city is not on their published list.',
        [market],
      )
    return __(
      'New Western does not list this city, but they buy elsewhere in this county ({0} market). Our inference, not their claim.',
      [market],
    )
  }
  if (b.status === 'Sold out - KG')
    return __(
      "KeyGlee's {0} territory is sold out — the area is taken, but no franchise is trading there today.",
      [market],
    )
  return __(
    'KeyGlee has an operating franchise in {0}, which covers this county. Their territory is drawn wider than the metro, so this is the conservative read.',
    [market],
  )
}
</script>
