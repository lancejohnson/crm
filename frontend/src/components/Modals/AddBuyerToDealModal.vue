<template>
  <Dialog
    v-model="show"
    :options="{
      title: props.lead ? __('Add buyer to this deal') : __('Add to a deal'),
      actions: [
        {
          label: __('Add'),
          variant: 'solid',
          onClick: submit,
        },
      ],
    }"
  >
    <template #body-content>
      <div class="flex flex-col gap-4">
        <!-- pick the missing side of the relationship -->
        <div v-if="props.lead" class="space-y-1.5">
          <label class="block text-xs text-ink-gray-5">{{ __('Buyer') }}</label>
          <Autocomplete
            :options="buyerOptions"
            :modelValue="pickedBuyer"
            :placeholder="__('Search buyers…')"
            @update:modelValue="(v) => (pickedBuyer = v?.value || '')"
          />
          <button
            class="text-xs text-ink-gray-5 underline hover:text-ink-gray-7"
            @click="showNewBuyer = true"
          >
            {{ __('Or create a new buyer') }}
          </button>
        </div>
        <div v-else class="space-y-1.5">
          <label class="block text-xs text-ink-gray-5">{{ __('Property (deal)') }}</label>
          <Autocomplete
            :options="propertyOptions"
            :modelValue="pickedLead"
            :placeholder="__('Search dispo properties…')"
            @update:modelValue="(v) => (pickedLead = v?.value || '')"
          />
        </div>

        <FormControl
          type="select"
          v-model="stage"
          :label="__('Interest stage')"
          :options="stages"
        />

        <ErrorMessage :message="error" />
      </div>
    </template>
  </Dialog>

  <BuyerModal
    v-model="showNewBuyer"
    :redirect="false"
    :with-property="false"
    @saved="(name) => (pickedBuyer = name)"
  />
</template>

<script setup>
import Autocomplete from '@/components/frappe-ui/Autocomplete.vue'
import BuyerModal from '@/components/Modals/BuyerModal.vue'
import { formatPhone } from '@/utils/phoneFormat'
import {
  Dialog,
  FormControl,
  ErrorMessage,
  call,
  createResource,
} from 'frappe-ui'
import { ref, computed, watch } from 'vue'

const props = defineProps({
  // exactly one of these is set: adding a buyer TO this lead, or adding
  // this buyer to a picked lead
  lead: { type: String, default: '' },
  buyer: { type: String, default: '' },
})
const emit = defineEmits(['saved'])
const show = defineModel()

const pickedBuyer = ref('')
const pickedLead = ref('')
const stage = ref('New')
const error = ref('')
const showNewBuyer = ref(false)

const stages = [
  'New',
  'Attempted to Contact',
  'Not Interested',
  'Interested',
  'Offer Made',
]

const buyers = createResource({ url: 'crm.api.buyers.get_buyers' })
const properties = createResource({
  url: 'crm.api.investorlift_ingest.get_dispo_properties',
})

watch(show, (v) => {
  if (!v) return
  error.value = ''
  pickedBuyer.value = ''
  pickedLead.value = ''
  stage.value = 'New'
  if (props.lead && !buyers.data) buyers.fetch()
  if (props.buyer && !properties.data) properties.fetch()
})

const buyerOptions = computed(() =>
  (buyers.data || []).map((b) => ({
    label: [b.buyer_name, formatPhone(b.phone)].filter(Boolean).join(' · '),
    value: b.name,
  })),
)
const propertyOptions = computed(() =>
  (properties.data || []).map((p) => ({ label: p.label, value: p.lead })),
)

async function submit() {
  error.value = ''
  const lead = props.lead || pickedLead.value
  const buyer = props.buyer || pickedBuyer.value
  if (!lead || !buyer) {
    error.value = props.lead ? __('Pick a buyer first.') : __('Pick a property first.')
    return
  }
  try {
    const r = await call('crm.api.buyers.add_buyer_to_lead', {
      lead,
      buyer,
      stage: stage.value,
    })
    show.value = false
    emit('saved', { ...r, lead, buyer })
  } catch (e) {
    error.value = e.messages?.[0] || e.message
  }
}
</script>
