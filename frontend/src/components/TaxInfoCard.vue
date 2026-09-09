<template>
  <div :class="embedded ? 'rounded-lg border border-outline-gray-2' : 'border-t'">
    <div class="flex items-center justify-between px-5 py-3">
      <div class="flex items-center gap-2 text-base font-medium text-ink-gray-8">
        <MoneyIcon class="size-4 text-ink-gray-7" />
        {{ __('Tax / liens') }}
      </div>
      <Button
        :tooltip="latest ? __('Re-pull tax & lien records') : __('Fetch tax & lien records')"
        :icon="latest ? 'rotate-ccw' : 'plus'"
        variant="ghost"
        @click="emit('fetch')"
      />
    </div>

    <div v-if="latest" class="px-5 pb-3 flex flex-col gap-1.5 text-sm">
      <div v-if="!latest.matched" class="text-ink-gray-5">
        {{ __('No property match found for this address.') }}
      </div>
      <template v-else>
        <Row v-if="latest.owner_name" :label="__('Owner')">
          {{ latest.owner_name }}
        </Row>
        <Row v-if="dd.mailing" :label="__('Mailing')">{{ dd.mailing }}</Row>
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
        <Row :label="__('Open liens')">
          {{ dd.open_lien_count ? dd.open_lien_count : __('None') }}
        </Row>
        <Row v-if="dd.free_and_clear" :label="__('Title')">
          {{ __('Free and clear') }}
        </Row>

        <button
          v-if="hasRecords"
          type="button"
          class="mt-1.5 flex w-full items-center justify-between rounded-md border border-outline-gray-2 bg-surface-gray-1 px-2.5 py-1.5 text-xs font-medium text-ink-gray-7 hover:bg-surface-gray-2"
          @click="open = !open"
        >
          <span>{{ __('Records') }}</span>
          <FeatherIcon :name="open ? 'chevron-up' : 'chevron-down'" class="size-3.5" />
        </button>

        <div v-if="open && hasRecords" class="mt-1 flex flex-col gap-3">
          <section v-if="dd.foreclosure">
            <h4 class="mb-1 text-2xs font-semibold uppercase tracking-wide text-ink-gray-5">
              {{ __('Foreclosure') }}
            </h4>
            <table class="w-full text-xs">
              <tbody>
                <tr v-for="row in foreclosureRows" :key="row[0]">
                  <td class="py-0.5 pr-2 text-ink-gray-5 whitespace-nowrap">{{ row[0] }}</td>
                  <td class="py-0.5 text-ink-gray-8">{{ row[1] }}</td>
                </tr>
              </tbody>
            </table>
          </section>

          <section v-if="dd.deeds?.length">
            <h4 class="mb-1 text-2xs font-semibold uppercase tracking-wide text-ink-gray-5">
              {{ __('Deeds') }}
            </h4>
            <div class="overflow-x-auto">
              <table class="w-full text-xs">
                <thead class="text-ink-gray-5">
                  <tr>
                    <th class="py-0.5 pr-2 text-left font-medium">{{ __('Date') }}</th>
                    <th class="py-0.5 pr-2 text-left font-medium">{{ __('Type') }}</th>
                    <th class="py-0.5 pr-2 text-left font-medium">{{ __('From / to') }}</th>
                    <th class="py-0.5 text-right font-medium">{{ __('Price') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(d, i) in dd.deeds" :key="i" class="border-t border-outline-gray-1">
                    <td class="py-0.5 pr-2 whitespace-nowrap">{{ d.date || '—' }}</td>
                    <td class="py-0.5 pr-2">
                      {{ d.type || '—' }}
                      <span v-if="d.foreclosure" class="text-ink-red-3"> · {{ __('FCL') }}</span>
                    </td>
                    <td class="py-0.5 pr-2">
                      {{ (d.sellers || []).join(', ') || '—' }}
                      → {{ (d.buyers || []).join(', ') || '—' }}
                    </td>
                    <td class="py-0.5 text-right whitespace-nowrap">
                      {{ d.price ? '$' + formatNumber(d.price) : '—' }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section v-if="dd.mortgages?.length">
            <h4 class="mb-1 text-2xs font-semibold uppercase tracking-wide text-ink-gray-5">
              {{ __('Mortgages') }}
            </h4>
            <div class="overflow-x-auto">
              <table class="w-full text-xs">
                <thead class="text-ink-gray-5">
                  <tr>
                    <th class="py-0.5 pr-2 text-left font-medium">{{ __('Date') }}</th>
                    <th class="py-0.5 pr-2 text-left font-medium">{{ __('Lender') }}</th>
                    <th class="py-0.5 pr-2 text-left font-medium">{{ __('Type') }}</th>
                    <th class="py-0.5 text-right font-medium">{{ __('Amount') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(m, i) in dd.mortgages"
                    :key="i"
                    class="border-t border-outline-gray-1"
                  >
                    <td class="py-0.5 pr-2 whitespace-nowrap">{{ m.date || '—' }}</td>
                    <td class="py-0.5 pr-2">{{ m.lender || '—' }}</td>
                    <td class="py-0.5 pr-2">
                      {{ m.type || '—'
                      }}<span v-if="m.rate" class="text-ink-gray-5"> · {{ m.rate }}%</span>
                    </td>
                    <td class="py-0.5 text-right whitespace-nowrap">
                      {{ m.amount ? '$' + formatNumber(m.amount) : '—' }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section v-if="dd.taxes?.length">
            <h4 class="mb-1 text-2xs font-semibold uppercase tracking-wide text-ink-gray-5">
              {{ __('Tax history') }}
            </h4>
            <table class="w-full text-xs">
              <thead class="text-ink-gray-5">
                <tr>
                  <th class="py-0.5 pr-2 text-left font-medium">{{ __('Year') }}</th>
                  <th class="py-0.5 text-right font-medium">{{ __('Amount') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(t, i) in dd.taxes" :key="i" class="border-t border-outline-gray-1">
                  <td class="py-0.5 pr-2">{{ t.year || '—' }}</td>
                  <td class="py-0.5 text-right">
                    {{ t.amount ? '$' + formatNumber(t.amount) : '—' }}
                  </td>
                </tr>
              </tbody>
            </table>
          </section>
        </div>
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

    <div v-else class="px-5 pb-3 text-sm text-ink-gray-5">
      {{ __('No tax info pulled yet.') }}
    </div>
  </div>
</template>

<script setup>
import MoneyIcon from '@/components/Icons/MoneyIcon.vue'
import { formatDate, formatNumber } from '@/utils'
import { globalStore } from '@/stores/global'
import { Button, FeatherIcon, createResource } from 'frappe-ui'
import { computed, h, onMounted, onBeforeUnmount, ref } from 'vue'

const props = defineProps({
  lead: { type: String, required: true },
  embedded: { type: Boolean, default: false },
})

const emit = defineEmits(['fetch'])

const { $socket } = globalStore()
const open = ref(false)

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
const dd = computed(() => latest.value?.dd || {})
const hasRecords = computed(
  () =>
    !!(
      dd.value.foreclosure ||
      dd.value.deeds?.length ||
      dd.value.mortgages?.length ||
      dd.value.taxes?.length
    ),
)

const foreclosureRows = computed(() => {
  const f = dd.value.foreclosure
  if (!f) return []
  return [
    [__('Status'), f.status],
    [__('Type'), f.type],
    [__('Recorded'), f.date],
    [__('Auction'), f.auction],
    [__('Case / TSN'), f.case],
    [__('Borrower'), f.borrower],
    [__('Trustee'), f.trustee],
  ].filter((row) => row[1])
})

function onTaxPull(data) {
  if (
    data.reference_doctype === 'CRM Lead' &&
    data.reference_docname === props.lead
  ) {
    taxPulls.reload()
    open.value = true
  }
}

onMounted(() => $socket.on('crm_tax_pull', onTaxPull))
onBeforeUnmount(() => $socket.off('crm_tax_pull', onTaxPull))
</script>
