<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="breadcrumbs" />
    </template>
  </LayoutHeader>

  <div v-if="data" class="flex h-full overflow-hidden">
    <Tabs
      v-model="tabIndex"
      :tabs="tabs"
      class="flex flex-1 overflow-hidden flex-col [&_[role='tab']]:px-0 [&_[role='tab']]:shrink-0 [&_[role='tablist']]:px-5 [&_[role='tablist']::-webkit-scrollbar]:h-0 [&_[role='tablist']]:min-h-[45px] [&_[role='tablist']]:gap-7.5 [&_[role='tabpanel']:not([hidden])]:flex [&_[role='tabpanel']:not([hidden])]:grow"
    >
      <template #tab-panel>
        <!-- Mobile: the details that live in the desktop right rail become a
             first-class tab (the fixed-width Resizer is unusable on a phone). -->
        <div
          v-if="currentTab === 'Details'"
          class="flex flex-1 flex-col overflow-y-auto"
        >
          <BuyerDetailPanel
            ref="detailPanel"
            :data="data"
            :deals="deals"
            :buyerId="buyerId"
            @edit="showEdit = true"
            @delete="showDelete = true"
            @reload="buyer.reload()"
            @add-to-deal="showAddToDeal = true"
            @create-agreement="createAgreementFor"
          />
        </div>
        <!-- Quo conversation: live texts + CRM Call Log calls. These are
             phone-matched (not reference-linked), so they render outside the
             Activities component. -->
        <div
          v-else-if="currentTab === 'Conversation'"
          class="flex flex-1 flex-col overflow-y-auto px-3 py-4 sm:px-10"
        >
          <div class="mb-3 flex items-center gap-2 text-base font-medium text-ink-gray-8">
            {{ __('Conversation') }}
            <span v-if="timeline.length" class="text-ink-gray-4">{{ timeline.length }}</span>
            <LoadingIndicator
              v-if="conversation.loading || calls.loading"
              class="size-3.5 text-ink-gray-4"
            />
          </div>

          <div v-if="timeline.length" class="flex max-w-2xl flex-col gap-1.5">
            <template v-for="(it, i) in timeline" :key="i">
              <!-- text -->
              <div
                v-if="it.kind === 'text'"
                class="flex flex-col"
                :class="isOut(it.item) ? 'items-end' : 'items-start'"
              >
                <div
                  class="max-w-[85%] rounded-2xl px-3 py-1.5 text-sm"
                  :class="isOut(it.item) ? 'bg-blue-500 text-white' : 'bg-surface-gray-3 text-ink-gray-8'"
                >
                  <SMSMedia
                    v-if="it.item.media?.length"
                    :media="it.item.media"
                    class="my-1"
                  />
                  <span v-if="it.item.text">{{ it.item.text }}</span>
                </div>
                <div class="mt-0.5 px-1 text-xs text-ink-gray-4">
                  {{ isOut(it.item) ? it.item.line : '' }}
                  {{ formatDate(it.item.at, 'MMM D, h:mm a') }}
                </div>
              </div>
              <!-- call — the lead timeline's call card -->
              <CallArea v-else class="my-2" :activity="it.item" />
            </template>
          </div>
          <div v-else-if="!conversation.loading && !calls.loading" class="text-sm text-ink-gray-5">
            {{ __('No Quo texts or calls with this buyer yet.') }}
          </div>
        </div>

        <!-- everything else (Activity / Comments / Tasks / Notes / Attachments)
             rides the same Activities component leads and deals use -->
        <Activities
          v-else
          ref="activities"
          v-model:tabIndex="tabIndex"
          doctype="CRM Buyer"
          :docname="buyerId"
          :tabs="tabs"
        />
      </template>
    </Tabs>

    <Resizer v-if="!isMobileView" class="flex flex-col border-l" side="right">
      <BuyerDetailPanel
        ref="detailPanel"
        :data="data"
        :deals="deals"
        :buyerId="buyerId"
        @edit="showEdit = true"
        @delete="showDelete = true"
        @reload="buyer.reload()"
        @add-to-deal="showAddToDeal = true"
        @create-agreement="createAgreementFor"
      />
    </Resizer>
  </div>

  <BuyerModal v-model="showEdit" :buyer="data" @saved="buyer.reload()" />
  <AddBuyerToDealModal
    v-model="showAddToDeal"
    :buyer="buyerId"
    @saved="buyer.reload()"
  />
  <!-- Same create flow as the lead page; referenceDoc is the picked engaged
       property's lead doc (agreements are property-keyed). -->
  <CreateAgreementModal
    v-if="showCreateAgreement"
    v-model="showCreateAgreement"
    :referenceDoc="agreementLeadDoc"
    :buyer="buyerId"
    :options="{ afterCreate: onAgreementCreated }"
  />
  <DeleteLinkedDocModal
    v-if="showDelete"
    v-model="showDelete"
    doctype="CRM Buyer"
    :docname="buyerId"
    name="Buyers"
  />
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import Activities from '@/components/Activities/Activities.vue'
import Resizer from '@/components/Resizer.vue'
import BuyerModal from '@/components/Modals/BuyerModal.vue'
import AddBuyerToDealModal from '@/components/Modals/AddBuyerToDealModal.vue'
import CreateAgreementModal from '@/components/Modals/CreateAgreementModal.vue'
import BuyerDetailPanel from '@/components/BuyerDetailPanel.vue'
import DeleteLinkedDocModal from '@/components/DeleteLinkedDocModal.vue'
import CallArea from '@/components/Activities/CallArea.vue'
import SMSMedia from '@/components/Activities/SMSMedia.vue'
import ActivityIcon from '@/components/Icons/ActivityIcon.vue'
import DetailsIcon from '@/components/Icons/DetailsIcon.vue'
import CommentIcon from '@/components/Icons/CommentIcon.vue'
import TaskIcon from '@/components/Icons/TaskIcon.vue'
import NoteIcon from '@/components/Icons/NoteIcon.vue'
import AttachmentIcon from '@/components/Icons/AttachmentIcon.vue'
import PhoneIcon from '@/components/Icons/PhoneIcon.vue'
import { useActiveTabManager } from '@/composables/useActiveTabManager'
import { isMobileView } from '@/composables/settings'
import { formatDate } from '@/utils'
import {
  Breadcrumbs,
  Tabs,
  LoadingIndicator,
  createResource,
  call,
  toast,
  usePageMeta,
} from 'frappe-ui'
import { globalStore } from '@/stores/global'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const buyerId = computed(() => route.params.buyerId)
const showEdit = ref(false)
const showDelete = ref(false)
const showAddToDeal = ref(false)
const activities = ref(null)
const detailPanel = ref(null)

