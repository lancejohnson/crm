<template>
  <LayoutHeader>
    <template #left-header>
      <div class="flex items-center gap-2">
        <span class="text-lg font-semibold text-ink-gray-8">{{ __('Today') }}</span>
        <Badge v-if="board.data?.date" variant="subtle" theme="gray" :label="prettyDate" />
        <!-- Whose board this is belongs next to the title, not in Filters: it
             says what you are looking at rather than narrowing it. -->
        <Dropdown :options="ownerOptions" placement="bottom-start">
          <Button :variant="viewingOwnBoard ? 'ghost' : 'subtle'" :theme="viewingOwnBoard ? 'gray' : 'blue'" icon-right="chevron-down">
            <span class="max-w-[12rem] truncate">{{ ownerLabel }}</span>
          </Button>
        </Dropdown>
      </div>
    </template>
    <template #right-header>
      <div class="flex flex-wrap items-center justify-end gap-2">
        <Dropdown :options="filterOptions" placement="bottom-end">
          <Button
            :label="activeFilterCount ? __('Filters ({0})', [activeFilterCount]) : __('Filters')"
            :variant="activeFilterCount ? 'subtle' : undefined"
            :theme="activeFilterCount ? 'blue' : 'gray'"
            icon-right="chevron-down"
          >
            <template #prefix><FeatherIcon name="filter" class="size-4" /></template>
          </Button>
        </Dropdown>
        <Button :label="streakLabel" @click="openTodayReport" />
        <Button :label="__('Priority')" @click="showPriorityModal = true">
          <template #prefix><FeatherIcon name="list" class="size-4" /></template>
        </Button>
        <Badge
          v-if="toCallCount"
          variant="subtle"
          theme="blue"
          :label="`${toCallLeadCount} ${toCallLeadCount === 1 ? __('lead') : __('leads')} · ${callsOwed} ${callsOwed === 1 ? __('call') : __('calls')}`"
        />
        <!-- "All clear" has to mean you FINISHED, not that you were never given
             anything: with the board scoped per person, a rep who owns no leads
             would otherwise get the same congratulatory badge as one who worked
             through 40 cards. -->
        <Badge
          v-else-if="boardCardCount"
          variant="subtle"
          theme="green"
          :label="__('All clear')"
        />
        <Badge
          v-else
          variant="subtle"
          theme="gray"
          :label="viewingOwnBoard ? __('No leads on your board') : __('No leads on this board')"
        />
        <Tooltip
          :text="__('Re-run the cadence now and add any newly-due leads or tasks')"
          placement="bottom"
        >
          <Button :label="__('Sync list')" :loading="refreshing" @click="syncList">
            <template #prefix><RefreshIcon class="h-4 w-4" /></template>
          </Button>
        </Tooltip>
        <Badge
          v-if="syncStatus"
          variant="subtle"
          :theme="syncStatusTheme"
          :label="syncStatus"
          role="status"
        />
      </div>
    </template>
  </LayoutHeader>

  <div v-if="board.data && !board.data.available" class="flex h-full items-center justify-center">
    <div class="text-center text-ink-gray-5">
      <p class="text-base">{{ __('The Today board is not set up on this site yet.') }}</p>
      <p class="mt-1 text-sm">{{ __('Run scripts/setup_today_board.py from the ops repo.') }}</p>
    </div>
  </div>

  <div v-else class="flex flex-1 gap-3 overflow-x-auto p-4">
    <div
      v-for="col in columns"
      :key="col.state"
      class="flex min-w-[17rem] flex-1 basis-0 flex-col rounded-lg bg-surface-gray-1"
    >
      <div class="flex items-center justify-between px-3 py-2">
        <div class="flex items-center gap-2">
          <div class="h-2 w-2 rounded-full" :class="dotClass(col.state)" />
          <span class="text-sm font-medium text-ink-gray-8">{{ __(col.state) }}</span>
          <span class="text-xs text-ink-gray-5">{{ col.items.length }}</span>
        </div>
      </div>

      <!-- `change` rather than `end`: it names the destination column and hands
           back the moved card, which is what decides whether the outcome modal
           has to open before anything is persisted. -->
      <Draggable
        v-model="col.items"
        :group="'today'"
        item-key="name"
        class="flex min-h-[6rem] flex-1 flex-col gap-2 overflow-y-auto px-2 pb-3"
        @change="onChange($event, col)"
      >
        <template #item="{ element: item }">
          <div
            class="group relative cursor-pointer rounded-lg bg-surface-white p-3 shadow-sm ring-1 ring-outline-gray-1 hover:ring-outline-gray-3"
            @click="openTodayItem(item)"
          >
            <div
              class="absolute right-2 top-2 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
              @click.stop
            >
              <Tooltip v-if="item.state !== 'Done'" :text="__('Done')">
                <button
                  class="flex size-7 items-center justify-center rounded-md hover:bg-surface-gray-2"
                  @click.stop="requestState(item, 'Done')"
                >
                  <CheckIcon class="size-4 text-ink-green-3" />
                </button>
              </Tooltip>
              <Tooltip v-if="item.state !== 'Skipped'" :text="__('Skip for today')">
                <button
                  class="flex size-7 items-center justify-center rounded-md hover:bg-surface-gray-2"
                  @click.stop="requestState(item, 'Skipped')"
                >
                  <BanIcon class="size-4 text-ink-gray-5" />
                </button>
              </Tooltip>
              <Tooltip v-if="item.state !== 'To Call'" :text="__('Put back')">
                <button
                  class="flex size-7 items-center justify-center rounded-md hover:bg-surface-gray-2"
                  @click.stop="requestState(item, 'To Call')"
                >
                  <UndoIcon class="size-4 text-ink-gray-5" />
                </button>
              </Tooltip>
            </div>

            <div class="min-w-0 pr-16">
              <div
                class="truncate text-base font-medium text-ink-gray-8"
                :class="item.state === 'Skipped' ? 'line-through opacity-60' : ''"
              >
                {{ item.lead_name }}
              </div>
              <button
                v-if="item.address"
                class="mt-0.5 block max-w-full truncate text-left text-xs text-ink-gray-5 hover:text-ink-blue-3 hover:underline"
                :title="item.address"
                @click.stop="openAddress(item.address)"
              >
                {{ item.address }}
              </button>
              <div v-else class="mt-0.5 text-xs text-ink-gray-5">—</div>
              <div v-if="item.mobile_no" class="mt-0.5 flex items-center gap-1.5">
                <a
                  :href="callHref(item.mobile_no)"
                  class="w-fit text-xs text-ink-blue-3 hover:underline"
                  @click.stop
                >
                  {{ formatPhone(item.mobile_no) }}
                </a>
                <Tooltip :text="__('Send text')">
                  <button
                    class="flex size-6 items-center justify-center rounded text-ink-blue-3 hover:bg-surface-blue-1"
                    @click.stop="openText(item)"
                  >
                    <FeatherIcon name="message-square" class="size-3.5" />
                  </button>
                </Tooltip>
              </div>
            </div>

            <div class="mt-2 flex flex-wrap items-center gap-1.5">
              <Badge
                v-if="PHASE[item.priority_key]"
                variant="subtle"
                :theme="PHASE[item.priority_key].theme"
                :label="__(PHASE[item.priority_key].label)"
              />
              <div @click.stop>
                <Dropdown
                  :options="leadStatusOptions(item)"
                  placement="bottom-start"
                >
                  <button
                    class="flex h-6 max-w-[12rem] items-center gap-1 rounded-full bg-surface-gray-2 px-2 text-xs font-medium text-ink-gray-7 hover:bg-surface-gray-3 disabled:cursor-wait disabled:opacity-60"
                    :disabled="savingStatusLeads.includes(item.lead)"
                    :title="__('Change lead status')"
                    @click.stop
                  >
                    <IndicatorIcon
                      v-if="getLeadStatus(item.lead_status)"
                      class="size-3 shrink-0"
                      :class="getLeadStatus(item.lead_status).color"
                    />
                    <span class="truncate">{{ item.lead_status || __('Set status') }}</span>
                    <FeatherIcon name="chevron-down" class="size-3 shrink-0 text-ink-gray-5" />
                  </button>
                </Dropdown>
              </div>
              <span class="text-xs text-ink-gray-5">
                {{ item.calls_today }} {{ __('logged today') }}
              </span>
            </div>

            <Tooltip
              v-if="item.last_incoming_text"
              :text="formatDate(item.last_incoming_text, 'ddd, MMM D, YYYY | hh:mm a')"
            >
              <div class="mt-2 flex w-fit items-center gap-1 rounded bg-surface-green-1 px-1.5 py-1 text-xs font-medium text-ink-green-3">
                <FeatherIcon name="flag" class="size-3.5" />
                {{ __('Texted us {0}', [__(timeAgo(item.last_incoming_text))]) }}
              </div>
            </Tooltip>

            <!-- The circle is its own hit target (tick/untick without leaving the
                 board); the rest of the row opens the lead's to-do list, where
                 this task can be edited AND more can be added — rather than a
                 single-task dialog that can only ever edit the one you clicked. -->
            <div
              v-if="item.task"
              class="mt-2 flex w-full items-center gap-1.5 rounded-md border border-outline-gray-1 bg-surface-gray-1 px-2 py-1.5 hover:border-outline-gray-3"
              @click.stop
            >
              <Tooltip
                :text="item.task.is_completed ? __('Mark as not done') : __('Mark as done')"
              >
                <button
                  class="flex shrink-0 items-center rounded disabled:cursor-wait disabled:opacity-60"
                  :disabled="togglingTasks.includes(item.task.name)"
                  @click.stop="toggleTask(item)"
                >
                  <FeatherIcon
                    :name="item.task.is_completed ? 'check-circle' : 'circle'"
                    class="size-3.5"
                    :class="
                      item.task.is_completed
                        ? 'text-ink-green-3'
                        : 'text-ink-gray-4 hover:text-ink-green-3'
                    "
                  />
                </button>
              </Tooltip>
              <!-- native `title` rather than <Tooltip>: Tooltip renders a wrapper
                   element, which would become the flex child and break the
                   truncating `min-w-0 flex-1` title on a narrow card. -->
              <button
                class="flex min-w-0 flex-1 items-center gap-1.5 text-left hover:opacity-80"
                :title="__('Open to-dos — edit this one or add more')"
                @click.stop="openTodayItem(item)"
              >
                <span
                  class="min-w-0 flex-1 truncate text-xs font-medium text-ink-gray-7"
                  :class="item.task.is_completed ? 'line-through opacity-60' : ''"
                >
                  {{ item.task.title }}
                </span>
                <span
                  v-if="item.task.completed_at || item.task.due_date"
                  class="shrink-0 text-xs text-ink-gray-5"
                >
                  {{
                    __(
                      timeAgo(
                        item.task.is_completed ? item.task.completed_at : item.task.due_date,
                      ),
                    )
                  }}
                </span>
              </button>
            </div>

            <!-- What the rep said when they resolved the card, kept on the card so
                 a wrong answer is visible (and fixable) rather than write-only. -->
            <div v-if="item.outcome || item.outcome_note" class="mt-2 flex flex-wrap items-center gap-1.5">
              <Badge
                v-if="item.outcome"
                variant="subtle"
                :theme="item.outcome === 'Booked an Appointment' ? 'green' : 'gray'"
                :label="__(item.outcome)"
              />
              <span
                v-if="item.outcome_note"
                class="min-w-0 flex-1 truncate text-xs text-ink-gray-5"
                :title="item.outcome_note"
              >
                {{ item.outcome_note }}
              </span>
            </div>

            <div v-if="item.reason" class="mt-1 truncate text-xs text-ink-gray-5">
              {{ item.reason }}
            </div>
          </div>
        </template>
      </Draggable>
    </div>
  </div>

  <TodayLeadModal
    v-model="showLeadModal"
    :item="selectedItem"
    @open-address="openAddress"
  />
  <LostReasonModal
    v-if="showLostReasonModal"
    v-model="showLostReasonModal"
    doctype="CRM Lead"
    :status="pendingLeadStatus?.status"
    :on-confirm="confirmLostStatus"
    :on-cancel="cancelLostStatus"
  />
  <PropertyLinkModal v-model="showPropertyLinkModal" :address="selectedAddress" />
  <TodayOutcomeModal
    v-model="showOutcomeModal"
    :item="pendingOutcome?.item"
    :state="pendingOutcome?.state || 'Done'"
    :saving="savingOutcome"
    @confirm="confirmOutcome"
  />
  <TodayReportModal
    v-model="showReportModal"
    :report="todayReport.data"
    :loading="todayReport.loading"
  />
  <TodayPriorityModal
    v-model="showPriorityModal"
    :priorities="priorityItems"
    :saving="savingPriority"
    @save="savePriorityOrder"
  />
  <SendTextModal
    v-if="showTextModal"
    v-model="showTextModal"
    :reference-doc="textReferenceDoc"
    doctype="CRM Lead"
    show-outcome-actions
    :options="{ afterInsert: () => board.reload() }"
    @finish="finishTextItem"
    @skip="skipTextItem"
  />
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import RefreshIcon from '@/components/Icons/RefreshIcon.vue'
import TodayLeadModal from '@/components/TodayLeadModal.vue'
import TodayPriorityModal from '@/components/TodayPriorityModal.vue'
import TodayReportModal from '@/components/TodayReportModal.vue'
import IndicatorIcon from '@/components/Icons/IndicatorIcon.vue'
import LostReasonModal from '@/components/Modals/LostReasonModal.vue'
import PropertyLinkModal from '@/components/Modals/PropertyLinkModal.vue'
import SendTextModal from '@/components/Modals/SendTextModal.vue'
import TodayOutcomeModal from '@/components/Modals/TodayOutcomeModal.vue'
import { globalStore } from '@/stores/global'
import { sessionStore } from '@/stores/session'
import { statusesStore } from '@/stores/statuses'
import { formatDate, timeAgo } from '@/utils'
import { callHref, formatPhone } from '@/utils/phoneFormat'
import {
  Badge,
  Button,
  Dropdown,
  FeatherIcon,
  Tooltip,
  call,
  createResource,
  toast,
} from 'frappe-ui'
import Draggable from 'vuedraggable'
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const { $socket } = globalStore()
const { statusOptions, getLeadStatus } = statusesStore()
const { user: sessionUser } = sessionStore()

