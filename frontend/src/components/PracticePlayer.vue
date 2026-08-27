<template>
  <Dialog
    v-model="show"
    :options="{ title: title || __('Practice recording'), size: '5xl' }"
  >
    <template #body-content>
      <div
        ref="panelEl"
        tabindex="0"
        class="flex max-h-[min(88vh,52rem)] flex-col gap-3 outline-none"
        data-practice-player
        @keydown="onPanelKey"
      >
        <div
          ref="stageEl"
          class="flex min-h-0 flex-col bg-black"
          :class="isFullscreen ? 'h-full' : ''"
        >
          <div
            class="relative flex items-center justify-center bg-black"
            :class="isFullscreen ? 'min-h-0 flex-1' : 'max-h-[min(48vh,32rem)]'"
          >
            <video
              ref="videoEl"
              class="w-full bg-black"
              :class="isFullscreen ? 'h-full object-contain' : 'max-h-[min(48vh,32rem)]'"
              controls
              autoplay
              playsinline
              preload="auto"
              :src="src"
              @loadedmetadata="onMeta"
              @durationchange="onMeta"
              @timeupdate="onTime"
              @play="isPaused = false"
              @pause="isPaused = true"
              @ended="isPaused = true"
            />
            <span
              v-for="b in bursts"
              :key="b.id"
              class="practice-burst pointer-events-none absolute text-3xl"
              :style="{ left: b.left, bottom: b.bottom }"
            >
              {{ b.emoji }}
            </span>
          </div>

          <div
            class="flex flex-col gap-1.5 px-2 py-2"
            :class="isFullscreen ? 'bg-black/80' : 'bg-surface-modal'"
          >
            <div v-if="list.length" class="relative h-5">
              <button
                v-for="r in list"
                :key="r.name"
                class="absolute top-0 -translate-x-1/2 rounded-full text-xs leading-none ring-1 ring-white transition-transform hover:scale-110"
                :class="
                  selected === r.name
                    ? 'z-10 bg-ink-gray-9 text-white'
                    : r.emoji
                      ? 'bg-surface-white'
                      : 'bg-violet-600 text-white'
                "
                :style="{ left: pos(r.at_time) }"
                :title="markerTitle(r)"
                @click="select(r)"
              >
                <span
                  class="flex size-5 items-center justify-center"
                  :class="r.emoji ? 'text-sm' : 'text-[10px] font-semibold'"
                >
                  {{ r.emoji || initialOf(r.author_name) }}
                </span>
              </button>
            </div>
            <div class="flex flex-wrap items-center gap-1.5">
              <button
                v-for="e in EMOJIS"
                :key="e"
                class="rounded px-1 text-base leading-none hover:bg-surface-gray-2"
                :title="__('React at this moment')"
                @click="dropEmoji(e)"
              >
                {{ e }}
              </button>
              <Button
                variant="ghost"
                icon="message-square"
                :label="__('Comment')"
                :title="__('Comment at this moment (C)')"
                @click="startComment"
              />
            </div>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-gray-5">
          <span class="inline-flex items-center gap-1">
            <kbd class="kbd">Space</kbd> {{ __('play') }}
          </span>
          <span class="inline-flex items-center gap-1">
            <kbd class="kbd">←</kbd><kbd class="kbd">→</kbd> {{ __('5s') }}
          </span>
          <span class="inline-flex items-center gap-1">
            <kbd class="kbd">C</kbd> {{ __('comment') }}
          </span>
          <span class="inline-flex items-center gap-1">
            <kbd class="kbd">F</kbd> {{ __('full') }}
          </span>
          <span class="inline-flex items-center gap-1">
            <kbd class="kbd">Esc</kbd> {{ __('close') }}
          </span>
        </div>

        <div
          v-if="composing"
          class="flex items-start gap-2 rounded-md border border-outline-gray-2 bg-surface-gray-1 p-2"
        >
          <span
            class="mt-1.5 shrink-0 rounded bg-surface-gray-3 px-1.5 py-0.5 text-[11px] font-medium tabular-nums text-ink-gray-7"
          >
            {{ fmt(draftTime) }}
          </span>
          <textarea
            ref="composerEl"
            v-model="draft"
            rows="2"
            :placeholder="__('Comment on this moment…')"
            class="min-w-0 flex-1 resize-none rounded-md border border-outline-gray-2 bg-surface-white px-2 py-1 text-sm text-ink-gray-9 focus:border-outline-gray-3 focus:outline-none"
            @keydown.enter.meta.prevent="submitComment"
            @keydown.enter.ctrl.prevent="submitComment"
            @keydown.esc.stop.prevent="cancelComment"
          />
          <div class="flex shrink-0 flex-col gap-1">
            <Button
              variant="solid"
              :label="__('Save')"
              :loading="saving"
              @click="submitComment"
            />
            <Button variant="ghost" :label="__('Cancel')" @click="cancelComment" />
          </div>
        </div>

        <div class="flex min-h-0 flex-1 flex-col">
          <div class="mb-1 text-sm font-medium text-ink-gray-5">
            {{ __('Comments') }}
            <span v-if="textComments.length"> · {{ textComments.length }}</span>
          </div>
          <div class="min-h-0 flex-1 overflow-y-auto">
            <div v-if="!textComments.length" class="py-3 text-sm text-ink-gray-5">
              {{ __('None yet — C to comment at this moment.') }}
            </div>
            <div
              v-for="c in textComments"
              :key="c.name"
              class="group flex items-start gap-2 rounded-md px-1.5 py-1.5"
              :class="
                selected === c.name ? 'bg-surface-gray-2' : 'hover:bg-surface-gray-1'
              "
            >
              <button
                class="mt-0.5 shrink-0 rounded bg-surface-gray-3 px-1.5 py-0.5 text-[11px] font-medium tabular-nums text-ink-gray-7 hover:text-ink-gray-9"
                :title="__('Jump to this moment')"
                @click="select(c)"
              >
                {{ fmt(c.at_time) }}
              </button>
              <div class="min-w-0 flex-1">
                <span class="text-xs font-medium text-ink-gray-8">
                  {{ c.author_name }}
                </span>
                <p class="whitespace-pre-line text-sm leading-snug text-ink-gray-7">
                  <span v-if="c.emoji" class="mr-1">{{ c.emoji }}</span>{{ c.content }}
                </p>
              </div>
              <button
                v-if="c.mine"
                class="shrink-0 opacity-0 group-hover:opacity-100"
                :title="__('Delete')"
                @click="maybeDelete(c)"
              >
                <FeatherIcon
                  name="trash-2"
                  class="size-3.5 text-ink-gray-4 hover:text-red-500"
                />
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { globalStore } from '@/stores/global'
import { Button, Dialog, FeatherIcon, call, createResource, toast } from 'frappe-ui'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const EMOJIS = ['👍', '👏', '❤️', '🔥', '😂', '😮']

