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
  dnc: false,
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
export async function enrich(number) {
  try {
    const r = await call('crm.api.telephony.lookup', { number })
    if (r?.dnc) phone.dnc = true
    if (r?.lead && !phone.lead) phone.lead = r.lead
    if (r?.lead_name && !phone.peerName) phone.peerName = r.lead_name
    return r
  } catch { return null }
}

export async function dial(number, { name = '', lead = null, line = null } = {}) {
  if (onCall.value) { toast.error(__('Finish your current call first')); return false }
  phone.error = ''
  Object.assign(phone, { peerNumber: number, peerName: name, lead, line, role: 'rep', state: 'connecting', callLog: null, dnc: false })
  const info = await enrich(number)
  if (info?.dnc) { reset(); toast.error(__('This number is on the do-not-contact list')); return false }
  try {
    await ensureClient()
    const started = await call('crm.api.telephony.dial', { to: number, line, lead })
    phone.callLog = started?.call_log || started?.desk_id || null
    // Server rings OUR credential first (conference-first). A second newCall
    // to the seller from the browser would double-dial them. Wait for the inbound.
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

function notify(title, body, tag) {
  try {
    if (typeof Notification === 'undefined' || document.hasFocus()) return
    if (Notification.permission === 'granted') {
      new Notification(title, { body, tag, silent: false })
    } else if (Notification.permission === 'default') {
      Notification.requestPermission()
    }
  } catch { /* permission API missing or denied */ }
}
export function requestNotifyPermission() {
  try {
    if (typeof Notification !== 'undefined' && Notification.permission === 'default') Notification.requestPermission()
  } catch { /* ignore */ }
}
export function notifyLiveOne(data) {
  notify(__('Got a live one'), `${data?.rep || ''} · ${data?.lead_name || data?.lead || ''}`.trim(), 'crm-live-one')
}

/** Incoming ring from `crm_incoming`; the SDK leg rings separately. */
export function ring(data) {
  if (onCall.value) return
  phone.incoming = data
  notify(__('Incoming call'), data?.lead_name || data?.from_name || data?.from || __('Unknown'), 'crm-incoming')
}
export async function answer() {
  if (!phone.incoming) return
  const inc = phone.incoming
  Object.assign(phone, { peerNumber: inc.from, peerName: inc.lead_name || inc.from_name || '', lead: inc.lead || null, line: inc.line || null, role: 'rep', callLog: inc.call_log, incoming: null, dnc: false })
  enrich(inc.from)
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
  const log = phone.callLog
  currentCall?.hangup()
  if (log) call('crm.api.telephony.hangup', { call_log: log }).catch(() => {})
  reset()
}
export function toggleMute() {
  if (!currentCall) return
  phone.muted = !phone.muted
  phone.muted ? currentCall.muteAudio() : currentCall.unmuteAudio()
}
export async function toggleHold() {
  if (!phone.callLog) return
  const next = !phone.held
  try {
    await call('crm.api.telephony.hold', { call_log: phone.callLog, held: next ? 1 : 0 })
    phone.held = next
  } catch (e) {
    toast.error(e?.messages?.[0] || __('Could not hold'))
  }
}
export function dtmf(digit) {
  currentCall?.dtmf(String(digit))
}
export async function inviteTeammate(user, mode = 'barge') {
  if (!phone.callLog || !user) return false
  try {
    await call('crm.api.telephony.invite', { call_log: phone.callLog, user, mode })
    toast.success(__('Ringing teammate…'))
    return true
  } catch (e) {
    toast.error(e?.messages?.[0] || __('Could not invite'))
    return false
  }
}
export async function transferTo(user) {
  if (!phone.callLog || !user) return false
  try {
    await call('crm.api.telephony.transfer', { call_log: phone.callLog, user })
    toast.success(__('Transferring… they take over when they answer.'))
    return true
  } catch (e) {
    toast.error(e?.messages?.[0] || __('Could not transfer'))
    return false
  }
}

function startTimer() { stopTimer(); phone.seconds = 0; timer = setInterval(() => (phone.seconds += 1), 1000) }
function stopTimer() { if (timer) clearInterval(timer); timer = null }
function reset() {
  stopTimer()
  Object.assign(phone, { state: 'idle', muted: false, held: false, callLog: null, role: 'rep', mode: 'monitor', dnc: false })
  currentCall = null
}
export function disconnect() {
  stopTimer()
  try { client?.disconnect() } catch { /* page is going away */ }
  client = null
}
