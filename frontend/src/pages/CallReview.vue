<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs
        :items="[{ label: 'Call Review', route: { name: 'Call Review' } }]"
      />
    </template>
    <template #right-header>
      <div class="flex flex-wrap items-center gap-2">
        <!-- rep filter -->
        <FormControl
          type="select"
          :options="repOptions"
          v-model="rep"
          :placeholder="__('All reps')"
        />
        <!-- min call length -->
        <FormControl
          type="select"
          :options="lengthOptions"
          v-model="minDuration"
        />
        <!-- review status -->
        <FormControl
          type="select"
          :options="reviewOptions"
          v-model="reviewFilter"
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
    <!-- summary (reflects the active filters) -->
    <div class="flex flex-wrap gap-3 border-b bg-surface-menu-bar px-5 py-3">
      <StatCard :label="__('Calls')" :value="displayTotals.calls" />
      <StatCard
        :label="__('Outbound / Inbound')"
        :value="`${displayTotals.outbound} / ${displayTotals.inbound}`"
      />
      <StatCard :label="__('Talk time')" :value="formatDuration(displayTotals.talk_time) || '0s'" />
      <StatCard :label="__('Leads')" :value="displayTotals.leads" />
      <StatCard :label="__('First-time calls')" :value="displayTotals.first_time" />
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
    <div
      v-else-if="!filteredReps.length"
      class="flex flex-1 items-center justify-center p-10 text-sm text-ink-gray-5"
    >
      {{ __('No calls match the current filters.') }}
    </div>

    <!-- per-rep sections -->
    <div v-else class="flex flex-col gap-6 p-5">
      <section v-for="r in filteredReps" :key="r.user || 'unassigned'">
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
                {{ formatPhone(ld.mobile_no) }}
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
                :id="'call-' + call.name"
                class="flex flex-col gap-2 border-l-2 px-4 py-2.5"
                :class="call.my_review.reviewed ? 'border-ink-green-3' : 'border-transparent'"
              >
                <div class="flex flex-wrap items-center gap-3 text-sm">
                  <input
                    type="checkbox"
                    class="size-4 shrink-0 cursor-pointer rounded border-outline-gray-2 text-ink-green-3 focus:ring-0"
                    :checked="call.my_review.reviewed"
                    :title="__('Mark reviewed')"
                    @change="toggleReviewed(call)"
                  />
                  <span class="w-16 shrink-0 text-ink-gray-5">
                    {{ callTime(call.time) }}
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
                  <span
                    v-if="!call.recording_url"
                    class="ml-auto text-xs text-ink-gray-4"
                  >
                    {{ __('No recording') }}
                  </span>
                  <Button
                    v-if="call.recording_url"
                    class="ml-auto"
                    variant="ghost"
                    :label="transcriptOpen[call.name] ? __('Hide Playback') : __('Playback')"
                    @click="toggleTranscript(call.name)"
                  />
                  <Button
                    v-if="call.ai_summary"
                    variant="ghost"
                    :label="expanded[call.name] ? __('Hide summary') : __('AI summary')"
                    @click="toggle(call.name)"
                  />
                  <Badge
                    v-if="call.ai_review"
                    :variant="'subtle'"
                    :theme="aiFlagTheme(call.ai_review.overall_flag)"
                    :label="aiFlagLabel(call.ai_review)"
                    class="cursor-pointer"
                    @click="toggleAi(call.name)"
                  />
                  <Button
                    variant="ghost"
                    :label="call.my_review.notes ? __('Notes ✎') : __('Add note')"
                    @click="toggleNotes(call)"
                  />
                  <span
                    v-if="reviewedByOthers(call)"
                    class="flex items-center gap-0.5 text-xs text-ink-gray-5"
                    :title="othersTitle(call)"
                  >
                    <FeatherIcon name="check" class="h-3.5 w-3.5 text-ink-green-3" />
                    {{ reviewedByOthers(call) }}
                  </span>
                </div>

                <div
                  v-if="transcriptOpen[call.name]"
                  class="rounded border bg-surface-white px-3 py-2.5"
                >
                  <CallTranscript
                    :call-log-name="call.name"
                    :seek-to="seekTarget[call.name]"
                    :link-target="
                      ld.reference_doctype === 'CRM Lead' && ld.reference_name
                        ? { type: 'leads', id: ld.reference_name }
                        : null
                    "
                  />
                </div>

                <div
                  v-if="call.ai_summary && expanded[call.name]"
                  class="whitespace-pre-wrap rounded bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-7"
                >
                  {{ call.ai_summary }}
                </div>

                <!-- AI integrity review (Lance-only Call Review tab) -->
                <div
                  v-if="call.ai_review && aiOpen[call.name]"
                  class="rounded border bg-surface-white px-3 py-2.5 text-sm text-ink-gray-7"
                >
                  <div class="mb-1.5 flex items-center gap-2">
                    <Badge
                      :variant="'subtle'"
                      :theme="aiFlagTheme(call.ai_review.overall_flag)"
                      :label="call.ai_review.overall_flag"
                    />
                    <span
                      v-if="call.ai_review.motivation_score !== null"
                      class="text-xs text-ink-gray-6"
                    >
                      {{ __('Motivation') }}: {{ call.ai_review.motivation_score }}/5
                    </span>
                  </div>
                  <p
                    v-if="call.ai_review.motivation_reason"
                    class="mb-2 text-ink-gray-6"
                  >
                    {{ call.ai_review.motivation_reason }}
                  </p>

                  <div v-if="call.ai_review.integrity_issues.length" class="mb-2">
                    <p class="mb-1 font-medium text-ink-gray-8">
                      {{ __('Integrity issues') }}
                    </p>
                    <div
                      v-for="(iss, i) in call.ai_review.integrity_issues"
                      :key="i"
                      class="mb-1.5 border-l-2 border-outline-red-2 pl-2"
                    >
                      <p class="text-ink-red-3">
                        “{{ iss.quote }}”
                        <button
                          v-if="iss.at_time !== null && iss.at_time !== undefined"
                          class="ml-1 whitespace-nowrap text-xs text-ink-blue-3 hover:underline"
                          @click="seekToTime(call, iss.at_time)"
                        >
                          ▶ {{ fmtTime(iss.at_time) }}
                        </button>
                      </p>
                      <p class="text-xs text-ink-gray-6">{{ iss.why }}</p>
                      <p class="text-xs text-ink-green-3">
                        {{ __('Better') }}: {{ iss.better_phrasing }}
                      </p>
                    </div>
                  </div>

                  <p v-if="call.ai_review.what_could_be_better" class="mb-1">
                    <span class="font-medium text-ink-gray-8">{{ __('What could be better') }}:</span>
                    {{ call.ai_review.what_could_be_better }}
                  </p>
                  <p v-if="call.ai_review.lead_status" class="text-xs text-ink-gray-5">
                    {{ __('Where the lead is at') }}: {{ call.ai_review.lead_status }}
                  </p>

                  <!-- Reply to the AI: re-reviews this call + remembers for next time -->
                  <div class="mt-3 border-t border-outline-gray-1 pt-2">
                    <p
                      v-if="call.ai_review.feedback"
                      class="mb-1 text-xs text-ink-gray-5"
                    >
                      <span class="font-medium">{{ __('Your last reply') }}:</span>
                      {{ call.ai_review.feedback }}
                    </p>
                    <p
                      v-if="replyLearned[call.name] && replyLearned[call.name].length"
                      class="mb-1 text-xs text-ink-green-3"
                    >
                      ✓ {{ __('Remembered') }}: {{ replyLearned[call.name].join('; ') }}
                    </p>
                    <FormControl
                      type="textarea"
                      :rows="2"
                      v-model="replyDraft[call.name]"
                      :placeholder="
                        __('Reply to the AI — e.g. “this was a dispo partner call, not a seller.” It re-reviews this call and remembers for next time.')
                      "
                    />
                    <div class="mt-1 flex justify-end">
                      <Button
                        variant="solid"
                        :loading="replySaving[call.name]"
                        :disabled="!replyDraft[call.name]"
                        :label="__('Send to AI')"
                        @click="submitReply(call)"
                      />
                    </div>
                  </div>
                </div>

                <!-- review panel: your notes + everyone else's marks -->
                <div
                  v-if="notesOpen[call.name]"
                  class="rounded bg-surface-gray-1 px-3 py-2"
                >
                  <div class="mb-1 text-xs font-medium text-ink-gray-5">
                    {{ __('Your notes') }}
                  </div>
                  <textarea
                    v-model="noteDraft[call.name]"
                    rows="3"
                    class="w-full rounded border bg-surface-white px-2 py-1 text-sm text-ink-gray-8 focus:outline-none"
                    :placeholder="__('Notes on this call…')"
                  />
                  <div class="mt-2 flex items-center gap-2">
                    <Button
                      variant="solid"
                      :label="__('Save')"
                      :loading="saving[call.name]"
                      @click="saveNotes(call)"
                    />
                    <Button
                      variant="ghost"
                      :label="__('Cancel')"
                      @click="closeNotes(call)"
                    />
                  </div>
                  <div
                    v-if="call.reviews.length"
                    class="mt-3 flex flex-col gap-2 border-t pt-2"
                  >
                    <div
                      v-for="r in call.reviews"
                      :key="r.reviewer"
                      class="text-sm"
                    >
                      <span class="font-medium text-ink-gray-7">
                        {{ r.reviewer_name }}
                      </span>
                      <Badge
                        v-if="r.reviewed"
                        :label="__('Reviewed')"
                        variant="subtle"
                        theme="green"
                        class="ml-1"
                      />
                      <div
                        v-if="r.notes"
                        class="mt-0.5 whitespace-pre-wrap text-ink-gray-6"
                      >
                        {{ r.notes }}
                      </div>
                    </div>
                  </div>
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
import CallTranscript from '@/components/Activities/CallTranscript.vue'
import { formatDuration } from '@/utils'
import { formatPhone } from '@/utils/phoneFormat'
import { dayjs } from 'frappe-ui'
import {
  Breadcrumbs,
  Button,
  Badge,
  FormControl,
  FeatherIcon,
  createResource,
  call as apiCall,
} from 'frappe-ui'
import { ref, computed, reactive, watch, h } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()