// Whose board is on screen. Deliberately NOT persisted across reloads: the
// board is the list you work from, and silently reopening on a teammate's list
// is the one mistake here that costs real calls. Switching is one click.
const ALL_OWNERS = 'all'
const selectedOwner = ref(sessionUser)
const refreshing = ref(false)
const syncStatus = ref('')
const syncStatusTheme = ref('green')
const selectedStatus = ref('')
const selectedPriority = ref('')
const selectedSignal = ref('')
const selectedItem = ref(null)
const showLeadModal = ref(false)
const savingStatusLeads = ref([])
const pendingLeadStatus = ref(null)
const showLostReasonModal = ref(false)
const selectedAddress = ref('')
const showPropertyLinkModal = ref(false)
const showReportModal = ref(false)
const showPriorityModal = ref(false)
const savingPriority = ref(false)
const togglingTasks = ref([])
const selectedTextItem = ref(null)
const showTextModal = ref(false)
// The card waiting on an answer before its state is written. Holds the
// destination column when the move came from a drag, because vuedraggable has
// already moved the card and a cancel has to put it back.
const pendingOutcome = ref(null)
const showOutcomeModal = ref(false)
const savingOutcome = ref(false)

const CheckIcon = () =>
  h('svg', { viewBox: '0 0 20 20', fill: 'none', stroke: 'currentColor', 'stroke-width': '2' }, [
    h('path', { d: 'M4 10.5l4 4 8-8', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }),
  ])
