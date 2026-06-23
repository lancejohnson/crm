<template>
  <div class="px-3 pt-3 sm:px-10">
    <div
      class="overflow-hidden rounded-lg border border-outline-gray-1 bg-surface-gray-1"
    >
      <div
        class="flex items-center gap-1.5 px-3 pt-2.5 pb-1 text-sm font-medium text-ink-gray-5"
      >
        <ListTodoIcon class="size-3.5" />
        <span>{{ __('To-do') }}</span>
        <span v-if="sortedTasks.length" class="text-ink-gray-4">
          {{ sortedTasks.length }}
        </span>
      </div>

      <!-- open tasks: click the circle to complete, click the row to edit -->
      <div
        v-for="task in sortedTasks"
        :key="task.name"
        class="group/td flex cursor-pointer items-center gap-2.5 px-3 py-1.5 hover:bg-surface-gray-2"
        @click="modalRef.showTask(task)"
      >
        <Tooltip :text="__('Mark as done')">
          <button
            class="flex shrink-0 items-center text-ink-gray-4 hover:text-ink-green-3"
            @click.stop="modalRef.updateTaskStatus('Done', task)"
          >
            <LucideCircle class="size-4 group-hover/td:hidden" />
            <LucideCircleCheckBig
              class="hidden size-4 text-ink-green-3 group-hover/td:block"
            />
          </button>
        </Tooltip>
        <div class="flex-1 truncate text-base text-ink-gray-8">
          {{ task.title }}
        </div>
        <Tooltip
          v-if="task.due_date"
          :text="formatDate(task.due_date, 'ddd, MMM D, YYYY | hh:mm a')"
        >
          <div class="shrink-0 text-sm" :class="dueClass(task.due_date)">
            {{ __(timeAgo(task.due_date)) }}
          </div>
        </Tooltip>
        <Tooltip :text="__('Delete')">
          <button
            class="hidden shrink-0 items-center text-ink-gray-4 hover:text-ink-red-3 group-hover/td:flex"
            @click.stop="modalRef.deleteTask(task.name)"
          >
            <LucideTrash2 class="size-3.5" />
          </button>
        </Tooltip>
      </div>

      <!-- Trello-style quick add: title + optional due date/time -->
      <div
        class="flex items-center gap-2 border-t border-outline-gray-1 px-3 py-1.5"
      >
        <LucidePlus class="size-4 shrink-0 text-ink-gray-4" />
        <input
          v-model="newTitle"
          type="text"
          :placeholder="__('Add a task…')"
          class="min-w-0 flex-1 bg-transparent text-base text-ink-gray-8 placeholder:text-ink-gray-4 focus:outline-none"
          @keydown.enter="submit"
        />
        <DateTimePicker
          v-model="newDue"
          class="todo-datepicker w-40 shrink-0"
          :placeholder="__('Due date')"
          :format="getFormat('', '', true, true, false)"
          input-class="border-none !bg-transparent text-sm"
        />
      </div>

      <!-- One-tap follow-up: drops a task due now + the interval. Uses the typed
           title if there is one, else "Follow up". Lands at the top of the feed,
           right where you return after a Send Text / Log a Call modal closes. -->
      <div
        class="flex items-center gap-2 border-t border-outline-gray-1 px-3 py-1.5"
      >
        <span class="shrink-0 text-sm text-ink-gray-4">
          {{ __('Follow up in') }}
        </span>
        <div class="flex flex-wrap items-center gap-1.5">
          <Tooltip
            v-for="f in followUps"
            :key="f.label"
            :text="dueTooltip(f)"
          >
            <button
              class="rounded-md border border-outline-gray-1 px-2 py-0.5 text-sm text-ink-gray-7 hover:bg-surface-gray-3"
              @click="followUp(f)"
            >
              {{ f.label }}
            </button>
          </Tooltip>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import ListTodoIcon from '~icons/lucide/list-todo'
import LucideCircle from '~icons/lucide/circle'
import LucideCircleCheckBig from '~icons/lucide/circle-check-big'
import LucidePlus from '~icons/lucide/plus'
import LucideTrash2 from '~icons/lucide/trash-2'
import { formatDate, timeAgo, dueColor, parseColor, getFormat } from '@/utils'
import { Tooltip, DateTimePicker, dayjs } from 'frappe-ui'
import { ref, computed } from 'vue'

const props = defineProps({
  tasks: { type: Array, default: () => [] },
  modalRef: { type: Object, default: () => ({}) },
})

const newTitle = ref('')
const newDue = ref('')

// open tasks sorted by due date ascending (overdue first → today → future);
// undated tasks sink to the bottom.
const sortedTasks = computed(() =>
  [...props.tasks].sort((a, b) => {
    if (!a.due_date) return 1
    if (!b.due_date) return -1
    return new Date(a.due_date) - new Date(b.due_date)
  }),
)

function dueClass(date) {
  const color = dueColor(date)
  return color ? parseColor(color) : 'text-ink-gray-5'
}

function submit() {
  const t = newTitle.value.trim()
  if (!t) return
  const due = newDue.value
  newTitle.value = ''
  newDue.value = ''
  props.modalRef.addTask(t, due)
}

// One-tap follow-up presets. `amount`/`unit` feed dayjs().add(); the resulting
// due date is formatted to match what the DateTimePicker emits (CRM Task
// due_date is a Datetime → 'YYYY-MM-DD HH:mm:ss').
const followUps = [
  { label: '2h', amount: 2, unit: 'hour' },
  { label: '24h', amount: 24, unit: 'hour' },
  { label: '1wk', amount: 1, unit: 'week' },
  { label: '1mo', amount: 1, unit: 'month' },
]

function dueAt(f) {
  return dayjs().add(f.amount, f.unit)
}

function dueTooltip(f) {
  return formatDate(dueAt(f), 'ddd, MMM D, YYYY | hh:mm a')
}

function followUp(f) {
  const title = newTitle.value.trim() || __('Follow up')
  newTitle.value = ''
  newDue.value = ''
  props.modalRef.addTask(title, dueAt(f).format('YYYY-MM-DD HH:mm:ss'))
}
</script>
