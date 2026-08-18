<template>
  <div class="desk">
    <!-- Header: identity, the facts a rep says out loud, then actions. Dense on
         purpose (7px/12px, 9px gaps) -- this is a working surface, and every row
         of chrome here is a row of map the rep does not get. -->
    <div class="hd">
      <div class="flex min-w-0 items-baseline gap-2">
        <h1 class="hd-name">{{ lead?.lead_name || leadId }}</h1>
        <span class="hd-ad">{{ address }}</span>
      </div>

      <!-- Facts as chips, keyed like the mockup: a 9.5px uppercase key and the
           value beside it, so four facts cost one line rather than four badges. -->
      <div class="dets">
        <span
          v-for="f in facts"
          :key="f.key"
          class="det"
          :class="{ wide: f.key === 'SQFT' }"
          :title="f.title"
        >
          <span class="dk">{{ f.key }}</span><span class="dv">{{ f.value }}</span>
        </span>
      </div>

      <div class="ml-auto flex shrink-0 items-center gap-2">
        <!-- The whole point of the desk: dial the person whose house is on the
             screen, from the screen. The softphone lives HERE rather than in the
             app shell -- a phone widget on the Settings page is a phone widget in
             the way, and this is the one surface where a call is the job. -->
        <button
          v-if="lead?.mobile_no || lead?.phone"
          class="hb call"
          @click="callLead"
        >
          <span class="ic" />Call
        </button>
        <!-- Activity is lead-level history, the same tier as the lead itself, so
             it sits with the lead-level actions rather than hiding behind an
             arrow on the window edge. -->
        <button class="hb" :class="{ on: showActivity }" @click="toggleActivity()">Activity</button>
        <button class="hb" @click="openLead">Open lead ↗</button>
      </div>
    </div>

    <!-- Body. Panes flex; the desk never scrolls as a page (see script note). -->
    <div class="relative flex min-h-0 flex-1">
      <!-- Centre: the real comps surface, not a reimplementation.

           `fill` is what makes it work here. CompsView was built as a full page:
           filter card + map + property list is ~1,010px tall, against 726px of
           body on the 1,280x800 laptop this desk is designed for, so verification
           found only 62px of the 320px list on screen -- one row -- with no way
           to wheel to the rest, because the page itself deliberately never
           scrolls. In `fill` mode the filters fold behind a toggle and the map
           and list share the height, each scrolling itself.

           The pane stays `overflow-y-auto` as a floor, not a plan: at a short
           enough window the map's 15rem minimum plus the list's 8rem eventually
           exceed the pane, and a scrollbar then is better than clipping. -->
      <div class="flex min-w-0 flex-1 flex-col overflow-y-auto">
        <CompsView
          v-if="leadId"
          :lead="leadId"
          :address="address"
          fill
          neighborhood
          @subject="onSubject"
          @picked="onPicked"
        />
      </div>

      <!-- Right rail: what the comps mean in money. -->
      <OfferRail
        v-if="leadId"
        ref="offerRail"
        :lead="leadId"
        :picked="picked"
        :subject="subject"
        :motivated="lead?.first_call_motivated || ''"
        :on-price="lead?.first_call_on_price || ''"
        @read-saved="leadResource.reload()"
        @saved="onDeterminationSaved"
      />

      <!-- The softphone renders nothing until there is a call, so it costs the
           layout nothing to have it mounted here. -->
      <TelnyxCallUI ref="phone" />

      <!-- Activity slides OVER the desk rather than taking a column of its own.
           Nothing reflows, so the map keeps its size and Leaflet keeps its
           measurement -- and the rep gets the history back out of the way with
           the same key that opened it.

           z-[1000] rather than a modest z-20, because Leaflet gives its own
           panes z-index 400-700 and `.leaflet-container` creates no stacking
           context of its own -- so those panes compete directly with this one.
           At z-20 the map PAINTED over the panel's left ~100px (the heading read
           "y" instead of "Activity") while still hit-testing as the panel
           underneath: clicks landed where the user could not see. -->
      <aside
        v-show="showActivity"
        class="absolute inset-y-0 right-0 z-[1000] flex w-[400px] flex-col border-l bg-surface-white shadow-2xl"
        style="border-color: var(--surface-gray-2)"
      >
        <div
          class="flex shrink-0 items-center gap-2 border-b px-3 py-1.5"
          style="border-color: var(--surface-gray-2)"
        >
          <span class="text-xs font-semibold uppercase tracking-wide text-ink-gray-5">
            {{ __('Activity') }}
          </span>
          <Button
            class="ml-auto"
            variant="ghost"
            icon="x"
            :title="__('Close (])')"
            @click="toggleActivity(false)"
          />
        </div>
        <!-- Mounted only once opened: the feed is six resources, and a rep who
             never opens the history should not pay for it on every lead. Kept
             mounted afterwards so reopening is instant and the scroll holds. -->
        <div v-if="activityOpened" class="flex min-h-0 flex-1 flex-col overflow-hidden">
          <Activities
            ref="activities"
            v-model:tabIndex="activityTab"
            doctype="CRM Lead"
            :docname="leadId"
            :tabs="activityTabs"
            :scroll-on-mount="false"
          />
        </div>
      </aside>
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
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createResource } from 'frappe-ui'
import CompsView from '@/components/CompsView.vue'
import OfferRail from '@/components/OfferRail.vue'
import Activities from '@/components/Activities/Activities.vue'
import TelnyxCallUI from '@/components/Telephony/TelnyxCallUI.vue'
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'
import { activeDetailPanel } from '@/composables/settings'

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

