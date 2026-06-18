<template>
  <div class="flex flex-col gap-3 text-sm">
    <!-- no recording at all -->
    <div
      v-if="!loading && !recordingPath"
      class="rounded-md bg-surface-gray-1 px-3 py-2 text-ink-gray-5"
    >
      {{ __('No recording for this call.') }}
    </div>

    <template v-else>
      <!-- transport + talk-ratio -->
      <div class="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Button
          variant="subtle"
          :icon="isPaused ? PlayIcon : PauseIcon"
          @click="playPause"
        />
        <span class="tnum shrink-0 text-ink-gray-7">
          {{ formatTime(currentTime) }} / {{ formatTime(displayDuration) }}
        </span>
        <Dropdown :options="speedOptions">
          <Button variant="ghost" :label="`${playbackSpeed}×`" />
        </Dropdown>
        <Button variant="ghost" icon="download" @click="download" />

        <!-- talk-time balance: the two voices as a tug-of-war -->
        <div
          v-if="hasTranscript"
          class="ml-auto flex min-w-[220px] flex-1 items-center gap-2"
          :title="
            __('Talk time') +
            ` — ${repName}: ${formatTime(talk.rep_seconds)}, ${leadName}: ${formatTime(
              talk.lead_seconds,
            )}`
          "
        >
          <span class="tnum shrink-0 text-xs font-medium" :style="{ color: REP }">
            {{ pct(talk.rep) }}
          </span>
          <div class="flex h-2 flex-1 overflow-hidden rounded-full bg-surface-gray-2">
            <div
              class="h-full transition-all"
              :style="{ width: pct(talk.rep), background: REP }"
            />
            <div
              class="h-full transition-all"
              :style="{ width: pct(talk.lead), background: LEAD }"
            />
          </div>
          <span class="tnum shrink-0 text-xs font-medium" :style="{ color: LEAD }">
            {{ pct(talk.lead) }}
          </span>
        </div>
      </div>

      <!-- waveform + chapter ticks -->
      <div class="relative" ref="waveWrap">
        <!-- chapter markers -->
        <div
          v-if="chapters.length"
          class="relative mb-1 h-4"
          aria-hidden="true"
        >
          <button
            v-for="(c, i) in chapters"
            :key="i"
            class="group absolute top-0 flex -translate-x-1/2 items-center"
            :style="{ left: posOf(c.start) }"
            :title="`${c.title} · ${formatTime(c.start)}`"
            @click="seek(c.start)"
          >
            <span
              class="h-3 w-px"
              :class="
                isChapterActive(c) ? 'bg-ink-gray-9' : 'bg-outline-gray-2'
              "
            />
            <span
              class="ml-1 max-w-[12ch] truncate text-[10px] leading-none transition-colors"
              :class="
                isChapterActive(c)
                  ? 'font-medium text-ink-gray-8'
                  : 'text-ink-gray-4 group-hover:text-ink-gray-6'
              "
            >
              {{ c.title }}
            </span>
          </button>
        </div>

        <canvas
          ref="canvas"
          class="block h-24 w-full cursor-pointer touch-none select-none"
          @pointerdown="onPointerDown"
        />

        <div
          v-if="waveLoading"
          class="pointer-events-none absolute inset-0 flex items-center justify-center"
        >
          <span class="h-px w-full animate-pulse bg-outline-gray-2" />
          <span class="absolute text-xs text-ink-gray-4">
            {{ __('Drawing waveform…') }}
          </span>
        </div>
      </div>

      <!-- transcript -->
      <div
        v-if="hasTranscript"
        ref="scroller"
        class="flex max-h-80 flex-col overflow-y-auto pr-1"
      >
        <button
          v-for="(line, i) in dialogue"
          :key="i"
          :data-idx="i"
          class="flex w-full items-start gap-2 rounded-md py-1.5 pl-2 pr-2 text-left transition-colors"
          :class="
            i === activeLine
              ? 'bg-surface-gray-2'
              : 'hover:bg-surface-gray-1'
          "
          :style="
            i === activeLine
              ? { boxShadow: `inset 3px 0 0 ${colorFor(line.speaker)}` }
              : {}
          "
          @click="seek(line.start)"
        >
          <span class="tnum w-11 shrink-0 pt-0.5 text-xs text-ink-gray-4">
            {{ formatTime(line.start) }}
          </span>
          <span
            class="w-12 shrink-0 pt-0.5 text-xs font-medium"
            :style="{ color: colorFor(line.speaker) }"
          >
            {{ line.speaker === 'rep' ? repName : leadName }}
          </span>
          <span
            class="flex-1 leading-relaxed"
            :class="
              i === activeLine ? 'text-ink-gray-9' : 'text-ink-gray-7'
            "
          >
            {{ line.content }}
          </span>
        </button>
      </div>

      <!-- recording exists but transcript not ready -->
      <div
        v-else-if="!waveLoading"
        class="rounded-md bg-surface-gray-1 px-3 py-2 text-ink-gray-5"
      >
        {{
          __(
            'Transcript is still processing — it usually appears a few minutes after the call ends.',
          )
        }}
      </div>
    </template>

    <audio
      ref="audioEl"
      preload="none"
      @loadedmetadata="onMeta"
      @timeupdate="onTimeUpdate"
      @play="isPaused = false"
      @pause="isPaused = true"
      @ended="isPaused = true"
    />
  </div>