const BanIcon = () =>
  h('svg', { viewBox: '0 0 20 20', fill: 'none', stroke: 'currentColor', 'stroke-width': '2' }, [
    h('circle', { cx: '10', cy: '10', r: '7' }),
    h('path', { d: 'M5 5l10 10', 'stroke-linecap': 'round' }),
  ])
const UndoIcon = () =>
  h('svg', { viewBox: '0 0 20 20', fill: 'none', stroke: 'currentColor', 'stroke-width': '2' }, [
    h('path', {
      d: 'M8 5L4 9l4 4M4 9h8a4 4 0 010 8h-1',
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
    }),
  ])

const PHASE = {
  never: { label: 'Never called', theme: 'red', defaultOrder: 0 },
  task: { label: 'Task due', theme: 'green', defaultOrder: 1 },
  week1_am: { label: 'Week 1 · morning', theme: 'orange', defaultOrder: 2 },
  week1_pm: { label: 'Week 1 · afternoon', theme: 'orange', defaultOrder: 3 },
  weekly: { label: 'Weekly', theme: 'blue', defaultOrder: 4 },
  monthly: { label: 'Monthly', theme: 'gray', defaultOrder: 5 },
}
const DEFAULT_PRIORITY_ORDER = Object.keys(PHASE)

const board = createResource({
  url: 'crm.api.today_board.get_today_board',
  auto: true,
  cache: 'today_board',
})
const todayReport = createResource({
  url: 'crm.api.today_board.get_today_report',
  auto: true,
  cache: 'today_report',
})

