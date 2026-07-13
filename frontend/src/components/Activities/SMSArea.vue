<template>
  <div class="pb-3">
    <div
      v-for="(sms, i) in messages"
      :key="sms.name"
      class="activity group flex gap-2"
      :class="[
        sms.type == 'Outgoing' ? 'flex-row-reverse' : '',
        startsRun(i) ? 'mt-3' : 'mt-0.5',
        i == 0 ? '!mt-0' : '',
      ]"
    >
      <!-- who sent it: lead avatar on the left, teammate avatar on the right,
           shown once at the end of each run of consecutive messages -->
      <div class="w-6 shrink-0 self-end">
        <template v-if="endsRun(i)">
          <UserAvatar
            v-if="sms.type == 'Outgoing' && sms.sender"
            :user="sms.sender"
            size="md"
          />
          <Avatar
            v-else-if="sms.type != 'Outgoing'"
            :image="contactImage"
            :label="contactName || __('Lead')"
            size="md"
          />
        </template>
      </div>
      <div
        class="flex max-w-[85%] flex-col"
        :class="sms.type == 'Outgoing' ? 'items-end' : 'items-start'"
      >
        <div
          v-if="startsRun(i) && senderLabel(sms)"
          class="mb-0.5 px-1 text-xs text-ink-gray-5"
        >
          {{ senderLabel(sms) }}
        </div>
        <div
          :id="sms.name"
          class="group/message relative rounded-lg p-1.5 pl-2 text-base shadow-sm whitespace-pre-wrap"
          :class="
            sms.type == 'Outgoing'
              ? 'bg-surface-blue-2 text-white'
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
              :class="
                sms.type == 'Outgoing' ? 'text-white' : 'text-ink-gray-5'
              "
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
  </div>
</template>

<script setup>
import CheckIcon from '@/components/Icons/CheckIcon.vue'
import DoubleCheckIcon from '@/components/Icons/DoubleCheckIcon.vue'
import SMSMedia from '@/components/Activities/SMSMedia.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { formatDate } from '@/utils'
import { Tooltip, Badge, Avatar } from 'frappe-ui'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  contactName: { type: String, default: '' },
  contactImage: { type: String, default: '' },
})

// a "run" = consecutive messages from the same person (same direction + same
// sending teammate); the name shows above a run, the avatar at its end
function sameAuthor(a, b) {
  return a && b && a.type == b.type && a.sender == b.sender
}

function startsRun(i) {
  return !sameAuthor(props.messages[i - 1], props.messages[i])
}

function endsRun(i) {
  return !sameAuthor(props.messages[i], props.messages[i + 1])
}

function senderLabel(sms) {
  if (sms.type == 'Outgoing') return sms.sender_name
  return props.contactName
}
</script>