</template>

<script setup>
import PlayIcon from '@/components/Icons/PlayIcon.vue'
import PauseIcon from '@/components/Icons/PauseIcon.vue'
import Dropdown from '@/components/frappe-ui/Dropdown.vue'
import { Button, createResource } from 'frappe-ui'
import {
  ref,
  reactive,
  computed,
  watch,
  onMounted,
  onBeforeUnmount,
  nextTick,
} from 'vue'

const props = defineProps({
  // CRM Call Log docname
  callLogName: { type: String, required: true },
})

// the two voices — kept here (not just CSS) because canvas needs raw colors
const REP = '#3B82F6'
const LEAD = '#F59E0B'
const SILENCE = 'rgba(148, 163, 184, 0.45)'
const PLAYHEAD = '#171717'

const colorFor = (s) => (s === 'rep' ? REP : LEAD)

// ---- data ---------------------------------------------------------------
const loading = ref(true)
const recordingPath = ref('')
const dialogue = ref([])
const chapters = ref([])
const talk = reactive({ rep: 0, lead: 0, rep_seconds: 0, lead_seconds: 0 })
const repName = ref(__('Rep'))
const leadName = ref(__('Caller'))
const apiDuration = ref(0)

const hasTranscript = computed(() => dialogue.value.length > 0)

const transcript = createResource({
  url: 'crm.api.call_transcript.get_call_transcript',
  params: { call_log: props.callLogName },
  auto: true,
  onSuccess(d) {
    loading.value = false
    recordingPath.value = d.recording_url_path || ''
    dialogue.value = d.dialogue || []
    chapters.value = d.chapters || []
    apiDuration.value = d.duration || 0
    talk.rep = d.talk_ratio?.rep || 0
    talk.lead = d.talk_ratio?.lead || 0
    talk.rep_seconds = d.talk_ratio?.rep_seconds || 0
    talk.lead_seconds = d.talk_ratio?.lead_seconds || 0
    if (d.rep_name) repName.value = d.rep_name
    if (d.lead_name) leadName.value = d.lead_name
    if (recordingPath.value) nextTick(loadAudio)
  },
  onError() {
    loading.value = false
  },
})

// ---- audio + playback ---------------------------------------------------
const audioEl = ref(null)
const isPaused = ref(true)
const currentTime = ref(0)
const mediaDuration = ref(0)
const playbackSpeed = ref(1)

// transcript timing can be more reliable than mp3 metadata for VBR files
const displayDuration = computed(
  () => mediaDuration.value || apiDuration.value || 0,
)

function onMeta() {
  const d = audioEl.value?.duration
  if (d && isFinite(d)) mediaDuration.value = d
  draw()
}

function onTimeUpdate() {
  currentTime.value = audioEl.value?.currentTime || 0
  draw()
}

function playPause() {
  const a = audioEl.value
  if (!a) return
  if (a.paused) a.play()
  else a.pause()
}

function seek(t) {
  const a = audioEl.value
  if (!a) return
  a.currentTime = Math.max(0, Math.min(t, displayDuration.value || t))
  currentTime.value = a.currentTime
  draw()
}

const speedOptions = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2].map((s) => ({
  label: s === 1 ? __('Normal') : `${s}×`,
  onClick: () => {
    playbackSpeed.value = s
    if (audioEl.value) audioEl.value.playbackRate = s
  },
}))

