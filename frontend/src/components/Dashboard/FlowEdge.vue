<template>
  <button
    class="group flex items-center gap-2 rounded-md border border-outline-gray-1 bg-surface-white px-2.5 py-1.5 text-sm hover:border-outline-gray-3 hover:bg-surface-gray-2 transition-colors w-full"
    :title="__('Show these leads')"
  >
    <!-- outflow: arrow + count first, then the destination status -->
    <template v-if="direction === 'out'">
      <span class="flex items-center gap-1 text-ink-gray-5 shrink-0">
        <span class="tabular-nums font-medium text-ink-gray-7">{{ count }}</span>
        <LucideArrowRight class="size-3.5" />
      </span>
      <IndicatorIcon :class="color" class="shrink-0" />
      <span class="truncate text-ink-gray-8">{{ label }}</span>
    </template>

    <!-- inflow: source status first, then count + arrow into the stage -->
    <template v-else>
      <IndicatorIcon :class="color" class="shrink-0" />
      <span class="truncate text-ink-gray-8">{{ label }}</span>
      <span class="flex items-center gap-1 text-ink-gray-5 shrink-0 ml-auto">
        <span class="tabular-nums font-medium text-ink-gray-7">{{ count }}</span>
        <LucideArrowRight class="size-3.5" />
      </span>
    </template>
  </button>
</template>

<script setup>
import IndicatorIcon from '@/components/Icons/IndicatorIcon.vue'
import LucideArrowRight from '~icons/lucide/arrow-right'

defineProps({
  stage: { type: String, default: '' },
  label: { type: String, default: '' },
  count: { type: Number, default: 0 },
  direction: { type: String, default: 'out' }, // 'in' | 'out'
  color: { type: String, default: 'text-ink-gray-4' },
})
</script>
