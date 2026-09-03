<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="[{ label: __('Refunds') }]" />
      <span class="text-base text-ink-gray-5">
        {{ total }} {{ total === 1 ? __('lead') : __('leads') }}
      </span>
    </template>
  </LayoutHeader>
  <div class="flex h-full overflow-x-auto">
    <div class="flex gap-2 p-3">
      <div
        v-for="col in columns"
        :key="col.name"
        class="flex w-72 min-w-72 flex-col gap-2 rounded-lg p-2.5 hover:bg-surface-gray-2"
      >
        <div class="flex items-center justify-between px-1 text-base text-ink-gray-9">
          <span class="font-medium">
            <span class="mr-1" aria-hidden="true">{{ refundDot(col.name) }}</span>
            {{ __(col.name) }}
          </span>
          <span class="text-ink-gray-5">{{ col.items.length }}</span>
        </div>
        <Draggable
          :list="col.items"
          group="refunds"
          item-key="name"
          class="flex min-h-[8rem] flex-1 flex-col gap-2"
          :delay="200"
          @change="onChange($event, col.name)"
        >
          <template #item="{ element: lead }">
            <router-link
              :to="{ name: 'Lead', params: { leadId: lead.name } }"
              class="block rounded-md border border-outline-gray-1 bg-surface-white p-3 shadow-sm hover:bg-surface-gray-1"
            >
              <div class="truncate font-medium text-ink-gray-9">
                {{ lead.lead_name || lead.name }}
              </div>
              <div class="mt-1 truncate text-sm text-ink-gray-5">
                {{ lead.source || __('No source') }}
                <template v-if="lead.lost_reason">
                  · {{ lead.lost_reason }}
                </template>
              </div>
              <div class="mt-2 flex flex-col gap-0.5 text-xs text-ink-gray-5">
                <div class="flex items-center gap-1.5">
                  <span class="w-14 shrink-0">{{ __('Owner') }}</span>
                  <span class="truncate text-ink-gray-8">
                    {{ ownerName(lead.lead_owner) }}
                  </span>
                </div>
                <div class="flex items-center gap-1.5">
                  <span class="w-14 shrink-0">{{ __('Updated') }}</span>
                  <span class="text-ink-gray-8" :title="formatDate(updatedAt(lead))">
                    {{ timeAgo(updatedAt(lead)) }}
                  </span>
                </div>
                <div class="flex items-center gap-1.5">
                  <span class="w-14 shrink-0">{{ __('Created') }}</span>
                  <span class="text-ink-gray-8" :title="formatDate(lead.creation)">
                    {{ formatDate(lead.creation, 'MMM D, YYYY') }}
                  </span>
                </div>
              </div>
              <div class="mt-2 flex items-center gap-1.5">
                <!-- The refund proof, one click from the board. A plain
                     button inside the router-link: stop + prevent so it does
                     not also open the lead. -->
                <button
                  class="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8"
                  :title="__('Download this lead\'s call history with recording links (CSV)')"
                  @click.stop.prevent="downloadCalls(lead)"
                >
                  <FeatherIcon name="download" class="size-3" />
                  {{ __('Calls') }}
                </button>
                <Badge
                  v-if="lead.custom_refund_manual_ticket"
                  variant="subtle"
                  theme="orange"
                  :label="__('Manual ticket')"
                />
                <Badge
                  v-else-if="lead.custom_refund_not_in_provider"
                  variant="subtle"
                  theme="orange"
                  :label="__('Not in provider form')"
                />
                <span
                  v-else-if="lead.custom_refund_requested"
                  class="text-xs text-ink-gray-5"
                >
                  {{ __('Requested') }}
                </span>
              </div>
            </router-link>
          </template>
        </Draggable>
      </div>
    </div>
  </div>
</template>

<script setup>
import Draggable from 'vuedraggable'
import { Badge, FeatherIcon, createListResource, call, toast, dayjs } from 'frappe-ui'
import { usersStore } from '@/stores/users'
import { formatDate, timeAgo } from '@/utils'
import { REFUND_STATUSES as STATUSES, refundDot } from '@/utils/refunds'
import { computed } from 'vue'

const { getUser } = usersStore()

// Last refund ACTION, not the lead's whole-doc `modified` (which moves for a
// status change or a note). Falls back until the ops field is provisioned.
function updatedAt(lead) {
  return lead.custom_refund_updated_on || lead.modified
}

function downloadCalls(lead) {
  window.open(
    `/api/method/crm.api.call_export.export_call_history?lead=${encodeURIComponent(lead.name)}&fmt=csv`,
    '_blank',
  )
}

function ownerName(email) {
  if (!email) return __('Unassigned')
  return getUser(email).full_name || email
}

const list = createListResource({
  doctype: 'CRM Lead',
  fields: [
    'name',
    'lead_name',
    'source',
    'lost_reason',
    'lead_owner',
    'custom_refundable',
    'custom_refund_requested',
    'custom_refund_status',
    'custom_refund_not_in_provider',
    'custom_refund_manual_ticket',
    'custom_refund_updated_on',
    'modified',
    'creation',
  ],
  filters: { custom_refundable: 1 },
  orderBy: 'custom_refund_updated_on desc, modified desc',
  pageLength: 500,
  auto: true,
})

const columns = computed(() => {
  const rows = list.data || []
  return STATUSES.map((name) => ({
    name,
    items: rows.filter((row) => statusOf(row) === name),
  }))
})

const total = computed(() => (list.data || []).length)

function statusOf(row) {
  if (STATUSES.includes(row.custom_refund_status)) return row.custom_refund_status
  return row.custom_refund_requested ? 'Requested' : 'To Request'
}

async function onChange(evt, toStatus) {
  const lead = evt.added?.element
  if (!lead || statusOf(lead) === toStatus) return
  try {
    await call('crm.api.refunds.set_refund_state', {
      lead: lead.name,
      status: toStatus,
    })
    lead.custom_refund_status = toStatus
    if (toStatus !== 'To Request') lead.custom_refund_requested = 1
    lead.custom_refund_updated_on = dayjs().format('YYYY-MM-DD HH:mm:ss')
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not move lead'))
    list.reload()
  }
}
</script>