function download() {
  if (!recordingPath.value) return
  const a = document.createElement('a')
  a.href = recordingPath.value
  a.download = `call-${props.callLogName}.mp3`
  a.click()
}

// ---- waveform: single fetch → decode peaks + play from the same bytes ----
const waveWrap = ref(null)
const canvas = ref(null)
const waveLoading = ref(false)
let peaks = [] // normalized 0..1 per bar
let barSpeakers = [] // 'rep' | 'lead' | null per bar (static once decoded)
let blobUrl = ''
let resizeObs = null

async function loadAudio() {
  const a = audioEl.value
  if (!a || !recordingPath.value) return
  a.playbackRate = playbackSpeed.value
  waveLoading.value = true
  try {
    const res = await fetch(recordingPath.value)
    if (!res.ok) throw new Error(`fetch ${res.status}`)
    const bytes = await res.arrayBuffer()
    // play from the bytes we already have (avoids a second download)
    blobUrl = URL.createObjectURL(new Blob([bytes], { type: 'audio/mpeg' }))
    a.src = blobUrl
    // decodeAudioData detaches its buffer, so hand it a copy
    const Ctx = window.AudioContext || window.webkitAudioContext
    const ctx = new Ctx()
    const audioBuf = await ctx.decodeAudioData(bytes.slice(0))
    peaks = computePeaks(audioBuf)
    computeBarSpeakers()
    ctx.close()
  } catch (e) {
    // waveform is a nicety; fall back to plain streaming playback
    console.warn('[CallTranscript] waveform decode failed, streaming instead', e)
    if (a && !a.src) a.src = recordingPath.value
    peaks = []
  } finally {
    waveLoading.value = false
    draw()
  }
}

function computePeaks(audioBuf) {
  const bars = barCount()
  const ch = audioBuf.numberOfChannels
  const len = audioBuf.length
  const step = Math.max(1, Math.floor(len / bars))
  const data = audioBuf.getChannelData(0)
  const data2 = ch > 1 ? audioBuf.getChannelData(1) : null
  const out = new Array(bars).fill(0)
  let max = 0.0001
  for (let b = 0; b < bars; b++) {
    const start = b * step
    const end = Math.min(start + step, len)
    let peak = 0
    for (let i = start; i < end; i += 2) {
      let v = Math.abs(data[i])
      if (data2) v = Math.max(v, Math.abs(data2[i]))
      if (v > peak) peak = v
    }
    out[b] = peak
    if (peak > max) max = peak
  }
  // normalize, with a gentle curve so quiet speech is still visible
  return out.map((p) => Math.pow(p / max, 0.7))
}

function barCount() {
  const w = waveWrap.value?.clientWidth || 600
  return Math.max(80, Math.min(700, Math.floor(w / 3)))
}

// which speaker holds a given time (for lane + color)
function speakerAt(t) {
  const d = dialogue.value
  for (let i = 0; i < d.length; i++) {
    if (t >= d[i].start && t < d[i].end) return d[i].speaker
  }
  return null
}

// precompute speaker per bar once (lane/color are static; only the played/
// unplayed split changes per frame)
function computeBarSpeakers() {
  const n = peaks.length
  const dur = displayDuration.value || 1
  barSpeakers = new Array(n)
  if (!hasTranscript.value) {
    barSpeakers.fill('rep')
    return
  }
  for (let i = 0; i < n; i++) {
    barSpeakers[i] = speakerAt((i / n) * dur)
  }
}

