<template>
  <Dialog v-model="show" :options="{ title: __('Team activity'), size: '4xl' }">
    <template #body-content>
      <div class="max-h-[68vh] overflow-y-auto pr-1">
        <div class="flex flex-col gap-4">
          <div class="flex flex-wrap items-end justify-between gap-3">
            <DialogDescription class="text-sm text-ink-gray-6">
              {{
                __(
                  'Calls, human-sent Quo texts, completed tasks, and finished Today cards.',
                )
              }}
              <span class="mt-0.5 block text-xs text-ink-gray-5">
                {{ __('Automated sequence texts are excluded.') }}
              </span>
            </DialogDescription>
            <div class="flex flex-wrap items-center gap-2">
              <FormControl v-model="selectedDate" type="date" class="w-36" />
              <Button
                v-if="selectedDate !== localToday()"
                :label="__('Today')"
                @click="selectedDate = localToday()"
              />
              <Button :label="__('Daily goals')" @click="beginGoalEdit" />
              <Button
                icon="refresh-cw"
                :loading="progress.loading"
                @click="reload"
              />
            </div>
          </div>

          <div
            v-if="editingGoals"
            class="rounded-xl border border-outline-gray-2 bg-surface-gray-1 p-4"
          >
            <div class="mb-3 flex items-start justify-between gap-3">
              <div>
                <div class="text-sm font-semibold text-ink-gray-8">
                  {{ __('Daily goals') }}
                </div>
                <div class="text-xs text-ink-gray-5">
                  {{
                    __(
                      'Set a goal to show progress; leave it at 0 to track the count only.',
                    )
                  }}
                </div>
              </div>
              <Button variant="ghost" icon="x" @click="editingGoals = false" />
            </div>
            <div class="overflow-x-auto">
              <div class="min-w-[560px]">
                <div
                  class="grid grid-cols-[minmax(150px,1fr)_repeat(4,90px)] gap-2 px-2 pb-1 text-xs text-ink-gray-5"
                >
                  <div>{{ __('Team member') }}</div>
                  <div v-for="metric in goalMetrics" :key="metric.key">
                    {{ metric.label }}
                  </div>
                </div>
                <div
                  v-for="person in progress.data?.people || []"
                  :key="person.user"
                  class="grid grid-cols-[minmax(150px,1fr)_repeat(4,90px)] items-center gap-2 rounded-lg px-2 py-1.5 odd:bg-surface-white"
                >
                  <div class="flex min-w-0 items-center gap-2">
                    <UserAvatar :user="person.user" size="sm" />
                    <span
                      class="truncate text-sm font-medium text-ink-gray-8"
                      >{{ person.name }}</span
                    >
                  </div>
                  <FormControl
                    v-for="metric in goalMetrics"
                    :key="metric.key"
                    v-model="goalDraft[person.user][metric.key]"
                    type="number"
                    min="0"
                    max="1000"
                  />
                </div>
              </div>
            </div>
            <div class="mt-3 flex justify-end gap-2">
              <Button :label="__('Cancel')" @click="editingGoals = false" />
              <Button
                variant="solid"
                :label="__('Save goals')"
                :loading="savingGoals"
                @click="saveGoals"
              />
            </div>
          </div>

          <div
            v-if="progress.loading && !progress.data"
            class="flex min-h-52 items-center justify-center"
          >
            <LoadingIndicator class="size-6 text-ink-gray-5" />
          </div>

          <div v-else-if="people.length" class="flex flex-col gap-3">
            <div
              v-for="person in people"
              :key="person.user"
              class="rounded-xl border border-outline-gray-1 bg-surface-white p-4"
            >
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div class="flex min-w-0 items-center gap-3">
                  <UserAvatar :user="person.user" size="lg" />
                  <div class="min-w-0">
                    <div
                      class="truncate text-base font-semibold text-ink-gray-9"
                    >
                      {{ person.name }}
                    </div>
                    <div class="mt-0.5 text-xs text-ink-gray-5">
                      <template v-if="lastEvent(person)">
                        {{
                          __('Last activity {0}', [
                            relativeTime(lastEvent(person).at),
                          ])
                        }}
                        · {{ formatTime(lastEvent(person).at) }}
                      </template>
                      <template v-else>{{
                        __('No activity this day')
                      }}</template>
                    </div>
                  </div>
                </div>
                <div class="text-right">
                  <div
                    v-if="goalTotal(person)"
                    class="text-lg font-semibold text-ink-gray-9"
                  >
                    {{ goalPercent(person) }}%
                  </div>
                  <div class="text-xs text-ink-gray-5">
                    {{ formatDuration(person.counts.talk_seconds) }}
                    {{ __('talk time') }}
                  </div>
                </div>
              </div>

              <div
                v-if="goalTotal(person)"
                class="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-gray-2"
              >
                <div
                  class="h-full rounded-full transition-all"
                  :class="
                    goalPercent(person) >= 100
                      ? 'bg-surface-green-3'
                      : 'bg-surface-blue-3'
                  "
                  :style="{ width: `${Math.min(100, goalPercent(person))}%` }"
                />
              </div>

              <div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                <div
                  v-for="metric in goalMetrics"
                  :key="metric.key"
                  class="rounded-lg bg-surface-gray-1 px-3 py-2"
                >
                  <div class="flex items-baseline justify-between gap-2">
                    <span class="text-xs text-ink-gray-5">{{
                      metric.label
                    }}</span>
                    <span
                      v-if="person.goals?.[metric.key]"
                      class="text-xs text-ink-gray-4"
                    >
                      / {{ person.goals[metric.key] }}
                    </span>
                  </div>
                  <div
                    class="mt-0.5 text-lg font-semibold"
                    :class="metric.textClass"
                  >
                    {{ person.counts[metric.key] || 0 }}
                  </div>
                  <div
                    v-if="metric.key === 'calls'"
                    class="text-[11px] text-ink-gray-5"
                  >
                    {{ person.counts.outbound_calls }} ↗ ·
                    {{ person.counts.inbound_calls }} ↙
                  </div>
                </div>
              </div>

              <div class="mt-4">
                <div
                  class="mb-1.5 flex items-center justify-between gap-3 text-[11px] text-ink-gray-5"
                >
                  <span>{{ firstTime(person) || '—' }}</span>
                  <span>{{ __('Activity through the day') }}</span>
                  <span>{{
                    lastEvent(person) ? formatTime(lastEvent(person).at) : '—'
                  }}</span>
                </div>
                <div
                  class="flex h-10 items-end gap-px rounded-md bg-surface-gray-1 px-1.5 py-1"
                >
                  <div
                    v-for="(bin, index) in activityBins(person)"
                    :key="index"
                    class="min-w-0 flex-1 rounded-sm opacity-90"
                    :class="bin.color"
                    :style="{ height: `${bin.height}px` }"
                    :title="bin.title"
                  />
                </div>
                <div class="mt-1 grid grid-cols-5 text-[10px] text-ink-gray-4">
                  <span>6a</span><span class="text-center">10a</span
                  ><span class="text-center">2p</span>
                  <span class="text-center">6p</span
                  ><span class="text-right">10p</span>
                </div>
              </div>
            </div>
          </div>

          <div
            v-else
            class="rounded-xl bg-surface-gray-1 px-4 py-8 text-center text-sm text-ink-gray-5"
          >
            {{ __('No team activity found for this day.') }}
          </div>

          <div
            class="flex flex-wrap items-center justify-between gap-3 text-xs text-ink-gray-5"
          >
            <div class="flex flex-wrap items-center gap-3">
              <span
                v-for="metric in goalMetrics"
                :key="metric.key"
                class="flex items-center gap-1"
              >
                <span class="size-2 rounded-sm" :class="metric.dotClass" />
                {{ metric.label }}
              </span>
            </div>
            <div v-if="unattributedTotal">
              {{
                __(
                  '{0} activities could not be safely attributed and are not shown.',
                  [unattributedTotal],
                )
              }}
            </div>
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
import UserAvatar from '@/components/UserAvatar.vue'
import {
  Button,
  Dialog,
  FormControl,
  LoadingIndicator,
  call,
  createResource,
  toast,
} from 'frappe-ui'
import { DialogDescription } from 'reka-ui'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'

