<template>
  <div class="border-t px-5 py-4">
    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-2 text-base font-medium text-ink-gray-8">
        <FeatherIcon name="rotate-ccw" class="size-4 text-ink-gray-7" />
        {{ __('Refund') }}
      </div>
      <Badge
        v-if="refundable"
        variant="subtle"
        theme="orange"
        :label="__('Refundable')"
      />
    </div>

    <template v-if="refundable">
      <div class="mt-3 flex items-center justify-between gap-2">
        <span class="text-sm text-ink-gray-6">{{ __('Board status') }}</span>
        <Dropdown :options="statusOptions" placement="bottom-end">
          <button
            class="flex h-7 items-center gap-1 rounded-md bg-surface-gray-2 px-2.5 text-sm font-medium text-ink-gray-7 hover:bg-surface-gray-3"
            :disabled="saving"
          >
            {{ refundDot(localStatus || 'To Request') }} {{ __(localStatus || 'To Request') }}
            <FeatherIcon name="chevron-down" class="size-3 text-ink-gray-5" />
          </button>
        </Dropdown>
      </div>

      <label class="mt-3 flex cursor-pointer items-start gap-2 text-sm text-ink-gray-7">
        <FormControl
          type="checkbox"
          :modelValue="notInProvider"
          :disabled="saving"
          @update:modelValue="setNotInProvider"
        />
        <span>
          <span class="font-medium text-ink-gray-8">{{ __('Not in provider refund form') }}</span>
          <span class="mt-0.5 block text-xs leading-relaxed text-ink-gray-5">
            {{ __('The lead is missing from the normal refund request list.') }}
          </span>
        </span>
      </label>

      <label class="mt-3 flex cursor-pointer items-start gap-2 text-sm text-ink-gray-7">
        <FormControl
          type="checkbox"
          :modelValue="manualTicket"
          :disabled="saving"
          @update:modelValue="setManualTicket"
        />
        <span>
          <span class="font-medium text-ink-gray-8">{{ __('Manual support ticket submitted') }}</span>
          <span class="mt-0.5 block text-xs leading-relaxed text-ink-gray-5">
            {{ __('Check after filing the fallback general support ticket.') }}
          </span>
        </span>
      </label>

      <Button
        class="mt-3"
        variant="ghost"
        :label="__('Remove from Refunds')"
        :loading="saving"
        @click="remove"
      />
    </template>

    <template v-else>
      <p class="mt-1 text-xs leading-relaxed text-ink-gray-5">
        {{ __('Keep following up while tracking this lead on the Refunds board.') }}
      </p>
      <Button
        class="mt-3"
        variant="outline"
        :label="__('Mark refundable')"
        :loading="saving"
        @click="mark"
      />
    </template>

    <!-- The proof a refund request needs: every dial on this lead with its
         recording link, as a CSV to attach or a numbered list to paste into
         the provider's form. Shown in both states -- the export is how a rep
         decides the lead is refundable in the first place. -->
    <div class="mt-4 border-t border-outline-gray-1 pt-3">
      <div class="flex items-center justify-between gap-2">
        <span class="text-sm font-medium text-ink-gray-8">{{ __('Call history') }}</span>
        <span v-if="history" class="text-xs text-ink-gray-5" :title="historyTitle">
          {{ historyLabel }}
        </span>
      </div>
      <p class="mt-0.5 text-xs leading-relaxed text-ink-gray-5">
        {{ __('Every call on this lead with its recording link, for the refund request.') }}
      </p>
      <div class="mt-2 flex flex-wrap gap-1.5">
        <Button
          variant="subtle"
          size="sm"
          :label="__('Download CSV')"
          iconLeft="download"
          @click="download('csv')"
        />
        <Button
          variant="subtle"
          size="sm"
          :label="copied ? __('Copied') : __('Copy list')"
          :iconLeft="copied ? 'check' : 'copy'"
          :loading="copying"
          :title="__('Copy the numbered list with recording links, for pasting into a ticket')"
          @click="copyList"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { Badge, Button, Dropdown, FeatherIcon, FormControl, call, toast } from 'frappe-ui'
import { computed, onMounted, ref, watch } from 'vue'
import { copyToClipboard } from '@/utils'

import { REFUND_STATUSES as STATUSES, refundDot } from '@/utils/refunds'

const props = defineProps({
  lead: { type: String, required: true },
  refundable: { type: [Boolean, Number], default: false },
  notInProvider: { type: [Boolean, Number], default: false },
  manualTicket: { type: [Boolean, Number], default: false },
  status: { type: String, default: '' },
})
const emit = defineEmits(['saved'])
const saving = ref(false)
const localStatus = ref(props.status || 'To Request')

watch(
  () => props.status,
  (value) => (localStatus.value = value || 'To Request'),
)

const statusOptions = computed(() =>
  STATUSES.map((value) => ({
    label: `${refundDot(value)} ${__(value)}`,
    onClick: () => setStatus(value),
  })),
)

async function update(values) {
  saving.value = true
  try {
    await call('crm.api.refunds.set_refund_state', { lead: props.lead, ...values })
    emit('saved')
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not update the refund.'))
  } finally {
    saving.value = false
  }
}

function mark() {
  update({ refundable: 1 })
}

function remove() {
  update({ refundable: 0 })
}

function setNotInProvider(value) {
  update({ not_in_provider: value ? 1 : 0 })
}

function setManualTicket(value) {
  update({ manual_ticket: value ? 1 : 0 })
}

function setStatus(value) {
  localStatus.value = value
  update({ status: value })
}

// --- call history export ---------------------------------------------------
const history = ref(null)
const copying = ref(false)
const copied = ref(false)

async function loadHistory() {
  try {
    history.value = await call('crm.api.call_export.get_call_history', { lead: props.lead })
  } catch {
    history.value = null
  }
}
onMounted(loadHistory)
watch(() => props.lead, loadHistory)

const historyLabel = computed(() => {
  const s = history.value?.summary
  if (!s) return ''
  return __('{0} calls · {1} recorded', [s.total, s.with_recording])
})
const historyTitle = computed(() => {
  const s = history.value?.summary
  if (!s) return ''
  const bits = [
    __('{0} outgoing', [s.outgoing]),
    __('{0} incoming', [s.incoming]),
    __('{0} connected', [s.connected]),
  ]
  if (s.first) bits.push(`${s.first} – ${s.last}`)
  return bits.join(' · ')
})

function download(fmt) {
  const url = `/api/method/crm.api.call_export.export_call_history?lead=${encodeURIComponent(props.lead)}&fmt=${fmt}`
  window.open(url, '_blank')
}

async function copyList() {
  // Copy synchronously inside the click when the list is already here --
  // Safari drops a clipboard write that waits on a fetch first. The refresh
  // afterwards keeps the NEXT copy current (a call logged since the card
  // opened belongs on a list that claims to be complete).
  if (history.value?.text) {
    copyToClipboard(history.value.text)
    copied.value = true
    setTimeout(() => (copied.value = false), 2500)
    loadHistory()
    return
  }
  copying.value = true
  try {
    const r = await call('crm.api.call_export.get_call_history', { lead: props.lead })
    history.value = r
    copyToClipboard(r.text)
    copied.value = true
    setTimeout(() => (copied.value = false), 2500)
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not copy the call list.'))
  } finally {
    copying.value = false
  }
}
</script>
