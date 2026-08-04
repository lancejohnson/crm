<template>
  <LayoutHeader>
    <template #left-header>
      <div class="flex items-center gap-2">
        <span class="text-lg font-semibold text-ink-gray-8">{{ __('Today') }}</span>
        <Badge v-if="board.data?.date" variant="subtle" theme="gray" :label="prettyDate" />
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
        <Button :label="__('Priority')" @click="showPriorityModal = true">
          <template #prefix><FeatherIcon name="list" class="size-4" /></template>
        </Button>
        <Badge
          v-if="toCallCount"
          variant="subtle"
          theme="blue"
          :label="`${toCallLeadCount} ${toCallLeadCount === 1 ? __('lead') : __('leads')} · ${callsOwed} ${callsOwed === 1 ? __('call') : __('calls')}`"
        />
        <Badge v-else variant="subtle" theme="green" :label="__('All clear')" />
        <Button :label="__('Refresh list')" :loading="refreshing" @click="refreshList">
          <template #prefix><RefreshIcon class="h-4 w-4" /></template>
        </Button>
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

      <Draggable
        v-model="col.items"
        :group="'today'"
        item-key="name"
        class="flex min-h-[6rem] flex-1 flex-col gap-2 overflow-y-auto px-2 pb-3"
        @end="onDrop($event, col)"
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
                  @click.stop="setState(item, 'Done')"
                >
                  <CheckIcon class="size-4 text-ink-green-3" />
                </button>
              </Tooltip>
              <Tooltip v-if="item.state !== 'Skipped'" :text="__('Skip for today')">
                <button
                  class="flex size-7 items-center justify-center rounded-md hover:bg-surface-gray-2"
                  @click.stop="setState(item, 'Skipped')"
                >
                  <BanIcon class="size-4 text-ink-gray-5" />
                </button>
              </Tooltip>
              <Tooltip v-if="item.state !== 'To Call'" :text="__('Put back')">
                <button
                  class="flex size-7 items-center justify-center rounded-md hover:bg-surface-gray-2"
                  @click.stop="setState(item, 'To Call')"
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
              <div class="mt-0.5 truncate text-xs text-ink-gray-5" :title="item.address">
                {{ item.address || '—' }}
              </div>
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
              <Badge variant="subtle" theme="gray" :label="item.lead_status" />
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

            <button
              v-if="item.task"
              class="mt-2 flex w-full items-center gap-1.5 rounded-md border border-outline-gray-1 bg-surface-gray-1 px-2 py-1.5 text-left hover:border-outline-gray-3 hover:bg-surface-gray-2"
              @click.stop="openTask(item.task)"
            >
              <FeatherIcon name="check-circle" class="size-3.5 shrink-0 text-ink-green-3" />
              <span class="min-w-0 flex-1 truncate text-xs font-medium text-ink-gray-7">
                {{ item.task.title }}
              </span>
              <span v-if="item.task.due_date" class="shrink-0 text-xs text-ink-gray-5">
                {{ __(timeAgo(item.task.due_date)) }}
              </span>
            </button>

            <div v-if="item.reason" class="mt-1 truncate text-xs text-ink-gray-5">
              {{ item.reason }}
            </div>
          </div>
        </template>
      </Draggable>
    </div>
  </div>

  <TodayLeadModal v-model="showLeadModal" :item="selectedItem" />
  <TodayPriorityModal
    v-model="showPriorityModal"
    :priorities="priorityItems"
    :saving="savingPriority"
    @save="savePriorityOrder"
  />
  <TaskModal
    v-if="showTaskModal"
    v-model="showTaskModal"
    :task="selectedTask"
    doctype="CRM Lead"
    :doc="selectedTask?.reference_docname"
    @after="board.reload()"
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
import SendTextModal from '@/components/Modals/SendTextModal.vue'
import TaskModal from '@/components/Modals/TaskModal.vue'
import { globalStore } from '@/stores/global'
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
const refreshing = ref(false)
const selectedStatus = ref('')
const selectedPriority = ref('')
const selectedSignal = ref('')
const selectedItem = ref(null)
const showLeadModal = ref(false)
const showPriorityModal = ref(false)
const savingPriority = ref(false)
const selectedTask = ref(null)
const showTaskModal = ref(false)
const selectedTextItem = ref(null)
const showTextModal = ref(false)

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

function openTodayItem(item) {
  selectedItem.value = item
  showLeadModal.value = true
}

function openTask(task) {
  selectedTask.value = { ...task }
  showTaskModal.value = true
}

function openText(item) {
  selectedTextItem.value = item
  showTextModal.value = true
}

function finishTextItem() {
  if (selectedTextItem.value) setState(selectedTextItem.value, 'Done')
}

function skipTextItem() {
  if (selectedTextItem.value) setState(selectedTextItem.value, 'Skipped')
}

async function setState(item, state) {
  const prev = item.state
  item.state = state
  const from = columns.value.find((c) => c.state === prev)
  const to = columns.value.find((c) => c.state === state)
  if (from && to) {
    const i = from.items.findIndex((x) => x.name === item.name)
    if (i > -1) from.items.splice(i, 1)
    to.items.unshift(item)
  }
  try {
    await call('crm.api.today_board.set_today_state', { item: item.name, state })
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not update'))
    board.reload()
  }
}

async function onDrop(evt, col) {
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

async function refreshList() {
  refreshing.value = true
  try {
    const r = await call('crm.api.today_board.generate_today')
    board.reload()
    toast.success(r.created ? __('Added {0} call(s)', [r.created]) : __('Already up to date'))
  } finally {
    refreshing.value = false
  }
}

function onRealtime() {
  board.reload()
}
onMounted(() => $socket.on('crm_today', onRealtime))
onBeforeUnmount(() => $socket.off('crm_today', onRealtime))
</script>
