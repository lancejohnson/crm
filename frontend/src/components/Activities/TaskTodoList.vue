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
      </div>

      <!-- Trello-style quick add -->
      <div
        class="flex items-center gap-2.5 border-t border-outline-gray-1 px-3 py-1.5"
      >
        <LucidePlus class="size-4 shrink-0 text-ink-gray-4" />
        <input
          v-model="newTitle"
          type="text"
          :placeholder="__('Add a task…')"
          class="flex-1 bg-transparent text-base text-ink-gray-8 placeholder:text-ink-gray-4 focus:outline-none"
          @keydown.enter="submit"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import ListTodoIcon from '~icons/lucide/list-todo'
import LucideCircle from '~icons/lucide/circle'
import LucideCircleCheckBig from '~icons/lucide/circle-check-big'
import LucidePlus from '~icons/lucide/plus'
import { formatDate, timeAgo, dueColor, parseColor } from '@/utils'
import { Tooltip } from 'frappe-ui'
import { ref, computed } from 'vue'

const props = defineProps({
  tasks: { type: Array, default: () => [] },
  modalRef: { type: Object, default: () => ({}) },
})

const newTitle = ref('')

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
  newTitle.value = ''
  props.modalRef.addTask(t)
}
</script>
