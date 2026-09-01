<template>
  <div
    class="flex flex-col overflow-hidden rounded-md bg-surface-cards text-base shadow"
  >
    <div class="truncate px-3 py-2 font-medium text-ink-gray-9">
      {{ subject }}
    </div>
    <div
      v-for="(msg, i) in ordered"
      :key="msg.name || i"
      class="border-t border-outline-gray-modals"
    >
      <button
        type="button"
        class="w-full px-3 text-left"
        :class="isOpen(i) ? 'pt-3' : 'py-2 hover:bg-surface-gray-1'"
        @click="toggle(i)"
      >
        <div class="flex items-baseline justify-between gap-2">
          <div class="min-w-0 truncate text-ink-gray-9">
            <span class="font-medium">{{
              msg.data?.sender_full_name || senderName(msg)
            }}</span>
            <span v-if="isOpen(i)" class="ml-1 text-sm text-ink-gray-5">
              &lt;{{ msg.data?.sender }}&gt;
            </span>
            <span v-else class="ml-2 text-sm text-ink-gray-5">
              {{ preview(msg) }}
            </span>
          </div>
          <div class="shrink-0 text-xs text-ink-gray-5">
            {{ formatDate(msg.communication_date || msg.creation, 'MMM D, h:mm a') }}
          </div>
        </div>
      </button>
      <div v-if="isOpen(i)" class="px-3 pb-3">
        <div class="text-sm text-ink-gray-5">
          {{ __('To') }}: {{ msg.data?.recipients }}
        </div>
        <EmailContent :content="msg.data?.content || ''" />
        <div class="mt-2 flex justify-end">
          <Button
            variant="ghost"
            :icon="ReplyIcon"
            :label="__('Reply')"
            @click="reply(msg)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import EmailContent from '@/components/Activities/EmailContent.vue'
import ReplyIcon from '@/components/Icons/ReplyIcon.vue'
import { formatDate } from '@/utils'
import { Button } from 'frappe-ui'
import { computed, ref, watch } from 'vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
})
const emit = defineEmits(['reply'])

const ordered = computed(() =>
  [...props.messages].sort(
    (a, b) =>
      new Date(b.communication_date || b.creation) -
      new Date(a.communication_date || a.creation),
  ),
)

const open = ref(new Set())

watch(
  ordered,
  (list) => {
    open.value = new Set(list.length ? [0] : [])
  },
  { immediate: true },
)

function isOpen(i) {
  return open.value.has(i)
}

function toggle(i) {
  const next = new Set(open.value)
  if (next.has(i)) next.delete(i)
  else next.add(i)
  open.value = next
}

function reply(msg) {
  emit('reply', msg.data)
}

function senderName(msg) {
  const from = msg.data?.sender || ''
  return from.split('@')[0] || from
}

function preview(msg) {
  const html = msg.data?.content || ''
  const text = html
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/\s+/g, ' ')
    .trim()
  return text.slice(0, 80)
}

const subject = computed(() => {
  const first = ordered.value[0]
  return (first?.data?.subject || '').replace(/^(re:\s*)+/i, '')
})
</script>
