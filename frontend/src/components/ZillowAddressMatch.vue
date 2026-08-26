<template>
  <div
    v-if="visible"
    class="flex flex-col gap-2 rounded-md border border-outline-amber-2 bg-surface-amber-1 px-3 py-2 text-xs text-ink-amber-3"
  >
    <div>
      <span class="font-medium">{{ __('Zillow doesn’t recognize this address.') }}</span>
      {{ __('Ask the seller to confirm it.') }}
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <input
        v-model="draft"
        type="text"
        class="min-w-0 flex-1 rounded border border-outline-amber-2 bg-surface-white px-2 py-1 text-xs text-ink-gray-8"
        :placeholder="__('Street, city, state ZIP')"
        @keydown.enter.prevent="save"
      />
      <Button
        :label="saving ? __('Saving…') : __('Save address')"
        variant="subtle"
        :disabled="!canSave || saving"
        @click="save"
      />
      <Button
        v-if="dirty"
        :label="rerunning ? __('Rerunning…') : __('Rerun comps')"
        variant="solid"
        :disabled="rerunning || saving"
        @click="rerun"
      />
    </div>
  </div>
</template>

<script setup>
/**
 * Shown when Zillow could not resolve the lead's address — the 310 Asbury
 * case. The setter asks the seller, types the correction, and only then
 * spends another lookup. Auto-refetching on every keystroke would re-bill
 * a miss that is still a miss.
 */
import { Button, call, toast } from 'frappe-ui'
import { computed, ref, watch } from 'vue'

const props = defineProps({
  lead: { type: String, required: true },
  address: { type: String, default: '' },
  match: { type: Object, default: null },
})
const emit = defineEmits(['saved', 'reran'])

const draft = ref(props.address || '')
const savedAddress = ref(props.address || '')
const savedSinceFetch = ref(false)
const saving = ref(false)
const rerunning = ref(false)

watch(
  () => props.address,
  (v) => {
    if (!saving.value && !savedSinceFetch.value) {
      draft.value = v || ''
      savedAddress.value = v || ''
    }
  },
)

function norm(s) {
  return String(s || '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}

const queried = computed(() => props.match?.queried_address || '')
const miss = computed(() => Boolean(props.match?.tried && !props.match?.matched))
const dirty = computed(() => {
  if (savedSinceFetch.value) return true
  const now = norm(savedAddress.value)
  const was = norm(queried.value)
  return Boolean(now && was && now !== was)
})
const visible = computed(() => miss.value || dirty.value)
const canSave = computed(() => {
  const next = norm(draft.value)
  return Boolean(next) && next !== norm(savedAddress.value)
})

async function save() {
  if (!canSave.value || !props.lead) return
  saving.value = true
  try {
    await call('frappe.client.set_value', {
      doctype: 'CRM Lead',
      name: props.lead,
      fieldname: 'property_address',
      value: draft.value.trim(),
    })
    savedAddress.value = draft.value.trim()
    savedSinceFetch.value = true
    emit('saved', savedAddress.value)
    toast.success(__('Address saved — rerun comps to look it up again.'))
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not save the address'))
  } finally {
    saving.value = false
  }
}

async function rerun() {
  if (!props.lead) return
  rerunning.value = true
  try {
    const res = await call('crm.api.zillow.refresh_lead_facts', { lead: props.lead })
    savedSinceFetch.value = false
    emit('reran', res || {})
    if (res?.matched) toast.success(__('Zillow found this address.'))
    else toast.warning(__('Zillow still doesn’t recognize this address.'))
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not rerun comps'))
  } finally {
    rerunning.value = false
  }
}
</script>