// The comps the rep ticked, straight from CompsView so the rail prices off
// exactly what is highlighted on the map — not a second derivation that could
// disagree with it.
const picked = ref([])
function onPicked(list) {
  picked.value = Array.isArray(list) ? list : []
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

const phone = ref(null)

/**
 * Dial this lead from the browser.
 *
 * The number comes from the lead record rather than being typed, which is the
 * difference between a call that is linked to the deal and one that is a row in
 * a phone bill.
 */
function callLead() {
  const number = lead.value?.mobile_no || lead.value?.phone
  if (!number) return
  phone.value?.dial(number, { name: lead.value?.lead_name || '' })
}

/**
 * The activity rail.
 *
 * This mounts the REAL `Activities.vue` -- the same timeline, quick comment box
 * and to-do quick-add the lead page and the Today modal use. A read-only feed
 * built for this screen would be a second answer to "what happened with this
 * seller", and the saved price determination lands here as a comment, so the
 * desk must show the same thing the lead page will.
 */
const showActivity = ref(false)
const activityOpened = ref(false)
const activityTab = ref(0)
const activities = ref(null)
// One tab, as in the Today modal. The unified Activity feed already merges
// calls, texts, comments, tasks and agreements newest-first, so a row of tabs on
// a 400px overlay would only add a decision to a screen that exists to remove
// them. Everything else is one click away on the lead page.
const activityTabs = [{ name: 'Activity', label: __('Activity') }]

function toggleActivity(v) {
  showActivity.value = typeof v === 'boolean' ? v : !showActivity.value
  if (showActivity.value) activityOpened.value = true
}

// `]` means "the detail panel" everywhere in this app (GlobalModals owns the
// binding; Resizer registers the lead/deal/buyer sidebars). Registering here
// keeps that one meaning rather than teaching the desk a private key.
const panelHandle = { toggle: () => toggleActivity() }
onMounted(() => (activeDetailPanel.value = panelHandle))
onBeforeUnmount(() => {
  if (activeDetailPanel.value === panelHandle) activeDetailPanel.value = null
})

const offerRail = ref(null)

// `S` saves the determination, as in v17. `skipWhenDialogOpen` is left ON here
// (unlike CompsView, which opts out because it WAS a dialog): a comp's photo
// gallery or the outcome modal being open means the rep is answering something
// else, and saving a price out from under that is not what S should do.
useKeyboardShortcuts({
  shortcuts: [{ keys: ['s', 'S'], action: () => offerRail.value?.save?.() }],
})

/**
 * A saved determination writes a Comment on the lead, so the feed has to be told
 * -- it has no listener for one. Reloading only the merged activity resource is
 * enough and avoids re-fetching the five sibling feeds.
 */
function onDeterminationSaved() {
  activities.value?.all_activities?.reload?.()
}
</script>

<style scoped>
/* Tokens from `~/crm-mockups/today-leadzolo/v17.html`, verbatim. The desk is the
   one screen with a settled visual design, and approximating it with the nearest
   Tailwind utility in twenty places is what made it look like something else. */
.desk {
  --t1: #18181a; --t2: #62636a; --t3: #9a9ba3;
  --bg: #fff; --bg1: #fbfbfc; --bg2: #f4f4f6;
  --br: #e8e8ec; --br2: #dcdce2;
  --green: #15683c;
  --rs: 5px;

  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background: var(--bg);
  font: 13px/1.5 InterVar, Inter, -apple-system, 'Segoe UI', system-ui, sans-serif;
  font-optical-sizing: auto;
  color: var(--t1);
}

.hd {
  display: flex; align-items: center; gap: 9px;
  padding: 7px 12px; border-bottom: 1px solid var(--br); flex: none;
}
.hd-name { margin: 0; font-size: 14.5px; font-weight: 600; letter-spacing: -0.01em; }
.hd-ad {
  font-size: 12px; color: var(--t2);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.dets { display: flex; align-items: center; gap: 4px; flex: none; }
.det {
  display: inline-flex; align-items: baseline; gap: 4px;
  padding: 2px 6px; border: 1px solid var(--br); border-radius: 5px;
  background: var(--bg1); font-size: 12px; font-weight: 500;
}
/* Fixed value field: hugging the content gave four chips four widths and the row
   read ragged. The mockup's are an even column. */
.det .dv { min-width: 30px; text-align: right; }
.det.wide .dv { min-width: 46px; }
.det .dk { font-size: 9.5px; font-weight: 500; text-transform: uppercase; color: var(--t3); }

.hb {
  height: 26px; padding: 0 9px; border: 1px solid var(--br2); border-radius: var(--rs);
  background: var(--bg); color: var(--t1); font-size: 12px; font-weight: 500;
  display: inline-flex; align-items: center; gap: 5px; cursor: pointer; white-space: nowrap;
}
.hb:hover { background: var(--bg2); }
.hb.on { background: var(--bg2); border-color: var(--t3); }
.hb.call { background: var(--green); border-color: var(--green); color: #fff; }
.hb.call:hover { filter: brightness(1.08); }
.hb .ic { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
</style>
