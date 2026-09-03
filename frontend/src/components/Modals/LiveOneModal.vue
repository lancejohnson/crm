<template>
  <Dialog v-model="show" :options="{ title: __('Got a live one?') }">
    <template #body-content>
      <DialogDescription class="sr-only">
        {{ __('Send a Mattermost message with a link to this lead.') }}
      </DialogDescription>
      <div class="flex flex-col gap-4">
        <p class="text-sm leading-relaxed text-ink-gray-7">{{ blurb }}</p>

        <div class="rounded-lg bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-7">
          <div class="font-medium text-ink-gray-9">{{ leadName }}</div>
          <div v-if="address" class="truncate">{{ address }}</div>
        </div>

        <!-- Optional. The link is the payload; a sentence of why ("wants to
             close in 2 weeks, price flexible") is what lets Dennis pick up
             the call warm instead of re-asking. -->
        <div>
          <div class="mb-1.5 text-xs text-ink-gray-5">{{ __('Anything to add? (optional)') }}</div>
          <Textarea
            ref="noteInput"
            v-model="note"
            :rows="3"
            :placeholder="__('Motivated, wants to close in 2 weeks…')"
            @keydown="onKeydown"
          />
        </div>

        <ErrorMessage :message="error" />
      </div>
    </template>
    <template #actions>
      <div class="flex w-full items-center gap-2">
        <Button :label="__('Cancel')" :disabled="sending" @click="show = false" />
        <Button
          class="ml-auto"
          variant="solid"
          :label="__('Send to {0}', [targetName])"
          :loading="sending"
          iconLeft="send"
          @click="send"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
/**
 * "Got a live one" — pings the closer (Dennis) in Mattermost with a link to
 * this lead's comps. Thin: the backend decides the recipient, the channel
 * (group with the rep when they have an account, else a direct message) and
 * writes the timeline entry. Mounted wherever a rep might be when they
 * realise the seller is real: the lead header, the mobile lead header, and
 * the comps view (page + Today modal).
 */
import { Button, Dialog, ErrorMessage, Textarea, call, toast } from 'frappe-ui'
import { DialogDescription } from 'reka-ui'
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  lead: { type: String, required: true },
  leadName: { type: String, default: '' },
  address: { type: String, default: '' },
})
const show = defineModel({ type: Boolean, default: false })

const note = ref('')
const error = ref('')
const sending = ref(false)
const noteInput = ref(null)
const target = ref(null)

const targetName = computed(() => target.value?.first_name || target.value?.name || __('Dennis'))
const blurb = computed(() =>
  __(
    'Sends {0} a Mattermost message from you with the lead, the phone number and a link to the comps screen.',
    [targetName.value],
  ),
)

async function loadTarget() {
  if (target.value) return
  try {
    target.value = await call('crm.api.live_one.get_target')
  } catch {
    // The default label is right for this team; a lookup failure is not
    // worth blocking the button over.
  }
}

watch(show, (open) => {
  if (!open) return
  note.value = ''
  error.value = ''
  loadTarget()
  nextTick(() => noteInput.value?.$el?.querySelector('textarea')?.focus())
})

function onKeydown(e) {
  // Cmd/Ctrl+Enter sends; plain Enter is a newline in the note.
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
    e.preventDefault()
    send()
  }
}

async function send() {
  if (sending.value) return
  sending.value = true
  error.value = ''
  try {
    const r = await call('crm.api.live_one.alert', { lead: props.lead, note: note.value })
    toast.success(
      r?.mode === 'group'
        ? __('Sent — {0} and you are in a group chat now', [r.to])
        : __('Sent to {0}', [r?.to || targetName.value]),
    )
    show.value = false
  } catch (e) {
    error.value = e.messages?.[0] || e.message || __('Could not send the alert.')
  } finally {
    sending.value = false
  }
}
</script>