const props = defineProps({
  attempt: { type: String, required: true },
  property: { type: String, required: true },
  src: { type: String, required: true },
  title: { type: String, default: '' },
})
const show = defineModel({ type: Boolean, default: false })

const { $socket } = globalStore()
const videoEl = ref(null)
const stageEl = ref(null)
const panelEl = ref(null)
const composerEl = ref(null)
const duration = ref(0)
const currentTime = ref(0)
const isPaused = ref(true)
const isFullscreen = ref(false)
const composing = ref(false)
const draft = ref('')
const draftTime = ref(0)
const saving = ref(false)
const selected = ref('')
const bursts = ref([])
let burstId = 0
let lastT = 0
let skipBurstUntil = 0
let durationFixed = false

const reactions = createResource({
  url: 'crm.api.practice.get_recording_reactions',
  makeParams: () => ({ attempt: props.attempt, property: props.property }),
  auto: true,
  initialData: [],
})
const list = computed(() => reactions.data || [])
const textComments = computed(() => list.value.filter((r) => r.content))

function fmt(t) {
  const n = Number(t)
  if (!Number.isFinite(n) || n < 0) return '0:00'
  const m = Math.floor(n / 60)
  const s = Math.floor(n % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}
function initialOf(name) {
  return (name || '?').trim().charAt(0).toUpperCase() || '?'
}
function pos(t) {
  const d = duration.value
  if (!d) return '0%'
  const pct = Math.min(100, Math.max(0, ((Number(t) || 0) / d) * 100))
  return `${pct}%`
}
function markerTitle(r) {
  const who = r.author_name || ''
  const bit = r.content || r.emoji || ''
  return `${who} · ${fmt(r.at_time)}${bit ? ' — ' + bit : ''}`
}
function nowTime() {
  return videoEl.value?.currentTime || 0
}

function mediaDuration(v) {
  const d = v?.duration
  return Number.isFinite(d) && d > 0 ? d : 0
}
function onMeta() {
  const v = videoEl.value
  if (!v) return
  const d = mediaDuration(v)
  if (d) {
    duration.value = d
    return
  }
  // MediaRecorder webm often reports Infinity until you seek past the end.
  if (durationFixed) return
  durationFixed = true
  const onUpdate = () => {
    const next = mediaDuration(v)
    if (!next) return
    v.removeEventListener('timeupdate', onUpdate)
    duration.value = next
    if (v.currentTime > 1e6) v.currentTime = 0
  }
  v.addEventListener('timeupdate', onUpdate)
  try {
    v.currentTime = 1e101
  } catch {
    /* ignore */
  }
}
function onTime() {
  const t = videoEl.value?.currentTime || 0
  currentTime.value = t
  const playing = videoEl.value && !videoEl.value.paused
  if (
    playing &&
    t > lastT &&
    t - lastT < 1 &&
    performance.now() > skipBurstUntil
  ) {
    for (const r of list.value) {
      if (r.emoji && r.at_time > lastT && r.at_time <= t) burst(r.emoji)
    }
  }
  lastT = t
}

function burst(emoji) {
  const id = ++burstId
  bursts.value = [
    ...bursts.value.slice(-6),
    {
      id,
      emoji,
      left: `${32 + Math.random() * 36}%`,
      bottom: `${22 + Math.random() * 18}%`,
    },
  ]
  setTimeout(() => {
    bursts.value = bursts.value.filter((b) => b.id !== id)
  }, 1400)
}

function playPause() {
  const v = videoEl.value
  if (!v) return
  if (v.paused) v.play().catch(() => {})
  else v.pause()
}
function skip(sec) {
  seek(nowTime() + sec)
}
function seek(t) {
  const v = videoEl.value
  if (!v) return
  const d = duration.value || mediaDuration(v) || 0
  const target = Number(t) || 0
  v.currentTime = d ? Math.max(0, Math.min(target, d)) : Math.max(0, target)
  currentTime.value = v.currentTime
  lastT = v.currentTime
}

function select(r) {
  if (r.mine && r.emoji && !r.content) {
    maybeDelete(r)
    return
  }
  selected.value = r.name
  seek(r.at_time)
}

async function dropEmoji(emoji) {
  const at = nowTime()
  skipBurstUntil = performance.now() + 800
  burst(emoji)
  try {
    await call('crm.api.practice.add_recording_reaction', {
      attempt: props.attempt,
      property: props.property,
      at_time: at,
      emoji,
    })
    reactions.reload()
  } catch (e) {
    toast.error(e?.messages?.[0] || __('Could not add reaction'))
  }
}

function startComment() {
  const v = videoEl.value
  if (v && !v.paused) v.pause()
  draftTime.value = nowTime()
  draft.value = ''
  composing.value = true
  nextTick(() => composerEl.value?.focus())
}
function cancelComment() {
  composing.value = false
  draft.value = ''
}
async function submitComment() {
  const content = draft.value.trim()
  if (!content || saving.value) return
  saving.value = true
  try {
    await call('crm.api.practice.add_recording_reaction', {
      attempt: props.attempt,
      property: props.property,
      at_time: draftTime.value,
      content,
    })
    composing.value = false
    draft.value = ''
    reactions.reload()
  } catch (e) {
    toast.error(e?.messages?.[0] || __('Could not add comment'))
  } finally {
    saving.value = false
  }
}

async function maybeDelete(r) {
  if (!r.mine) return
  try {
    await call('crm.api.practice.delete_recording_reaction', { name: r.name })
    if (selected.value === r.name) selected.value = ''
    reactions.reload()
  } catch (e) {
    toast.error(e?.messages?.[0] || __('Could not delete'))
  }
}

function fsEl() {
  return document.fullscreenElement || document.webkitFullscreenElement
}
function syncFs() {
  isFullscreen.value = !!fsEl()
}
async function toggleFullscreen() {
  try {
    if (fsEl()) {
      const exit = document.exitFullscreen || document.webkitExitFullscreen
      await exit?.call(document)
      return
    }
    const el = stageEl.value
    const req = el?.requestFullscreen || el?.webkitRequestFullscreen
    await req?.call(el)
  } catch {
    toast.error(__('Could not enter fullscreen'))
  }
}
function onEsc(e) {
  if (!fsEl()) return
  e.stopPropagation()
  e.preventDefault()
  toggleFullscreen()
}

function onEvent(data) {
  if (data?.attempt === props.attempt && data?.property === props.property) {
    reactions.reload()
  }
}

function onPanelKey(e) {
  const t = e.target
  const tag = t?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || t?.isContentEditable) return
  e.stopPropagation()
  if (t?.closest?.('video')) return
  const k = e.key
  if (k === 'Escape') {
    onEsc(e)
    return
  }
  if (k === ' ' || k === 'k' || k === 'K') {
    e.preventDefault()
    playPause()
    return
  }
  if (k === 'ArrowLeft') {
    e.preventDefault()
    skip(-5)
    return
  }
  if (k === 'ArrowRight') {
    e.preventDefault()
    skip(5)
    return
  }
  if (k === 'c' || k === 'C') {
    e.preventDefault()
    startComment()
    return
  }
  if (k === 'f' || k === 'F') {
    e.preventDefault()
    toggleFullscreen()
  }
}