const show = defineModel({ type: Boolean })
const selectedDate = ref(localToday())
const editingGoals = ref(false)
const savingGoals = ref(false)
const goalDraft = reactive({})
const clock = ref(Date.now())
let refreshTimer = null
let clockTimer = null

const goalMetrics = [
  {
    key: 'calls',
    label: __('Calls'),
    textClass: 'text-ink-blue-3',
    dotClass: 'bg-surface-blue-3',
  },
  {
    key: 'texts',
    label: __('Texts'),
    textClass: 'text-ink-green-3',
    dotClass: 'bg-surface-green-3',
  },
  {
    key: 'tasks',
    label: __('Tasks'),
    textClass: 'text-ink-orange-3',
    dotClass: 'bg-surface-orange-3',
  },
  {
    key: 'today',
    label: __('Cards'),
    textClass: 'text-ink-violet-3',
    dotClass: 'bg-surface-violet-3',
  },
]

const progress = createResource({
  url: 'crm.api.activity_progress.get_activity_progress',
  makeParams: () => ({ for_date: selectedDate.value }),
  auto: false,
})

const people = computed(() => {
  const rows = [...(progress.data?.people || [])]
  return rows.sort((a, b) => {
    const aLast = lastEvent(a)?.at || ''
    const bLast = lastEvent(b)?.at || ''
    return bLast.localeCompare(aLast) || a.name.localeCompare(b.name)
  })
})

const unattributedTotal = computed(() =>
  Object.values(progress.data?.unattributed || {}).reduce(
    (sum, value) => sum + Number(value || 0),
    0,
  ),
)

