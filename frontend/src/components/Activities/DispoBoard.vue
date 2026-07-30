<template>
  <!-- LIST view -->
  <div v-if="view === 'list'" class="flex-1 overflow-y-auto">
    <div
      class="grid items-center gap-3 border-b px-4 py-2 text-xs font-medium uppercase text-ink-gray-5 sm:px-5"
      :style="listCols"
    >
      <span>{{ __('Stage') }}</span>
      <span>{{ __('Name') }}</span>
      <span>{{ __('Type') }}</span>
      <span>{{ __('Phone') }}</span>
      <span>{{ __('Direction') }}</span>
      <span>{{ __('Last active') }}</span>
      <span class="text-right">{{ __('Msgs') }}</span>
    </div>

    <router-link
      v-for="b in flatBuyers"
      :key="b.name"
      :to="{ name: 'Buyer', params: { buyerId: b.buyer } }"
      class="grid items-center gap-3 border-b border-outline-gray-1 px-4 py-2.5 text-sm text-ink-gray-8 hover:bg-surface-gray-1 sm:px-5"
      :style="listCols"
    >
      <span class="flex min-w-0 items-center gap-1.5">
        <IndicatorIcon :class="b._stageColor" />
        <span class="truncate text-ink-gray-6">{{ b.interest_stage || 'New' }}</span>
      </span>
      <span class="flex min-w-0 items-center gap-1.5">
        <span class="truncate font-medium">{{ b.buyer_name || '—' }}</span>
        <BadgeCheckIcon v-if="b.verified" class="size-3.5 shrink-0 text-ink-blue-3" />
      </span>
      <span class="flex min-w-0 flex-wrap gap-1">
        <span
          v-for="t in tagList(b.buyer_type)"
          :key="t"
          class="rounded bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-7"
        >
          {{ t }}
        </span>
        <span v-if="!tagList(b.buyer_type).length" class="text-ink-gray-4">—</span>
      </span>
      <a
        v-if="b.phone"
        :href="telHref(b.phone)"
        class="truncate text-ink-gray-6 hover:text-ink-blue-3"
        @click.stop
      >
        {{ formatPhone(b.phone) }}
      </a>
      <span v-else class="text-ink-gray-4">—</span>
      <span>
        <Badge
          v-if="b.direction"
          :theme="b.direction === 'Inbound' ? 'green' : 'blue'"
          variant="subtle"
          size="sm"
        >
          {{ b.direction }}
        </Badge>
        <span v-else class="text-ink-gray-4">—</span>
      </span>
      <span class="truncate text-ink-gray-6">
        {{ b.last_active ? formatDate(b.last_active, '', true) : '—' }}
      </span>
      <span class="text-right text-ink-gray-6">{{ b.message_count || 0 }}</span>
    </router-link>

    <div
      v-if="!flatBuyers.length"
      class="flex flex-col items-center justify-center gap-2 py-16 text-ink-gray-4"
    >
      <span class="text-base">{{ __('No buyers on this property yet.') }}</span>
    </div>
  </div>

  <!-- BOARD (Kanban) view -->
  <div v-else class="flex h-full overflow-x-auto px-2 py-3 sm:px-4">
    <div
      v-for="col in columns"
      :key="col.stage"
      class="flex min-w-72 w-72 flex-col gap-2.5 rounded-lg p-2.5"
    >
      <div class="flex items-center gap-2 px-1">
        <IndicatorIcon :class="col.color" />
        <div class="text-base text-ink-gray-9">{{ col.stage }}</div>
        <div class="text-ink-gray-4">{{ col.buyers.length }}</div>
      </div>

      <Draggable
        :list="col.buyers"
        group="dispo-buyers"
        item-key="name"
        class="flex min-h-12 flex-1 flex-col gap-3.5 overflow-y-auto rounded-md"
        :class="moving ? 'bg-surface-gray-1' : ''"
        :delay="isTouchScreenDevice() ? 200 : 0"
        :data-stage="col.stage"
        @start="moving = true"
        @end="moveBuyer"
      >
        <template #item="{ element: b }">
          <router-link
            :to="{ name: 'Buyer', params: { buyerId: b.buyer } }"
            :data-name="b.name"
            class="flex cursor-grab flex-col rounded-lg border bg-surface-white px-3.5 pb-2.5 pt-3 text-base text-ink-gray-9 hover:border-outline-gray-3 active:cursor-grabbing"
          >
          <!-- title: name + verified + direction -->
          <div class="flex items-center gap-1.5">
            <span class="truncate font-medium">{{ b.buyer_name || '—' }}</span>
            <BadgeCheckIcon
              v-if="b.verified"
              class="size-4 shrink-0 text-ink-blue-3"
            />
            <div class="flex-1" />
            <Badge
              v-if="b.direction"
              :theme="b.direction === 'Inbound' ? 'green' : 'blue'"
              variant="subtle"
              size="sm"
            >
              {{ b.direction }}
            </Badge>
            <div @click.stop.prevent>
              <Dropdown :options="stageOptions(b)">
                <button
                  type="button"
                  class="flex size-6 items-center justify-center rounded text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8"
                  :title="__('Move buyer')"
                >
                  <MoreHorizontalIcon class="size-4" />
                </button>
              </Dropdown>
            </div>
          </div>

          <div class="my-2.5 h-px border-b" />

          <!-- fields -->
          <div class="flex flex-col gap-2 text-sm">
            <div v-if="b.buyer_type" class="flex flex-wrap gap-1">
              <span
                v-for="t in tagList(b.buyer_type)"
                :key="t"
                class="rounded bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-7"
              >
                {{ t }}
              </span>
            </div>
            <a
              v-if="b.phone"
              :href="telHref(b.phone)"
              class="flex items-center gap-1.5 text-ink-gray-8 hover:text-ink-blue-3"
              @click.stop
            >
              <PhoneIcon class="size-3.5 text-ink-gray-5" />
              {{ formatPhone(b.phone) }}
            </a>
            <div v-if="b.deal_history" class="flex items-center gap-1.5 text-ink-gray-6">
              <HistoryIcon class="size-3.5 text-ink-gray-5" />
              {{ b.deal_history }}
            </div>
          </div>

          <div class="mb-2 mt-2.5 h-px border-b" />
          <div class="flex items-center justify-between text-xs text-ink-gray-5">
            <span>{{ b.last_active ? formatDate(b.last_active, '', true) : '' }}</span>
            <span v-if="b.message_count" class="flex items-center gap-1">
              <NoteIcon class="size-3" /> {{ b.message_count }}
            </span>
          </div>
          </router-link>
        </template>
        <template #footer>
          <div v-if="!col.buyers.length" class="px-1 py-2 text-sm text-ink-gray-4">
            {{ moving ? __('Drop buyer here') : __('No buyers') }}
          </div>
        </template>
      </Draggable>
    </div>
  </div>
