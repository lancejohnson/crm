<template>
  <div class="flex flex-wrap items-center gap-2 rounded-md bg-surface-gray-1 px-2.5 py-2">
    <span class="shrink-0 text-xs text-ink-gray-5">{{ __('Send at') }}</span>
    <button
      v-for="c in chips"
      :key="c.label"
      type="button"
      class="rounded-full border px-2 py-0.5 text-xs"
      :class="
        sendAt === c.value
          ? 'border-outline-gray-4 bg-surface-gray-2 text-ink-gray-8'
          : 'border-outline-gray-2 text-ink-gray-6 hover:border-outline-gray-3'
      "
      @click="sendAt = c.value"
    >
      {{ c.label }}
    </button>
    <DateTimePicker
      v-model="sendAt"
      class="min-w-[11rem] flex-1"
      :placeholder="__('Pick a time')"
      :format="getFormat('', '', true, true, false)"
      input-class="!bg-transparent text-sm"
    />
    <Button
      variant="solid"
      :label="__('Schedule')"
      :loading="busy"
      :disabled="disabled || !sendAt"
      @click="$emit('confirm', snapMidnightToMorning(sendAt))"
    />
    <Button variant="ghosted" icon="x" @click="$emit('cancel')" />
  </div>
</template>

<script setup>
import { getFormat } from '@/utils'
import { formatDueStamp, snapMidnightToMorning, TASK_DUE_HOUR, TASK_DUE_TZ } from '@/utils/taskDue'
import { Button, DateTimePicker, dayjs } from 'frappe-ui'
import { computed, ref } from 'vue'

defineProps({
  busy: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})
defineEmits(['confirm', 'cancel'])

// Quick picks at 9am Chicago: tomorrow, and the coming Saturday / Monday —
// the two days a weekend text task actually lands on.
function morning(d) {
  return formatDueStamp(d.hour(TASK_DUE_HOUR).minute(0).second(0).millisecond(0))
}
const chips = computed(() => {
  const now = dayjs().tz(TASK_DUE_TZ)
  const out = [{ label: __('Tomorrow 9am'), value: morning(now.add(1, 'day')) }]
  const sat = now.add(((6 - now.day() + 7) % 7) || 7, 'day')
  const mon = now.add(((1 - now.day() + 7) % 7) || 7, 'day')
  out.push({ label: __('Sat 9am'), value: morning(sat) })
  out.push({ label: __('Mon 9am'), value: morning(mon) })
  return out
})
const sendAt = ref(chips.value[0].value)
</script>