const buyer = createResource({
  url: 'crm.api.investorlift_ingest.get_buyer',
  makeParams: () => ({ buyer: buyerId.value }),
  auto: true,
})

const data = computed(() => buyer.data || null)
const deals = computed(() => data.value?.deals || [])

const tabs = computed(() =>
  [
    // Mobile-only: the desktop right-rail details as a tab (no fixed Resizer).
    {
      name: 'Details',
      label: __('Details'),
      icon: DetailsIcon,
      condition: () => isMobileView.value,
    },
    { name: 'Activity', label: __('Activity'), icon: ActivityIcon },
    { name: 'Conversation', label: __('Conversation'), icon: PhoneIcon },
    { name: 'Comments', label: __('Comments'), icon: CommentIcon },
    { name: 'Tasks', label: __('Tasks'), icon: TaskIcon },
    { name: 'Notes', label: __('Notes'), icon: NoteIcon },
    { name: 'Attachments', label: __('Attachments'), icon: AttachmentIcon },
  ].filter((tab) => (tab.condition ? tab.condition() : true)),
)
const { tabIndex } = useActiveTabManager(tabs, 'lastBuyerTab')
const currentTab = computed(() => tabs.value[tabIndex.value]?.name)

// live Quo texts with this buyer (calls come from CRM Call Log below)
const conversation = createResource({
  url: 'crm.api.investorlift_ingest.get_buyer_conversation',
  makeParams: () => ({ buyer: buyerId.value }),
  auto: true,
})
// CRM Call Log calls — same shape as the lead timeline's call entries
const calls = createResource({
  url: 'crm.api.buyers.get_buyer_calls',
  makeParams: () => ({ buyer: buyerId.value }),
  auto: true,
})
const timeline = computed(() => {
  const items = []
  for (const t of conversation.data?.items || []) {
    if (t.kind !== 'text') continue
    items.push({
      kind: 'text',
      item: t,
      epoch: (t.at_epoch || 0) * 1000 || Date.parse(t.at) || 0,
    })
  }
  for (const c of calls.data || []) {
    items.push({ kind: 'call', item: c, epoch: (c.at_epoch || 0) * 1000 })
  }
  return items.sort((a, b) => a.epoch - b.epoch)
})
function isOut(it) {
  return it.direction === 'outgoing'
}

// Live refresh: buyer texts are stored Quo Message rows now (webhook-mirrored),
// so the thread updates in place; crm_buyer_update fires when the Quo-contact
// pull sync changes this buyer (name/tags edited in the Quo app).
const { $socket } = globalStore()

function onQuoMessage(data) {
  if (
    data.reference_doctype === 'CRM Buyer' &&
    data.reference_docname === buyerId.value
  ) {
    conversation.reload()
  }
}
function onBuyerUpdate(data) {
  if (data.buyer === buyerId.value) buyer.reload()
}

// Activities' unmount does a blanket $socket.off('quo_message') — and it
// unmounts exactly when the Conversation tab opens — so (re)attach our
// handler on every switch into Conversation instead of only on mount.
watch(
  currentTab,
  (tab) => {
    if (tab === 'Conversation') {
      $socket.off('quo_message', onQuoMessage)
      $socket.on('quo_message', onQuoMessage)
    }
  },
  { immediate: true },
)

onMounted(() => {
  $socket.on('crm_buyer_update', onBuyerUpdate)
})
onBeforeUnmount(() => {
  $socket.off('quo_message', onQuoMessage)
  $socket.off('crm_buyer_update', onBuyerUpdate)
})

// Create a purchase agreement for one of the buyer's engaged properties:
// fetch that lead's doc (the modal prefills from property/seller fields).
const showCreateAgreement = ref(false)
const agreementLeadDoc = ref({})

async function createAgreementFor(lead) {
  try {
    agreementLeadDoc.value = await call('frappe.client.get', {
      doctype: 'CRM Lead',
      name: lead,
    })
    showCreateAgreement.value = true
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not load the property'))
  }
}

function onAgreementCreated() {
  detailPanel.value?.reloadAgreements()
}

const breadcrumbs = computed(() => [
  { label: __('Buyers'), route: { name: 'Buyers' } },
  { label: data.value?.buyer_name || __('Buyer') },
])

usePageMeta(() => ({ title: data.value?.buyer_name || 'Buyer' }))
</script>
