<template>
  <div class="border-t px-5 py-3">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2 text-base font-medium text-ink-gray-8">
        <MoneyIcon class="size-4 text-ink-gray-7" />
        {{ __('Tax Info') }}
      </div>
      <Button
        :tooltip="latest ? __('Re-pull tax info') : __('Fetch tax info')"
        :icon="latest ? 'rotate-ccw' : 'plus'"
        variant="ghost"
        @click="emit('fetch')"
      />
    </div>

    <div v-if="latest" class="mt-2.5 flex flex-col gap-1.5 text-sm">
      <div v-if="!latest.matched" class="text-ink-gray-5">
        {{ __('No property match found for this address.') }}
      </div>
      <template v-else>
        <Row v-if="latest.owner_name" :label="__('Owner')">
          {{ latest.owner_name }}
        </Row>
        <Row v-if="latest.owner_status_type" :label="__('Owner type')">
          {{ latest.owner_status_type
          }}<span v-if="latest.owner_occupied" class="text-ink-gray-5">
            · {{ __('owner-occupied') }}</span
          >
        </Row>
        <Row v-if="latest.apn" :label="__('APN')">{{ latest.apn }}</Row>
        <Row v-if="latest.tax_status" :label="__('Tax status')">
          <span
            :class="
              latest.tax_default || latest.tax_delinquent_year
                ? 'font-medium text-ink-red-3'
                : 'text-ink-gray-8'
            "
            >{{ latest.tax_status }}</span
          >
        </Row>
        <Row v-if="latest.annual_tax" :label="__('Annual tax')">
          ${{ formatNumber(latest.annual_tax)
          }}<span v-if="latest.tax_year" class="text-ink-gray-5">
            ({{ latest.tax_year }})</span
          >
        </Row>
        <Row v-if="latest.assessed_value" :label="__('Assessed value')">
          ${{ formatNumber(latest.assessed_value) }}
        </Row>
        <Row v-if="latest.estimated_value" :label="__('Est. value')">
          ${{ formatNumber(latest.estimated_value) }}
        </Row>
      </template>

      <div class="mt-1 text-xs text-ink-gray-5">
        {{ __('Pulled by') }}
        <span class="text-ink-gray-7">{{
          latest.pulled_by_name || latest.pulled_by
        }}</span>
        · {{ formatDate(latest.pulled_at || latest.creation, '', true) }}
        <span v-if="pulls.length > 1" class="text-ink-gray-4">
          · {{ pulls.length }} {{ __('pulls') }}</span
        >
      </div>
    </div>

    <div v-else class="mt-2 text-sm text-ink-gray-5">
      {{ __('No tax info pulled yet.') }}
    </div>
  </div>
</template>

<script setup>
import MoneyIcon from '@/components/Icons/MoneyIcon.vue'
import { formatDate, formatNumber } from '@/utils'
import { globalStore } from '@/stores/global'
import { Button, createResource } from 'frappe-ui'
import { computed, h, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  lead: { type: String, required: true },
})

const emit = defineEmits(['fetch'])

const { $socket } = globalStore()

// Tiny label/value row helper (keeps the template readable).
const Row = (p, { slots }) =>
  h('div', { class: 'flex gap-1.5' }, [
    h('span', { class: 'shrink-0 text-ink-gray-5' }, p.label),
    h('span', { class: 'text-ink-gray-8' }, slots.default?.()),
  ])

const taxPulls = createResource({
  url: 'crm.api.tax_info.get_tax_pulls',
  cache: ['tax_pulls', props.lead],
  params: { lead: props.lead },
  auto: true,
})

const pulls = computed(() => taxPulls.data || [])
const latest = computed(() => pulls.value[0] || null)

function onTaxPull(data) {
  if (
    data.reference_doctype === 'CRM Lead' &&
    data.reference_docname === props.lead
  ) {
    taxPulls.reload()
  }
}

onMounted(() => $socket.on('crm_tax_pull', onTaxPull))
onBeforeUnmount(() => $socket.off('crm_tax_pull', onTaxPull))
</script>