function draw() {
  const cv = canvas.value
  if (!cv) return
  const dpr = window.devicePixelRatio || 1
  const cssW = cv.clientWidth
  const cssH = cv.clientHeight
  if (!cssW || !cssH) return
  if (cv.width !== cssW * dpr || cv.height !== cssH * dpr) {
    cv.width = cssW * dpr
    cv.height = cssH * dpr
  }
  const g = cv.getContext('2d')
  g.setTransform(dpr, 0, 0, dpr, 0, 0)
  g.clearRect(0, 0, cssW, cssH)

  const axis = cssH / 2
  const dur = displayDuration.value || 1
  const progressX = (currentTime.value / dur) * cssW

  if (!peaks.length) {
    // no decoded waveform — draw a quiet baseline so the control still reads
    g.strokeStyle = SILENCE
    g.beginPath()
    g.moveTo(0, axis)
    g.lineTo(cssW, axis)
    g.stroke()
    drawPlayhead(g, progressX, cssH)
    return
  }

  const n = peaks.length
  const bw = cssW / n
  const barW = Math.max(1, bw * 0.7)
  const maxH = axis - 3
  for (let i = 0; i < n; i++) {
    const x = i * bw + (bw - barW) / 2
    const sp = barSpeakers[i] !== undefined ? barSpeakers[i] : 'rep'
    const h = Math.max(1, peaks[i] * maxH)
    const played = x < progressX
    let color = sp === 'lead' ? LEAD : sp === 'rep' ? REP : SILENCE
    g.fillStyle = played ? color : withAlpha(color, 0.35)
    if (sp === 'lead') {
      // lead lane: below the axis
      g.fillRect(x, axis + 1, barW, h)
    } else if (sp === 'rep') {
      // rep lane: above the axis
      g.fillRect(x, axis - h, barW, h)
    } else {
      // silence: a small centered nub
      const nub = Math.max(1, h * 0.35)
      g.fillRect(x, axis - nub / 2, barW, nub)
    }
  }
  drawPlayhead(g, progressX, cssH)
}

function drawPlayhead(g, x, h) {
  g.fillStyle = PLAYHEAD
  g.fillRect(Math.max(0, Math.min(x, g.canvas.clientWidth) - 1), 0, 1.5, h)
}

function withAlpha(color, a) {
  if (color.startsWith('rgba')) return color
  // hex → rgba
  const m = color.replace('#', '')
  const r = parseInt(m.slice(0, 2), 16)
  const gg = parseInt(m.slice(2, 4), 16)
  const b = parseInt(m.slice(4, 6), 16)
  return `rgba(${r}, ${gg}, ${b}, ${a})`
}

// ---- seek by clicking / dragging the waveform ---------------------------
function timeFromEvent(e) {
  const rect = canvas.value.getBoundingClientRect()
  const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width))
  return (x / rect.width) * (displayDuration.value || 0)
}
function onPointerDown(e) {
  seek(timeFromEvent(e))
  const move = (ev) => seek(timeFromEvent(ev))
  const up = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}

// ---- active transcript line + auto-scroll -------------------------------
const scroller = ref(null)
const activeLine = computed(() => {
  const t = currentTime.value
  const d = dialogue.value
  for (let i = 0; i < d.length; i++) {
    if (t >= d[i].start && t < d[i].end) return i
  }
  return -1
})
// The line to keep in view: the active one if any, else the last line that has
// begun (so seeking into a silence gap still scrolls to where we are). Segments
// can overlap and aren't strictly sorted, so scan for the greatest start <= t.
const scrollLine = computed(() => {
  if (activeLine.value >= 0) return activeLine.value
  const t = currentTime.value
  const d = dialogue.value
  let idx = d.length ? 0 : -1
  let best = -Infinity
  for (let i = 0; i < d.length; i++) {
    if (d[i].start <= t && d[i].start > best) {
      best = d[i].start
      idx = i
    }
  }
  return idx
})
watch(scrollLine, (i) => {
  if (i < 0 || !scroller.value) return
  nextTick(() => {
    const el = scroller.value?.querySelector(`[data-idx="${i}"]`)
    if (el?.scrollIntoView) el.scrollIntoView({ block: 'nearest' })
  })
})

// ---- chapters -----------------------------------------------------------
function posOf(t) {
  const dur = displayDuration.value || 1
  return `${Math.max(0, Math.min((t / dur) * 100, 100))}%`
}
function isChapterActive(c) {
  const t = currentTime.value
  return t >= c.start && (c.end == null || t < c.end)
}

// ---- helpers ------------------------------------------------------------
function formatTime(t) {
  if (!t || isNaN(t)) return '0:00'
  const m = Math.floor(t / 60)
  const s = Math.floor(t % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}
function pct(r) {
  return `${Math.round((r || 0) * 100)}%`
}

onMounted(() => {
  resizeObs = new ResizeObserver(() => {
    // bar count tracks width; recompute peaks lazily on next decode, redraw now
    draw()
  })
  if (waveWrap.value) resizeObs.observe(waveWrap.value)
})

onBeforeUnmount(() => {
  resizeObs?.disconnect()
  if (blobUrl) URL.revokeObjectURL(blobUrl)
})

watch(() => props.callLogName, () => transcript.reload())
</script>

<style scoped>
.tnum {
  font-variant-numeric: tabular-nums;
}
</style>
