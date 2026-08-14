<template>
  <Dialog
    v-model="show"
    :options="{ size: '5xl', title: leadDoc?.lead_name || __('Lead') }"
  >
    <template #body>
      <div
        class="flex h-[88vh] max-h-[88vh] flex-col overflow-hidden bg-surface-modal"
      >
        <div
          class="flex items-start justify-between gap-4 border-b px-5 py-4 sm:px-6"
        >
          <div class="flex min-w-0 items-center gap-3">
            <Avatar
              v-if="leadDoc"
              :image="leadDoc.image"
              :label="leadDoc.lead_name || leadId"
              size="xl"
            />
            <div class="min-w-0">
              <div class="mb-1 flex flex-wrap items-center gap-2">
                <!-- Status reads as a coloured dot + label, the same idiom the
                     Kanban card title and the Today card use. Deliberately not a
                     Badge: `getLeadStatus().color` is a CSS class for
                     IndicatorIcon ("text-red-500"), not one of Badge's themes,
                     so feeding it to :theme silently renders the wrong colour. -->
                <span
                  v-if="leadDoc?.status"
                  class="flex items-center gap-1.5 text-sm text-ink-gray-7"
                >
                  <IndicatorIcon :class="statusColor" />
                  {{ leadDoc.status }}
                </span>
                <span
                  v-if="ownerName"
                  class="truncate text-xs text-ink-gray-5"
                >
                  {{ ownerName }}
                </span>
              </div>
              <h2 class="truncate text-2xl font-semibold text-ink-gray-9">
                {{ leadDoc?.lead_name || __('Loading…') }}
              </h2>
            </div>
          </div>

          <div class="flex shrink-0 items-center gap-2">
            <!--
              A real <router-link>, not a button that calls router.push. This is
              the escape hatch to the full record, so cmd/middle-click has to be
              able to put it in a background tab and leave the board exactly
              where it is -- which is the entire reason this modal exists. A
              button would swallow that.
            -->
            <router-link :to="fullLeadRoute" class="shrink-0">
              <Button variant="solid" :label="__('Open full lead')">
                <template #suffix>
                  <FeatherIcon name="arrow-up-right" class="size-4" />
                </template>
              </Button>
            </router-link>
            <Button variant="ghost" icon="x" @click="show = false" />
          </div>
        </div>

        <div class="flex min-h-0 flex-1 flex-col md:flex-row">
          <aside
            class="max-h-[42vh] shrink-0 overflow-y-auto border-b p-4 sm:p-5 md:max-h-none md:w-72 md:border-b-0 md:border-r"
          >
            <div class="flex flex-col gap-2 text-sm text-ink-gray-6">
              <a
                v-if="leadDoc?.mobile_no"
                :href="callHref(leadDoc.mobile_no)"
                class="w-fit text-ink-blue-3 hover:underline"
              >
                {{ formatPhone(leadDoc.mobile_no) }}
              </a>
              <a
                v-if="leadDoc?.property_address"
                :href="mapsUrl(leadDoc.property_address)"
                target="_blank"
                rel="noopener"
                class="text-left hover:text-ink-blue-3 hover:underline"
              >
                {{ leadDoc.property_address }}
              </a>
              <a
                v-if="leadDoc?.email"
                :href="`mailto:${leadDoc.email}`"
                class="w-fit hover:text-ink-gray-8 hover:underline"
              >
                {{ leadDoc.email }}
              </a>
            </div>

            <!-- The same editable 2x2 the full Lead page and the Today modal
                 mount. One component means an answer given here is the lead's
                 durable First-Call Read, not modal-only state. -->
            <div v-if="leadDoc" class="-mx-4 mt-4 sm:-mx-5">
              <FirstCallReadCard
                :lead="leadId"
                :motivated="leadDoc.first_call_motivated"
                :on-price="leadDoc.first_call_on_price"
                :set-by="leadDoc.first_call_by"
                :set-at="leadDoc.first_call_at"
                @saved="loadLead(true)"
              />
            </div>
          </aside>

          <!-- The lead page's ACTUAL activity surface, not a lookalike: same
               timeline, same to-do quick-add, same quick comments, same realtime.
               scrollOnMount=false keeps the pinned To-do block in view instead of
               the Lead page's normal mount-scroll hiding it, exactly as the Today
               modal does. -->
          <div
            class="flex min-h-0 flex-1 flex-col overflow-hidden bg-surface-white"
          >
            <Activities
              v-if="show && leadId"
              :key="leadId"
              v-model:tabIndex="tabIndex"
              doctype="CRM Lead"
              :docname="leadId"
              :tabs="tabs"
              :scroll-on-mount="false"
            />
          </div>
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import Activities from '@/components/Activities/Activities.vue'
import FirstCallReadCard from '@/components/FirstCallReadCard.vue'
import { callHref, formatPhone } from '@/utils/phoneFormat'
import { mapsUrl } from '@/utils/propertyLinks'
import IndicatorIcon from '@/components/Icons/IndicatorIcon.vue'
import { usersStore } from '@/stores/users'
import { statusesStore } from '@/stores/statuses'
import { Avatar, Button, Dialog, FeatherIcon, call } from 'frappe-ui'
import { computed, ref, watch } from 'vue'

const props = defineProps({
  leadId: { type: String, default: '' },
})

const show = defineModel({ type: Boolean })

const tabIndex = ref(0)
const tabs = [{ name: 'Activity', label: __('Activity') }]

const { getUser } = usersStore()
const { getLeadStatus } = statusesStore()

const leadDoc = ref(null)
// Cache by lead id. Clicking around a board revisits the same handful of cards,
// and re-fetching a document we already hold just to redraw a header is the sort
// of thing that makes a "quick" view feel slower than the page it replaced.
const leadCache = new Map()
let requestToken = 0

const ownerName = computed(
  () => getUser(leadDoc.value?.lead_owner)?.full_name || '',
)

// Guarded: getLeadStatus() dereferences leadStatuses.data[0] when handed a
// falsy name, which throws on a board rendered before the statuses resource has
// resolved.
const statusColor = computed(() => {
  const status = leadDoc.value?.status
  if (!status) return 'text-ink-gray-4'
  return getLeadStatus(status)?.color || 'text-ink-gray-4'
})

const fullLeadRoute = computed(() => ({
  name: 'Lead',
  params: { leadId: props.leadId },
}))

watch(
  () => props.leadId,
  (lead) => {
    tabIndex.value = 0
    // Never leave the previous lead's details on screen under a new lead's id.
    // FirstCallReadCard writes against `leadId`, so a click in that window would
    // save one lead's answer onto another.
    leadDoc.value = leadCache.get(lead) || null
  },
)

watch(
  () => [show.value, props.leadId],
  ([open]) => {
    if (open && props.leadId) loadLead()
  },
  { immediate: true },
)

async function loadLead(force = false) {
  const lead = props.leadId
  if (!lead) return
  if (!force && leadCache.has(lead)) {
    leadDoc.value = leadCache.get(lead)
    return
  }
  const token = ++requestToken
  try {
    const doc = await call('frappe.client.get', {
      doctype: 'CRM Lead',
      name: lead,
    })
    // A slower earlier request must not overwrite a newer lead's document.
    if (token !== requestToken) return
    leadDoc.value = doc
    leadCache.set(lead, doc)
  } catch (e) {
    if (token === requestToken && !force) leadDoc.value = null
  }
}
</script>
