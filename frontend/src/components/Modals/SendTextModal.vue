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
        <div v-else class="flex flex-col gap-1">
          <QuoFromSelect v-model="fromNumber" :label="__('Send from')" />
          <div class="text-xs text-ink-gray-5">
            {{ __('Pick the Quo number to text from — saved to your profile.') }}
          </div>
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
        :disabled="!content.trim()"
        @click="sendSMS"
      />
    </template>
  </Dialog>
</template>

<script setup>
import QuoFromSelect from '@/components/QuoFromSelect.vue'
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
// the picker is shown and the chosen number is passed + saved on send
const linkedNumber = ref('')
const fromNumber = ref('')

watch(
  show,
  (open) => {
    if (open) {
      to.value = props.referenceDoc?.mobile_no || props.referenceDoc?.phone || ''
      content.value = ''
      error.value = null
      linkedNumber.value = myQuoNumber()
      fromNumber.value = linkedNumber.value
    }
  },
  { immediate: true },
)

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
