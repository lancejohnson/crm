<template>
  <div class="flex flex-col gap-1">
    <div v-if="label" class="text-sm text-ink-gray-6">{{ label }}</div>
    <div
      v-if="modelValue"
      class="flex items-center gap-2 rounded-md border border-outline-gray-2 px-2 py-1.5 text-sm"
    >
      <span class="min-w-0 flex-1 truncate" :title="display">{{ display }}</span>
      <button
        type="button"
        class="shrink-0 text-ink-gray-5 hover:text-ink-gray-8"
        :title="__('Unlink')"
        @click="clear"
      >
        <FeatherIcon name="x" class="size-3.5" />
      </button>
    </div>
    <Autocomplete
      v-else
      :key="key"
      :options="options"
      :placeholder="placeholder || __('Search a lead by name or address…')"
      @update:query="onQuery"
      @update:modelValue="onPick"
    />
  </div>
</template>

<script setup>
import Autocomplete from '@/components/frappe-ui/Autocomplete.vue'
import { FeatherIcon, call } from 'frappe-ui'
import { useDebounceFn } from '@vueuse/core'
import { computed, ref } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  leadName: { type: String, default: '' },
  label: { type: String, default: '' },
  placeholder: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'update:leadName'])

const options = ref([])
const key = ref(0)
const display = computed(
  () => props.leadName || props.modelValue || '',
)

const search = useDebounceFn(async (q) => {
  try {
    const rows = await call('crm.api.properties.search_leads', { q: q || '' })
    options.value = (rows || []).map((r) => ({
      label: [r.lead_name, r.property_address].filter(Boolean).join(' · ') || r.name,
      value: r.name,
      lead_name: r.lead_name || '',
    }))
  } catch {
    options.value = []
  }
}, 200)

function onQuery(q) {
  search(q)
}
function onPick(opt) {
  const name = opt?.value || ''
  if (!name) return
  emit('update:modelValue', name)
  emit('update:leadName', opt.lead_name || opt.label || '')
  key.value++
  options.value = []
}
function clear() {
  emit('update:modelValue', '')
  emit('update:leadName', '')
  key.value++
}
</script>
