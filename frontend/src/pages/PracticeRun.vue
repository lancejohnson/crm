<template>
  <div class="flex min-h-0 flex-1 flex-col overflow-hidden">
    <div class="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-outline-gray-1 px-3 py-2 sm:px-4">
      <span
        class="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide text-amber-800"
      >
        {{ __('Practice') }}
      </span>
      <button
        class="truncate text-sm font-medium text-ink-gray-8 hover:underline"
        @click="leave"
      >
        {{ attempt.set_title || __('Practice') }}
      </button>
      <span class="text-sm text-ink-gray-5">
        {{ currentIndex + 1 }}/{{ properties.length }}
      </span>
      <span
        class="tabular-nums text-sm font-medium"
        :class="timerClass"
      >
        {{ timerLabel }}
      </span>
      <span
        v-if="current && attempt.status === 'In Progress'"
        class="tabular-nums text-sm text-ink-gray-6"
      >
        {{ __('this house') }} {{ fmtDuration(houseElapsed(current)) }}
      </span>
      <span v-if="attempt.paused" class="text-xs font-medium text-amber-700">
        {{ __('Paused') }}
      </span>
      <span v-else-if="attempt.status !== 'In Progress'" class="text-xs text-ink-gray-5">
        {{ reviewLabel }}
      </span>
      <span
        v-if="recording || uploading"
        class="flex items-center gap-1 text-xs font-medium text-red-600"
      >
        <span class="size-1.5 rounded-full bg-red-600" />
        {{ uploading ? __('Saving recording…') : attempt.paused ? __('REC paused') : __('REC') }}
      </span>
      <div class="ml-auto flex items-center gap-2">
        <Button
          v-if="attempt.status === 'In Progress' && attempt.mine"
          :label="attempt.paused ? __('Resume') : __('Pause')"
          :loading="pausing"
          @click="togglePause"
        />
        <Button
          v-if="attempt.status === 'In Progress' && attempt.mine"
          :label="__('Done with this one')"
          :disabled="!current"
          :loading="marking"
          @click="doneCurrent"
        />
        <Button
          v-if="attempt.status === 'In Progress' && attempt.mine"
          variant="solid"
          :label="__('Submit set')"
          :loading="submitting || uploading"
          @click="() => submit()"
        />
        <Button :label="__('Exit')" @click="leave" />
      </div>
    </div>

    <div class="flex shrink-0 gap-1 overflow-x-auto border-b border-outline-gray-1 px-3 py-1.5 sm:px-4">
      <button
        v-for="(p, i) in properties"
        :key="p.name"
        class="flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 py-1 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ink-gray-4"
        :class="chipClass(p, i)"
        :title="p.property_address"
        @click="select(i)"
      >
        <span>{{ i + 1 }}. {{ street(p.property_address) }}</span>
        <span v-if="houseElapsed(p)" class="tabular-nums opacity-70">
          {{ fmtDuration(houseElapsed(p)) }}
        </span>
      </button>
    </div>

    <div
      v-if="current"
      class="flex min-h-0 flex-1 flex-col overflow-hidden px-3 py-3 sm:px-5 sm:py-4"
    >
      <textarea
        v-model="condition"
        rows="2"
        class="form-input mb-2 w-full shrink-0 resize-y text-sm"
        :placeholder="__('Condition — roof, kitchen, foundation…')"
        :disabled="attempt.status !== 'In Progress' || attempt.mine === false"
        @blur="persistCondition(current.name)"
      />
      <CompsView
        ref="compsRef"
        :key="current.name"
        :lead="current.source_lead"
        :address="current.property_address"
        :practice-attempt="attemptId"
        :practice-property="current.name"
        :seller-note="current.seller_note || ''"
        page-mode
        hide-address-match
      />
    </div>
  </div>
</template>

<script setup>
import CompsView from '@/components/CompsView.vue'
import { Button, call, createResource, toast } from 'frappe-ui'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { sidebarCollapsedOverride } from '@/composables/settings'
import {
  beginPropertyRecording,
  hasPracticeRecorder,
  isPracticeRecording,
  pausePracticeRecording,
  resumePracticeRecording,
  setPracticeAttempt,
  stopPracticeRecording,
  watchPracticeRecording,
} from '@/utils/practiceRecorder'

