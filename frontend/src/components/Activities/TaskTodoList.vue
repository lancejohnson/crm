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

      <ul v-if="sortedTasks.length">
      <li
        v-for="task in sortedTasks"
        :key="task.name"
        class="group/td flex items-center gap-2.5 px-3 py-1.5 hover:bg-surface-gray-2"
      >
        <Tooltip :text="__('Mark as done')">
          <button
            class="flex size-7 shrink-0 items-center justify-center rounded text-ink-gray-4 hover:bg-surface-gray-3 hover:text-ink-green-3"
            @click="modalRef.updateTaskStatus('Done', task)"
          >
            <LucideCircle class="size-4 group-hover/td:hidden" />
            <LucideCircleCheckBig
              class="hidden size-4 text-ink-green-3 group-hover/td:block"
            />
          </button>
        </Tooltip>

        <button
          class="min-w-0 flex-1 truncate text-left text-sm text-ink-gray-8 hover:underline"
          :title="__('Edit task and schedule')"
          @click="modalRef.showTask(task)"
        >
          {{ task.title }}
        </button>

        <Tooltip
          v-if="task.due_date"
          :text="formatDate(task.due_date, 'ddd, MMM D, YYYY | hh:mm a')"
        >
          <div
            class="shrink-0 text-xs tabular-nums"
            :class="dueClass(task.due_date)"
          >
            {{ dueLabel(task.due_date) }}
          </div>
        </Tooltip>

        <Tooltip :text="__('Delete')">
          <button
            class="flex size-7 shrink-0 items-center justify-center rounded text-ink-gray-4 opacity-100 hover:bg-surface-red-1 hover:text-ink-red-3 focus:opacity-100 sm:opacity-0 sm:group-hover/td:opacity-100"
            @click="modalRef.deleteTask(task.name)"
          >
            <LucideTrash2 class="size-3.5" />
          </button>
        </Tooltip>
      </li>
    </ul>
    <!-- pencil editor for the due chips -->
    <div v-if="editing" class="flex flex-col gap-2 border-t border-outline-gray-1 px-3 pt-2 pb-2.5">
      <div
        v-for="(row, i) in draft"
        :key="i"
        class="flex items-center gap-2"
      >
        <input
          v-model="draft[i].label"
          type="text"
          :placeholder="__('3d')"
          class="w-16 rounded-md border border-outline-gray-2 bg-surface-white px-2 py-1 text-sm text-ink-gray-8 focus:outline-none focus:ring-1 focus:ring-outline-gray-3"
        />
        <input
          v-model.number="draft[i].amount"
          type="number"
          min="1"
          max="365"
          class="w-16 rounded-md border border-outline-gray-2 bg-surface-white px-2 py-1 text-sm text-ink-gray-8 focus:outline-none focus:ring-1 focus:ring-outline-gray-3"
        />
        <select
          v-model="draft[i].unit"
          class="min-w-0 flex-1 rounded-md border border-outline-gray-2 bg-surface-white px-2 py-1 text-sm text-ink-gray-8 focus:outline-none focus:ring-1 focus:ring-outline-gray-3"
        >
          <option
            v-for="u in TASK_DUE_UNITS"
            :key="u.value"
            :value="u.value"
          >
            {{ u.label }}
          </option>
        </select>
        <Tooltip :text="__('Remove')">
          <button
            class="flex shrink-0 items-center text-ink-gray-4 hover:text-ink-red-3"
            @click="draft.splice(i, 1)"
          >
            <LucideTrash2 class="size-3.5" />
          </button>
        </Tooltip>
      </div>
      <button
        class="flex items-center gap-2 self-start text-sm text-ink-gray-5 hover:text-ink-gray-7"
        @click="addDraftRow"
      >
        <LucidePlus class="size-4" />
        {{ __('Add a chip') }}
      </button>
      <p class="text-xs text-ink-gray-4">
        {{ __('Days, weeks, and months land at 9:00am CT. Hours stay relative to now.') }}
      </p>
      <div class="flex items-center justify-end gap-2">
        <Button :label="__('Cancel')" @click="editing = false" />
        <Button
          variant="solid"
          :label="__('Save')"
          :loading="saving"
          @click="savePresets"
        />
      </div>
    </div>

    <!-- Say what the task is, choose when, then Add. A due chip with a typed
         title selects the date; with an EMPTY title it creates a "Follow up"
         task at that time in one tap (Lance, 2026-09-03 — the common case is
         "bump this lead", and typing a title first was friction). -->
    <div v-else class="border-t border-outline-gray-1 px-3 pt-2 pb-2.5">
      <div class="flex items-center gap-2">
        <LucidePlus class="size-4 shrink-0 text-ink-gray-4" />
        <input
          v-model="newTitle"
          type="text"
          :placeholder="__('What needs to happen?')"
          autocomplete="off"
          class="todo-composer min-w-0 flex-1 text-sm text-ink-gray-8 placeholder:text-ink-gray-4"
          @keydown.enter.prevent="submit"
        />
      </div>
      <div
        class="mt-2 flex flex-wrap items-center gap-1.5 pl-6"
        role="group"
        :aria-label="__('When')"
      >
        <span class="mr-0.5 text-xs text-ink-gray-4">{{ __('When') }}</span>
        <button
          type="button"
          class="rounded-md border px-2 py-0.5 text-sm"
          :class="dueChoiceClass(!newDue)"
          :aria-pressed="!newDue"
          @click="clearDue"
        >
          {{ __('No date') }}
        </button>
        <Tooltip
          v-for="(f, i) in presets"
          :key="i"
          :text="dueTooltip(f)"
        >
          <button
            type="button"
            class="rounded-md border px-2 py-0.5 text-sm"
            :class="dueChoiceClass(selectedPresetIndex === i)"
            :aria-pressed="selectedPresetIndex === i"
            @click="selectPreset(f, i)"
          >
            {{ f.label }}
          </button>
        </Tooltip>
        <Tooltip :text="__('Pick a due date')">
          <button
            type="button"
            class="flex items-center rounded-md border px-1.5 py-1"
            :class="dueChoiceClass(showDatePicker && selectedPresetIndex < 0)"
            :aria-pressed="showDatePicker && selectedPresetIndex < 0"
            :aria-label="__('Pick a due date')"
            @click="openDatePicker"
          >
            <LucideCalendar class="size-3.5" />
          </button>
        </Tooltip>
        <Tooltip :text="__('Customize due-date choices')">
          <button
            type="button"
            class="flex size-7 items-center justify-center rounded text-ink-gray-4 hover:bg-surface-gray-2 hover:text-ink-gray-7"
            :aria-label="__('Customize due-date choices')"
            @click="startEdit"
          >
            <LucidePencil class="size-3.5" />
          </button>
        </Tooltip>
        <Button
          class="ml-auto"
          variant="solid"
          :label="__('Add')"
          :disabled="!newTitle.trim()"
          @click="submit"
        />
      </div>
      <div
        v-if="showDatePicker"
        class="mt-1.5 flex items-center gap-2 pl-6"
      >
        <span class="shrink-0 text-xs text-ink-gray-4">{{ __('Due') }}</span>
        <DateTimePicker
          v-model="newDue"
          @update:modelValue="selectedPresetIndex = -1"
          class="todo-datepicker flex-1"
          :placeholder="__('Due date')"
          :format="getFormat('', '', true, true, false)"
          input-class="border-none !bg-transparent text-sm"
        />
      </div>
    </div>
    </div>
  </div>
