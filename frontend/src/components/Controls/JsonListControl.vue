<template>
  <div class="flex min-w-0 flex-1 flex-wrap items-center gap-1 py-0.5">
    <span
      v-for="item in items"
      :key="item"
      class="flex min-w-0 items-center gap-1 rounded bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-7"
    >
      <span class="max-w-48 truncate">{{ item }}</span>
      <button
        v-if="!disabled"
        type="button"
        class="shrink-0 text-ink-gray-4 hover:text-ink-gray-7"
        :aria-label="__('Remove {0}', [item])"
        @click.stop="remove(item)"
      >
        <XIcon class="size-3" />
      </button>
    </span>

    <Autocomplete
      v-if="!disabled"
      :options="availableOptions"
      :modelValue="''"
      @update:modelValue="addOption"
    >
      <template #target="{ togglePopover }">
        <button
          type="button"
          class="rounded px-1.5 py-0.5 text-xs text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8"
          @click.stop="togglePopover()"
        >
          + {{ items.length ? __('Add') : placeholder }}
        </button>
      </template>
      <template #footer="{ value: query, close }">
        <Button
          v-if="canCreate(query)"
          variant="ghost"
          class="w-full !justify-start"
          :label="__('Add') + ' “' + query.trim() + '”'"
          iconLeft="plus"
          @click="addCustom(query, close)"
        />
      </template>
    </Autocomplete>

    <span v-else-if="!items.length" class="text-sm text-ink-gray-4">—</span>
  </div>
</template>

<script setup>
import Autocomplete from '@/components/frappe-ui/Autocomplete.vue'
import XIcon from '~icons/lucide/x'
import { Button } from 'frappe-ui'
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  options: { type: Array, default: () => [] },
  placeholder: { type: String, default: 'Select…' },
  disabled: { type: Boolean, default: false },
  allowCreate: { type: Boolean, default: true },
})

const emit = defineEmits(['update:modelValue', 'change'])

const items = computed(() =>
  [...new Set((props.modelValue || []).map((v) => String(v).trim()).filter(Boolean))],
)

const normalizedOptions = computed(() =>
  (props.options || []).map((option) =>
    typeof option === 'string'
      ? { label: option, value: option }
      : { label: option.label || option.value, value: option.value },
  ),
)

const availableOptions = computed(() =>
  normalizedOptions.value.filter((option) => !items.value.includes(option.value)),
)

function commit(next) {
  const value = [...new Set(next.map((v) => String(v).trim()).filter(Boolean))]
  emit('update:modelValue', value)
  emit('change', value)
}

function addOption(option) {
  const value = option?.value
  if (value && !items.value.includes(value)) commit([...items.value, value])
}

function remove(item) {
  commit(items.value.filter((value) => value !== item))
}

function canCreate(query) {
  const value = (query || '').trim()
  if (!props.allowCreate || !value) return false
  const lower = value.toLowerCase()
  return ![...items.value, ...normalizedOptions.value.map((o) => o.value)].some(
    (item) => String(item).toLowerCase() === lower,
  )
}

function addCustom(query, close) {
  const value = (query || '').trim()
  if (!value) return
  commit([...items.value, value])
  close?.()
}
</script>