// local YYYY-MM-DD for "today" (browser tz; matches the user's working day)
const todayStr = (() => {
  const d = new Date()
  const off = d.getTimezoneOffset()
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10)
})()

// deep link from the digest email: ?date=YYYY-MM-DD&call=<name>&t=<seconds>
const queryDate =
  typeof route.query.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(route.query.date)
    ? route.query.date
    : ''
const date = ref(queryDate || todayStr)
const rep = ref('')
const minDuration = ref('0')
const reviewFilter = ref('all')
const expanded = reactive({})
const aiOpen = reactive({})
const transcriptOpen = reactive({})
const seekTarget = reactive({})
const replyDraft = reactive({})
const replySaving = reactive({})
const replyLearned = reactive({})
const notesOpen = reactive({})
const noteDraft = reactive({})
const saving = reactive({})

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

const repOptions = computed(() => [
  { label: __('All reps'), value: '' },
  ...(repsResource.data || []),
])

const lengthOptions = [
  { label: __('Any length'), value: '0' },
  { label: __('≥ 10s'), value: '10' },
  { label: __('≥ 30s'), value: '30' },
  { label: __('≥ 1 min'), value: '60' },
  { label: __('≥ 2 min'), value: '120' },
  { label: __('≥ 5 min'), value: '300' },
]
const reviewOptions = [
  { label: __('All calls'), value: 'all' },
  { label: __('Not reviewed'), value: 'unreviewed' },
  { label: __('Reviewed'), value: 'reviewed' },
]

