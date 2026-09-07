import { call, toast } from 'frappe-ui'
import { computed, reactive } from 'vue'

/**
 * The one WebRTC leg for the next workspace's phone dock. Same token flow as
 * TelnyxCallUI.vue: `crm.integrations.telnyx.api.webrtc_token` mints a short-
 * lived per-user JWT server-side (the API key never reaches the browser) and
 * the SDK is imported lazily on the first call. Server-side call control —
 * conference, recording, supervisor joins — goes through `crm.api.telephony.*`;
 * this only owns the audio leg and its local state.
 */
export const phone = reactive({
  state: 'idle', // idle | connecting | ringing-out | ringing-in | active
  peerNumber: '',
  peerName: '',
  callLog: null, // CRM Call Log name once the server tells us
  lead: null,
  line: null,
  role: 'rep', // rep | supervisor
  mode: 'monitor', // supervisor audience: monitor | whisper | barge
  muted: false,
  held: false,
  seconds: 0,
  error: '',
  incoming: null, // { call_log, from, lead, lead_name, line } from crm_incoming
})

let client = null
let currentCall = null
let timer = null

export const elapsed = computed(() => {
  const m = Math.floor(phone.seconds / 60)
  const s = phone.seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
})
export const onCall = computed(() => phone.state !== 'idle')

async function ensureClient() {
  if (client) return client
  const { TelnyxRTC } = await import('@telnyx/webrtc')
  const cred = await call('crm.integrations.telnyx.api.webrtc_token')
  client = new TelnyxRTC({ login_token: cred.token })
  client.on('telnyx.ready', () => (phone.error = ''))
  client.on('telnyx.error', (e) => { phone.error = e?.error?.message || __('Phone error') })
  client.on('telnyx.notification', (n) => {
    const c = n.call
    if (!c) return
    currentCall = c
    const s = c.state
    if (s === 'ringing') phone.state = c.direction === 'inbound' ? 'ringing-in' : 'ringing-out'
    else if (s === 'active') { phone.state = 'active'; startTimer() }
    else if (['hangup', 'destroy'].includes(s)) reset()
    else if (['new', 'trying', 'requesting'].includes(s)) phone.state = 'connecting'
    phone.peerNumber = c.options?.remoteCallerNumber || phone.peerNumber
    phone.peerName = c.options?.remoteCallerName || phone.peerName
  })
  await client.connect()
  return client
}

/** Outbound: the server creates the conference-first call and we join our leg. */
export async function dial(number, { name = '', lead = null, line = null } = {}) {
  if (onCall.value) { toast.error(__('Finish your current call first')); return false }
  phone.error = ''
  Object.assign(phone, { peerNumber: number, peerName: name, lead, line, role: 'rep', state: 'connecting', callLog: null })
  try {
    const c = await ensureClient()
    const cred = await call('crm.integrations.telnyx.api.webrtc_token')
    const started = await call('crm.api.telephony.dial', { to: number, line })
    phone.callLog = started?.call_log || null
    currentCall = c.newCall({
      destinationNumber: number,
      callerNumber: line || cred.caller_number,
      callerName: cred.caller_name,
      audio: true,
      video: false,
      clientState: started?.client_state,
    })
    return true
  } catch (e) {
    reset()
    phone.error = e?.messages?.[0] || e?.message || __('Could not start the call')
    toast.error(phone.error)
    return false
  }
}

/** Supervisor join: the server adds our WebRTC leg to the conference with the mode. */
export async function join(callLog, mode = 'monitor', { name = '', lead = null } = {}) {
  if (onCall.value) { toast.error(__('Finish your current call first')); return false }
  phone.error = ''
  Object.assign(phone, { peerName: name, lead, role: 'supervisor', mode, state: 'connecting', callLog })
  try {
    await ensureClient()
    await call('crm.api.telephony.join', { call_log: callLog, mode })
    // The server dials our credential; the inbound notification lands as ringing-in.
    return true
  } catch (e) {
    reset()
    phone.error = e?.messages?.[0] || e?.message || __('Could not join the call')
    toast.error(phone.error)
    return false
  }
}

export async function setMode(mode) {
  if (phone.role !== 'supervisor' || !phone.callLog) return false
  await call('crm.api.telephony.set_mode', { call_log: phone.callLog, mode })
  phone.mode = mode
  return true
}

/** Incoming ring from `crm_incoming`; the SDK leg rings separately. */
export function ring(data) {
  if (onCall.value) return
  phone.incoming = data
}
export async function answer() {
  if (!phone.incoming) return
  const inc = phone.incoming
  Object.assign(phone, { peerNumber: inc.from, peerName: inc.lead_name || '', lead: inc.lead || null, line: inc.line || null, role: 'rep', callLog: inc.call_log, incoming: null })
  await ensureClient()
  if (currentCall?.state === 'ringing') currentCall.answer()
  else phone.state = 'connecting'
}
export async function decline() {
  const inc = phone.incoming
  phone.incoming = null
  if (currentCall?.state === 'ringing') currentCall.hangup()
  if (inc?.call_log) { try { await call('crm.api.telephony.decline', { call_log: inc.call_log }) } catch { /* the leg is already gone */ } }
}

export function hangup() {
  currentCall?.hangup()
  reset()
}
export function toggleMute() {
  if (!currentCall) return
  phone.muted = !phone.muted
  phone.muted ? currentCall.muteAudio() : currentCall.unmuteAudio()
}
export function toggleHold() {
  if (!currentCall) return
  phone.held = !phone.held
  phone.held ? currentCall.hold() : currentCall.unhold()
}
export function dtmf(digit) {
  currentCall?.dtmf(String(digit))
}

function startTimer() { stopTimer(); phone.seconds = 0; timer = setInterval(() => (phone.seconds += 1), 1000) }
function stopTimer() { if (timer) clearInterval(timer); timer = null }
function reset() {
  stopTimer()
  Object.assign(phone, { state: 'idle', muted: false, held: false, callLog: null, role: 'rep', mode: 'monitor' })
  currentCall = null
}
export function disconnect() {
  stopTimer()
  try { client?.disconnect() } catch { /* page is going away */ }
  client = null
}
