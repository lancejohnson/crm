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
        :placeholder="__('Sales User')"
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

        <!-- 3. New leads by source -->
        <div
          class="rounded-md bg-surface-white shadow h-80 overflow-hidden lg:w-1/2"
        >
          <DonutChart
            v-if="data.leads_by_source.data.length"
            :config="data.leads_by_source"
          />
          <div
            v-else
            class="h-full flex items-center justify-center text-ink-gray-5"
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
import LucideRefreshCcw from '~icons/lucide/refresh-ccw'
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
