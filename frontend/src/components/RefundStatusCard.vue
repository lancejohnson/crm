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
            {{ __(localStatus || 'To Request') }}
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
  </div>
</template>

<script setup>
import { Badge, Button, Dropdown, FeatherIcon, FormControl, call, toast } from 'frappe-ui'
import { computed, ref, watch } from 'vue'

const STATUSES = ['To Request', 'Requested', 'Waiting on us', 'Waiting on them', 'Complete']

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
    label: __(value),
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
</script>
