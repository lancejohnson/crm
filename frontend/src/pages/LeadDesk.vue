<template>
  <div class="flex h-screen flex-col overflow-hidden bg-surface-white">
    <!-- Header row: identity + the facts a rep says out loud, then actions. -->
    <div
      class="flex shrink-0 items-center gap-3 border-b px-3 py-2"
      style="border-color: var(--surface-gray-2)"
    >
      <div class="flex min-w-0 items-baseline gap-2">
        <h1 class="truncate text-base font-semibold text-ink-gray-9">
          {{ lead?.lead_name || leadId }}
        </h1>
        <span class="truncate text-sm text-ink-gray-6">
          {{ address }}
        </span>
      </div>

      <div class="flex shrink-0 items-center gap-1.5">
        <Badge
          v-for="f in facts"
          :key="f.key"
          variant="subtle"
          :label="`${f.key} ${f.value}`"
          :title="f.title"
        />
      </div>

      <div class="ml-auto flex shrink-0 items-center gap-2">
        <Button :label="__('Open lead')" iconLeft="external-link" @click="openLead" />
      </div>
    </div>

    <!-- Body. Panes flex; the desk never scrolls as a page (see script note). -->
    <div class="flex min-h-0 flex-1">
      <!-- Centre: the real comps surface, not a reimplementation. -->
      <div class="flex min-w-0 flex-1 flex-col overflow-hidden">
        <CompsView
          v-if="leadId"
          :lead="leadId"
          :address="address"
          @subject="onSubject"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * The lead desk — the single screen a rep works a live seller call from.
 *
 * Slice 1 of the port from `~/crm-mockups/today-leadzolo/v17.html`. The design
 * is settled there (layout, offer formula, the 2x2, shortcuts, Street View);
 * this is the port, not a redesign. Read docs/lead-desk/PLAN.md first.
 *
 * WHY THIS EMBEDS CompsView RATHER THAN THE MOCKUP'S MAP. v17 hand-rolled a
 * Leaflet map because a static HTML file had nothing to reuse. CompsView is
 * 1,424 lines that already solve the parts that are actually hard and were
 * learned the expensive way: the preset ladder, recency-faded pills, the
 * self-comp exclusion, hide/use state, the divIcon centring bug, and the
 * `between`-means-DATES trap. Reimplementing that from the mockup would throw
 * all of it away and re-earn the same bugs.
 *
 * `pageMode` is deliberately NOT passed. It gates the underwriting-sheet action,
 * which belongs on the standalone comps page where a rep goes to underwrite —
 * on the desk the offer is computed live in the right rail, and two competing
 * ways to price the same deal is exactly the ambiguity this screen removes.
 *
 * Desktop only, and `h-screen` rather than the app's usual scrolling layout:
 * this is a working surface on a ~1280x800 laptop, and a rep mid-call should
 * never have to scroll to find the offer.
 */
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createResource, Badge, Button } from 'frappe-ui'
import CompsView from '@/components/CompsView.vue'

const route = useRoute()
const router = useRouter()

const leadId = computed(() => route.params.leadId)

const leadResource = createResource({
  url: 'frappe.client.get',
  makeParams() {
    return { doctype: 'CRM Lead', name: leadId.value }
  },
  auto: true,
})

const lead = computed(() => leadResource.data || null)

/**
 * The subject's facts come from CompsView's `subject` emit, NOT from the lead
 * record. `get_lead_comps` merges them best-first and labels each with where it
 * came from — Zillow, then the property's own row in the comp inventory, then
 * the lead's pick-list bands, then the tax pull.
 *
 * Reading CRM Lead directly is what the first cut did, and verification caught
 * it: the header showed `YR 1900-1950` (a seller-entered band) while the map
 * pill three inches below already said 1930, and beds/baths/sqft were blank
 * because the lead's own fields were empty even though Zillow had 3/2/1444sf.
 * One screen must not show two different answers to "what is this house".
 */
const subject = ref(null)
function onSubject(s) {
  subject.value = s || null
}

/**
 * The payload shape, which is NOT what the first cut assumed. get_lead_comps
 * returns FLAT scalars with parallel sidecars, not {value, source} objects:
 *
 *   beds: 2.0, beds_label: "2", beds_exact: true,
 *   source: { beds: "zillow", baths: "zillow", ... }
 *
 * Guessing the shape produced an empty badge row, which looked like "this lead
 * has no data" rather than like a bug -- the failure mode that hides itself.
 *
 * Use the *_label the backend already formatted: it renders a real half-bath as
 * "1.5" and a vague seller answer as the band actually given ("1000 - 2000"),
 * which is precisely the distinction *_exact then lets the tooltip admit to.
 */
const FACTS = [
  ['BD', 'beds'],
  ['BA', 'baths'],
  ['SQFT', 'sqft'],
  ['YR', 'year_built'],
]

const facts = computed(() => {
  const s = subject.value
  if (!s) return []
  const src = s.source || {}
  const out = []
  for (const [key, field] of FACTS) {
    const label = s[`${field}_label`]
    if (label == null || label === '') continue
    const source = src[field] || ''
    const note = s[`${field}_exact`] === false ? ' (range, not exact)' : ''
    out.push({
      key,
      value: String(label),
      title: source ? `source: ${source}${note}` : note.trim(),
    })
  }
  return out
})

/**
 * Compose the full address the same way the comps/agreement code does: a
 * webhook lead carries the whole string in `property_address`, a hand-entered
 * one has only the street with city/state/zip in their own fields. Appending
 * unconditionally would produce "123 Main St, Olivia MN, Olivia, MN".
 */
const address = computed(() => {
  const d = lead.value
  if (!d) return ''
  const base = (d.property_address || '').trim()
  const parts = [base]
  for (const key of ['property_city', 'property_state', 'property_zip']) {
    const v = (d[key] || '').toString().trim()
    if (v && !base.toLowerCase().includes(v.toLowerCase())) parts.push(v)
  }
  return parts.filter(Boolean).join(', ')
})

function openLead() {
  router.push({ name: 'Lead', params: { leadId: leadId.value } })
}
</script>