const props = defineProps({
  setId: { type: String, required: true },
  attemptId: { type: String, required: true },
})
const router = useRouter()
const currentIndex = ref(0)
const marking = ref(false)
const submitting = ref(false)
const remaining = ref(null)
const elapsed = ref(0)
const recording = ref(false)
const uploading = ref(false)
const pausing = ref(false)
const condition = ref('')
let tick = null
let fetchedAt = 0
let flushed = false
let unwatchRec = null

onMounted(() => {
  sidebarCollapsedOverride.value = true
  if (attempt.value.mine !== false) setPracticeAttempt(props.attemptId)
  recording.value = isPracticeRecording()
  unwatchRec = watchPracticeRecording((on) => {
    recording.value = on
  })
})
onUnmounted(() => {
  sidebarCollapsedOverride.value = null
  clearInterval(tick)
  unwatchRec?.()
  if (!flushed && isPracticeRecording()) flushRecording()
})

const run = createResource({
  url: 'crm.api.practice.get_attempt',
  makeParams: () => ({ name: props.attemptId }),
  auto: true,
  onSuccess: syncClock,
})

const attempt = computed(() => run.data || {})
const properties = computed(() => attempt.value.properties || [])
const current = computed(() => properties.value[currentIndex.value] || null)

const reviewLabel = computed(() => {
  if (attempt.value.mine) return attempt.value.status
  return __("{0}'s run", [attempt.value.user_name || __('Teammate')])
})

const timerLabel = computed(() => {
  if (remaining.value == null) return fmtDuration(elapsed.value)
  return fmtDuration(remaining.value)
})

function houseElapsed(p) {
  if (!p) return 0
  let s = Number(p.elapsed_seconds || p.duration_seconds || 0)
  if (
    attempt.value.status === 'In Progress' &&
    !attempt.value.paused &&
    p.name === current.value?.name
  ) {
    s += Math.max(0, (Date.now() - fetchedAt) / 1000)
  }
  return s
}
const timerClass = computed(() => {
  if (attempt.value.status !== 'In Progress') return 'text-ink-gray-5'
  if (remaining.value == null) return 'text-ink-gray-8'
  if (remaining.value <= 60) return 'text-red-600'
  if (remaining.value <= 5 * 60) return 'text-amber-700'
  return 'text-ink-gray-8'
})