function callPasses(c) {
  if ((c.duration || 0) < Number(minDuration.value)) return false
  if (reviewFilter.value === 'unreviewed' && c.my_review.reviewed) return false
  if (reviewFilter.value === 'reviewed' && !c.my_review.reviewed) return false
  return true
}

function totalsOf(leads) {
  const t = { calls: 0, inbound: 0, outbound: 0, talk_time: 0, leads: leads.length, first_time: 0 }
  for (const ld of leads) {
    if (ld.first_time_today) t.first_time++
    for (const c of ld.calls) {
      t.calls++
      t.talk_time += c.duration || 0
      if (c.type === 'Incoming') t.inbound++
      else t.outbound++
    }
  }
  return t
}

// filter calls live (by length + my review state), dropping emptied leads/reps
// and recomputing totals so the header reflects what's shown
const filteredReps = computed(() => {
  const out = []
  for (const r of reps.value) {
    const leads = []
    for (const ld of r.leads) {
      const calls = ld.calls.filter(callPasses)
      if (calls.length) leads.push({ ...ld, calls })
    }
    if (leads.length) out.push({ ...r, leads, totals: totalsOf(leads) })
  }
  return out
})

const displayTotals = computed(() => {
  const o = { calls: 0, inbound: 0, outbound: 0, talk_time: 0, leads: 0, first_time: 0 }
  for (const r of filteredReps.value) {
    for (const k in o) o[k] += r.totals[k]
  }
  return o
})

watch([date, rep], () => review.reload())

