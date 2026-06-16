<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs
        :items="[{ label: 'Call Review', route: { name: 'Call Review' } }]"
      />
    </template>
    <template #right-header>
      <div class="flex items-center gap-2">
        <!-- rep filter -->
        <FormControl
          type="select"
          :options="repOptions"
          v-model="rep"
          :placeholder="__('All reps')"
        />
        <!-- date nav -->
        <div class="flex items-center gap-1">
          <Button variant="ghost" icon="chevron-left" @click="shiftDay(-1)" />
          <input
            type="date"
            class="rounded bg-surface-gray-2 px-2 py-1 text-sm text-ink-gray-8 focus:outline-none"
            :max="todayStr"
            v-model="date"
          />
          <Button
            variant="ghost"
            icon="chevron-right"
            :disabled="date >= todayStr"
            @click="shiftDay(1)"
          />
          <Button
            v-if="date !== todayStr"
            variant="subtle"
            :label="__('Today')"
            @click="date = todayStr"
          />
        </div>
      </div>
    </template>
  </LayoutHeader>

  <div class="flex flex-1 flex-col overflow-y-auto">
    <!-- overall summary -->
    <div class="flex flex-wrap gap-3 border-b bg-surface-menu-bar px-5 py-3">
      <StatCard :label="__('Calls')" :value="totals.calls" />
      <StatCard
        :label="__('Outbound / Inbound')"
        :value="`${totals.outbound} / ${totals.inbound}`"
      />
      <StatCard :label="__('Talk time')" :value="formatDuration(totals.talk_time) || '0s'" />
      <StatCard :label="__('Leads')" :value="totals.leads" />
      <StatCard :label="__('First-time calls')" :value="totals.first_time" />
    </div>

    <div
      v-if="review.loading && !review.data"
      class="p-6 text-sm text-ink-gray-5"
    >
      {{ __('Loading…') }}
    </div>
    <div
      v-else-if="!reps.length"
      class="flex flex-1 items-center justify-center p-10 text-sm text-ink-gray-5"
    >
      {{ __('No calls logged on this day.') }}
    </div>

    <!-- per-rep sections -->
    <div v-else class="flex flex-col gap-6 p-5">
      <section v-for="r in reps" :key="r.user || 'unassigned'">
        <div class="mb-2 flex items-center gap-3">
          <h2 class="text-base font-semibold text-ink-gray-9">
            {{ r.user_name }}
          </h2>
          <span class="text-xs text-ink-gray-5">
            {{ r.totals.calls }} {{ __('calls') }} ·
            {{ r.totals.outbound }}↑ / {{ r.totals.inbound }}↓ ·
            {{ formatDuration(r.totals.talk_time) || '0s' }} {{ __('talk') }} ·
            {{ r.totals.leads }} {{ __('leads') }}
            <template v-if="r.totals.first_time">
              · {{ r.totals.first_time }} {{ __('first-time') }}
            </template>
          </span>
        </div>

        <!-- lead cards -->
        <div class="flex flex-col gap-3">
          <div
            v-for="ld in r.leads"
            :key="ld.reference_name || ld.lead_name"
            class="rounded-lg border bg-surface-white"
          >
            <!-- lead header -->
            <div
              class="flex flex-wrap items-center gap-2 border-b px-4 py-2.5"
            >
              <button
                class="font-medium text-ink-gray-8 hover:text-ink-gray-9 hover:underline"
                :disabled="ld.reference_doctype !== 'CRM Lead'"
                @click="openLead(ld)"
              >
                {{ ld.lead_name }}
              </button>
              <Badge
                v-if="ld.status"
                :label="ld.status"
                variant="subtle"
                theme="gray"
              />
              <Badge
                v-if="ld.first_time_today"
                :label="__('First call')"
                variant="subtle"
                theme="green"
              />
              <span v-if="ld.mobile_no" class="text-xs text-ink-gray-4">
                {{ ld.mobile_no }}
              </span>
              <span class="ml-auto text-xs text-ink-gray-4">
                {{ ld.calls.length }}
                {{ ld.calls.length === 1 ? __('call') : __('calls') }}
              </span>
            </div>

            <!-- calls -->
            <div class="flex flex-col divide-y">
              <div
                v-for="call in ld.calls"
                :key="call.name"
                class="flex flex-col gap-2 px-4 py-2.5"
              >
                <div class="flex flex-wrap items-center gap-3 text-sm">
                  <span class="w-16 shrink-0 text-ink-gray-5">
                    {{ formatDate(call.time, 'h:mm a') }}
                  </span>
                  <span
                    class="flex items-center gap-1"
                    :title="call.type"
                  >
                    <FeatherIcon
                      :name="call.type === 'Incoming' ? 'phone-incoming' : 'phone-outgoing'"
                      class="h-4 w-4"
                      :class="call.type === 'Incoming' ? 'text-ink-blue-3' : 'text-ink-green-3'"
                    />
                    <span class="text-ink-gray-6">
                      {{ formatDuration(call.duration) || '0s' }}
                    </span>
                  </span>
                  <Badge
                    :label="call.status"
                    variant="outline"
                    :theme="statusTheme(call.status)"
                  />
                  <Badge
                    v-if="call.call_outcome"
                    :label="call.call_outcome"
                    variant="subtle"
                    theme="blue"
                  />
                  <audio
                    v-if="call.recording_url"
                    controls
                    preload="none"
                    :src="call.recording_url"
                    class="ml-auto h-8 max-w-[260px]"
                  />
                  <span v-else class="ml-auto text-xs text-ink-gray-4">
                    {{ __('No recording') }}
                  </span>
                  <Button
                    v-if="call.ai_summary"
                    variant="ghost"
                    :label="expanded[call.name] ? __('Hide summary') : __('AI summary')"
                    @click="toggle(call.name)"
                  />
                </div>
                <div
                  v-if="call.ai_summary && expanded[call.name]"
                  class="whitespace-pre-wrap rounded bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-7"
                >
                  {{ call.ai_summary }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import { formatDate, formatDuration } from '@/utils'
import {
  Breadcrumbs,
  Button,
  Badge,
  FormControl,
  FeatherIcon,
  createResource,
} from 'frappe-ui'
import { ref, computed, reactive, watch, h } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

// local YYYY-MM-DD for "today" (browser tz; matches the user's working day)
const todayStr = (() => {
  const d = new Date()
  const off = d.getTimezoneOffset()
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10)
})()

