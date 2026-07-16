<template>
  <Dialog v-model="show" :options="{ title: __('Send Text') }">
    <template #body-content>
      <div class="flex flex-col gap-4">
        <FormControl
          v-model="to"
          type="text"
          :label="__('To')"
          :placeholder="__('+1XXXXXXXXXX')"
        />
        <div v-if="linkedNumber" class="text-xs text-ink-gray-5">
          {{ __('Sending from') }}
          <span class="font-medium text-ink-gray-7">
            {{ formatPhone(linkedNumber) }}
          </span>
        </div>
        <div v-else class="flex items-center justify-between gap-2">
          <span class="text-xs text-ink-gray-5">
            {{ __('No Quo number linked to your profile yet.') }}
          </span>
          <Button
            :label="__('Select number')"
            @click="showSelectNumber = true"
          />
        </div>
        <div>
          <div class="mb-1.5 text-xs text-ink-gray-5">{{ __('Message') }}</div>
          <Textarea
            v-model="content"
            :rows="5"
            :placeholder="__('Type your message here...')"
            @keydown.enter.stop="(e) => sendOnCmdEnter(e)"
          />
        </div>
        <ErrorMessage :message="error" />
      </div>
    </template>
    <template #actions>
      <Button
        class="w-full"
        variant="solid"
        :label="__('Send')"
        :loading="sending"
        :disabled="!content.trim() || !to.trim()"
        @click="sendSMS"
      />
    </template>
  </Dialog>
  <SelectQuoNumberModal
    v-model="showSelectNumber"
    @saved="onNumberSaved"
  />
</template>

<script setup>
import SelectQuoNumberModal from '@/components/Modals/SelectQuoNumberModal.vue'
import { myQuoNumber, formatPhone } from '@/composables/quoSender'
import {
  call,
  Dialog,
  FormControl,
  Textarea,
  Button,
  ErrorMessage,
  toast,
} from 'frappe-ui'
import { ref, watch } from 'vue'

const props = defineProps({
  referenceDoc: { type: Object, default: () => ({}) },
  doctype: { type: String, default: 'CRM Lead' },
  options: { type: Object, default: () => ({ afterInsert: () => {} }) },
})

const show = defineModel({ type: Boolean })

const to = ref('')
const content = ref('')
const sending = ref(false)
const error = ref(null)
// the sender's already-linked number (read once when the modal opens); if empty
// a modal asks them to pick their number from the Quo workspace list first
const linkedNumber = ref('')
const fromNumber = ref('')
const showSelectNumber = ref(false)

watch(
  show,
  (open) => {
    if (open) {
      to.value = props.referenceDoc?.mobile_no || props.referenceDoc?.phone || ''
      content.value = ''
      error.value = null
      linkedNumber.value = myQuoNumber()
      fromNumber.value = linkedNumber.value
      if (!linkedNumber.value) showSelectNumber.value = true
    }
  },
  { immediate: true },
)

function onNumberSaved(number) {
  linkedNumber.value = number
  fromNumber.value = number
}

// Texts are lead-scoped. On a deal, send to the originating lead.
function leadName() {
  if (props.doctype === 'CRM Deal') return props.referenceDoc?.lead || ''
  return props.referenceDoc?.name || ''
}

// Cmd/Ctrl+Enter sends; plain Enter inserts a newline.
function sendOnCmdEnter(event) {
  if (event.metaKey || event.ctrlKey) {
    event.preventDefault()
    sendSMS()
  }
}

async function sendSMS() {
  const message = content.value.trim()
  if (!message || sending.value) return
  const lead = leadName()
  if (!lead) {
    error.value = __('No lead linked to text.')
    return
  }
  if (!to.value.trim()) {
    error.value = __("Enter the recipient's mobile number.")
    return
  }
  if (!fromNumber.value) {
    error.value = __('Select a Quo number to send from.')
    return
  }
  sending.value = true
  error.value = null
  try {
    await call('send-text', {
      reference_doctype: 'CRM Lead',
      reference_docname: lead,
      content: message,
      to: to.value,
      from_number: fromNumber.value,
    })
    toast.success(__('Text sent'))
    show.value = false
    props.options.afterInsert?.()
  } catch (e) {
    error.value = e.messages?.[0] || __('Failed to send text')
  } finally {
    sending.value = false
  }
}
</script>
