<template>
  <Dialog
    v-model="show"
    :options="{ size: pane === 'desk' ? '7xl' : '5xl', title: item?.lead_name || __('Lead details') }"
  >
    <template #body>
      <div class="flex h-[88vh] max-h-[88vh] flex-col overflow-hidden bg-surface-modal">
        <div class="flex items-start justify-between gap-4 border-b px-5 py-4 sm:px-6">
          <div class="min-w-0">
            <div class="mb-1 flex flex-wrap items-center gap-2">
              <Badge
                v-if="item?.lead_status"
                variant="subtle"
                theme="gray"
                :label="item.lead_status"
              />
              <Badge
                v-if="item?.total_calls > 1"
                variant="subtle"
                theme="blue"
                :label="__('Call {0} of {1}', [item.call_number, item.total_calls])"
              />
            </div>
            <h2 class="truncate text-2xl font-semibold text-ink-gray-9">
              {{ item?.lead_name || __('Lead details') }}
            </h2>
          </div>
          <Button variant="ghost" icon="x" class="shrink-0" @click="show = false" />
        </div>

        <div class="flex min-h-0 flex-1 flex-col md:flex-row">
          <!-- Hidden on the desk, and that is the point of the desk: its own rail
               already carries the 2x2, and the map needs every pixel this aside
               would take. The card context that matters mid-call (status, call N
               of M, why today) is in the header above, where it stays visible on
               every pane. -->
          <aside
            v-show="pane !== 'desk'"
            class="max-h-[42vh] shrink-0 overflow-y-auto border-b p-4 md:max-h-none md:w-72 md:border-b-0 md:border-r sm:p-5"
          >
            <div class="flex flex-col gap-2 text-sm text-ink-gray-6">
              <a
                v-if="item?.mobile_no"
                :href="callHref(item.mobile_no)"
                class="w-fit text-ink-blue-3 hover:underline"
              >
                {{ formatPhone(item.mobile_no) }}
              </a>
              <button
                v-if="item?.address"
                class="text-left hover:text-ink-blue-3 hover:underline"
                @click="emit('openAddress', item.address)"
              >
                {{ item.address }}
              </button>
              <a
                v-if="item?.email"
                :href="`mailto:${item.email}`"
                class="w-fit hover:text-ink-gray-8 hover:underline"
              >
                {{ item.email }}
              </a>
            </div>

            <div
              v-if="item?.reason"
              class="mt-4 rounded-lg border border-outline-gray-1 bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-6"
            >
              <div class="mb-0.5 text-xs font-medium text-ink-gray-8">
                {{ __('Why today') }}
              </div>
              {{ item.reason }}
            </div>

            <!-- The exact same editable 2×2 used on the full Lead page. Keeping
                 one component means a Today answer immediately becomes the lead's
                 durable First-Call Read rather than modal-only state. -->
            <div v-if="leadDoc && item?.lead" class="-mx-4 mt-4 sm:-mx-5">
              <FirstCallReadCard
                :lead="item.lead"
                :motivated="leadDoc.first_call_motivated"
                :on-price="leadDoc.first_call_on_price"
                :set-by="leadDoc.first_call_by"
                :set-at="leadDoc.first_call_at"
                @saved="loadLead(true)"
              />
            </div>
            <div
              v-else-if="leadLoading"
              class="mt-4 h-52 animate-pulse rounded-lg bg-surface-gray-2"
            />
          </aside>

          <!-- Activity and the comps MAP are peers here, not a strip stacked above
               a feed. The horizontal card list this replaced could show eight
               comps with no sense of where any of them were, which is the one
               thing that decides whether a sale is comparable; the map answers
               that first and carries the filters, recency fade, hide/use and
               photos with it. Both panes stay mounted, so switching costs neither
               a refetch nor the Activity scroll position, and Activity keeps the
               lead page's ACTUAL surface — calls, texts, to-dos and realtime
               behave exactly as they do there. -->
          <div class="flex min-h-0 flex-1 flex-col overflow-hidden bg-surface-white">
            <div class="flex shrink-0 items-center gap-4 border-b px-5 sm:px-6">
              <button
                v-for="p in panes"
                :key="p.value"
                class="-mb-px whitespace-nowrap border-b-2 py-2.5 text-base transition"
                :class="
                  pane === p.value
                    ? 'border-outline-gray-5 font-medium text-ink-gray-9'
                    : 'border-transparent text-ink-gray-5 hover:text-ink-gray-7'
                "
                @click="pane = p.value"
              >
                {{ p.label }}
              </button>
              <!-- Underwriting deliberately lives only on the full page, so the way
                   to it has to be visible from here rather than remembered. -->
              <Button
                v-if="pane === 'comps' && item?.lead"
                class="ml-auto"
                variant="ghost"
                :label="__('Open comps page')"
                @click="openCompsPage"
              >
                <template #suffix>
                  <FeatherIcon name="arrow-up-right" class="size-4" />
                </template>
              </Button>
            </div>

            <div
              v-show="pane === 'activity'"
              class="flex min-h-0 flex-1 flex-col overflow-hidden"
            >
              <Activities
                v-if="show && item?.lead"
                :key="item.lead"
                v-model:tabIndex="tabIndex"
                doctype="CRM Lead"
                :docname="item.lead"
                :tabs="tabs"
                :scroll-on-mount="false"
              />
            </div>

            <!-- Mounted only once the pane has actually been opened: comps cost a
                 server round trip and, on a lead we have not looked up before, a
                 billed Zillow lookup. Nobody should pay that for a lead they only
                 opened to read the timeline. -->
            <div
              v-if="compsOpened && show && item?.lead"
              v-show="pane === 'comps'"
              class="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5"
            >
              <CompsView :key="item.lead" :lead="item.lead" :address="item.address" />
            </div>

            <!-- THE DESK. This is the screen a Today card opens: the same comps
                 map, and beside it what the comps MEAN in money -- ARV from the
                 ticked comps, repairs, the offer, and a saved determination.
                 v17 was always a modal over the board (the mockup folder is
                 "today-leadzolo"), not a page somewhere else: a rep works a queue
                 of cards, and sending them to a different URL per card loses the
                 queue. Same components as /leads/<id>/desk, so there is one
                 implementation and not two that drift. -->
            <div
              v-if="deskOpened && show && item?.lead"
              v-show="pane === 'desk'"
              class="flex min-h-0 flex-1"
            >
              <div class="flex min-w-0 flex-1 flex-col overflow-y-auto p-4 sm:p-5">
                <CompsView
                  :key="`desk-${item.lead}`"
                  :lead="item.lead"
                  :address="item.address"
                  fill
                  neighborhood
                  @subject="onSubject"
                  @picked="onPicked"
                />
              </div>
              <OfferRail
                :lead="item.lead"
                :picked="picked"
                :subject="subject"
                :motivated="leadDoc?.first_call_motivated || ''"
                :on-price="leadDoc?.first_call_on_price || ''"
                @read-saved="loadLead(true)"
              />
            </div>
          </div>
        </div>

        <div class="flex justify-end gap-2 border-t px-5 py-3 sm:px-6">
          <Button :label="__('Close')" @click="show = false" />
          <Button variant="solid" :label="__('Open full lead')" @click="openFullLead">
            <template #suffix><FeatherIcon name="arrow-up-right" class="size-4" /></template>
          </Button>
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import Activities from '@/components/Activities/Activities.vue'
import CompsView from '@/components/CompsView.vue'
import FirstCallReadCard from '@/components/FirstCallReadCard.vue'
import OfferRail from '@/components/OfferRail.vue'
import { callHref, formatPhone } from '@/utils/phoneFormat'
import { Badge, Button, Dialog, FeatherIcon, call } from 'frappe-ui'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  item: { type: Object, default: null },
})
const emit = defineEmits(['openAddress'])