const date = ref(todayStr)
const rep = ref('')
const expanded = reactive({})

const review = createResource({
  url: 'crm.api.reports.get_call_review',
  makeParams() {
    return { date: date.value, user: rep.value || undefined }
  },
  auto: true,
})

const repsResource = createResource({
  url: 'crm.api.reports.get_call_review_reps',
  auto: true,
})

const reps = computed(() => review.data?.reps || [])
const totals = computed(
  () =>
    review.data?.totals || {
      calls: 0,
      inbound: 0,
      outbound: 0,
      talk_time: 0,
      leads: 0,
      first_time: 0,
    },
)

const repOptions = computed(() => [
  { label: __('All reps'), value: '' },
  ...(repsResource.data || []),
])

watch([date, rep], () => review.reload())

function shiftDay(delta) {
  const d = new Date(date.value + 'T00:00:00')
  d.setDate(d.getDate() + delta)
  const next = d.toISOString().slice(0, 10)
  if (next > todayStr) return
  date.value = next
}

function toggle(name) {
  expanded[name] = !expanded[name]
}

function openLead(ld) {
  if (ld.reference_doctype !== 'CRM Lead' || !ld.reference_name) return
  router.push({ name: 'Lead', params: { leadId: ld.reference_name } })
}

function statusTheme(status) {
  if (status === 'Completed') return 'green'
  if (['No Answer', 'Busy', 'Failed', 'Canceled'].includes(status)) return 'orange'
  return 'gray'
}

// tiny inline stat card
const StatCard = (props) =>
  h('div', { class: 'flex flex-col rounded-md bg-surface-white px-3 py-1.5 min-w-[110px]' }, [
    h('span', { class: 'text-xs text-ink-gray-5' }, props.label),
    h('span', { class: 'text-lg font-semibold text-ink-gray-9' }, String(props.value)),
  ])
StatCard.props = ['label', 'value']
</script>