// once the deep-linked call's card exists, open its Playback (+ AI panel) and
// scroll it into view; retry the scroll since the list re-lays-out after mount
let pendingCall = typeof route.query.call === 'string' ? route.query.call : ''
watch(
  () => review.data,
  () => {
    if (!pendingCall) return
    const target = pendingCall
    const found = reps.value.some((r) =>
      r.leads.some((ld) => ld.calls.some((c) => c.name === target))
    )
    if (!found) return
    pendingCall = ''
    transcriptOpen[target] = true
    aiOpen[target] = true
    const t = Number(route.query.t)
    if (Number.isFinite(t) && t > 0) seekTarget[target] = t
    let tries = 0
    const scroll = () => {
      const el = document.getElementById('call-' + target)
      if (el) el.scrollIntoView({ block: 'start', behavior: 'smooth' })
      if (++tries < 5) setTimeout(scroll, 400)
    }
    setTimeout(scroll, 100)
  },
  { immediate: true }
)

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

function toggleTranscript(name) {
  transcriptOpen[name] = !transcriptOpen[name]
}

function toggleAi(name) {
  aiOpen[name] = !aiOpen[name]
}

function aiFlagTheme(flag) {
  return flag === 'serious' ? 'red' : flag === 'review' ? 'orange' : 'green'
}

function aiFlagLabel(ai) {
  const n = ai.integrity_issues?.length || 0
  if (ai.overall_flag === 'serious') return n ? `AI: serious (${n})` : 'AI: serious'
  if (ai.overall_flag === 'review') return n ? `AI: review (${n})` : 'AI: review'
  return 'AI: ok'
}

function fmtTime(s) {
  s = Math.max(0, Math.floor(Number(s) || 0))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

// Open the inline Playback and seek it to the integrity-issue's moment.
function seekToTime(call, t) {
  transcriptOpen[call.name] = true
  seekTarget[call.name] = Number(t) || 0
}

// Reply to the AI on a call: re-reviews it honoring the feedback + remembers
// lessons (global rules + per-contact facts) for future reviews.
async function submitReply(call) {
  const text = (replyDraft[call.name] || '').trim()
  if (!text) return
  replySaving[call.name] = true
  try {
    const res = await apiCall('crm.api.call_review_ai.reply_to_review', {
      call_log: call.name,
      feedback: text,
    })
    call.ai_review = {
      motivation_score: res.motivation_score,
      motivation_reason: res.motivation_reason,
      integrity_issues: res.integrity_issues,
      lead_status: res.lead_status,
      what_could_be_better: res.what_could_be_better,
      overall_flag: res.overall_flag,
      feedback: text,
    }
    replyLearned[call.name] = res.learned || []
    replyDraft[call.name] = ''
  } catch (e) {
    console.error('reply_to_review failed', e)
  } finally {
    replySaving[call.name] = false
  }
}

// Call times are stored as the rep's local (Chicago) wall-clock, NOT UTC, so
// format them verbatim — running them through dayjsLocal would re-convert an
// already-local time and shift it by the viewer's timezone offset.
function callTime(t) {
  return t ? dayjs(t.slice(0, 19)).format('h:mm a') : ''
}

function reviewedByOthers(call) {
  return call.reviews.filter((r) => r.reviewed).length
}

function othersTitle(call) {
  return call.reviews
    .filter((r) => r.reviewed)
    .map((r) => r.reviewer_name)
    .join(', ')
}

async function toggleReviewed(call) {
  const next = !call.my_review.reviewed
  call.my_review.reviewed = next // optimistic
  try {
    await apiCall('crm.api.reports.set_call_review', {
      call_log: call.name,
      reviewed: next ? 1 : 0,
    })
  } catch (e) {
    call.my_review.reviewed = !next // revert on failure
    console.error('set_call_review (reviewed) failed', e)
  }
}

function toggleNotes(call) {
  if (!notesOpen[call.name]) noteDraft[call.name] = call.my_review.notes || ''
  notesOpen[call.name] = !notesOpen[call.name]
}

function closeNotes(call) {
  notesOpen[call.name] = false
}

async function saveNotes(call) {
  const notes = noteDraft[call.name] ?? ''
  saving[call.name] = true
  try {
    await apiCall('crm.api.reports.set_call_review', {
      call_log: call.name,
      notes,
    })
    call.my_review.notes = notes
    notesOpen[call.name] = false
  } catch (e) {
    console.error('set_call_review (notes) failed', e)
  } finally {
    saving[call.name] = false
  }
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
