<template>
  <Tooltip :text="displayName">
    <div class="relative h-7 w-7 shrink-0">
      <img
        v-if="photo"
        :src="photo"
        :alt="displayName"
        class="h-7 w-7 rounded-full object-cover"
      />
      <div
        v-else
        class="flex h-7 w-7 select-none items-center justify-center rounded-full bg-surface-gray-3 text-[10px] font-medium uppercase text-ink-gray-6"
      >
        {{ initials }}
      </div>
      <div
        class="absolute -bottom-1 -right-1 flex size-4 items-center justify-center rounded-full ring-2 ring-surface-white"
        :class="badge.classes"
      >
        <component :is="badge.icon" class="size-2.5" />
      </div>
    </div>
  </Tooltip>
</template>

<script setup>
import CommentIcon from '@/components/Icons/CommentIcon.vue'
import EditIcon from '@/components/Icons/EditIcon.vue'
import InboundCallIcon from '@/components/Icons/InboundCallIcon.vue'
import OutboundCallIcon from '@/components/Icons/OutboundCallIcon.vue'
import Email2Icon from '@/components/Icons/Email2Icon.vue'
import TaskIcon from '@/components/Icons/TaskIcon.vue'
import MoneyIcon from '@/components/Icons/MoneyIcon.vue'
import DetailsIcon from '@/components/Icons/DetailsIcon.vue'
import AttachmentIcon from '@/components/Icons/AttachmentIcon.vue'
import ArrowUpRightIcon from '@/components/Icons/ArrowUpRightIcon.vue'
import DotIcon from '@/components/Icons/DotIcon.vue'
import { usersStore } from '@/stores/users'
import { Tooltip } from 'frappe-ui'
import { computed, markRaw } from 'vue'

const props = defineProps({
  // a User email → resolved via the users store; else image/label render the lead
  user: { type: String, default: '' },
  image: { type: String, default: '' },
  label: { type: String, default: '' },
  type: { type: String, default: '' },
})

const { getUser } = usersStore()

const displayName = computed(() => {
  if (props.user) return getUser(props.user).full_name || props.user
  return props.label || __('Lead')
})

const photo = computed(() => {
  if (props.user) return getUser(props.user).user_image
  return props.image
})

// "Dennis Szafran" → DS; single word → its first two letters; phone → last 2 digits
const initials = computed(() => {
  const name = (displayName.value || '').trim()
  if (!name) return '?'
  const words = name.split(/\s+/).filter((w) => /[a-z]/i.test(w[0]))
  if (words.length >= 2) return words[0][0] + words[words.length - 1][0]
  if (words.length == 1) return words[0].slice(0, 2)
  return name.replace(/\D/g, '').slice(-2) || '?'
})

// one hue per activity family: blue=text, cyan=call, amber=comment,
// green=task, violet=docs & money, orange=status, pink=email
const BADGES = {
  outgoing_text: [CommentIcon, 'bg-surface-blue-1 text-ink-blue-3'],
  incoming_text: [CommentIcon, 'bg-surface-blue-1 text-ink-blue-3'],
  outgoing_call: [OutboundCallIcon, 'bg-surface-cyan-1 text-ink-cyan-1'],
  incoming_call: [InboundCallIcon, 'bg-surface-cyan-1 text-ink-cyan-1'],
  comment: [EditIcon, 'bg-surface-amber-1 text-ink-amber-2'],
  communication: [Email2Icon, 'bg-surface-pink-1 text-ink-pink-1'],
  task: [TaskIcon, 'bg-surface-green-1 text-ink-green-2'],
  tax_pull: [MoneyIcon, 'bg-surface-violet-1 text-ink-violet-1'],
  agreement: [DetailsIcon, 'bg-surface-violet-1 text-ink-violet-1'],
  underwriting: [DetailsIcon, 'bg-surface-violet-1 text-ink-violet-1'],
  attachment_log: [AttachmentIcon, 'bg-surface-gray-2 text-ink-gray-5'],
  changed: [ArrowUpRightIcon, 'bg-surface-orange-1 text-ink-gray-7'],
  added: [ArrowUpRightIcon, 'bg-surface-orange-1 text-ink-gray-7'],
  removed: [ArrowUpRightIcon, 'bg-surface-orange-1 text-ink-gray-7'],
  creation: [DotIcon, 'bg-surface-gray-2 text-ink-gray-5'],
}

const badge = computed(() => {
  const [icon, classes] = BADGES[props.type] || BADGES.creation
  return { icon: markRaw(icon), classes }
})
</script>