const columns = ref([])
function syncColumns() {
  columns.value = (board.data?.columns || []).map((c) => ({
    state: c.state,
    items: [...(c.items || [])],
  }))
}
watch(() => board.data, syncColumns, { immediate: true, deep: false })

const toCallItems = computed(
  () => columns.value.find((c) => c.state === 'To Call')?.items || [],
)
const toCallCount = computed(() => toCallItems.value.length)
const toCallLeadCount = computed(
  () => new Set(toCallItems.value.map((item) => item.lead)).size,
)
const callsOwed = computed(() => toCallCount.value)
const boardCardCount = computed(() =>
  columns.value.reduce((total, col) => total + col.items.length, 0),
)
const streakLabel = computed(() => {
  const days = todayReport.data?.streak?.current || 0
  return `🔥 ${days} ${days === 1 ? __('day') : __('days')}`
})
const activeFilterCount = computed(
  () => [selectedStatus.value, selectedPriority.value, selectedSignal.value].filter(Boolean).length,
)
const priorityItems = computed(() => {
  const order = board.data?.priority_order || DEFAULT_PRIORITY_ORDER
  return order.map((key) => ({ key, ...PHASE[key] })).filter((item) => item.label)
})
const filterOptions = computed(() => {
  const statusCounts = board.data?.status_counts || []
  return [
    {
      group: __('Lead status'),
      items: [
        {
          label: __('All statuses'),
          icon: selectedStatus.value ? null : 'check',
          onClick: () => setFilter('status', ''),
        },
        ...statusCounts.map((row) => ({
          label: `${row.status} (${row.count})`,
          icon: selectedStatus.value === row.status ? 'check' : null,
          onClick: () => setFilter('status', row.status),
        })),
      ],
    },
    {
      group: __('Priority'),
      items: [
        {
          label: __('All priorities'),
          icon: selectedPriority.value ? null : 'check',
          onClick: () => setFilter('priority', ''),
        },
        ...priorityItems.value.map((item) => ({
          label: __(item.label),
          icon: selectedPriority.value === item.key ? 'check' : null,
          onClick: () => setFilter('priority', item.key),
        })),
      ],
    },
    {
      group: __('Signals'),
      items: [
        {
          label: __('All cards'),
          icon: selectedSignal.value ? null : 'check',
          onClick: () => setFilter('signal', ''),
        },
        {
          label: __('Texted us'),
          icon: selectedSignal.value === 'incoming' ? 'check' : null,
          onClick: () => setFilter('signal', 'incoming'),
        },
        {
          label: __('Has an open task'),
          icon: selectedSignal.value === 'task' ? 'check' : null,
          onClick: () => setFilter('signal', 'task'),
        },
      ],
    },
  ]
})
const prettyDate = computed(() => {
  if (!board.data?.date) return ''
  return new Date(board.data.date + 'T00:00:00').toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
})
const textReferenceDoc = computed(() => ({
  name: selectedTextItem.value?.lead,
  lead_name: selectedTextItem.value?.lead_name,
  mobile_no: selectedTextItem.value?.mobile_no,
  phone: selectedTextItem.value?.mobile_no,
}))

