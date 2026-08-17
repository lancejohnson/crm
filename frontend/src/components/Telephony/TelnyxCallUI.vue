<template>
  <!-- Nothing is rendered until there is a call. A softphone that is always on
       screen is a softphone in the way; this appears when it has something to
       say and disappears when the call ends. -->
  <div
    v-if="state !== 'idle'"
    class="fixed bottom-4 right-4 z-[1100] w-72 rounded-lg border bg-surface-white p-3 shadow-2xl"
    style="border-color: var(--surface-gray-3)"
  >
    <div class="flex items-center gap-2">
      <span
        class="size-2 shrink-0 rounded-full"
        :class="state === 'active' ? 'bg-surface-green-3' : 'animate-pulse bg-surface-amber-3'"
      />
      <div class="min-w-0 flex-1">
        <div class="truncate text-sm font-medium text-ink-gray-9">
          {{ peerName || formatPhone(peerNumber) || __('Call') }}
        </div>
        <div class="text-xs text-ink-gray-5">{{ statusLabel }}</div>
      </div>
      <span v-if="state === 'active'" class="tabular-nums text-xs text-ink-gray-6">
        {{ elapsed }}
      </span>
    </div>

    <div class="mt-3 flex gap-2">
      <Button
        v-if="state === 'ringing-in'"
        class="flex-1"
        variant="solid"
        theme="green"
        :label="__('Answer')"
        @click="answer"
      />
      <Button
        class="flex-1"
        :variant="state === 'ringing-in' ? 'subtle' : 'solid'"
        theme="red"
        :label="state === 'ringing-in' ? __('Decline') : __('Hang up')"
        @click="hangup"
      />
      <Button
        v-if="state === 'active'"
        :variant="muted ? 'solid' : 'subtle'"
        :icon="muted ? 'mic-off' : 'mic'"
        :title="muted ? __('Unmute') : __('Mute')"
        @click="toggleMute"
      />
    </div>

    <div v-if="error" class="mt-2 text-xs text-ink-red-4">{{ error }}</div>
  </div>
</template>

<script setup>
/**
 * Browser softphone on Telnyx WebRTC.
 *
 * WHY A SOFTPHONE AT ALL. The desk exists so a rep works a call from one screen;
 * dialling from a handset means the number they are looking at and the number
 * they are calling are in two different places, and the call has no connection
 * to the lead until someone types it in.
 *
 * THE API KEY NEVER COMES HERE. `crm.integrations.telnyx.api.webrtc_token` mints
 * a short-lived JWT per user, server-side. A key in a bundle is a key on every
 * machine that ever loaded the page.
 *
 * The SDK is loaded LAZILY, on the first call rather than at app start: it is a
 * WebRTC stack, and no rep should pay for it on a page they opened to read a
 * timeline.
 */
import { Button, call, toast } from 'frappe-ui'
import { computed, onBeforeUnmount, ref } from 'vue'
import { formatPhone } from '@/utils/phoneFormat'

const state = ref('idle') // idle | connecting | ringing-out | ringing-in | active
const peerNumber = ref('')
const peerName = ref('')
const error = ref('')
const muted = ref(false)
const seconds = ref(0)

let client = null
let currentCall = null
let timer = null

const statusLabel = computed(
  () =>
    ({
      connecting: __('Connecting…'),
      'ringing-out': __('Ringing…'),
      'ringing-in': __('Incoming call'),
      active: __('On the call'),
    })[state.value] || '',
)

const elapsed = computed(() => {
  const m = Math.floor(seconds.value / 60)
  const s = seconds.value % 60
  return `${m}:${String(s).padStart(2, '0')}`
})

async function ensureClient() {
  if (client) return client
  const { TelnyxRTC } = await import('@telnyx/webrtc')
  const cred = await call('crm.integrations.telnyx.api.webrtc_token')

  client = new TelnyxRTC({ login_token: cred.token })
  client.on('telnyx.ready', () => (error.value = ''))
  client.on('telnyx.error', (e) => {
    error.value = e?.error?.message || __('Phone error')
  })
  client.on('telnyx.notification', (n) => {
    const c = n.call
    if (!c) return
    currentCall = c
    // Telnyx's own state names, mapped to the four a human cares about.
    const s = c.state
    if (s === 'ringing') state.value = c.direction === 'inbound' ? 'ringing-in' : 'ringing-out'
    else if (s === 'active') {
      state.value = 'active'
      startTimer()
    } else if (['hangup', 'destroy'].includes(s)) reset()
    else if (['new', 'trying', 'requesting'].includes(s)) state.value = 'connecting'

    peerNumber.value = c.options?.remoteCallerNumber || peerNumber.value
    peerName.value = c.options?.remoteCallerName || peerName.value
  })

  await client.connect()
  return client
}

/** Place a call. Exposed so the desk and the Today card can both dial. */
async function dial(number, { name = '' } = {}) {
  error.value = ''
  peerNumber.value = number
  peerName.value = name
  state.value = 'connecting'
  try {
    const c = await ensureClient()
    const cred = await call('crm.integrations.telnyx.api.webrtc_token')
    currentCall = c.newCall({
      destinationNumber: number,
      callerNumber: cred.caller_number,
      callerName: cred.caller_name,
      audio: true,
      video: false,
    })
  } catch (e) {
    reset()
    // Voicemail-not-set is a real, actionable refusal from the server -- show it
    // rather than a generic failure.
    error.value = e?.messages?.[0] || e?.message || __('Could not start the call')
    toast.error(error.value)
  }
}

function answer() {
  currentCall?.answer()
}

function hangup() {
  currentCall?.hangup()
  reset()
}

function toggleMute() {
  if (!currentCall) return
  muted.value = !muted.value
  muted.value ? currentCall.muteAudio() : currentCall.unmuteAudio()
}

function startTimer() {
  stopTimer()
  seconds.value = 0
  timer = setInterval(() => (seconds.value += 1), 1000)
}
function stopTimer() {
  if (timer) clearInterval(timer)
  timer = null
}

function reset() {
  stopTimer()
  state.value = 'idle'
  muted.value = false
  currentCall = null
}

onBeforeUnmount(() => {
  stopTimer()
  try {
    client?.disconnect()
  } catch {
    /* the socket is going away with the page anyway */
  }
})

defineExpose({ dial, hangup, state })
</script>
