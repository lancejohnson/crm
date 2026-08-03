<template>
  <LayoutHeader>
    <template #left-header>
      <div class="flex items-center gap-2">
        <span class="text-lg font-semibold text-ink-gray-8">{{ __('Today') }}</span>
        <Badge v-if="board.data?.date" variant="subtle" theme="gray" :label="prettyDate" />
      </div>
    </template>
    <template #right-header>
      <div class="flex items-center gap-2">
        <Badge
          v-if="toCallCount"
          variant="subtle"
          theme="blue"
          :label="`${toCallCount} to call · ${callsOwed} calls`"
        />
        <Badge v-else variant="subtle" theme="green" :label="__('All clear')" />
        <Button
          :label="__('Refresh list')"
          :loading="refreshing"
          @click="refreshList"
        >
          <template #prefix><RefreshIcon class="h-4 w-4" /></template>
        </Button>
      </div>
    </template>
  </LayoutHeader>

  <div v-if="board.data && !board.data.available" class="flex h-full items-center justify-center">
    <div class="text-center text-ink-gray-5">
      <p class="text-base">{{ __('The Today board is not set up on this site yet.') }}</p>
      <p class="mt-1 text-sm">
        {{ __('Run scripts/setup_today_board.py from the ops repo.') }}
      </p>
    </div>
  </div>

  <div v-else class="flex flex-1 gap-3 overflow-x-auto p-4">
    <div
      v-for="col in columns"
      :key="col.state"
      class="flex w-[22rem] shrink-0 flex-col rounded-lg bg-surface-gray-1"
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
            @click="openLead(item)"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <div
                  class="truncate text-base font-medium text-ink-gray-8"
                  :class="item.state === 'Skipped' ? 'line-through opacity-60' : ''"
                >
                  {{ item.lead_name }}
                </div>
                <div class="mt-0.5 truncate text-xs text-ink-gray-5">
                  {{ item.address || item.mobile_no || '—' }}
                </div>
              </div>
              <!-- hover-only actions; stop propagation so they never open the lead -->
              <div
                class="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100"
                @click.stop
              >
                <Button
                  v-if="item.state !== 'Done'"
                  variant="ghost"
                  class="!h-7 !w-7"
                  :tooltip="__('Done')"
                  @click.stop="setState(item, 'Done')"
                >
                  <CheckIcon class="h-4 w-4 text-ink-green-3" />
                </Button>
                <Button
                  v-if="item.state !== 'Skipped'"
                  variant="ghost"
                  class="!h-7 !w-7"
                  :tooltip="__('Skip for today')"
                  @click.stop="setState(item, 'Skipped')"
                >
                  <BanIcon class="h-4 w-4 text-ink-gray-5" />
                </Button>
                <Button
                  v-if="item.state !== 'To Call'"
                  variant="ghost"
                  class="!h-7 !w-7"
                  :tooltip="__('Put back')"
                  @click.stop="setState(item, 'To Call')"
                >
                  <UndoIcon class="h-4 w-4 text-ink-gray-5" />
                </Button>
              </div>
            </div>

            <div class="mt-2 flex flex-wrap items-center gap-1.5">
              <Badge
                v-if="PHASE[item.phase]"
                variant="subtle"
                :theme="PHASE[item.phase].theme"
                :label="__(PHASE[item.phase].label)"
              />
              <Badge variant="subtle" theme="gray" :label="item.lead_status" />
              <span class="text-xs text-ink-gray-5">
                {{ item.calls_today }}/{{ item.calls_needed + item.calls_today }}
                {{ __('calls today') }}
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
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import RefreshIcon from '@/components/Icons/RefreshIcon.vue'
import { globalStore } from '@/stores/global'
import { Badge, Button, call, createResource, toast } from 'frappe-ui'
import Draggable from 'vuedraggable'
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const { $socket } = globalStore()
const refreshing = ref(false)

// tiny inline icons (no new asset files for three glyphs)
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
  never: { label: 'Never called', theme: 'red' },
  week1: { label: 'Week 1', theme: 'blue' },
  weekly: { label: 'Weekly', theme: 'orange' },
  monthly: { label: 'Monthly', theme: 'gray' },
  task: { label: 'Task due', theme: 'violet' },
}

const board = createResource({
  url: 'crm.api.today_board.get_today_board',
  auto: true,
  cache: 'today_board',
})

// local, mutable copy — vuedraggable needs to write to the arrays it binds.
// Synced with a watcher rather than `board.onSuccess = ...`: the resource is
// `auto: true`, so it can resolve BEFORE a post-hoc onSuccess assignment lands,
// and the board then renders permanently empty ('All clear' over 66 real cards).
// The watcher is timing-independent and also covers every later reload.
const columns = ref([])
function syncColumns() {
  columns.value = (board.data?.columns || []).map((c) => ({
    state: c.state,
    items: [...(c.items || [])],
  }))
}
watch(() => board.data, syncColumns, { immediate: true, deep: false })

const toCallCount = computed(
  () => columns.value.find((c) => c.state === 'To Call')?.items.length || 0,
)
const callsOwed = computed(() =>
  (columns.value.find((c) => c.state === 'To Call')?.items || []).reduce(
    (n, i) => n + (i.calls_needed || 0),
    0,
  ),
)
const prettyDate = computed(() => {
  if (!board.data?.date) return ''
  return new Date(board.data.date + 'T00:00:00').toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
})

function dotClass(state) {
  return {
    'To Call': 'bg-surface-blue-3',
    Done: 'bg-surface-green-3',
    Skipped: 'bg-surface-gray-4',
  }[state]
}

function openLead(item) {
  router.push({ name: 'Lead', params: { leadId: item.lead } })
}

async function setState(item, state) {
  const prev = item.state
  item.state = state
  // move it locally straight away so the card visibly leaves the column
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
    // keep each card's own state in step with the column it now sits in
    col.items.forEach((i) => (i.state = col.state))
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not reorder'))
    board.reload()
  }
}

async function refreshList() {
  refreshing.value = true
  try {
    const r = await call('crm.api.today_board.generate_today')
    board.reload()
    toast.success(
      r.created ? __('Added {0} lead(s)').replace('{0}', r.created) : __('Already up to date'),
    )
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
