<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="breadcrumbs" />
    </template>
  </LayoutHeader>

  <div v-if="data" class="flex-1 overflow-y-auto">
    <!-- profile header -->
    <div class="flex items-start gap-4 border-b px-6 py-5">
      <Avatar size="3xl" :label="data.buyer_name || '?'" />
      <div class="flex-1">
        <div class="flex items-center gap-2">
          <h1 class="text-2xl font-semibold text-ink-gray-9">
            {{ data.buyer_name || __('Unknown buyer') }}
          </h1>
          <BadgeCheckIcon
            v-if="data.verified"
            class="size-5 text-ink-blue-3"
            :title="__('Verified')"
          />
        </div>

        <!-- contact row -->
        <div class="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-sm">
          <a
            v-if="data.phone"
            :href="'tel:' + telDigits"
            class="flex items-center gap-1.5 text-ink-gray-8 hover:text-ink-blue-3"
          >
            <PhoneIcon class="size-3.5 text-ink-gray-5" />
            {{ data.phone }}
          </a>
          <button
            v-if="data.phone"
            class="text-ink-gray-4 hover:text-ink-gray-7"
            :title="__('Copy phone')"
            @click="copyToClipboard(data.phone)"
          >
            <CopyIcon class="size-3.5" />
          </button>
          <a
            v-if="data.email"
            :href="'mailto:' + data.email"
            class="flex items-center gap-1.5 text-ink-gray-8 hover:text-ink-blue-3"
          >
            <Email2Icon class="size-3.5 text-ink-gray-5" />
            {{ data.email }}
          </a>
        </div>

        <!-- type tags -->
        <div v-if="tags.length" class="mt-2.5 flex flex-wrap gap-1">
          <span
            v-for="t in tags"
            :key="t"
            class="rounded bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-7"
          >
            {{ t }}
          </span>
        </div>

        <!-- deal history + last active -->
        <div class="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-gray-6">
          <span v-if="data.deal_history" class="flex items-center gap-1.5">
            <HistoryIcon class="size-3.5 text-ink-gray-5" />
            {{ data.deal_history }}
          </span>
          <span v-if="data.last_active">
            {{ __('Last active') }} {{ timeAgo(data.last_active) }}
          </span>
          <span class="text-ink-gray-4">{{ __('via InvestorLift') }}</span>
        </div>
      </div>
    </div>

    <!-- engaged properties -->
    <div class="px-6 py-5">
      <div class="mb-3 flex items-center gap-2 text-base font-medium text-ink-gray-8">
        <DispoIcon class="size-4 text-ink-gray-7" />
        {{ __('Engaged properties') }}
        <span class="text-ink-gray-4">{{ deals.length }}</span>
      </div>

      <div v-if="deals.length" class="overflow-hidden rounded-lg border border-outline-gray-1">
        <router-link
          v-for="d in deals"
          :key="d.lead"
          :to="{ name: 'Lead', params: { leadId: d.lead } }"
          class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0 hover:bg-surface-gray-1"
        >
          <div class="min-w-0 flex-1">
            <div class="truncate text-base text-ink-gray-8">{{ d.label }}</div>
            <div class="mt-0.5 flex items-center gap-2 text-xs text-ink-gray-5">
              <span v-if="d.direction">{{ d.direction }}</span>
              <span v-if="d.last_active">· {{ __('active') }} {{ timeAgo(d.last_active) }}</span>
            </div>
          </div>
          <Badge v-if="d.interest_stage" :theme="stageTheme(d.interest_stage)" variant="subtle">
            {{ d.interest_stage }}
          </Badge>
        </router-link>
      </div>
      <div v-else class="text-sm text-ink-gray-5">
        {{ __('Not engaged with any property yet.') }}
      </div>
    </div>

    <!-- Quo conversation (live texts + calls with this buyer) -->
    <div class="border-t px-6 py-5">
      <div class="mb-3 flex items-center gap-2 text-base font-medium text-ink-gray-8">
        <CommentIcon class="size-4 text-ink-gray-7" />
        {{ __('Conversation') }}
        <span v-if="convo.length" class="text-ink-gray-4">{{ convo.length }}</span>
        <LoadingIndicator v-if="conversation.loading" class="size-3.5 text-ink-gray-4" />
      </div>

      <div v-if="convo.length" class="flex max-w-2xl flex-col gap-1.5">
        <template v-for="(it, i) in convo" :key="i">
          <!-- text -->
          <div
            v-if="it.kind === 'text'"
            class="flex flex-col"
            :class="isOut(it) ? 'items-end' : 'items-start'"
          >
            <div
              class="max-w-[85%] rounded-2xl px-3 py-1.5 text-sm"
              :class="isOut(it) ? 'bg-blue-500 text-white' : 'bg-surface-gray-3 text-ink-gray-8'"
            >
              {{ it.text }}
            </div>
            <div class="mt-0.5 px-1 text-xs text-ink-gray-4">
              {{ isOut(it) ? it.line : '' }}
              {{ formatDate(it.at, 'MMM D, h:mm a') }}
            </div>
          </div>
          <!-- call -->
          <div v-else class="my-1 flex items-center justify-center gap-2 text-xs text-ink-gray-5">
            <PhoneIcon class="size-3" />
            <span>
              {{ it.direction === 'outgoing' ? __('Outgoing call') : __('Incoming call') }}
              <template v-if="it.duration"> · {{ fmtDur(it.duration) }}</template>
              · {{ formatDate(it.at, 'MMM D, h:mm a') }}
              <span class="text-ink-gray-4"> · {{ it.line }}</span>
            </span>
          </div>
        </template>
      </div>
      <div v-else-if="!conversation.loading" class="text-sm text-ink-gray-5">
        {{ __('No Quo texts or calls with this buyer yet.') }}
      </div>
    </div>
  </div>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import PhoneIcon from '@/components/Icons/PhoneIcon.vue'
