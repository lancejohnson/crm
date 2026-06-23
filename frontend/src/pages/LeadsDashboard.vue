<template>
  <div class="flex flex-col h-full overflow-hidden">
    <LayoutHeader>
      <template #left-header>
        <ViewBreadcrumbs routeName="Dashboard" />
      </template>
      <template #right-header>
        <Button
          :label="__('Refresh')"
          :iconLeft="LucideRefreshCcw"
          :loading="dashboard.loading"
          @click="dashboard.reload"
        />
      </template>
    </LayoutHeader>

    <div class="p-5 pb-2 flex items-center gap-4 flex-wrap">
      <Dropdown
        v-if="!showDatePicker"
        :options="rangeOptions"
        class="form-control"
        :button="{
          label: __(preset),
          class:
            '!w-full justify-start [&>span]:mr-auto [&>svg]:text-ink-gray-5',
          variant: 'outline',
          iconRight: 'chevron-down',
          iconLeft: 'calendar',
        }"
      />
      <DateRangePicker
        v-else
        ref="datePickerRef"
        class="!w-48"
        :value="filters.period"
        variant="outline"
        :placeholder="__('Period')"
        :formatter="formatRange"
        @change="
          (v) => {
            showDatePicker = false
            if (!v) {
              filters.period = getLastXDays()
              preset = 'Last 30 Days'
            } else {
              filters.period = v
              preset = formatter(v)
            }
            dashboard.reload()
          }
        "
      >
        <template #prefix>
          <LucideCalendar class="size-4 text-ink-gray-5 mr-2" />
        </template>
      </DateRangePicker>

      <Link
        v-if="isAdmin() || isManager()"
        class="form-control w-48"
        variant="outline"
        :value="filters.user && getUser(filters.user).full_name"
        doctype="User"
        :filters="{
          name: ['in', users.data?.crmUsers?.map((u) => u.name)],
          ignore_user_type: 1,
        }"
        :placeholder="__('All users')"
        :hideMe="true"
        @change="(v) => updateUser(v)"
      >
        <template #prefix>
          <UserAvatar
            v-if="filters.user"
            class="mr-2"
            :user="filters.user"
            size="sm"
          />
        </template>
        <template #item-prefix="{ option }">
          <UserAvatar class="mr-2" :user="option.value" size="sm" />
        </template>
        <template #item-label="{ option }">
          <Tooltip :text="option.value">
            <div class="cursor-pointer">
              {{ getUser(option.value).full_name }}
            </div>
          </Tooltip>
        </template>
      </Link>
    </div>

    <div class="flex-1 overflow-y-auto px-5 pb-6">
      <div v-if="dashboard.loading" class="text-ink-gray-5 p-4">
        {{ __('Loading…') }}
      </div>
      <div v-else-if="data" class="flex flex-col gap-5">
        <!-- Summary numbers -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div
            v-for="(stat, i) in data.summary"
            :key="i"
            class="rounded shadow overflow-hidden bg-surface-white"
          >
            <NumberChart class="!items-start" :config="stat" />
          </div>
        </div>

        <!-- Activity: leads called / texted + agreements sent (unfold to leads) -->
        <ActivityReport
          :activity="data.activity"
          :fromDate="fromDate"
          :toDate="toDate"
          :user="filters.user"
        />

        <!-- 1. New leads per day -->
        <div class="rounded-md bg-surface-white shadow h-80 p-1">
          <AxisChart :config="data.new_leads_trend" />
        </div>

        <!-- 2. Status Change Report (table + flow + drill-down) -->
        <StatusChangeReport
          :fromDate="fromDate"
          :toDate="toDate"
          :user="filters.user"
        />

        <!-- 3. New leads by source (click a source to drill into its leads) -->
        <div class="rounded-md bg-surface-white shadow overflow-hidden">
          <div
            v-if="sources.length"
            class="flex items-center gap-2 flex-wrap p-1"
          >
            <div class="h-80 flex-1 min-w-[300px]">
              <DonutChart :config="sourceConfig" />
            </div>
            <div class="flex-1 min-w-[240px] p-4 flex flex-col gap-1.5">
              <div class="text-xs uppercase tracking-wide text-ink-gray-5 mb-1">
                {{ __('Open a source in Leads') }}
              </div>
              <button
                v-for="(s, i) in sources"
                :key="s.source"
                class="group flex items-center gap-2 rounded-md border border-outline-gray-1 px-2.5 py-1.5 text-sm hover:border-outline-gray-3 hover:bg-surface-gray-2 transition-colors"
                @click="drillSource(s.source)"
              >
                <span
                  class="size-2.5 rounded-full shrink-0"
                  :style="{ backgroundColor: palette[i % palette.length] }"
                />
                <span class="truncate text-ink-gray-8">{{ s.source }}</span>
                <span class="ml-auto shrink-0 tabular-nums text-ink-gray-6">
                  {{ s.count }}
                  <span class="text-ink-gray-4">({{ s.pct }}%)</span>
                </span>
                <LucideArrowRight class="size-3.5 text-ink-gray-5 shrink-0" />
              </button>
            </div>
          </div>
          <div
            v-else
            class="h-80 flex items-center justify-center text-ink-gray-5"
          >
            {{ __('No leads in this range') }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import ViewBreadcrumbs from '@/components/ViewBreadcrumbs.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import Link from '@/components/Controls/Link.vue'
import StatusChangeReport from '@/components/Dashboard/StatusChangeReport.vue'
import ActivityReport from '@/components/Dashboard/ActivityReport.vue'
import LucideRefreshCcw from '~icons/lucide/refresh-ccw'
import LucideArrowRight from '~icons/lucide/arrow-right'
import { leadDrilldownStore } from '@/stores/leadDrilldown'
import { useRouter } from 'vue-router'
import { usersStore } from '@/stores/users'
import {
  getLastXDays,
  getDateRange,
  formatter,
  formatRange,
} from '@/utils/dashboard'
import {
  usePageMeta,
  createResource,
  AxisChart,
  DonutChart,
  NumberChart,
  DateRangePicker,
  Dropdown,
  Tooltip,
} from 'frappe-ui'
import { ref, reactive, computed } from 'vue'

const { users, getUser, isManager, isAdmin } = usersStore()

const showDatePicker = ref(false)
const datePickerRef = ref(null)
const preset = ref('Today')

const filters = reactive({
  period: getDateRange('Today'),
  user: null,
})

const fromDate = computed(() => filters.period?.split(',')[0] ?? null)
const toDate = computed(() => filters.period?.split(',')[1] ?? null)

const dashboard = createResource({
  url: 'crm.api.leads_dashboard.get_leads_dashboard',
  makeParams() {
    return {
      from_date: fromDate.value,
      to_date: toDate.value,
      user: filters.user,
    }
  },
  auto: true,
})

const data = computed(() => dashboard.data)

// --- Leads by source: clickable drill-down --------------------------------
const router = useRouter()
const drilldown = leadDrilldownStore()

// Shared colour order for the donut + the clickable source list.
const palette = [
  '#2490EF',
  '#FFB300',
  '#28A745',
  '#E24C4C',
  '#7C4DFF',
  '#00BCD4',
  '#FF7043',
  '#9C27B0',
]

const sourceConfig = computed(() => ({
  ...(data.value?.leads_by_source || {}),
  colors: palette,
}))

const sources = computed(() => {
  const rows = data.value?.leads_by_source?.data || []
  const total = rows.reduce((acc, r) => acc + (r.count || 0), 0)
  return rows.map((r) => ({
    source: r.source,
    count: r.count,
    pct: total ? Math.round((r.count / total) * 100) : 0,
  }))
})

const sourceResolver = createResource({
  url: 'crm.api.leads_dashboard.get_leads_by_source_names',
})

async function drillSource(source) {
  const res = await sourceResolver.submit({
    source,
    from_date: fromDate.value,
    to_date: toDate.value,
    user: filters.user,
  })
  if (!res) return
  drilldown.set({
    names: res.names,
    label: `${__('Source')}: ${source}`,
    sub: `${__('created')} ${fromDate.value} – ${toDate.value}`,
    truncated: res.truncated,
  })
  router.push({ name: 'Leads', params: { viewType: 'list' } })
}

function updateUser(v) {
  filters.user = v
  dashboard.reload()
}

function applyPreset(label, period) {
  preset.value = label
  filters.period = period
  dashboard.reload()
}

const calendarPresets = [
  'Today',
  'Yesterday',
  'This Week',
  'Last Week',
  'This Quarter',
  'Last Quarter',
]

const lastXDayPresets = [
  ['Last 7 Days', 7],
  ['Last 30 Days', 30],
  ['Last 60 Days', 60],
  ['Last 90 Days', 90],
]

const rangeOptions = computed(() => [
  {
    group: 'Presets',
    hideLabel: true,
    items: calendarPresets.map((label) => ({
      label: __(label),
      onClick: () => applyPreset(label, getDateRange(label)),
    })),
  },
  {
    group: 'Rolling',
    hideLabel: true,
    items: lastXDayPresets.map(([label, days]) => ({
      label: __(label),
      onClick: () => applyPreset(label, getLastXDays(days)),
    })),
  },
  {
    label: __('Custom Range'),
    onClick: () => {
      showDatePicker.value = true
      setTimeout(() => datePickerRef.value?.open(), 0)
      preset.value = 'Custom Range'
      filters.period = null
    },
  },
])

usePageMeta(() => {
  return { title: __('Leads Dashboard') }
})
</script>