function localToday() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function reload() {
  return progress.reload()
}

watch(show, (open) => {
  if (!open) {
    clearInterval(refreshTimer)
    clearInterval(clockTimer)
    refreshTimer = null
    clockTimer = null
    editingGoals.value = false
    return
  }
  selectedDate.value = localToday()
  reload()
  refreshTimer = setInterval(() => {
    if (selectedDate.value === localToday()) reload()
  }, 60_000)
  clockTimer = setInterval(() => (clock.value = Date.now()), 60_000)
})

watch(selectedDate, () => {
  if (show.value) reload()
})

onBeforeUnmount(() => {
  clearInterval(refreshTimer)
  clearInterval(clockTimer)
})

function parseDateTime(value) {
  if (!value) return null
  if (value instanceof Date) return value
  return new Date(String(value).replace(' ', 'T'))
}

function lastEvent(person) {
  return person.events?.length ? person.events[person.events.length - 1] : null
}

function firstTime(person) {
  const first = person.events?.[0]
  return first ? formatTime(first.at) : ''
}

function formatTime(value) {
  const date = parseDateTime(value)
  if (!date || Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  })
}

function relativeTime(value) {
  if (selectedDate.value !== localToday()) return __('at')
  const date = parseDateTime(value)
  if (!date) return ''
  const minutes = Math.max(
    0,
    Math.round((clock.value - date.getTime()) / 60_000),
  )
  if (minutes < 1) return __('just now')
  if (minutes < 60) return __('{0}m ago', [minutes])
  const hours = Math.floor(minutes / 60)
  const remainder = minutes % 60
  return remainder
    ? __('{0}h {1}m ago', [hours, remainder])
    : __('{0}h ago', [hours])
}

function formatDuration(seconds) {
  const mins = Math.round(Number(seconds || 0) / 60)
  if (mins < 60) return `${mins}m`
  const hours = Math.floor(mins / 60)
  return `${hours}h ${mins % 60}m`
}

function goalTotal(person) {
  return goalMetrics.reduce(
    (sum, metric) => sum + Number(person.goals?.[metric.key] || 0),
    0,
  )
}

function goalDone(person) {
  return goalMetrics.reduce((sum, metric) => {
    if (!Number(person.goals?.[metric.key] || 0)) return sum
    return sum + Number(person.counts?.[metric.key] || 0)
  }, 0)
}

function goalPercent(person) {
  const total = goalTotal(person)
  return total ? Math.round((goalDone(person) * 100) / total) : 0
}

function activityBins(person) {
  const startHour = 6
  const binMinutes = 30
  const count = 32
  const bins = Array.from({ length: count }, (_, index) => ({
    index,
    counts: { calls: 0, texts: 0, tasks: 0, today: 0 },
    total: 0,
  }))
  for (const event of person.events || []) {
    const date = parseDateTime(event.at)
    if (!date || Number.isNaN(date.getTime())) continue
    const minutes = date.getHours() * 60 + date.getMinutes() - startHour * 60
    const index = Math.max(
      0,
      Math.min(count - 1, Math.floor(minutes / binMinutes)),
    )
    const key = event.kind?.startsWith('call') ? 'calls' : event.kind
    if (!bins[index].counts[key] && bins[index].counts[key] !== 0) continue
    bins[index].counts[key] += 1
    bins[index].total += 1
  }
  const max = Math.max(1, ...bins.map((bin) => bin.total))
  const colors = {
    calls: 'bg-surface-blue-3',
    texts: 'bg-surface-green-3',
    tasks: 'bg-surface-orange-3',
    today: 'bg-surface-violet-3',
  }
  return bins.map((bin) => {
    const dominant =
      Object.entries(bin.counts).sort((a, b) => b[1] - a[1])[0]?.[0] || 'calls'
    const hour = startHour + Math.floor(bin.index / 2)
    const minute = bin.index % 2 ? '30' : '00'
    const details = goalMetrics
      .map((metric) => `${metric.label}: ${bin.counts[metric.key]}`)
      .join(' · ')
    return {
      color: bin.total ? colors[dominant] : 'bg-transparent',
      height: bin.total ? Math.max(3, Math.round((bin.total / max) * 32)) : 0,
      title: `${hour}:${minute} · ${details}`,
    }
  })
}

function beginGoalEdit() {
  for (const person of progress.data?.people || []) {
    goalDraft[person.user] = {}
    for (const metric of goalMetrics) {
      goalDraft[person.user][metric.key] = Number(
        person.goals?.[metric.key] || 0,
      )
    }
  }
  editingGoals.value = true
}

async function saveGoals() {
  savingGoals.value = true
  try {
    await call('crm.api.activity_progress.set_activity_goals', {
      goals: JSON.stringify(goalDraft),
    })
    toast.success(__('Daily goals saved'))
    editingGoals.value = false
    await reload()
  } catch (error) {
    toast.error(__('Could not save daily goals'))
  } finally {
    savingGoals.value = false
  }
}
</script>
