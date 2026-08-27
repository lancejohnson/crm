<template>
  <div
    class="flex flex-col rounded-md bg-surface-cards px-3 py-2 text-base shadow"
  >
    <div class="truncate pb-2 font-medium text-ink-gray-9">
      {{ subject }}
    </div>
    <div
      v-for="(msg, i) in ordered"
      :key="msg.name || i"
      class="border-t border-outline-gray-modals py-3"
    >
      <div class="mb-1 flex items-baseline justify-between gap-2">
        <div class="min-w-0 truncate text-ink-gray-9">
          <span class="font-medium">{{
            msg.data?.sender_full_name || msg.data?.sender
          }}</span>
          <span class="ml-1 text-sm text-ink-gray-5">
            &lt;{{ msg.data?.sender }}&gt;
          </span>
        </div>
        <div class="shrink-0 text-xs text-ink-gray-5">
          {{ formatDate(msg.communication_date || msg.creation, 'MMM D, h:mm a') }}
        </div>
      </div>
      <div class="text-sm text-ink-gray-5">
        {{ __('To') }}: {{ msg.data?.recipients }}
      </div>
      <EmailContent :content="msg.data?.content || ''" />
    </div>
  </div>
</template>

<script setup>
import EmailContent from '@/components/Activities/EmailContent.vue'
import { formatDate } from '@/utils'
import { computed } from 'vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
})

const ordered = computed(() =>
  [...props.messages].sort(
    (a, b) =>
      new Date(a.communication_date || a.creation) -
      new Date(b.communication_date || b.creation),
  ),
)

const subject = computed(() => {
  const last = ordered.value[ordered.value.length - 1]
  return (last?.data?.subject || '').replace(/^(re:\s*)+/i, '')
})
</script>
