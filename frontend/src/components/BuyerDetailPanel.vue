<template>
  <div class="flex h-full flex-col overflow-y-auto">
    <!-- profile -->
    <div class="flex flex-col gap-3 border-b p-5">
      <div class="flex items-start gap-3">
        <Avatar size="2xl" :label="data.buyer_name || '?'" />
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5">
            <div class="truncate text-lg font-semibold text-ink-gray-9">
              {{ data.buyer_name || __('Unknown buyer') }}
            </div>
            <BadgeCheckIcon
              v-if="data.verified"
              class="size-4 shrink-0 text-ink-blue-3"
              :title="__('Verified')"
            />
          </div>
          <div v-if="data.il_buyer_id" class="text-xs text-ink-gray-4">
            {{ __('via InvestorLift') }}
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            :label="__('Edit')"
            @click="$emit('edit')"
          />
          <Button
            variant="subtle"
            theme="red"
            size="sm"
            icon="trash-2"
            :tooltip="__('Delete buyer')"
            @click="$emit('delete')"
          />
        </div>
      </div>

      <!-- Do not contact. Stated as a banner rather than a field in the list
           below, because it overrides everything else on this panel: it is the
           answer to "can I text this person", and the Danny Stoica incident
           (gw296) happened because that answer was buried in a board column
           another system could quietly change. -->
      <div
        v-if="data.do_not_contact"
        class="flex items-start gap-2 rounded border border-outline-red-2 bg-surface-red-1 px-3 py-2"
      >
        <BanIcon class="mt-0.5 size-4 shrink-0 text-ink-red-4" />
        <div class="min-w-0 flex-1">
          <div class="text-sm font-medium text-ink-red-4">
            {{ __('Do not contact') }}
          </div>
          <div v-if="data.do_not_contact_reason" class="mt-0.5 break-words text-xs text-ink-red-3">
            {{ data.do_not_contact_reason }}
          </div>
          <div class="mt-1 text-xs text-ink-gray-5">
            {{ __('Bulk texting is blocked for this buyer.') }}
          </div>
        </div>
        <Button
          variant
          size="sm"
          :loading="dncSaving"
          :label="__('Allow')"
          @click="setDoNotContact(false)"
        />
      </div>
      <div v-else class="flex justify-end">
        <Button
          variant="ghost"
          size="sm"
          :loading="dncSaving"
          :label="__('Mark do not contact')"
          @click="setDoNotContact(true)"
        />
      </div>

      <!-- contact -->
      <div class="flex flex-col gap-1.5 text-sm">
        <div v-if="data.phone" class="flex items-center gap-1.5">
          <PhoneIcon class="size-3.5 shrink-0 text-ink-gray-5" />
          <a :href="'tel:' + telDigits" class="text-ink-gray-8 hover:text-ink-blue-3">
            {{ formatPhone(data.phone) }}
          </a>
          <button
            class="text-ink-gray-4 hover:text-ink-gray-7"
            :title="__('Copy phone')"
            @click="copyToClipboard(data.phone)"
          >
            <CopyIcon class="size-3.5" />
          </button>
        </div>
        <a
          v-if="data.email"
          :href="'mailto:' + data.email"
          class="flex items-center gap-1.5 text-ink-gray-8 hover:text-ink-blue-3"
        >
          <Email2Icon class="size-3.5 shrink-0 text-ink-gray-5" />
          <span class="truncate">{{ data.email }}</span>
        </a>
      </div>

      <span
        v-if="(data.metros || []).length"
        class="flex items-center gap-1.5 text-sm text-ink-gray-6"
      >
        <MapPinIcon class="size-3.5 shrink-0 text-ink-gray-5" />
        {{ data.metros.join(' · ') }}
      </span>
    </div>

    <!-- Globally configurable buyer side details. Managers can use the pencil
         on either section to add/reorder any CRM Buyer field. -->
    <SidePanelLayout
      v-if="sections.data"
      :key="buyerId + '-' + (data.modified || '')"
      :sections="sections.data"
      doctype="CRM Buyer"
      :docname="buyerId"
      @reload="sections.reload"
      @afterFieldChange="$emit('reload')"
    />

    <div class="border-t" />

    <!-- engaged properties -->
    <div class="px-5 py-3">
      <div class="flex items-center gap-2 text-base font-medium text-ink-gray-8">
        <DispoIcon class="size-4 text-ink-gray-7" />
        {{ __('Engaged properties') }}
        <span class="text-ink-gray-4">{{ deals.length }}</span>
        <Button
          class="ml-auto"
          variant="ghost"
          icon="plus"
          :tooltip="__('Add to deal')"
          @click="$emit('add-to-deal')"
        />
      </div>

      <div
        v-if="deals.length"
        class="mt-2 overflow-hidden rounded-lg border border-outline-gray-1"
      >
        <router-link
          v-for="d in deals"
          :key="d.lead"
          :to="{ name: 'Lead', params: { leadId: d.lead } }"
          class="flex items-center gap-2 border-b border-outline-gray-1 px-3 py-2.5 last:border-b-0 hover:bg-surface-gray-1"
        >
          <div class="min-w-0 flex-1">
            <div class="truncate text-sm text-ink-gray-8">{{ d.label }}</div>
            <div class="mt-0.5 flex items-center gap-2 text-xs text-ink-gray-5">
              <span v-if="d.direction">{{ d.direction }}</span>
              <span v-if="d.last_active">· {{ __('active') }} {{ timeAgo(d.last_active) }}</span>
            </div>
          </div>
          <Badge
            v-if="d.interest_stage"
            class="shrink-0"
            :theme="stageTheme(d.interest_stage)"
            variant="subtle"
          >
            {{ d.interest_stage }}
          </Badge>
        </router-link>
      </div>
      <div v-else class="mt-2 text-sm text-ink-gray-5">
        {{ __('Not engaged with any property yet.') }}
      </div>
    </div>

    <!-- e-sign agreements across the buyer's engaged properties -->
    <BuyerAgreementsCard
      ref="agreementsCard"
      :buyer="buyerId"
      :deals="deals"
      @create="(lead) => $emit('create-agreement', lead)"
    />
  </div>
