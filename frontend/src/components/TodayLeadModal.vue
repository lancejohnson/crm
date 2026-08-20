<template>
  <Dialog
    v-model="show"
    :options="{ size: '5xl', title: item?.lead_name || __('Lead details') }"
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
          <aside class="max-h-[42vh] shrink-0 overflow-y-auto border-b p-4 md:max-h-none md:w-72 md:border-b-0 md:border-r sm:p-5">
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
              <!-- The comps pane is the real comps PAGE (page-mode): cash-offer
                   calc, red/yellow pins, photo tray, underwriting. Open-in-tab
                   remains for the extra room. -->
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
              class="flex min-h-0 flex-1 flex-col overflow-y-auto p-3 sm:p-4"
            >
              <!-- page-mode: same surface as /leads/:id/comps — CompOfferCalc,
                   Zillow pin colours, photo tray, underwriting. fillHeight follows
                   from pageMode so map+tray share the pane when it is wide enough;
                   when it stacks, this host scrolls. -->
              <CompsView
                :key="item.lead"
                :lead="item.lead"
                :address="item.address"
                page-mode
                :fill="false"
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
  { value: 'comps', label: __('Comps') },
])
const compsOpened = ref(false)
watch(pane, (v) => {
  if (v === 'comps') compsOpened.value = true
})
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