function dotClass(state) {
  return {
    'To Call': 'bg-surface-blue-3',
    Done: 'bg-surface-green-3',
    Skipped: 'bg-surface-gray-4',
  }[state]
}

function reloadWithFilters() {
  board.params = {
    owner: selectedOwner.value,
    ...(selectedStatus.value ? { status: selectedStatus.value } : {}),
    ...(selectedPriority.value ? { priority: selectedPriority.value } : {}),
    ...(selectedSignal.value ? { signal: selectedSignal.value } : {}),
  }
  board.reload()
}

function setFilter(type, value) {
  if (type === 'status') selectedStatus.value = value
  if (type === 'priority') selectedPriority.value = value
  if (type === 'signal') selectedSignal.value = value
  reloadWithFilters()
}

function setOwner(owner) {
  if (owner === selectedOwner.value) return
  selectedOwner.value = owner
  reloadWithFilters()
  // The report panel has to follow the board, or its progress bar describes a
  // card set that isn't the one on screen.
  todayReport.params = { owner: owner }
  todayReport.reload()
}

const ownerLabel = computed(() => {
  if (selectedOwner.value === ALL_OWNERS) return __('Everyone')
  const match = (board.data?.owners || []).find(
    (o) => o.user === selectedOwner.value,
  )
  if (match) return match.full_name
  return selectedOwner.value === sessionUser ? __('My leads') : selectedOwner.value
})