</template>

<script setup>
import BuyerAgreementsCard from '@/components/BuyerAgreementsCard.vue'
import SidePanelLayout from '@/components/SidePanelLayout.vue'
import PhoneIcon from '@/components/Icons/PhoneIcon.vue'
import Email2Icon from '@/components/Icons/Email2Icon.vue'
import CopyIcon from '~icons/lucide/copy'
import BadgeCheckIcon from '~icons/lucide/badge-check'
import BanIcon from '~icons/lucide/ban'
import MapPinIcon from '~icons/lucide/map-pin'
import DispoIcon from '~icons/lucide/columns-3'
import { copyToClipboard, timeAgo } from '@/utils'
import { formatPhone } from '@/utils/phoneFormat'
import { Avatar, Badge, Button, call, createResource, toast } from 'frappe-ui'
import { computed, ref } from 'vue'

const props = defineProps({
  data: { type: Object, required: true },
  deals: { type: Array, default: () => [] },
  buyerId: { type: String, required: true },
})

const emit = defineEmits(['edit', 'delete', 'reload', 'add-to-deal', 'create-agreement'])

const agreementsCard = ref(null)
const dncSaving = ref(false)

// Turning this ON needs no confirmation — erring toward not texting someone is
// free. Turning it OFF is the one that can put a text in front of a person who
// asked us to stop, so it asks first.
async function setDoNotContact(enabled) {
  if (!enabled) {
    const who = props.data?.buyer_name || __('this buyer')
    if (
      !window.confirm(
        __('Allow contacting {0} again? They previously asked to be removed.', [who]),
      )
    )
      return
  }
  dncSaving.value = true
  try {
    await call('crm.api.do_not_contact.set_buyer_do_not_contact', {
      buyer: props.buyerId,
      enabled: enabled ? 1 : 0,
    })
    emit('reload')
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not update Do Not Contact'))
  } finally {
    dncSaving.value = false
  }
}
const sections = createResource({
  url: 'crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections',
  cache: ['sidePanelSections', 'CRM Buyer'],
  params: { doctype: 'CRM Buyer' },
  auto: true,
})
const telDigits = computed(() => (props.data?.phone || '').replace(/[^\d+]/g, ''))

function stageTheme(stage) {
  return (
    {
      New: 'blue',
      'Attempted to Contact': 'orange',
      'Not Interested': 'gray',
      Interested: 'green',
      'Offer Made': 'purple',
    }[stage] || 'gray'
  )
}

defineExpose({
  reloadAgreements: () => agreementsCard.value?.reload(),
})
</script>
