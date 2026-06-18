<template>
  <div>
    <div
      v-for="sms in messages"
      :key="sms.name"
      class="activity group flex gap-2 mb-3"
      :class="sms.type == 'Outgoing' ? 'flex-row-reverse' : ''"
    >
      <div
        :id="sms.name"
        class="group/message relative max-w-[90%] rounded-md p-1.5 pl-2 text-base shadow-sm whitespace-pre-wrap"
        :class="
          sms.type == 'Outgoing'
            ? 'bg-surface-gray-7 text-ink-white'
            : 'bg-surface-gray-2 text-ink-gray-9'
        "
      >
        <Badge
          v-if="sms.status == 'failed' || sms.status == 'undelivered'"
          theme="red"
          :label="sms.status"
          class="absolute -top-2 right-0"
        />
        <SMSMedia
          v-if="sms.media?.length"
          :media="sms.media"
          :class="sms.message ? 'mb-1' : ''"
        />
        <div class="flex gap-2 justify-between">
          <div v-if="sms.message" class="break-words">{{ sms.message }}</div>
          <div
            class="-mb-1 flex shrink-0 items-end gap-1"
            :class="sms.type == 'Outgoing' ? 'text-ink-white' : 'text-ink-gray-5'"
          >
            <Tooltip :text="formatDate(sms.creation, 'ddd, MMM D, YYYY')">
              <div class="text-2xs">
                {{ formatDate(sms.creation, 'hh:mm a') }}
              </div>
            </Tooltip>
            <div v-if="sms.type == 'Outgoing'">
              <CheckIcon
                v-if="['sent', 'queued', 'success'].includes(sms.status)"
                class="size-4"
              />
              <DoubleCheckIcon
                v-else-if="['delivered', 'read'].includes(sms.status)"
                class="size-4"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import CheckIcon from '@/components/Icons/CheckIcon.vue'
import DoubleCheckIcon from '@/components/Icons/DoubleCheckIcon.vue'
import SMSMedia from '@/components/Activities/SMSMedia.vue'
import { formatDate } from '@/utils'
import { Tooltip, Badge } from 'frappe-ui'

defineProps({
  messages: { type: Array, default: () => [] },
})
</script>
