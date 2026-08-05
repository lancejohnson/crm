<template>
  <Dialog v-model="show" :options="{ title: __('Team activity'), size: '6xl' }">
    <template #body-content>
      <div class="max-h-[74vh] overflow-y-auto pr-1">
        <!-- summary line -->
        <div class="mb-3 flex flex-wrap items-end justify-between gap-3">
          <DialogDescription class="text-p-sm text-ink-gray-6">
            <b class="text-ink-gray-9">{{ prettyDate }}</b> ·
            <b class="text-ink-gray-9">{{ totals.calls }}</b> calls ·
            <b class="text-ink-gray-9">{{ totals.texts }}</b> texts ·
            <b class="text-ink-gray-9">{{ board.done }}</b> of
            <b class="text-ink-gray-9">{{ board.total }}</b> cards done ·
            <b class="text-ink-gray-9">{{ fmtHours(totals.tracked) }}</b>
            tracked
            <span class="mt-0.5 block text-xs text-ink-gray-5">
              {{
                __(
                  'Calls and texts are Quo; hours are Toggl. Automated sequence texts are excluded.',
                )
              }}
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
          v-if="progress.loading && !progress.data"
          class="flex min-h-56 items-center justify-center"
        >
          <LoadingIndicator class="size-6 text-ink-gray-5" />
        </div>

        <template v-else>
          <!-- goals editor -->
          <section
            v-if="editingGoals"
            class="mb-3 rounded-xl border border-outline-gray-2 bg-surface-gray-1 p-4"
          >
            <div class="mb-2 flex items-start justify-between gap-3">
              <div>
                <div
                  class="text-xs font-bold uppercase tracking-wide text-ink-gray-6"
                >
                  {{ __('Daily goals') }}
                </div>
                <div class="mt-0.5 text-xs text-ink-gray-5">
                  {{
                    __(
                      'A goal shows progress; leave 0 to track the count only.',
                    )
                  }}
                </div>
              </div>
              <Button variant="ghost" icon="x" @click="editingGoals = false" />
            </div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[560px] text-base">
                <thead>
                  <tr
                    class="text-[10px] uppercase tracking-wide text-ink-gray-5"
                  >
                    <th class="pb-1 pr-2 text-left font-extrabold">
                      {{ __('Team member') }}
                    </th>
                    <th
                      v-for="m in metrics"
                      :key="m.key"
                      class="pb-1 pr-2 text-left font-extrabold"
                    >
                      {{ m.label }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="p in people" :key="p.user">
                    <td class="py-1 pr-2">
                      <div class="flex items-center gap-2">
                        <UserAvatar :user="p.user" size="sm" />
                        <span
                          class="truncate text-base font-medium text-ink-gray-8"
                          >{{ p.name }}</span
                        >
                      </div>
                    </td>
                    <td v-for="m in metrics" :key="m.key" class="py-1 pr-2">
                      <FormControl
                        v-model="goalDraft[p.user][m.key]"
                        type="number"
                        min="0"
                        max="1000"
                        class="w-20"
                      />
                    </td>
                  </tr>
                </tbody>
              </table>
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
          </section>

          <!-- the team table -->
          <section
            class="mb-3 rounded-xl border border-outline-gray-2 bg-surface-white p-4"
          >
            <div
              class="mb-2 text-xs font-bold uppercase tracking-wide text-ink-gray-6"
            >
              {{ __('The team — {0}', [prettyDate]) }}
            </div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[940px] text-base">
                <thead>
                  <tr
                    class="border-b border-outline-gray-2 text-[10px] uppercase tracking-wide text-ink-gray-5"
                  >
                    <th class="pb-1.5 pr-3 text-left font-extrabold">
                      {{ __('Person') }}
                    </th>
                    <th class="pb-1.5 pr-3 text-right font-extrabold">
                      {{ __('Tracked') }}
                    </th>
                    <th class="pb-1.5 pr-3 text-left font-extrabold">
                      {{ __('Clocked in') }}
                    </th>
                    <th class="pb-1.5 pr-3 text-right font-extrabold">
                      {{ __('Calls') }}
                    </th>
                    <th class="pb-1.5 pr-3 text-left font-extrabold"></th>
                    <th class="pb-1.5 pr-3 text-right font-extrabold">
                      {{ __('Talk') }}
                    </th>
                    <th class="pb-1.5 pr-3 text-right font-extrabold">
                      {{ __('Texts') }}
                    </th>
                    <th class="pb-1.5 pr-3 text-right font-extrabold">
                      {{ __('Cards') }}
                    </th>
                    <th class="pb-1.5 pr-3 text-right font-extrabold">
                      {{ __('Tasks') }}
                    </th>
                    <th class="pb-1.5 pr-3 text-left font-extrabold">
                      {{ __('Active') }}
                    </th>
                    <th class="pb-1.5 text-right font-extrabold">
                      {{ __('Goal') }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="p in people"
                    :key="p.user"
                    class="border-b border-outline-gray-1 last:border-0 align-top"
                  >
                    <td class="py-1.5 pr-3">
                      <div class="flex items-center gap-2">
                        <UserAvatar :user="p.user" size="sm" />
                        <span class="truncate font-medium text-ink-gray-8">{{
                          p.name
                        }}</span>
                      </div>
                    </td>
                    <td class="py-1.5 pr-3 text-right tabular-nums">
                      <span
                        :class="
                          p.suspectTimer
                            ? 'font-semibold text-ink-amber-3'
                            : 'text-ink-gray-8'
                        "
                      >
                        {{ p.toggl.seconds ? fmtHours(p.toggl.seconds) : '—' }}
                      </span>
                      <span
                        v-if="p.toggl.running"
                        class="ml-1 inline-block size-1.5 rounded-full bg-surface-green-3 align-middle"
                        :title="__('timer running')"
                      />
                    </td>
                    <td class="py-1.5 pr-3 text-p-sm text-ink-gray-6">
                      <span v-if="p.clockWindow">{{ p.clockWindow }}</span>
                      <span v-else class="text-ink-gray-4">—</span>
                      <span
                        v-if="p.suspectTimer"
                        class="ml-1 rounded-full border border-outline-amber-2 bg-surface-amber-1 px-1.5 text-[10px] font-bold text-ink-amber-3"
                      >
                        {{ __('timer left running?') }}
                      </span>
                    </td>
                    <td
                      class="py-1.5 pr-3 text-right font-semibold tabular-nums text-ink-gray-9"
                    >
                      {{ p.counts.calls }}
                      <span
                        v-if="p.counts.calls_internal"
                        class="block text-[10px] font-normal text-ink-gray-4"
                        :title="
                          __('teammate-to-teammate, not counted as outreach')
                        "
                      >
                        +{{ p.counts.calls_internal }} {{ __('internal') }}
                      </span>
                    </td>
                    <td class="py-1.5 pr-3">
                      <div class="flex items-center gap-1.5">
                        <span
                          class="inline-flex h-2 overflow-hidden rounded-sm"
                          :style="{ width: barPx(p.counts.calls, max.calls) }"
                        >
                          <span
                            class="h-full bg-surface-blue-3"
                            :style="{ width: seg(p, 'calls_lead') }"
                          />
                          <span
                            class="h-full bg-surface-green-3"
                            :style="{ width: seg(p, 'calls_buyer') }"
                          />
                          <span
                            class="h-full bg-surface-amber-3"
                            :style="{ width: seg(p, 'calls_outside') }"
                          />
                        </span>
                        <span
                          class="whitespace-nowrap text-[10px] text-ink-gray-5"
                        >
                          <span class="text-ink-blue-3"
                            >{{ p.counts.calls_lead }} lead</span
                          >
                          ·
                          <span class="text-ink-green-3"
                            >{{ p.counts.calls_buyer }} buyer</span
                          >
                          <template v-if="p.counts.calls_outside">
                            ·
                            <span
                              class="font-semibold text-ink-amber-3"
                              :title="__('not in the CRM when called')"
                              >{{ p.counts.calls_outside }} out</span
                            >
                          </template>
                        </span>
                      </div>
                      <div class="text-[10px] text-ink-gray-4">
                        {{ p.counts.outbound_calls }}↗
                        {{ p.counts.inbound_calls }}↙
                      </div>
                    </td>
                    <td
                      class="py-1.5 pr-3 text-right tabular-nums text-ink-gray-7"
                    >
                      {{ fmtDur(p.counts.talk_seconds) }}
                    </td>
                    <td
                      class="py-1.5 pr-3 text-right tabular-nums text-ink-gray-8"
                    >
                      {{ p.counts.texts || '—' }}
                    </td>
                    <td class="py-1.5 pr-3 text-right tabular-nums">
                      <span class="font-semibold text-ink-green-3">{{
                        p.counts.cards || 0
                      }}</span>
                      <span class="text-ink-gray-4"> / </span>
                      <span class="text-ink-gray-6">{{
                        p.counts.cards_skipped || 0
                      }}</span>
                    </td>
                    <td class="py-1.5 pr-3 text-right tabular-nums">
                      <span class="text-ink-gray-8">{{
                        p.counts.tasks || 0
                      }}</span>
                      <span
                        v-if="p.counts.tasks"
                        class="text-[10px] text-ink-gray-5"
                      >
                        ({{ p.counts.tasks_on_list
                        }}<span class="text-ink-gray-4"
                          >/{{ p.counts.tasks_other }}</span
                        >)
                      </span>
                    </td>
                    <td
                      class="py-1.5 pr-3 whitespace-nowrap text-p-sm text-ink-gray-6"
                    >
                      {{ p.activeWindow || '—' }}
                    </td>
                    <td class="py-1.5 text-right">
                      <span
                        v-if="p.goalTotal"
                        class="rounded-full border px-1.5 py-px text-[10px] font-bold"
                        :class="
                          p.goalPct >= 100
                            ? 'border-outline-green-2 bg-surface-green-1 text-ink-green-3'
                            : 'border-outline-amber-2 bg-surface-amber-1 text-ink-amber-3'
                        "
                        >{{ p.goalPct }}%</span
                      >
                      <span v-else class="text-ink-gray-4">—</span>
                    </td>
                  </tr>
                  <tr class="text-ink-gray-7">
                    <td
                      class="pt-2 pr-3 text-[10px] font-extrabold uppercase tracking-wide text-ink-gray-5"
                    >
                      {{ __('Total') }}
                    </td>
                    <td class="pt-2 pr-3 text-right font-semibold tabular-nums">
                      {{ fmtHours(totals.tracked) }}
                    </td>
                    <td class="pt-2 pr-3"></td>
                    <td class="pt-2 pr-3 text-right font-semibold tabular-nums">
                      {{ totals.calls }}
                      <span
                        v-if="totals.internal"
                        class="block text-[10px] font-normal text-ink-gray-4"
                      >
                        +{{ totals.internal }} {{ __('internal') }}
                      </span>
                    </td>
                    <td
                      class="pt-2 pr-3 text-[10px] font-semibold text-ink-gray-5"
                    >
                      <span class="text-ink-blue-3"
                        >{{ totals.lead }} lead</span
                      >
                      ·
                      <span class="text-ink-green-3"
                        >{{ totals.buyer }} buyer</span
                      >
                      ·
                      <span class="text-ink-amber-3"
                        >{{ totals.outside }} out</span
                      >
                    </td>
                    <td class="pt-2 pr-3 text-right font-semibold tabular-nums">
                      {{ fmtDur(totals.talk) }}
                    </td>
                    <td class="pt-2 pr-3 text-right font-semibold tabular-nums">
                      {{ totals.texts }}
                    </td>
                    <td class="pt-2 pr-3 text-right font-semibold tabular-nums">
                      {{ totals.cards }} / {{ totals.cardsSkipped }}
                    </td>
                    <td class="pt-2 pr-3 text-right font-semibold tabular-nums">
                      {{ totals.tasks }}
                    </td>
                    <td class="pt-2 pr-3"></td>
                    <td class="pt-2"></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <!-- the day -->
          <section
            class="mb-3 rounded-xl border border-outline-gray-2 bg-surface-white p-4"
          >
            <div
              class="mb-2 text-xs font-bold uppercase tracking-wide text-ink-gray-6"
            >
              {{ __('The day') }}
            </div>
            <div class="overflow-x-auto">
              <div class="min-w-[820px]">
                <div class="mb-1 flex text-[10px] text-ink-gray-4">
                  <div class="w-36 shrink-0"></div>
                  <div class="relative h-3 flex-1">
                    <span
                      v-for="h in hourTicks"
                      :key="h"
                      class="absolute -translate-x-1/2"
                      :style="{ left: pctOf(h) }"
                    >
                      {{ hourLabel(h) }}
                    </span>
                  </div>
                </div>
                <div
                  v-for="p in people"
                  :key="p.user"
                  class="mb-1 flex items-center"
                >
                  <div
                    class="w-36 shrink-0 truncate pr-2 text-p-sm text-ink-gray-7"
                  >
                    {{ p.name }}
                  </div>
                  <div class="relative h-6 flex-1 rounded bg-surface-gray-2">
                    <div
                      v-for="(b, i) in p.toggl.bands"
                      :key="'b' + i"
                      class="absolute inset-y-0 rounded-sm bg-surface-green-1 ring-1 ring-inset ring-outline-green-2"
                      :style="{
                        left: pctOf(hourFloat(b[0])),
                        width: spanPct(b[0], b[1]),
                      }"
                      :title="
                        __('clocked in {0}–{1}', [clock(b[0]), clock(b[1])])
                      "
                    />
                    <div
                      v-for="(e, i) in p.events"
                      :key="'e' + i"
                      class="absolute top-1 h-4 w-[2px] rounded-sm"
                      :class="tickClass(e.kind)"
                      :style="{ left: pctOf(hourFloat(e.at)) }"
                      :title="`${tickLabel(e.kind)} ${clock(e.at)}`"
                    />
                    <div
                      v-for="h in hourTicks"
                      :key="'g' + h"
                      class="absolute inset-y-0 w-px bg-surface-white/70"
                      :style="{ left: pctOf(h) }"
                    />
                  </div>
                </div>
              </div>
            </div>
          </section>

          <!-- board + caveats -->
          <section class="mb-3 grid gap-3 sm:grid-cols-2">
            <div
              class="rounded-xl border border-outline-blue-2 bg-surface-blue-1 p-3"
            >
              <div
                class="text-[10px] font-extrabold uppercase tracking-wide text-ink-blue-3 opacity-80"
              >
                {{ __('Today board') }}
              </div>
              <div class="mt-1 text-base text-ink-gray-8">
                <b>{{ board.done }}</b> {{ __('done') }} ·
                <b>{{ board.skipped }}</b> {{ __('skipped') }} ·
                <b>{{ board.remaining }}</b> {{ __('left') }} {{ __('of') }}
                <b>{{ board.total }}</b>
              </div>
              <div
                class="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-white"
              >
                <div
                  class="h-full bg-surface-green-3"
                  :style="{ width: pct(board.done, board.total) }"
                />
              </div>
            </div>
            <div
              v-if="caveats.length"
              class="rounded-xl border border-outline-amber-2 bg-surface-amber-1 p-3"
            >
              <div
                class="text-[10px] font-extrabold uppercase tracking-wide text-ink-amber-3 opacity-80"
              >
                {{ __('Worth knowing') }}
              </div>
              <ul class="mt-1 space-y-0.5 text-p-sm text-ink-gray-7">
                <li v-for="(c, i) in caveats" :key="i">• {{ c }}</li>
              </ul>
            </div>
          </section>

          <!-- legend -->
          <div
            class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-gray-5"
          >
            <span
              ><span
                class="mr-1 inline-block size-2.5 rounded-sm bg-surface-blue-3 align-[-1px]"
              />{{ __('call to a lead') }}</span
            >
            <span
              ><span
                class="mr-1 inline-block size-2.5 rounded-sm bg-surface-green-3 align-[-1px]"
              />{{ __('call to a buyer') }}</span
            >
            <span
              ><span
                class="mr-1 inline-block size-2.5 rounded-sm bg-surface-amber-3 align-[-1px]"
              />{{ __('out = not in the CRM when called') }}</span
            >
            <span
              ><span
                class="mr-1 inline-block size-2.5 rounded-sm bg-surface-amber-3 align-[-1px]"
              />{{ __('task completed') }}</span
            >
            <span
              ><span
                class="mr-1 inline-block size-2.5 rounded-sm bg-surface-gray-6 align-[-1px]"
              />{{ __('Today card') }}</span
            >
            <span
              ><span
                class="mr-1 inline-block size-2.5 rounded-sm border border-outline-green-2 bg-surface-green-1 align-[-1px]"
              />{{ __('clocked in (Toggl)') }}</span
            >
            <span class="text-ink-gray-4">{{
              __(
                'Cards is done / skipped · Tasks is total (on today’s list / other) · teammate calls are listed separately and not counted as outreach',
              )
            }}</span>
          </div>
        </template>
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
let refreshTimer = null

// the day track spans 6am–8pm; anything outside is clamped onto the edges
const DAY_START = 6
const DAY_END = 20
const hourTicks = [6, 8, 10, 12, 14, 16, 18, 20]

const metrics = [
  { key: 'calls', label: __('Calls') },
  { key: 'texts', label: __('Texts') },
  { key: 'tasks', label: __('Tasks') },
  { key: 'cards', label: __('Cards') },
]

const progress = createResource({
  url: 'crm.api.activity_progress.get_activity_progress',
  makeParams: () => ({ for_date: selectedDate.value }),
  auto: false,
})

const board = computed(
  () => progress.data?.board || { total: 0, done: 0, skipped: 0, remaining: 0 },
)

const people = computed(() =>
  [...(progress.data?.people || [])]
    .map((p) => {
      const bands = p.toggl?.bands || []
      const longest = bands.reduce(
        (m, b) => Math.max(m, spanSeconds(b[0], b[1])),
        0,
      )
      const first = p.events?.[0]?.at
      const last = p.events?.length ? p.events[p.events.length - 1].at : null
      return {
        ...p,
        clockWindow: bands.length
          ? `${clock(bands[0][0])}–${clock(bands[bands.length - 1][1])}`
          : '',
        // a single band over 10h (or a >12h day) is almost always a forgotten timer
        suspectTimer:
          longest > 10 * 3600 || (p.toggl?.seconds || 0) > 12 * 3600,
        // worked in the CRM but never started a timer
        noClock: (p.events?.length || 0) > 0 && !(p.toggl?.seconds || 0),
        activeWindow: first ? `${clock(first)}–${clock(last)}` : '',
        goalTotal: goalTotal(p),
        goalPct: goalPct(p),
      }
    })
    .sort(
      (a, b) => b.counts.calls - a.counts.calls || a.name.localeCompare(b.name),
    ),
)

const totals = computed(() => {
  const t = {
    calls: 0,
    lead: 0,
    buyer: 0,
    outside: 0,
    internal: 0,
    texts: 0,
    talk: 0,
    cards: 0,
    cardsSkipped: 0,
    tasks: 0,
    tracked: 0,
  }
  for (const p of people.value) {
    t.calls += p.counts.calls
    t.lead += p.counts.calls_lead || 0
    t.buyer += p.counts.calls_buyer || 0
    t.outside += p.counts.calls_outside || 0
    t.internal += p.counts.calls_internal || 0
    t.texts += p.counts.texts
    t.talk += p.counts.talk_seconds
    t.cards += p.counts.cards || 0
    t.cardsSkipped += p.counts.cards_skipped || 0
    t.tasks += p.counts.tasks || 0
    t.tracked += p.toggl?.seconds || 0
  }
  return t
})

const max = computed(() => ({
  calls: Math.max(1, ...people.value.map((p) => p.counts.calls)),
}))

const caveats = computed(() => {
  const out = []
  const d = progress.data
  if (!d) return out
  if (!d.toggl_ok) {
    out.push(
      __('Toggl hours unavailable ({0}).', [d.toggl_reason || __('error')]),
    )
  }
  if (d.unattributed?.cards) {
    out.push(
      __(
        '{0} resolved cards have no owner recorded — skips before the tracking field existed.',
        [d.unattributed.cards],
      ),
    )
  }
  for (const p of people.value) {
    if (p.suspectTimer) {
      out.push(
        __(
          '{0}’s Toggl shows {1} in one stretch ({2}) — likely a timer left running.',
          [p.name.split(' ')[0], fmtHours(p.toggl.seconds), p.clockWindow],
        ),
      )
    }
    if (p.noClock && d.toggl_ok) {
      out.push(
        __('{0} was active ({1} calls, {2} texts) but tracked no Toggl time.', [
          p.name.split(' ')[0],
          p.counts.calls,
          p.counts.texts,
        ]),
      )
    }
  }
  const other = Object.entries(d.unattributed || {})
    .filter(([k, v]) => k !== 'cards' && v)
    .reduce((s, [, v]) => s + v, 0)
  if (other)
    out.push(__('{0} activities could not be attributed to a person.', [other]))
  return out
})

const prettyDate = computed(() => {
  const d = parse(`${selectedDate.value}T00:00:00`)
  return d
    ? d.toLocaleDateString(undefined, {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
      })
    : ''
})

function localToday() {
  const n = new Date()
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}-${String(n.getDate()).padStart(2, '0')}`
}
function parse(v) {
  if (!v) return null
  const d = v instanceof Date ? v : new Date(String(v).replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? null : d
}
function clock(v) {
  const d = parse(v)
  return d
    ? d
        .toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
        .replace(/\s/g, '')
    : ''
}
function hourFloat(v) {
  const d = parse(v)
  return d ? d.getHours() + d.getMinutes() / 60 : DAY_START
}
function spanSeconds(a, b) {
  const x = parse(a)
  const y = parse(b)
  return x && y ? (y - x) / 1000 : 0
}
function pctOf(hour) {
  const clamped = Math.min(DAY_END, Math.max(DAY_START, hour))
  return `${((clamped - DAY_START) / (DAY_END - DAY_START)) * 100}%`
}
function spanPct(a, b) {
  const s = Math.min(DAY_END, Math.max(DAY_START, hourFloat(a)))
  const e = Math.min(DAY_END, Math.max(DAY_START, hourFloat(b)))
  return `${Math.max(0.4, ((e - s) / (DAY_END - DAY_START)) * 100)}%`
}
function pct(n, d) {
  return `${d ? Math.round((n * 100) / d) : 0}%`
}
function barPx(n, m) {
  return `${Math.max(2, Math.round((n / m) * 96))}px`
}
function seg(p, key) {
  const total = p.counts.calls || 0
  return total ? `${((p.counts[key] || 0) / total) * 100}%` : '0%'
}
function fmtHours(seconds) {
  return `${((seconds || 0) / 3600).toFixed(1)} h`
}
function fmtDur(seconds) {
  const mins = Math.round((seconds || 0) / 60)
  if (!mins) return '—'
  return mins < 60
    ? `${mins}m`
    : `${Math.floor(mins / 60)}h ${String(mins % 60).padStart(2, '0')}m`
}
function hourLabel(h) {
  const ampm = h >= 12 ? 'p' : 'a'
  const hr = h % 12 === 0 ? 12 : h % 12
  return `${hr}${ampm}`
}
function tickClass(kind) {
  return (
    {
      call_out: 'bg-surface-blue-3',
      call_in: 'bg-surface-blue-3',
      text: 'bg-surface-green-3',
      task: 'bg-surface-amber-3',
      call_internal: 'bg-surface-gray-3',
      card_done: 'bg-surface-gray-6',
      card_skip: 'bg-surface-gray-4',
    }[kind] || 'bg-surface-gray-5'
  )
}
function tickLabel(kind) {
  return (
    {
      call_out: __('call out'),
      call_in: __('call in'),
      text: __('text'),
      task: __('task'),
      call_internal: __('internal call'),
      card_done: __('card done'),
      card_skip: __('card skipped'),
    }[kind] || kind
  )
}
function goalTotal(p) {
  return metrics.reduce((s, m) => s + Number(p.goals?.[m.key] || 0), 0)
}
function goalPct(p) {
  const total = goalTotal(p)
  if (!total) return 0
  const done = metrics.reduce(
    (s, m) =>
      Number(p.goals?.[m.key] || 0) ? s + Number(p.counts?.[m.key] || 0) : s,
    0,
  )
  return Math.round((done * 100) / total)
}

function reload() {
  return progress.reload()
}

watch(show, (open) => {
  if (!open) {
    clearInterval(refreshTimer)
    refreshTimer = null
    editingGoals.value = false
    return
  }
  selectedDate.value = localToday()
  reload()
  refreshTimer = setInterval(() => {
    if (selectedDate.value === localToday()) reload()
  }, 60_000)
})
watch(selectedDate, () => {
  if (show.value) reload()
})
onBeforeUnmount(() => clearInterval(refreshTimer))

function beginGoalEdit() {
  for (const p of progress.data?.people || []) {
    goalDraft[p.user] = {}
    for (const m of metrics)
      goalDraft[p.user][m.key] = Number(p.goals?.[m.key] || 0)
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
  } catch (e) {
    toast.error(__('Could not save daily goals'))
  } finally {
    savingGoals.value = false
  }
}
</script>
