<template>
  <Dialog
    v-model="show"
    :options="{ title: __('Lost Reason') }"
    @close="cancel"
  >
    <template #body-content>
      <div class="-mt-3 mb-4 text-p-base text-ink-gray-7">
        {{
          isRefundPool
            ? __(
                'Pick the refund category that applies — this queues the lead for a refund request to the lead provider',
              )
            : __('Please provide a reason for marking this {0} as lost', [
                doctype.toLowerCase().replace('crm ', ''),
              ])
        }}
      </div>
      <div class="flex flex-col gap-3">
        <div>
          <div class="mb-2 text-sm text-ink-gray-5">
            {{ __('Lost Reason') }}
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
const error = ref('')
let saved = false

// refund-pool statuses (e.g. Dead Lead) only offer the lead provider's
// refund categories; other lost statuses only offer the standard reasons
const isRefundPool = computed(() => {
  if (props.doctype !== 'CRM Lead') return false
  const statusName = props.status || doc?.status
  if (!statusName) return false
  return !!getLeadStatus(statusName)?.custom_refund_pool
})

const reasonFilters = computed(() => {
  if (props.doctype !== 'CRM Lead') return {}
  return { custom_refund_eligible: isRefundPool.value ? 1 : 0 }
})

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
    })
    return
  }

  doc.lost_reason = lostReason.value
  doc.lost_notes = lostNotes.value
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