</template>

<script setup>
import ListTodoIcon from '~icons/lucide/list-todo'
import LucideCalendar from '~icons/lucide/calendar'
import LucideCircle from '~icons/lucide/circle'
import LucideCircleCheckBig from '~icons/lucide/circle-check-big'
import LucidePencil from '~icons/lucide/pencil'
import LucidePlus from '~icons/lucide/plus'
import LucideTrash2 from '~icons/lucide/trash-2'
import {
  TASK_DUE_UNITS,
  dueFromPreset,
  dueLabel,
  formatDueStamp,
  snapMidnightToMorning,
} from '@/utils/taskDue'
import { formatDate, dueColor, parseColor, getFormat } from '@/utils'
import { usersStore } from '@/stores/users'
import { useTaskDuePresets } from '@/composables/taskDuePresets'
import { Button, Tooltip, DateTimePicker, call, toast } from 'frappe-ui'
import { ref, computed } from 'vue'

const props = defineProps({
  tasks: { type: Array, default: () => [] },
  modalRef: { type: Object, default: () => ({}) },
})

const { getUser } = usersStore()

const newTitle = ref('')
const newDue = ref('')
const showDatePicker = ref(false)
const selectedPresetIndex = ref(-1)

// Shared with the Today board's follow-up strip.
const { presets } = useTaskDuePresets()

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
  const due = snapMidnightToMorning(newDue.value)
  newTitle.value = ''
  newDue.value = ''
  showDatePicker.value = false
  selectedPresetIndex.value = -1
  props.modalRef.addTask(t, due)
}

function dueTooltip(f) {
  return __('Follow up') + ' · ' + formatDate(dueFromPreset(f), 'ddd, MMM D, YYYY | hh:mm a')
}

function selectPreset(f, index) {
  const due = formatDueStamp(dueFromPreset(f))
  if (!newTitle.value.trim()) {
    // Nothing typed: one tap = a "Follow up" task at that time.
    newDue.value = ''
    showDatePicker.value = false
    selectedPresetIndex.value = -1
    props.modalRef.addTask(__('Follow up'), snapMidnightToMorning(due))
    return
  }
  selectedPresetIndex.value = index
  newDue.value = due
  showDatePicker.value = false
}

function clearDue() {
  selectedPresetIndex.value = -1
  newDue.value = ''
  showDatePicker.value = false
}

function openDatePicker() {
  selectedPresetIndex.value = -1
  showDatePicker.value = !showDatePicker.value
}

function dueChoiceClass(selected) {
  return selected
    ? 'border-outline-gray-3 bg-surface-gray-3 font-medium text-ink-gray-8'
    : 'border-outline-gray-1 bg-surface-white text-ink-gray-6 hover:bg-surface-gray-2'
}

const editing = ref(false)
const saving = ref(false)
const draft = ref([])

function startEdit() {
  draft.value = presets.value.map((p) => ({ ...p }))
  editing.value = true
}

function addDraftRow() {
  draft.value.push({ label: '', amount: 3, unit: 'day' })
}

async function savePresets() {
  const cleaned = draft.value
    .map((p) => ({
      label: String(p.label || '').trim(),
      amount: parseInt(p.amount, 10),
      unit: p.unit,
    }))
    .filter((p) => p.label && p.amount > 0 && p.unit)
  saving.value = true
  try {
    const stored = await call('crm.api.task_presets.set_user_task_due_presets', {
      presets: JSON.stringify(cleaned),
    })
    getUser('sessionUser').custom_task_due_presets = JSON.stringify(stored)
    editing.value = false
    toast.success(__('Due-date chips saved'))
  } catch (e) {
    toast.error(__('Could not save due-date chips'))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.todo-composer {
  appearance: none;
  border: none !important;
  outline: none !important;
  box-shadow: none !important;
  background: transparent;
  padding: 0;
}
.todo-composer:focus,
.todo-composer:focus-visible {
  outline: none !important;
  border: none !important;
  box-shadow: none !important;
}
</style>