onMounted(() => {
  $socket?.on('crm_practice_reaction', onEvent)
  document.addEventListener('fullscreenchange', syncFs)
  document.addEventListener('webkitfullscreenchange', syncFs)
  nextTick(() => panelEl.value?.focus())
})
onBeforeUnmount(() => {
  $socket?.off('crm_practice_reaction', onEvent)
  document.removeEventListener('fullscreenchange', syncFs)
  document.removeEventListener('webkitfullscreenchange', syncFs)
  if (fsEl()) {
    const exit = document.exitFullscreen || document.webkitExitFullscreen
    exit?.call(document)
  }
})
watch(
  () => [props.attempt, props.property],
  () => {
    selected.value = ''
    composing.value = false
    durationFixed = false
    duration.value = 0
    reactions.reload()
  },
)
</script>

<style scoped>
.kbd {
  display: inline-flex;
  min-width: 1.35rem;
  align-items: center;
  justify-content: center;
  padding: 0 5px;
  border-radius: 4px;
  border: 1px solid var(--outline-gray-2);
  background: var(--surface-gray-1);
  box-shadow: 0 1px 0 var(--outline-gray-2);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.6;
  color: var(--ink-gray-7);
}
.practice-burst {
  animation: practice-burst 1.4s ease-out forwards;
}
@keyframes practice-burst {
  0% {
    transform: translate(-50%, 0) scale(0.5);
    opacity: 0;
  }
  18% {
    transform: translate(-50%, -10px) scale(1.25);
    opacity: 1;
  }
  100% {
    transform: translate(-50%, -56px) scale(1);
    opacity: 0;
  }
}
</style>
