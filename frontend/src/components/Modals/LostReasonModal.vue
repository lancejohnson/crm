<template>
  <Dialog
    v-model="show"
    :options="{ title: modalTitle }"
    @close="cancel"
  >
    <template #body-content>
      <div class="-mt-3 mb-4 text-p-base text-ink-gray-7">
        {{ helperText }}
      </div>
      <div class="flex flex-col gap-3">
        <FormControl
          v-if="isRefundPool"
          type="checkbox"
          :label="__('This lead is refundable')"
          :modelValue="refundable"
          @update:modelValue="onRefundableToggle"
        />
        <div>
          <div class="mb-2 text-sm text-ink-gray-5">
            {{ reasonLabel }}
            <span class="text-ink-red-2">*</span>
          </div>
          <Link
            ref="linkRef"
            class="form-control flex-1 truncate"
            :value="lostReason"
            doctype="CRM Lost Reason"
            :filters="reasonFilters"
            :onCreate="onCreate"
            @change="(v) => (lostReason = v)"
          />
        </div>
        <div>
          <div class="mb-2 text-sm text-ink-gray-5">
            {{ __('Lost Notes') }}
            <span v-if="lostReason.startsWith('Other')" class="text-ink-red-2"
              >*</span
            >
          </div>
          <FormControl
            class="form-control flex-1 truncate"
            type="textarea"
            :value="lostNotes"
            @change="(e) => (lostNotes = e.target.value)"
          />
        </div>
      </div>
    </template>
    <template #actions>
      <div class="flex justify-between items-center gap-2">
        <div><ErrorMessage :message="error" /></div>
        <div class="flex gap-2">
          <Button :label="__('Cancel')" @click="cancel" />
          <Button variant="solid" :label="__('Save')" @click="save" />
        </div>
      </div>
    </template>
  </Dialog>
</template>
<script setup>
import Link from '@/components/Controls/Link.vue'
import { createDocument } from '@/composables/document'
import { statusesStore } from '@/stores/statuses'
import { Dialog } from 'frappe-ui'
import { ref, computed } from 'vue'

const props = defineProps({
  doctype: { type: String, default: 'CRM Lead' },
  // document composable (detail pages) — omit when using onConfirm/onCancel
  document: { type: Object, default: null },
  onConfirm: { type: Function, default: null },
  onCancel: { type: Function, default: null },
  // target status when not using a document (kanban drag)
  status: { type: String, default: '' },
})

const show = defineModel({ type: Boolean })

const { getLeadStatus } = statusesStore()

const linkRef = ref(null)
const doc = props.document?.doc
const lostReason = ref(doc?.lost_reason || '')
const lostNotes = ref(doc?.lost_notes || '')
const refundable = ref(!!doc?.custom_refundable)
const error = ref('')
let saved = false

// Dead Lead is the refund pool. Lost is the ordinary dead-end. The
// refundable checkbox is what actually queues a Dead Lead for a refund;
// unchecked stays dead and out of the pipeline.
const isRefundPool = computed(() => {
  if (props.doctype !== 'CRM Lead') return false
  const statusName = props.status || doc?.status
  if (!statusName) return false
  return !!getLeadStatus(statusName)?.custom_refund_pool
})

const modalTitle = computed(() =>
  isRefundPool.value ? __('Dead Lead') : __('Lost Reason'),
)

const reasonLabel = computed(() => {
  if (!isRefundPool.value) return __('Lost Reason')
  return refundable.value ? __('Refund reason') : __('Dead reason')
})

const helperText = computed(() => {
  if (!isRefundPool.value) {
    return __('Please provide a reason for marking this {0} as lost', [
      props.doctype.toLowerCase().replace('crm ', ''),
    ])
  }
  return refundable.value
    ? __('Pick the refund category — this queues a refund request to the lead provider')
    : __('This lead is dead. Check “refundable” only if we should ask the provider for a refund.')
})

const reasonFilters = computed(() => {
  if (props.doctype !== 'CRM Lead') return {}
  return {
    custom_refund_eligible: isRefundPool.value && refundable.value ? 1 : 0,
  }
})

function onRefundableToggle(value) {
  refundable.value = !!value
  lostReason.value = ''
}

function cancel() {
  show.value = false
  if (saved) return
  error.value = ''
  lostReason.value = ''
  lostNotes.value = ''
  if (props.document) {
    doc.status = props.document.originalDoc.status
  }
  props.onCancel?.()
}

function save() {
  if (!lostReason.value) {
    error.value = __('Lost Reason is required')
    return
  }
  if (lostReason.value.startsWith('Other') && !lostNotes.value) {
    error.value = __('Lost Notes are required when Lost Reason is "Other"')
    return
  }

  error.value = ''
  saved = true
  show.value = false

  if (props.onConfirm) {
    props.onConfirm({
      lost_reason: lostReason.value,
      lost_notes: lostNotes.value,
      ...(isRefundPool.value
        ? {
            custom_refundable: refundable.value ? 1 : 0,
            custom_refund_status: refundable.value ? 'To Request' : '',
          }
        : {}),
    })
    return
  }

  doc.lost_reason = lostReason.value
  doc.lost_notes = lostNotes.value
  if (isRefundPool.value) {
    doc.custom_refundable = refundable.value ? 1 : 0
    doc.custom_refund_status = refundable.value ? 'To Request' : ''
  }
  props.document.save.submit()
}

function onCreate(value, close) {
  let doc = { lost_reason: value }
  createDocument('CRM Lost Reason', doc, close, (doc) => {
    lostReason.value = doc.name
    linkRef.value?.reload('', true)
  })
}
</script>
