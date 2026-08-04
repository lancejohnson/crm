<template>
  <Dialog
    v-model="show"
    :options="{ title: __('Why is this buyer not interested?') }"
    @close="cancel"
  >
    <template #body-content>
      <div class="-mt-3 mb-4 text-p-base text-ink-gray-7">
        <span v-if="buyerName" class="font-medium text-ink-gray-9">{{
          buyerName
        }}</span>
        <span v-if="buyerName"> · </span>{{ __('Select all that apply') }}
      </div>

      <div class="flex max-h-80 flex-col gap-1.5 overflow-y-auto pr-1">
        <button
          v-for="reason in BUYER_REJECTION_REASONS"
          :key="reason.value"
          type="button"
          :aria-pressed="selected.includes(reason.value)"
          class="flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left text-base transition-colors"
          :class="
            selected.includes(reason.value)
              ? 'border-outline-orange-2 bg-surface-orange-1 text-ink-gray-9'
              : 'border-transparent bg-surface-gray-1 text-ink-gray-7 hover:bg-surface-gray-2'
          "
          @click="toggle(reason.value)"
        >
          <BuyerRejectionReasonBadge :reason="reason.value" />
          <span class="flex-1">{{ reason.value }}</span>
          <CheckIcon
            v-if="selected.includes(reason.value)"
            class="size-4 shrink-0 text-ink-orange-3"
          />
        </button>
      </div>

      <button
        v-if="!noteVisible"
        type="button"
        class="mt-4 flex items-center gap-2 text-sm text-ink-gray-6 hover:text-ink-gray-9"
        @click="noteVisible = true"
      >
        <PlusIcon class="size-4" />
        {{ __('Add a note') }}
      </button>
      <div v-else class="mt-4">
        <div class="mb-1.5 text-sm text-ink-gray-5">
          {{ __('Note (optional)') }}
        </div>
        <textarea
          v-model="note"
          class="min-h-24 w-full resize-y rounded border border-outline-gray-2 bg-surface-white px-3 py-2 text-base text-ink-gray-9 focus:border-outline-gray-4 focus:outline-none"
          :placeholder="__('Add context for the team…')"
          maxlength="1000"
          autofocus
        />
      </div>
    </template>

    <template #actions>
      <div class="flex items-center justify-between gap-3">
        <ErrorMessage :message="error" />
        <div class="ml-auto flex gap-2">
          <Button :label="__('Cancel')" :disabled="saving" @click="cancel" />
          <Button
            variant="solid"
            :label="__('Submit')"
            :loading="saving"
            @click="save"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import BuyerRejectionReasonBadge from '@/components/BuyerRejectionReasonBadge.vue'
import { BUYER_REJECTION_REASONS } from '@/utils/buyerRejectionReasons'
import CheckIcon from '~icons/lucide/check'
import PlusIcon from '~icons/lucide/plus'
import { Dialog } from 'frappe-ui'
import { ref } from 'vue'

const props = defineProps({
  buyerName: { type: String, default: '' },
  initialReasons: { type: Array, default: () => [] },
  initialNote: { type: String, default: '' },
  onConfirm: { type: Function, required: true },
  onCancel: { type: Function, default: null },
})

const show = defineModel({ type: Boolean })
const selected = ref([...props.initialReasons])
const note = ref(props.initialNote || '')
const noteVisible = ref(!!props.initialNote)
const error = ref('')
const saving = ref(false)
let saved = false
let cancelled = false

function toggle(reason) {
  error.value = ''
  selected.value = selected.value.includes(reason)
    ? selected.value.filter((value) => value !== reason)
    : [...selected.value, reason]
}

function cancel() {
  if (saving.value || saved || cancelled) return
  cancelled = true
  show.value = false
  props.onCancel?.()
}

async function save() {
  if (!selected.value.length) {
    error.value = __('Select at least one reason')
    return
  }
  saving.value = true
  error.value = ''
  try {
    await props.onConfirm({
      reasons: selected.value,
      note: note.value.trim(),
    })
    saved = true
    show.value = false
  } catch (e) {
    error.value = e.messages?.[0] || e.message || __('Could not save reasons')
  } finally {
    saving.value = false
  }
}
</script>
