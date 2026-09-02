<template>
  <!-- Only exists to disagree: the server sends `redfin_check` as null when the
       check did not run, found no Redfin row, or the two sources agree, so this
       renders nothing in the common case. Amber, not red — it is a "verify
       before pricing" nudge, not an error. -->
  <div
    v-if="rows.length"
    class="mt-1 rounded border border-outline-amber-2 bg-surface-amber-1 px-1.5 py-1 text-2xs text-ink-amber-3"
    :title="__('Zillow and Redfin disagree about this property — verify before pricing off it.')"
  >
    <div class="flex items-center gap-1 font-semibold">
      <FeatherIcon name="alert-triangle" class="size-3 shrink-0" />
      {{ __('Zillow ≠ Redfin') }}
    </div>
    <div v-for="row in rows" :key="row.field">
      {{ __('Zillow {0} · Redfin {1} {2}', [fmt(row.zillow), fmt(row.redfin), row.label]) }}
    </div>
  </div>
</template>

<script setup>
/**
 * Amber "the sources disagree" flag on the comps subject. Fed by the
 * `subject.redfin_check` field on get_lead_comps — one field, one component,
 * deliberately self-contained so it composes with whatever else lands on the
 * subject card.
 */
import { FeatherIcon } from 'frappe-ui'
import { computed } from 'vue'

const props = defineProps({
  check: { type: Object, default: null },
})

const rows = computed(() =>
  (props.check?.fields || []).filter((r) => r && r.zillow != null && r.redfin != null),
)

function fmt(v) {
  const n = Number(v)
  if (!isFinite(n)) return String(v)
  // Baths keep their half; everything else here is a whole number.
  return Number.isInteger(n) ? n.toLocaleString() : String(n)
}
</script>
