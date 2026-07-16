<template>
  <div class="flex flex-col" v-bind="$attrs">
    <!-- shown only when the sender has no Quo number yet: pick one to text from -->
    <div
      v-if="!linkedNumber"
      class="flex items-center justify-between gap-2 px-3 pt-2.5 sm:px-10"
    >
      <span class="text-base text-ink-gray-6">
        {{ __('No Quo number linked to your profile yet.') }}
      </span>
      <Button
        :label="__('Select number')"
        @click="showSelectNumber = true"
      />
    </div>
    <div class="flex items-end gap-2 px-3 py-2.5 sm:px-10">
      <Textarea
        ref="textareaRef"
        v-model="content"
        type="textarea"
        class="min-h-8 w-full"
        :rows="rows"
        :placeholder="placeholder"
        @focus="rows = 6"
        @blur="rows = 1"
        @keydown.enter.stop="(e) => sendOnCmdEnter(e)"
      />
      <Button
        variant="solid"
        :loading="sending"
        :disabled="!content.trim() || !fromNumber"
        :label="__('Send')"
        @click="sendSMS()"
      />
    </div>
  </div>
  <SelectQuoNumberModal
    v-model="showSelectNumber"
    @saved="onNumberSaved"
  />
</template>

<script setup>
import SelectQuoNumberModal from '@/components/Modals/SelectQuoNumberModal.vue'
import { myQuoNumber } from '@/composables/quoSender'
import { call, Textarea, Button, toast } from 'frappe-ui'
import { ref, onMounted } from 'vue'

const props = defineProps({
  doctype: { type: String, default: '' },
})

const doc = defineModel({ type: Object, default: () => ({}) })
// the messages resource, so we can refresh the thread after sending
const sms = defineModel('sms', { type: Object, default: () => ({}) })

const rows = ref(1)
const textareaRef = ref(null)
const content = ref('')
const sending = ref(false)
const placeholder = ref(__('Type your message here...'))

// sender's linked Quo number; if empty, a modal asks them to pick their number
// from the Quo workspace list (saved to their profile) before they can send
const linkedNumber = ref('')
const fromNumber = ref('')
const showSelectNumber = ref(false)

onMounted(() => {
  linkedNumber.value = myQuoNumber()
  fromNumber.value = linkedNumber.value
  if (!linkedNumber.value) showSelectNumber.value = true
})

function onNumberSaved(number) {
  linkedNumber.value = number
  fromNumber.value = number
}

function show() {
  // nothing to focus until a number is chosen
  if (textareaRef.value?.el) textareaRef.value.el.focus()
}

// Texts are lead-scoped. On a deal, send to the originating lead.
function leadName() {
  if (props.doctype === 'CRM Deal') return doc.value.lead || ''
  return doc.value.name
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
  if (!fromNumber.value) {
    toast.error(__('Select a Quo number to send from.'))
    return
  }
  const lead = leadName()
  if (!lead) {
    toast.error(__('No lead linked to text.'))
    return
  }
  sending.value = true
  try {
    await call('send-text', {
      reference_doctype: 'CRM Lead',
      reference_docname: lead,
      content: message,
      from_number: fromNumber.value,
    })
    content.value = ''
    textareaRef.value?.el?.blur()
    // once they've picked, they're linked going forward
    linkedNumber.value = fromNumber.value
    sms.value?.reload?.()
  } catch (error) {
    toast.error(error.messages?.[0] || __('Failed to send text'))
  } finally {
    sending.value = false
  }
}

defineExpose({ show })
</script>
