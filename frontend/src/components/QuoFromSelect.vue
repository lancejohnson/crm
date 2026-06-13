<template>
  <FormControl
    type="select"
    :model-value="modelValue"
    :label="label"
    :options="options"
    @update:model-value="(v) => emit('update:modelValue', v)"
  />
</template>

<script setup>
import { FormControl } from 'frappe-ui'
import { computed, onMounted } from 'vue'
import { quoNumbers, formatPhone } from '@/composables/quoSender'

defineProps({
  modelValue: { type: String, default: '' },
  label: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const options = computed(() => [
  { label: __('Select a Quo number'), value: '' },
  ...(quoNumbers.data || []).map((n) => ({
    label: formatPhone(n.number) + (n.name ? ` — ${n.name}` : ''),
    value: n.number,
  })),
])

onMounted(() => {
  if (!quoNumbers.data && !quoNumbers.loading) quoNumbers.fetch()
})
</script>