const show = defineModel({ type: Boolean })
const router = useRouter()
const tabIndex = ref(0)
const tabs = [{ name: 'Activity', label: __('Activity') }]

// Which pane is open. Deliberately NOT reset per lead, unlike the Activity tab
// below: a rep comping a run of leads is in comping mode, and dropping them back
// on the timeline at every card would make them re-click it every time.
const pane = ref('activity')
const panes = computed(() => [
  { value: 'activity', label: __('Activity') },
  { value: 'desk', label: __('Desk') },
  { value: 'comps', label: __('Comps') },
])
const compsOpened = ref(false)
const deskOpened = ref(false)
watch(pane, (v) => {
  if (v === 'comps') compsOpened.value = true
  if (v === 'desk') deskOpened.value = true
})

// The desk prices off exactly what the rep ticked on ITS map -- taken from the
// component's own emits rather than re-derived, so the rail and the map can
// never disagree about which comps produced the number.
const picked = ref([])
const subject = ref(null)
function onPicked(list) {
  picked.value = Array.isArray(list) ? list : []
}
function onSubject(s) {
  subject.value = s || null
}
// A different lead is a different price. Clearing on switch stops the rail
// showing the previous card's ARV for the moment before the new map loads.
watch(
  () => props.item?.lead,
  () => {
    picked.value = []
    subject.value = null
  },
)
const leadDoc = ref(null)
const leadLoading = ref(false)
const leadCache = new Map()
let leadRequestToken = 0

watch(
  () => props.item?.lead,
  (lead) => {
    tabIndex.value = 0
    // Never render the previous lead's answers against the new lead id while its
    // document is loading — a click in that window would save the wrong state.
    leadDoc.value = leadCache.get(lead) || null
  },
)
watch(
  () => [show.value, props.item?.lead],
  ([open]) => {
    if (open && props.item?.lead) loadLead()
  },
  { immediate: true },
)

async function loadLead(force = false) {
  const lead = props.item?.lead
  if (!lead) return
  if (!force && leadCache.has(lead)) {
    leadDoc.value = leadCache.get(lead)
    return
  }
  const token = ++leadRequestToken
  leadLoading.value = true
  try {
    const doc = await call('frappe.client.get', { doctype: 'CRM Lead', name: lead })
    if (token !== leadRequestToken) return
    leadDoc.value = doc
    leadCache.set(lead, doc)
  } catch {
    if (token === leadRequestToken && !force) leadDoc.value = null
  } finally {
    if (token === leadRequestToken) leadLoading.value = false
  }
}

function openFullLead() {
  if (!props.item?.lead) return
  show.value = false
  router.push({ name: 'Lead', params: { leadId: props.item.lead } })
}

// A new tab, matching both Lead pages: the comps page is something a rep leaves
// open beside the board, and navigating away would close the card they are on.
function openCompsPage() {
  if (!props.item?.lead) return
  const win = window.open(`/crm/leads/${props.item.lead}/comps`, '_blank')
  if (win) win.opener = null
  else router.push({ name: 'Comps', params: { leadId: props.item.lead } })
}
</script>