const viewingOwnBoard = computed(() => selectedOwner.value === sessionUser)

const ownerOptions = computed(() => {
  const owners = board.data?.owners || []
  const mine = owners.find((o) => o.user === sessionUser)
  const options = [
    {
      label: `${__('My leads')}${mine ? ` (${mine.count})` : ''}`,
      icon: viewingOwnBoard.value ? 'check' : null,
      onClick: () => setOwner(sessionUser),
    },
  ]
  const others = owners.filter((o) => o.user !== sessionUser)
  if (others.length) {
    options.push({
      group: __('Other boards'),
      items: others.map((o) => ({
        label: `${o.full_name} (${o.count})`,
        icon: selectedOwner.value === o.user ? 'check' : null,
        onClick: () => setOwner(o.user),
      })),
    })
  }
  options.push({
    group: __('Everyone'),
    items: [
      {
        label: __('The whole team'),
        icon: selectedOwner.value === ALL_OWNERS ? 'check' : null,
        onClick: () => setOwner(ALL_OWNERS),
      },
    ],
  })
  return options
})

function openTodayItem(item) {
  selectedItem.value = item
  showLeadModal.value = true
}

function leadStatusOptions(item) {
  return statusOptions('lead', [], (status) => chooseLeadStatus(item, status))
}

function chooseLeadStatus(item, status) {
  if (!item || !status || status === item.lead_status) return
  if (getLeadStatus(status)?.type === 'Lost') {
    pendingLeadStatus.value = { item, status }
    showLostReasonModal.value = true
    return
  }
  updateLeadStatus(item, status)
}

function confirmLostStatus(values) {
  const pending = pendingLeadStatus.value
  pendingLeadStatus.value = null
  if (!pending) return
  updateLeadStatus(pending.item, pending.status, values)
}

function cancelLostStatus() {
  pendingLeadStatus.value = null
}

async function updateLeadStatus(item, status, extraValues = {}) {
  if (savingStatusLeads.value.includes(item.lead)) return
  const oldStatus = item.lead_status
  savingStatusLeads.value = [...savingStatusLeads.value, item.lead]

  // A lead can have two independently actionable call cards. Keep both badges
  // in step while the save is in flight rather than showing conflicting states.
  for (const col of columns.value) {
    for (const card of col.items) {
      if (card.lead === item.lead) card.lead_status = status
    }
  }

  try {
    await call('crm.api.today_board.set_today_lead_status', {
      item: item.name,
      status,
      ...extraValues,
    })
    await board.reload()
  } catch (e) {
    for (const col of columns.value) {
      for (const card of col.items) {
        if (card.lead === item.lead) card.lead_status = oldStatus
      }
    }
    toast.error(e.messages?.[0] || __('Could not update lead status'))
    board.reload()
  } finally {
    savingStatusLeads.value = savingStatusLeads.value.filter(
      (lead) => lead !== item.lead,
    )
  }
}

function openTodayReport() {
  showReportModal.value = true
  todayReport.reload()
}

function openAddress(address) {
  if (!address) return
  selectedAddress.value = address
  showPropertyLinkModal.value = true
}

// Tick a task straight off the card, in either direction. Reopening matters as
// much as completing: the checkbox is one pixel from the row that opens the
// task, so a mis-click has to be undoable without hunting for the lead.
async function toggleTask(item) {
  const task = item.task
  if (!task || togglingTasks.value.includes(task.name)) return
  const wasCompleted = task.is_completed
  togglingTasks.value = [...togglingTasks.value, task.name]
  task.is_completed = !wasCompleted
  try {
    await call('frappe.client.set_value', {
      doctype: 'CRM Task',
      name: task.name,
      fieldname: 'status',
      value: wasCompleted ? 'Todo' : 'Done',
    })
    await board.reload()
  } catch (e) {
    task.is_completed = wasCompleted
    toast.error(e.messages?.[0] || __('Could not update the task'))
    board.reload()
  } finally {
    togglingTasks.value = togglingTasks.value.filter((name) => name !== task.name)
  }
}

function openText(item) {
  selectedTextItem.value = item
  showTextModal.value = true
}

