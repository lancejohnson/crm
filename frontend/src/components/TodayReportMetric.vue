<template>
  <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-3">
    <div class="text-xs text-ink-gray-5">{{ label }}</div>
    <div class="mt-1 text-xl font-semibold" :class="valueClass">{{ value }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, default: '' },
  value: { type: [Number, String], default: 0 },
  tone: { type: String, default: 'gray' },
})

const valueClass = computed(
  () =>
    ({
      green: 'text-ink-green-3',
      orange: 'text-ink-orange-3',
      blue: 'text-ink-blue-3',
      gray: 'text-ink-gray-9',
    })[props.tone] || 'text-ink-gray-9',
)
</script>