function fmtDuration(sec) {
  sec = Math.max(0, Math.floor(Number(sec) || 0))
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function street(addr) {
  return String(addr || '').split(',')[0].trim() || __('Property')
}

function chipClass(p, i) {
  if (i === currentIndex.value) return 'bg-gray-900 text-white'
  if (p.done_at) return 'bg-green-100 text-green-800'
  if (p.opened_at) return 'bg-surface-gray-2 text-ink-gray-8'
  return 'text-ink-gray-6 hover:bg-surface-gray-1'
}

function syncClock(d) {
  fetchedAt = Date.now()
  remaining.value = d?.remaining_seconds ?? null
  elapsed.value = d?.elapsed_seconds || 0
  if (d?.status === 'Timed Out' && submitting.value === false) {
    toast.warning(__('Time is up — run submitted.'))
  }
}

function onTick() {
  const d = attempt.value
  if (!d?.started_at) return
  if (d.paused) {
    remaining.value = d.remaining_seconds ?? null
    elapsed.value = d.elapsed_seconds || 0
    return
  }
  const waited = (Date.now() - fetchedAt) / 1000
  if (d.remaining_seconds == null) {
    remaining.value = null
    elapsed.value = (d.elapsed_seconds || 0) + waited
    return
  }
  remaining.value = Math.max(0, Math.floor(d.remaining_seconds - waited))
  elapsed.value = (d.elapsed_seconds || 0) + waited
  if (remaining.value === 0 && d.status === 'In Progress') onTimeUp()
}

async function onTimeUp() {
  if (submitting.value) return
  await submit(true)
}

watch(
  () => attempt.value.status,
  (s) => {
    clearInterval(tick)
    if (s === 'In Progress') tick = setInterval(onTick, 250)
  },
  { immediate: true },
)

watch(
  () => current.value?.name,
  async (name, prev) => {
    if (prev) await persistCondition(prev)
    condition.value =
      properties.value.find((p) => p.name === name)?.condition || ''
    if (!name || attempt.value.status !== 'In Progress' || attempt.value.mine === false) return
    try {
      const res = await call('crm.api.practice.touch_property', {
        attempt: props.attemptId,
        property: name,
      })
      run.data = { ...run.data, ...res }
      syncClock(res)
      if (!condition.value) {
        condition.value =
          res.properties?.find((p) => p.name === name)?.condition || ''
      }
    } catch (e) {
      toast.error(e.messages?.[0] || __('Could not open that property.'))
    }
    if (attempt.value.paused || !isPracticeRecording()) return
    if (hasPracticeRecorder() && !prev) return
    uploading.value = true
    try {
      const ended = await beginPropertyRecording(name)
      applyRecording(ended)
    } catch {
      toast.error(__('Could not save the recording for the last property.'))
    } finally {
      uploading.value = false
    }
  },
)

function select(i) {
  currentIndex.value = i
}

const compsRef = ref(null)

async function doneCurrent() {
  if (!current.value) return
  marking.value = true
  try {
    try {
      await compsRef.value?.saveCalcs?.()
    } catch {
      /* calc save is best-effort — still mark the house done */
    }
    const res = await call('crm.api.practice.mark_property_done', {
      attempt: props.attemptId,
      property: current.value.name,
    })
    run.data = { ...run.data, ...res }
    syncClock(res)
    if (currentIndex.value < properties.value.length - 1) {
      currentIndex.value += 1
    }
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not mark that done.'))
  } finally {
    marking.value = false
  }
}

async function persistCondition(propertyName) {
  if (!propertyName || attempt.value.status !== 'In Progress') return
  const text = condition.value
  const existing =
    properties.value.find((p) => p.name === propertyName)?.condition || ''
  if ((text || '') === existing) return
  try {
    const res = await call('crm.api.practice.save_condition', {
      attempt: props.attemptId,
      property: propertyName,
      text,
    })
    run.data = { ...run.data, ...res }
    syncClock(res)
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not save condition.'))
  }
}

async function togglePause() {
  if (attempt.value.status !== 'In Progress' || !attempt.value.mine) return
  pausing.value = true
  try {
    if (current.value) await persistCondition(current.value.name)
    const res = attempt.value.paused
      ? await call('crm.api.practice.resume_attempt', { attempt: props.attemptId })
      : await call('crm.api.practice.pause_attempt', { attempt: props.attemptId })
    run.data = { ...run.data, ...res }
    syncClock(res)
    if (res.paused) {
      pausePracticeRecording()
    } else {
      resumePracticeRecording()
      if (isPracticeRecording() && current.value && !hasPracticeRecorder()) {
        await beginPropertyRecording(current.value.name)
      }
    }
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not pause.'))
  } finally {
    pausing.value = false
  }
}

function applyRecording(res) {
  if (!res?.url || !res?.property || !run.data?.properties) return
  run.data = {
    ...run.data,
    properties: run.data.properties.map((p) =>
      p.name === res.property ? { ...p, recording_url: res.url } : p,
    ),
  }
}

async function flushRecording() {
  if (flushed) return
  if (!isPracticeRecording() && !recording.value) return
  flushed = true
  uploading.value = true
  recording.value = false
  try {
    applyRecording(await stopPracticeRecording())
  } catch {
    toast.error(__('Could not save the recording.'))
  } finally {
    uploading.value = false
  }
}

async function submit(timedOut = false) {
  submitting.value = true
  try {
    if (current.value) await persistCondition(current.value.name)
    await flushRecording()
    const res = await call('crm.api.practice.submit_attempt', {
      attempt: props.attemptId,
    })
    run.data = { ...run.data, ...res }
    syncClock(res)
    if (!timedOut) toast.success(__('Submitted'))
    router.push({ name: 'PracticeSet', params: { setId: props.setId } })
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not submit.'))
  } finally {
    submitting.value = false
  }
}

async function leave() {
  if (current.value) await persistCondition(current.value.name)
  await flushRecording()
  router.push({ name: 'PracticeSet', params: { setId: props.setId } })
}
</script>