function finishTextItem() {
  if (selectedTextItem.value) requestState(selectedTextItem.value, 'Done')
}

function skipTextItem() {
  if (selectedTextItem.value) requestState(selectedTextItem.value, 'Skipped')
}

// Resolving a card asks what happened first. Putting one BACK doesn't: undoing a
// mis-click is not a judgement worth interrogating, and a prompt there would
// make the mistake more expensive than the action.
function requestState(item, state) {
  if (state === 'To Call') {
    applyState(item, state)
    return
  }
  pendingOutcome.value = { item, state, col: null, viaDrag: false }
  showOutcomeModal.value = true
}

function onChange(evt, col) {
  if (evt.moved) {
    persistOrder(col)
    return
  }
  if (!evt.added) return
  const item = evt.added.element
  if (item.state === col.state) {
    persistOrder(col)
    return
  }
  if (col.state === 'To Call') {
    applyState(item, 'To Call', { col, alreadyMoved: true })
    return
  }
  pendingOutcome.value = { item, state: col.state, col, viaDrag: true }
  showOutcomeModal.value = true
}

async function confirmOutcome({ outcome, outcome_note }) {
  const pending = pendingOutcome.value
  if (!pending) return
  pendingOutcome.value = null
  savingOutcome.value = true
  try {
    await applyState(pending.item, pending.state, {
      outcome,
      outcome_note,
      col: pending.col,
      alreadyMoved: pending.viaDrag,
    })
  } finally {
    savingOutcome.value = false
    showOutcomeModal.value = false
  }
}

// Esc, the backdrop and Cancel all land here. A dragged card is sitting in the
// wrong column until the server is re-read, so abandoning the answer has to put
// it back rather than leave the board lying.
watch(showOutcomeModal, (open) => {
  if (open) return
  const pending = pendingOutcome.value
  pendingOutcome.value = null
  if (pending?.viaDrag) board.reload()
})

async function applyState(item, state, options = {}) {
  const { outcome = '', outcome_note = '', col = null, alreadyMoved = false } = options
  const prev = item.state
  item.state = state
  if (!alreadyMoved) {
    const from = columns.value.find((c) => c.state === prev)
    const to = columns.value.find((c) => c.state === state)
    if (from && to) {
      const i = from.items.findIndex((x) => x.name === item.name)
      if (i > -1) from.items.splice(i, 1)
      to.items.unshift(item)
    }
  }
  item.outcome = outcome
  item.outcome_note = outcome_note
  try {
    await call('crm.api.today_board.set_today_state', {
      item: item.name,
      state,
      outcome,
      outcome_note,
    })
    if (col) await persistOrder(col)
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not update'))
    board.reload()
  }
}

async function persistOrder(col) {
  try {
    await call('crm.api.today_board.reorder_today', {
      order: col.items.map((i) => i.name),
      state: col.state,
    })
    col.items.forEach((i) => (i.state = col.state))
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not reorder'))
    board.reload()
  }
}

async function savePriorityOrder(order) {
  savingPriority.value = true
  try {
    await call('crm.api.today_board.set_today_priority_order', { order })
    showPriorityModal.value = false
    await board.reload()
    toast.success(__('Priority order saved'))
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not save priority order'))
  } finally {
    savingPriority.value = false
  }
}

async function syncList() {
  refreshing.value = true
  syncStatus.value = ''
  try {
    const r = await call('crm.api.today_board.generate_today')
    await Promise.all([board.reload(), todayReport.reload()])
    // `closed` has to be said out loud: after 5pm the sync deliberately adds
    // nothing, and "List is up to date" would read as a lie to anyone who knows
    // a lead just came in.
    const message = r.closed
      ? __('The list is closed for today — new leads go on tomorrow’s list')
      : r.created
        ? __('Added {0} new call(s)', [r.created])
        : __('List is up to date')
    syncStatusTheme.value = r.closed ? 'orange' : 'green'
    syncStatus.value = message
    toast.success(message)
  } catch (e) {
    const message = e.messages?.[0] || __('Could not sync the list')
    syncStatusTheme.value = 'red'
    syncStatus.value = __('Sync failed')
    toast.error(message)
  } finally {
    refreshing.value = false
  }
}

function onRealtime() {
  board.reload()
  todayReport.reload()
}
onMounted(() => $socket.on('crm_today', onRealtime))
onBeforeUnmount(() => {
  $socket.off('crm_today', onRealtime)
})
</script>