</template>

<script setup>
import IndicatorIcon from '@/components/Icons/IndicatorIcon.vue'
import PhoneIcon from '@/components/Icons/PhoneIcon.vue'
import NoteIcon from '@/components/Icons/NoteIcon.vue'
import BadgeCheckIcon from '~icons/lucide/badge-check'
import HistoryIcon from '~icons/lucide/history'
import MoreHorizontalIcon from '~icons/lucide/more-horizontal'
import { formatDate, isTouchScreenDevice, parseColor } from '@/utils'
import { formatPhone } from '@/utils/phoneFormat'
import { globalStore } from '@/stores/global'
import { Badge, Dropdown, call, createResource, toast } from 'frappe-ui'
import Draggable from 'vuedraggable'
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'

const props = defineProps({
  lead: { type: String, required: true },
  view: { type: String, default: 'board' }, // 'board' | 'list'
})

const listCols = {
  gridTemplateColumns:
    'minmax(9rem,10rem) minmax(9rem,1.3fr) minmax(8rem,1.2fr) 9rem 6rem 8rem 3rem',
}

const { $socket } = globalStore()
const moving = ref(false)

// Canonical stage order + column colors (mirrors the InvestorLift board).
const STAGES = [
  { stage: 'New', color: 'blue' },
  { stage: 'Attempted to Contact', color: 'orange' },
  { stage: 'Not Interested', color: 'gray' },
  { stage: 'Interested', color: 'green' },
  { stage: 'Offer Made', color: 'purple' },
]

const buyers = createResource({
  url: 'crm.api.investorlift_ingest.get_deal_buyers',
  params: { lead: props.lead },
  cache: ['deal_buyers', props.lead],
  auto: true,
})

const columns = computed(() => {
  const rows = buyers.data || []
  const byStage = {}
  for (const s of STAGES) byStage[s.stage] = []
  for (const r of rows) {
    const stage = byStage[r.interest_stage] ? r.interest_stage : 'New'
    byStage[stage].push(r)
  }
  return STAGES.map((s) => ({
    stage: s.stage,
    color: parseColor(s.color),
    buyers: byStage[s.stage],
  }))
})

// flat, stage-ordered list of buyers for the list view (each tagged with its
// stage's indicator color so the Stage column matches the board's column dots)
const flatBuyers = computed(() =>
  columns.value.flatMap((c) =>
    c.buyers.map((b) => ({ ...b, _stageColor: c.color })),
  ),
)

function tagList(buyer_type) {
  return (buyer_type || '')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
}

function telHref(phone) {
  return 'tel:' + (phone || '').replace(/[^\d+]/g, '')
}

function stageOptions(buyer) {
  return [
    {
      group: __('Move to'),
      items: STAGES.filter(({ stage }) => stage !== buyer.interest_stage).map(
        ({ stage }) => ({
          label: stage,
          onClick: () => updateStage(buyer.name, stage),
        }),
      ),
    },
  ]
}

async function updateStage(relationship, toStage) {
  try {
    await call('crm.api.buyers.move_buyer_stage', {
      relationship,
      stage: toStage,
    })
    const row = (buyers.data || []).find((buyer) => buyer.name === relationship)
    if (row) row.interest_stage = toStage
  } catch (error) {
    await buyers.reload()
    toast.error(error.messages?.[0] || __('Could not move buyer'))
  }
}

function moveBuyer(event) {
  moving.value = false
  const relationship = event?.item?.dataset?.name
  const fromStage = event?.from?.dataset?.stage
  const toStage = event?.to?.dataset?.stage
  if (!relationship || !toStage || fromStage === toStage) return
  updateStage(relationship, toStage)
}

function onBuyers(data) {
  if (data.reference_doctype === 'CRM Lead' && data.reference_docname === props.lead) {
    buyers.reload()
  }
}
onMounted(() => $socket.on('crm_il_buyers', onBuyers))
onBeforeUnmount(() => $socket.off('crm_il_buyers', onBuyers))
</script>
