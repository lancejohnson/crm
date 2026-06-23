<template>
  <div class="rounded-md bg-surface-white shadow">
    <!-- Header -->
    <div class="flex items-start justify-between gap-4 flex-wrap px-4 pt-4 pb-3">
      <div>
        <div class="text-lg font-semibold text-ink-gray-9">
          {{ __('Activity') }}
        </div>
        <div class="text-sm text-ink-gray-5 mt-0.5">
          {{ __('Leads reached by call, text, and agreement in this range') }}
        </div>
      </div>

      <!-- Quo talk time (call duration) -->
      <Tooltip
        v-if="talkSecs.all"
        :text="
          __('Outbound {0} · All {1}', [
            formatDuration(talkSecs.out) || '0s',
            formatDuration(talkSecs.all) || '0s',
          ])
        "
      >
        <div
          class="rounded-md border border-outline-gray-1 px-3 py-1.5 text-right"
        >
          <div class="text-xs uppercase tracking-wide text-ink-gray-5">
            {{ __('Talk time') }}
          </div>
          <div class="text-lg font-semibold text-ink-gray-9 tabular-nums">
            {{ formatDuration(talkSecs.all) }}
          </div>
        </div>
      </Tooltip>
    </div>

    <div
      v-if="!rows.length"
      class="px-4 py-10 text-center text-ink-gray-5 border-t border-outline-gray-1"
    >
      {{ __('No activity in this range') }}
    </div>

    <table v-else class="w-full text-sm border-t border-outline-gray-1">
      <thead>
        <tr class="text-ink-gray-5 text-xs uppercase tracking-wide">
          <th rowspan="2" class="text-left font-medium py-2 pl-4 pr-2 align-bottom">
            {{ __('Activity') }}
          </th>
          <th
            colspan="2"
            class="text-center font-medium pt-2 pb-1 px-2 border-l border-outline-gray-1"
          >
            <Tooltip :text="__('Distinct leads with this activity')">
              <span>{{ __('Unique leads') }}</span>
            </Tooltip>
          </th>
          <th
            colspan="2"
            class="text-center font-medium pt-2 pb-1 px-2 border-l border-outline-gray-1"
          >
            <Tooltip :text="__('Every call / text / agreement logged')">
              <span>{{ __('Total actions') }}</span>
            </Tooltip>
          </th>
        </tr>
        <tr class="text-ink-gray-5 text-xs tracking-wide">
          <th class="text-right font-normal pb-2 px-2 w-24 border-l border-outline-gray-1">
            {{ __('Outbound') }}
          </th>
          <th class="text-right font-normal pb-2 px-2 w-24">
            {{ __('All') }}
          </th>
          <th class="text-right font-normal pb-2 px-2 w-24 border-l border-outline-gray-1">
            {{ __('Outbound') }}
          </th>
          <th class="text-right font-normal pb-2 pl-2 pr-4 w-24">
            {{ __('All') }}
          </th>
        </tr>
      </thead>
      <tbody>
        <template v-for="row in rows" :key="row.key">
          <tr
            class="border-t border-outline-gray-1 hover:bg-surface-gray-1 cursor-pointer"
            @click="toggle(row.key)"
          >
            <td class="py-2.5 pl-4 pr-2">
              <div class="flex items-center gap-2">
                <LucideChevronRight
                  class="size-3.5 text-ink-gray-5 transition-transform shrink-0"
                  :class="expanded.has(row.key) ? 'rotate-90' : ''"
                />
                <component
                  :is="iconFor(row.key)"
                  class="size-4 text-ink-gray-5 shrink-0"
                />
                <span class="text-ink-gray-8">{{ row.title }}</span>
              </div>
            </td>
            <!-- Unique leads: outbound / all (clickable → drill into Leads) -->
            <td class="text-right py-2.5 px-2 tabular-nums border-l border-outline-gray-1">
              <button
                v-if="row.unique_out"
                class="text-ink-gray-8 hover:text-ink-blue-3 hover:underline"
                @click.stop="drill(row, 'out')"
              >
                {{ fmt(row.unique_out) }}
              </button>
              <span v-else class="text-ink-gray-4">–</span>
            </td>
            <td class="text-right py-2.5 px-2 tabular-nums">
              <button
                v-if="row.unique_all"
                class="text-ink-gray-8 hover:text-ink-blue-3 hover:underline"
                @click.stop="drill(row, 'all')"
              >
                {{ fmt(row.unique_all) }}
              </button>
              <span v-else class="text-ink-gray-4">–</span>
            </td>
            <!-- Total actions: outbound / all -->
            <td class="text-right py-2.5 px-2 tabular-nums text-ink-gray-7 border-l border-outline-gray-1">
              {{ row.total_out ? fmt(row.total_out) : '–' }}
            </td>
            <td class="text-right py-2.5 pl-2 pr-4 tabular-nums text-ink-gray-7">
              {{ row.total_all ? fmt(row.total_all) : '–' }}
            </td>
          </tr>

          <!-- Unfolded: the leads behind this activity -->
          <tr v-if="expanded.has(row.key)" :key="row.key + '-leads'">
            <td colspan="5" class="bg-surface-gray-1 px-4 py-3">
              <div
                v-if="unfold[row.key]?.loading"
                class="text-ink-gray-5 text-sm py-2"
              >
                {{ __('Loading…') }}
              </div>
              <div
                v-else-if="!unfold[row.key]?.leads?.length"
                class="text-ink-gray-5 text-sm py-2"
              >
                {{ __('No leads to show.') }}
              </div>
              <div v-else>
                <div class="flex items-center justify-between mb-2">
                  <div class="text-xs uppercase tracking-wide text-ink-gray-5">
                    {{ __('Leads') }} ({{ unfold[row.key].count }})
                  </div>
                  <Button
                    variant="ghost"
                    :label="__('Open all in Leads')"
                    @click="drill(row, 'all')"
                  >
                    <template #suffix>
                      <LucideArrowRight class="size-3.5" />
                    </template>
                  </Button>
                </div>
                <div
                  class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-1 max-h-72 overflow-y-auto"
                >
                  <button
                    v-for="lead in unfold[row.key].leads"
                    :key="lead.name"
                    class="group flex items-center gap-2 rounded-md border border-outline-gray-1 bg-surface-white px-2.5 py-1.5 text-sm hover:border-outline-gray-3 hover:bg-surface-gray-2 transition-colors text-left"
                    @click="openLead(lead.name)"
                  >
                    <span class="truncate text-ink-gray-8 flex-1">{{
                      lead.lead_name
                    }}</span>
                    <span
                      v-if="row.key === 'calls' && lead.secs"
                      class="shrink-0 tabular-nums text-ink-gray-4 text-xs"
                      >{{ formatDuration(lead.secs) }}</span
                    >
                    <span class="shrink-0 tabular-nums text-ink-gray-5">{{
                      lead.count
                    }}</span>
                    <LucideArrowRight
                      class="size-3.5 text-ink-gray-4 shrink-0 opacity-0 group-hover:opacity-100"
                    />
                  </button>
                </div>
                <div
                  v-if="unfold[row.key].truncated"
                  class="text-xs text-ink-gray-5 mt-2"
                >
                  {{ __('Showing the first {0} leads.', [unfold[row.key].leads.length]) }}
                </div>
              </div>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import LucideChevronRight from '~icons/lucide/chevron-right'