import Email2Icon from '@/components/Icons/Email2Icon.vue'
import CopyIcon from '~icons/lucide/copy'
import CommentIcon from '@/components/Icons/CommentIcon.vue'
import BadgeCheckIcon from '~icons/lucide/badge-check'
import HistoryIcon from '~icons/lucide/history'
import DispoIcon from '~icons/lucide/columns-3'
import { copyToClipboard, timeAgo, formatDate } from '@/utils'
import {
  Breadcrumbs,
  Avatar,
  Badge,
  LoadingIndicator,
  createResource,
  usePageMeta,
} from 'frappe-ui'
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const buyerId = computed(() => route.params.buyerId)

const buyer = createResource({
  url: 'crm.api.investorlift_ingest.get_buyer',
  makeParams: () => ({ buyer: buyerId.value }),
  auto: true,
})

const data = computed(() => buyer.data || null)
const deals = computed(() => data.value?.deals || [])
const tags = computed(() =>
  (data.value?.buyer_type || '')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean),
)
const telDigits = computed(() => (data.value?.phone || '').replace(/[^\d+]/g, ''))

// live Quo conversation (texts + calls) with this buyer
const conversation = createResource({
  url: 'crm.api.investorlift_ingest.get_buyer_conversation',
  makeParams: () => ({ buyer: buyerId.value }),
  auto: true,
})
const convo = computed(() => conversation.data?.items || [])
function isOut(it) {
  return it.direction === 'outgoing'
}
function fmtDur(secs) {
  secs = Number(secs) || 0
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return m ? `${m}m ${s}s` : `${s}s`
}

const breadcrumbs = computed(() => [
  { label: __('Buyer') },
  { label: data.value?.buyer_name || __('Buyer') },
])

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

usePageMeta(() => ({ title: data.value?.buyer_name || 'Buyer' }))
</script>
