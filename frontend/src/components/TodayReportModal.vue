<template>
  <Dialog v-model="show" :options="{ title: __('Today report'), size: 'xl' }">
    <template #body-content>
      <DialogDescription class="mb-4 text-sm text-ink-gray-6">
        {{ scopeDescription }}
      </DialogDescription>
      <div v-if="loading" class="flex min-h-48 items-center justify-center">
        <LoadingIndicator class="size-6 text-ink-gray-5" />
      </div>
      <div v-else class="flex flex-col gap-5">
        <div class="rounded-xl border border-outline-orange-1 bg-surface-orange-1 p-4">
          <div class="flex items-start justify-between gap-4">
            <div>
              <div class="text-sm font-medium text-ink-orange-3">
                {{ isScoped ? __('Your streak') : __('Team streak') }}
              </div>
              <div class="mt-1 text-2xl font-semibold text-ink-gray-9">
                🔥 {{ streak.current }}
                {{ streak.current === 1 ? __('business day') : __('business days') }}
              </div>
              <div class="mt-1 text-sm text-ink-gray-6">
                <template v-if="streak.current">
                  {{ __('100% completed through {0}', [dayLabel(streak.through)]) }}
                </template>
                <template v-else>{{ __('Complete every card to start the streak.') }}</template>
              </div>
            </div>
            <Badge
              variant="subtle"
              theme="orange"
              :label="__('Best: {0}', [streak.best || 0])"
            />
          </div>
          <div class="mt-3 text-xs text-ink-gray-5">{{ report?.definition }}</div>
        </div>

        <div>
          <div class="mb-2 flex items-center justify-between gap-3">
            <div>
              <div class="text-sm font-semibold text-ink-gray-8">{{ __('Today') }}</div>
              <div class="text-xs text-ink-gray-5">
                {{ today.done + today.skipped }} {{ __('of') }} {{ today.total }} {{ __('cards resolved') }}
              </div>
            </div>
            <div class="text-2xl font-semibold text-ink-gray-9">{{ today.completion_rate }}%</div>
          </div>
          <div class="h-2 overflow-hidden rounded-full bg-surface-gray-2">
            <div
              class="h-full rounded-full bg-surface-green-3 transition-all"
              :style="{ width: `${today.completion_rate || 0}%` }"
            />
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricCard :label="__('Total')" :value="today.total" />
          <MetricCard :label="__('Done')" :value="today.done" tone="green" />
          <MetricCard :label="__('Skipped')" :value="today.skipped" tone="orange" />
          <MetricCard :label="__('Remaining')" :value="today.remaining" tone="blue" />
        </div>

        <div v-if="report?.completed_by?.length">
          <div class="mb-2 text-sm font-semibold text-ink-gray-8">{{ __('Completed by') }}</div>
          <div class="flex flex-wrap gap-2">
            <div
              v-for="person in report.completed_by"
              :key="person.user"
              class="rounded-full bg-surface-gray-2 px-3 py-1.5 text-sm text-ink-gray-7"
            >
              <span class="font-medium">{{ person.name }}</span>
              <span class="ml-1 text-ink-gray-5">{{ person.done }}</span>
            </div>
          </div>
        </div>

        <div>
          <div class="mb-2 flex items-center justify-between gap-3">
            <div class="text-sm font-semibold text-ink-gray-8">
              {{ isScoped ? __('Recent business days (yours)') : __('Recent business days') }}
            </div>
            <div class="text-xs text-ink-gray-5">
              {{ __('Average: {0}%', [report?.recent_average || 0]) }}
            </div>
          </div>
          <div
            v-if="report?.recent?.length"
            class="divide-y divide-outline-gray-1 overflow-hidden rounded-lg border border-outline-gray-1"
          >
            <div
              v-for="day in report.recent"
              :key="day.date"
              class="grid grid-cols-[1fr_auto] items-center gap-3 px-3 py-2.5"
            >
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span class="text-sm font-medium text-ink-gray-8">{{ dayLabel(day.date) }}</span>
                  <Badge
                    v-if="day.perfect"
                    variant="subtle"
                    theme="green"
                    :label="__('Perfect')"
                  />
                </div>
                <div class="mt-0.5 text-xs text-ink-gray-5">
                  {{ day.done }} {{ __('done') }} · {{ day.skipped }} {{ __('skipped') }} ·
                  {{ day.remaining }} {{ __('left') }}
                </div>
              </div>
              <div class="text-sm font-semibold text-ink-gray-8">{{ day.completion_rate }}%</div>
            </div>
          </div>
          <div v-else class="rounded-lg bg-surface-gray-1 px-3 py-3 text-sm text-ink-gray-5">
            {{ __('No completed business days to show yet.') }}
          </div>
        </div>
      </div>
    </template>
    <template #actions>
      <Button class="w-full" :label="__('Close')" @click="show = false" />
    </template>
  </Dialog>
</template>

<script setup>
import MetricCard from '@/components/TodayReportMetric.vue'
import { Badge, Button, Dialog, LoadingIndicator } from 'frappe-ui'
import { DialogDescription } from 'reka-ui'
import { computed } from 'vue'

const props = defineProps({
  report: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})
const show = defineModel({ type: Boolean })

const today = computed(() =>
  props.report?.today || {
    total: 0,
    done: 0,
    skipped: 0,
    remaining: 0,
    completion_rate: 0,
  },
)
const streak = computed(() => props.report?.streak || { current: 0, best: 0, through: null })

// Every figure in the panel now describes the SAME card set — when a board is
// scoped to one person, so are their streak and recent-day history (see
// get_today_report). The team numbers are still what the "all" board shows.
const isScoped = computed(() => props.report?.scope?.today === 'owner')
const scopeDescription = computed(() =>
  isScoped.value
    ? __('Your progress and streak on today’s calling queue.')
    : __('Shared progress for today’s calling queue.'),
)

function dayLabel(date) {
  if (!date) return ''
  return new Date(`${date}T00:00:00`).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
}
</script>