import LucideArrowRight from '~icons/lucide/arrow-right'
import LucidePhone from '~icons/lucide/phone'
import LucideMessageSquare from '~icons/lucide/message-square'
import LucideFileSignature from '~icons/lucide/file-signature'
import { leadDrilldownStore } from '@/stores/leadDrilldown'
import { formatDuration } from '@/utils'
import { createResource, Button, Tooltip } from 'frappe-ui'
import { ref, computed, reactive } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  activity: { type: Array, default: () => [] },
  fromDate: { type: String, default: null },
  toDate: { type: String, default: null },
  user: { type: String, default: null },
})

const router = useRouter()
const drilldown = leadDrilldownStore()

const expanded = ref(new Set())
const unfold = reactive({}) // { [key]: { loading, leads, count, truncated } }

// Only show rows that actually have data so an absent doctype (texts /
// agreements not provisioned) silently drops out.
const rows = computed(() =>
  (props.activity || []).filter((r) => r.unique_all || r.total_all),
)

// Quo talk time = total call duration (lives on the calls row).
const talkSecs = computed(() => {
  const calls = (props.activity || []).find((r) => r.key === 'calls')
  return { out: calls?.secs_out || 0, all: calls?.secs_all || 0 }
})

const icons = {
  calls: LucidePhone,
  texts: LucideMessageSquare,
  agreements: LucideFileSignature,
}
function iconFor(key) {
  return icons[key] || LucidePhone
}

function fmt(n) {
  return (n ?? 0).toLocaleString()
}

const resolver = createResource({
  url: 'crm.api.leads_dashboard.get_activity_leads',
})

async function toggle(key) {
  const next = new Set(expanded.value)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
    loadLeads(key)
  }
  expanded.value = next
}

async function loadLeads(key) {
  // Cache per (key + range + user) so reopening is instant but a filter change refetches.
  const stamp = `${props.fromDate}|${props.toDate}|${props.user}`
  if (unfold[key] && unfold[key].stamp === stamp) return
  unfold[key] = { loading: true, leads: [], count: 0, truncated: false, stamp }
  const res = await resolver.submit({
    activity: key,
    scope: 'all',
    from_date: props.fromDate,
    to_date: props.toDate,
    user: props.user,
  })
  if (!res) {
    unfold[key] = { loading: false, leads: [], count: 0, truncated: false, stamp }
    return
  }
  unfold[key] = {
    loading: false,
    leads: res.leads || [],
    count: res.count || 0,
    truncated: res.truncated,
    stamp,
  }
}

async function drill(row, scope) {
  const res = await resolver.submit({
    activity: row.key,
    scope,
    from_date: props.fromDate,
    to_date: props.toDate,
    user: props.user,
  })
  if (!res) return
  const scopeLabel = scope === 'out' ? __('outbound') : __('all')
  drilldown.set({
    names: res.names,
    label: `${row.title} (${scopeLabel})`,
    sub: `${props.fromDate} – ${props.toDate}`,
    truncated: res.truncated,
  })
  router.push({ name: 'Leads', params: { viewType: 'list' } })
}

function openLead(name) {
  router.push({ name: 'Lead', params: { leadId: name } })
}
</script>
