<template>
  <div v-if="linked" class="px-3 pt-3 sm:px-10">
    <div
      class="overflow-hidden rounded-lg border border-outline-gray-1 bg-surface-gray-1"
    >
      <div
        class="flex items-center gap-1.5 px-3 pt-2.5 pb-1 text-sm font-medium text-ink-gray-5"
      >
        <MegaphoneIcon class="size-3.5" />
        <span>{{ __('InvestorLift Marketing') }}</span>
        <Badge v-if="m.status" :theme="statusTheme(m.status)" variant="subtle" class="ml-1">
          {{ m.status }}
        </Badge>
        <div class="flex-1" />
        <router-link
          :to="{ name: 'Dispo', params: { leadId: lead } }"
          class="flex items-center gap-1 text-xs font-normal text-ink-blue-3 hover:underline"
        >
          <DispoIcon class="size-3" />
          {{ __('Dispo board') }}
        </router-link>
        <a
          v-if="m.admin_url"
          :href="m.admin_url"
          target="_blank"
          class="flex items-center gap-1 text-xs font-normal text-ink-blue-3 hover:underline"
        >
          {{ __('Admin listing') }}
          <ExternalLinkIcon class="size-3" />
        </a>
        <a
          v-if="m.marketplace_url"
          :href="m.marketplace_url"
          target="_blank"
          class="flex items-center gap-1 text-ink-blue-3 hover:underline"
        >
          <ExternalLinkIcon class="size-3.5" />
          {{ __('Public listing') }}
        </a>
      </div>

      <div class="flex flex-wrap gap-x-6 gap-y-2 px-3 pt-1 pb-3">
        <Stat :label="__('Texts sent')" :value="formatNumber(m.sms.sent)" />
        <Stat :label="__('Delivered')" :value="formatNumber(m.sms.delivered)" />
        <Stat
          :label="__('Clicks')"
          :value="formatNumber(m.sms.clicked)"
          :sub="m.sms.ctr ? m.sms.ctr + '% CTR' : ''"
        />
        <Stat v-if="m.email.sent" :label="__('Emails')" :value="formatNumber(m.email.sent)" />
        <Stat :label="__('Views')" :value="formatNumber(m.views)" />
        <Stat :label="__('Spend')" :value="'$' + formatNumber(m.spend)" />
      </div>
    </div>
  </div>
</template>

<script setup>
import MegaphoneIcon from '~icons/lucide/megaphone'
import ExternalLinkIcon from '~icons/lucide/external-link'
import DispoIcon from '~icons/lucide/columns-3'
import { formatNumber } from '@/utils'
import { globalStore } from '@/stores/global'
import { Badge, createResource } from 'frappe-ui'
import { computed, h, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  lead: { type: String, required: true },
})

const { $socket } = globalStore()

const Stat = (p) =>
  h('div', { class: 'flex flex-col' }, [
    h('div', { class: 'text-lg font-semibold leading-6 text-ink-gray-9' }, p.value),
    h('div', { class: 'flex items-baseline gap-1.5' }, [
      h('span', { class: 'text-xs text-ink-gray-5' }, p.label),
      p.sub ? h('span', { class: 'text-xs text-ink-green-3' }, p.sub) : null,
    ]),
  ])

const marketing = createResource({
  url: 'crm.api.investorlift.get_marketing',
  params: { lead: props.lead },
  cache: ['il_marketing', props.lead],
  auto: true,
})

const m = computed(() => marketing.data || {})
const linked = computed(() => !!m.value.linked)

function statusTheme(status) {
  const s = (status || '').toLowerCase()
  if (s === 'sold') return 'green'
  if (s === 'pending') return 'orange'
  if (s === 'available') return 'blue'
  return 'gray'
}

function onSync(data) {
  if (data.reference_doctype === 'CRM Lead' && data.reference_docname === props.lead) {
    marketing.reload()
  }
}
onMounted(() => $socket.on('crm_il_sync', onSync))
onBeforeUnmount(() => $socket.off('crm_il_sync', onSync))
</script>
