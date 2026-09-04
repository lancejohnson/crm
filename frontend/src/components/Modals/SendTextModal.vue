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
        <div v-if="toChoices.length > 1" class="flex flex-wrap gap-1.5">
          <button
            v-for="p in toChoices"
            :key="p.last10"
            type="button"
            class="rounded-full border px-2 py-0.5 text-xs"
            :class="
              toLast10 === p.last10
                ? 'border-outline-gray-4 bg-surface-gray-2 text-ink-gray-8'
                : 'border-outline-gray-2 text-ink-gray-6 hover:border-outline-gray-3'
            "
            @click="to = p.number"
          >
            {{ formatPhone(p.number) }}
          </button>
        </div>
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
        <TextPresetChips :lead="leadName()" @pick="applyPreset" />
        <div>
          <div class="mb-1.5 text-xs text-ink-gray-5">{{ __('Message') }}</div>
          <Textarea
            ref="messageInput"
            v-model="content"
            :rows="5"
            :placeholder="__('Type your message here...')"
            @keydown.enter.stop="(e) => sendOnCmdEnter(e)"
          />
          <div
            v-if="unfilled"
            class="mt-1.5 text-xs font-medium text-ink-amber-3"
          >
            {{ __('Fill in the [ ? ] parts before sending — the lead is missing that detail.') }}
          </div>
        </div>
        <ErrorMessage :message="error" />
      </div>
    </template>
    <template #actions>
      <div v-if="showOutcomeActions" class="flex w-full items-center gap-2">
        <Button
          :label="__('Skip')"
          :disabled="sending"
          @click="skip"
        />
        <Button
          class="ml-auto"
          :label="__('Send')"
          :loading="sending && !finishing"
          :disabled="!canSend"
          @click="sendSMS(false)"
        />
        <Button
          variant="solid"
          :label="__('Send & finish')"
          :loading="sending && finishing"
          :disabled="!canSend"
          @click="sendSMS(true)"
        />
      </div>
      <Button
        v-else
        class="w-full"
        variant="solid"
        :label="__('Send')"
        :loading="sending"
        :disabled="!canSend"
        @click="sendSMS(false)"
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
import TextPresetChips from '@/components/TextPresetChips.vue'
import { hasUnfilled } from '@/composables/textPresets'
import { myQuoNumber, formatPhone } from '@/composables/quoSender'
import { listLeadPhones, primaryLeadPhone } from '@/utils/leadPhones'
import {
  call,
  Dialog,
  FormControl,
  Textarea,
  Button,
  ErrorMessage,
  toast,
} from 'frappe-ui'
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  referenceDoc: { type: Object, default: () => ({}) },
  doctype: { type: String, default: 'CRM Lead' },
  options: { type: Object, default: () => ({ afterInsert: () => {} }) },
  showOutcomeActions: { type: Boolean, default: false },
})

const emit = defineEmits(['finish', 'skip'])
const show = defineModel({ type: Boolean })

const to = ref('')
const content = ref('')
const sending = ref(false)
const finishing = ref(false)
const error = ref(null)
const messageInput = ref(null)
// the sender's already-linked number (read once when the modal opens); if empty
// a modal asks them to pick their number from the Quo workspace list first
const linkedNumber = ref('')
const fromNumber = ref('')
const showSelectNumber = ref(false)

watch(
  show,
  (open) => {
    if (open) {
      to.value = primaryLeadPhone(props.referenceDoc)
      content.value = ''
      error.value = null
      linkedNumber.value = myQuoNumber()
      fromNumber.value = linkedNumber.value
      if (!linkedNumber.value) showSelectNumber.value = true
      nextTick(() => {
        messageInput.value?.el?.focus?.()
        messageInput.value?.$el?.querySelector?.('textarea')?.focus?.()
      })
    }
  },
  { immediate: true },
)

const toChoices = computed(() => listLeadPhones(props.referenceDoc))
const toLast10 = computed(() =>
  String(to.value || '').replace(/\D/g, '').slice(-10),
)

const unfilled = computed(() => hasUnfilled(content.value))
const canSend = computed(
  () =>
    !sending.value &&
    !!content.value.trim() &&
    !!to.value.trim() &&
    !unfilled.value,
)

// A preset chip replaces the draft with the filled-in text and puts the cursor
// at the end (or on the first [ ? ] marker, which is what needs fixing).
function applyPreset(text) {
  content.value = text
  nextTick(() => {
    const el =
      messageInput.value?.el ||
      messageInput.value?.$el?.querySelector?.('textarea')
    if (!el) return
    el.focus()
    const m = text.match(/\[[a-z ]+\?\]/)
    if (m) el.setSelectionRange(m.index, m.index + m[0].length)
    else el.setSelectionRange(text.length, text.length)
  })
}

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

function skip() {
  if (sending.value) return
  show.value = false
  emit('skip')
}

async function sendSMS(markFinished = false) {
  const message = content.value.trim()
  if (!message || sending.value || unfilled.value) return
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
  finishing.value = markFinished
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
    if (markFinished) emit('finish')
  } catch (e) {
    error.value = e.messages?.[0] || __('Failed to send text')
  } finally {
    sending.value = false
    finishing.value = false
  }
}
</script>
