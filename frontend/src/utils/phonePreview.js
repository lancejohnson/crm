// In-memory design fixtures. No provider, storage, network, or CRM mutations.
export const previewCalls = [
  // `linked`: the rep's call matched a CRM lead. In the mockup that lead is
  // whichever real lead the preview last saw (state.previewLead); a cold call
  // to an unlinked number has no lead and joining it stays put.
  { id: 'demo-exe', rep: 'Exe', name: 'Jordan Ellis', number: '(202) 555-0123', elapsed: '08:42', linked: true },
  { id: 'demo-german', rep: 'Germán', name: 'Unlinked number', number: '(202) 555-0147', elapsed: '02:16', linked: false },
]
// Resolve a team call to the shape join() needs: a `lead` when it is linked.
export function previewTeamCall(state, call) {
  return { ...call, lead: call.linked ? state.previewLead || null : null }
}
export const previewTeammates = ['Exe', 'Germán', 'Dennis']
export const phoneDesigns = { A: 'Quick pocket', B: 'Conversation desk', C: 'Slim rail' }
export function selectPhoneDesign(state, design) {
  if (!Object.hasOwn(phoneDesigns, design)) return false
  Object.assign(state, { design, tab: design === 'A' ? 'History' : design === 'B' ? 'Texts' : 'Dial', minimized: false, panelsMinimized: false, settingsOpen: false })
  return true
}
export const audiences = {
  Listen: 'You hear both people. Neither hears you.',
  Whisper: 'Only the rep hears you. The other caller cannot hear your coaching.',
  Barge: 'Both people hear you. You are part of the conversation.',
}
export function previewNumberKey(number) {
  const digits = String(number || '').replace(/\D/g, '')
  if (digits.length < 10 || digits.length > 15) return ''
  return `+${digits.length === 10 ? '1' : ''}${digits}`
}
export function newPhonePreview() {
  return {
    // workspace: 'classic' | 'next' — see utils/workspaceVersion.js (the real
    // thing is a per-user Frappe default; the preview keeps it in memory).
    enabled: false, workspace: 'classic', workspaceBanner: false, workspaceBannerSeen: false,
    design: 'A', previewLead: null, incoming: null, role: 'rep', call: null, mode: 'Listen', muted: false, held: false,
    invited: false, joined: false, minimized: true, tab: 'History', number: '(202) 555-0147', note: '', nextSequence: 10,
    history: [
      { id: 'call-jordan-ready', sequence: 5, name: 'Jordan Ellis', number: '(202) 555-0123', direction: 'Outbound', result: 'Connected', time: 'Today · 10:14 AM', duration: '04:32', recording: 'ready', summary: 'Jordan wants a flexible closing date and would like to discuss repairs before considering an offer. Suggested next step: review the repair scope together.' },
      { id: 'call-unlinked-missed', sequence: 2, name: 'Unlinked number', number: '(202) 555-0147', direction: 'Inbound', result: 'Missed', time: 'Today · 9:48 AM', duration: '', recording: 'none', summary: '' },
      { id: 'call-jordan-pending', sequence: 1, name: 'Jordan Ellis', number: '(202) 555-0123', direction: 'Inbound', result: 'Connected', time: 'Today · 9:10 AM', duration: '01:18', recording: 'pending', summary: '' },
      { id: 'call-morgan-no-answer', sequence: 0, name: 'Morgan Lee', number: '(202) 555-0188', direction: 'Outbound', result: 'No answer', time: 'Yesterday · 3:20 PM', duration: '', recording: 'none', summary: '' },
    ],
    conversations: [
      { id: '+12025550123', name: 'Jordan Ellis', number: '(202) 555-0123', draft: '', messages: [
        { sequence: 3, direction: 'out', text: 'Would this afternoon work for a call?', time: 'Today · 10:10 AM' },
        { sequence: 4, direction: 'in', text: 'Yes, after two works for me.', time: 'Today · 10:12 AM' },
      ] },
      { id: '+12025550147', name: 'Unlinked number', number: '(202) 555-0147', draft: '', messages: [
        { sequence: 0, direction: 'in', text: 'Can you send me the details?', time: 'Yesterday · 4:06 PM' },
      ] },
    ],
    textThread: null, newTextNumber: '', notice: '', keypad: false, digits: '', alert: null, endedIds: [],
    chatOpen: false, chatUser: null,
    chats: Object.fromEntries(previewTeammates.map(name => [name, { draft: '', messages: [
      { author: name, text: name === 'Dennis' ? 'Flag me when they’re ready to talk numbers.' : 'I’m working my follow-ups. Message me here.', time: 'Example' },
    ] }])),
    settingsOpen: false, panelsMinimized: false, sound: false, browserNotice: false,
    phoneSettings: {
      recordingDefault: true,
      numbers: [
        { number: '(202) 555-0123', label: 'Exe’s line', owner: 'Exe', recording: 'inherit', members: { 'Exe': { view: true, use: true, ring: true }, 'Germán': { view: true, use: false, ring: false }, 'Dennis': { view: true, use: true, ring: false } } },
        { number: '(202) 555-0188', label: 'Acquisitions', owner: 'Dennis', recording: 'off', members: { 'Exe': { view: true, use: true, ring: true }, 'Germán': { view: true, use: true, ring: true }, 'Dennis': { view: true, use: true, ring: true } } },
      ],
    },
  }
}
export function startPreviewCall(state, role, call = previewCalls[0]) {
  if (state.call) {
    Object.assign(state, { notice: 'End or leave your current demo call before starting another.', minimized: false, panelsMinimized: false, tab: 'Dial' })
    return false
  }
  if (state.incoming && state.incoming.id !== call.id) {
    state.notice = 'Answer or decline the incoming demo call first.'
    state.panelsMinimized = false
    return false
  }
  state.endedIds = state.endedIds.filter(id => id !== call.id)
  Object.assign(state, { enabled: true, role, call: { direction: 'Outbound', ...call }, mode: 'Listen', muted: false, held: false, invited: false, joined: false, minimized: false, panelsMinimized: false, tab: 'Dial', notice: '', keypad: false, digits: '' })
  return true
}
export function triggerPreviewIncoming(state, unknown = false) {
  if (!state.incoming) state.incoming = {
    id: 'demo-incoming', rep: 'You', name: unknown ? 'Unknown caller' : 'Jordan Ellis',
    number: unknown ? '(202) 555-0199' : '(202) 555-0123', direction: 'Inbound', elapsed: '00:00',
    line: 'Acquisitions', context: unknown ? 'No matching contact in the demo.' : '1842 Willow Bend · Last spoke today',
  }
  Object.assign(state, { minimized: false, panelsMinimized: false, settingsOpen: false, notice: '' })
}
export function answerPreviewIncoming(state) {
  if (!state.incoming || !startPreviewCall(state, 'rep', state.incoming)) return false
  state.incoming = null
  return true
}
export function declinePreviewIncoming(state) {
  if (!state.incoming) return false
  const { name, number } = state.incoming
  const sequence = state.nextSequence++
  state.history.unshift({ id: `call-${sequence}`, sequence, name, number, direction: 'Inbound', result: 'Declined', time: 'Just now', duration: '', recording: 'none', summary: '' })
  state.incoming = null
  state.notice = 'Incoming call declined. Saved in History.'
  return true
}
export function callbackPreview(state, item) {
  if (!previewNumberKey(item.number)) { state.notice = 'Enter a 10–15 digit demo phone number.'; return false }
  return startPreviewCall(state, 'rep', { id: `demo-dial-${previewNumberKey(item.number)}`, name: item.name || 'Unlinked number', number: item.number, rep: 'You', elapsed: '00:00' })
}
// Where a joiner should land. A closer who accepts a live-one needs the house
// in front of them (the comps map is where Dennis prices from), not a phone
// panel. Calls with no CRM lead have nowhere to go, so they return null.
export function previewJoinDestination(call) {
  return call?.lead ? `/leads/${encodeURIComponent(call.lead)}/comps` : null
}
// Run a join attempt and say where the joiner should go. `start` is the guarded
// join (startPreviewCall / joinPreviewAlert); a blocked join returns null so
// callers never navigate away from a call in progress. Shared by the phone
// team bar and every comms mockup surface, so the rule cannot drift.
export function previewJoinOutcome(state, call, start, currentPath = '') {
  if (!start()) return null
  const destination = previewJoinDestination(call)
  if (!destination || destination === currentPath) return null
  state.minimized = true
  state.notice = `Joined listening · opened comps for ${call.lead}.`
  return destination
}
export function triggerPreviewAlert(state, lead = null) {
  state.panelsMinimized = false
  if (state.alert) return
  if (state.endedIds.includes(previewCalls[0].id)) state.endedIds = state.endedIds.filter(id => id !== previewCalls[0].id)
  state.alert = { call: { ...previewCalls[0], lead }, note: 'Ready to talk numbers. Can you join?', recipient: 'You' }
}
export function invitePreviewCloser(state) {
  if (!state.call || state.role !== 'rep') return
  state.invited = true
  state.notice = 'Demo alert sent to Dennis. Your call continues.'
}
export function joinPreviewAlert(state) {
  if (!state.alert || state.endedIds.includes(state.alert.call.id)) return false
  if (!startPreviewCall(state, 'closer', state.alert.call)) return false
  state.alert = null
  return true
}
export function endPreviewTeamCall(state, id) {
  if (!state.endedIds.includes(id)) state.endedIds.push(id)
  if (state.alert?.call.id === id) state.alert = null
  if (state.call?.id === id) { state.call = null; state.minimized = true }
  state.notice = 'Demo call ended. Its invite is no longer available.'
}
export function leavePreviewCall(state) {
  if (state.call && state.role === 'rep') {
    const sequence = state.nextSequence++
    state.history.unshift({ id: `call-${sequence}`, sequence, number: state.call.number, name: state.call.name, direction: state.call.direction, result: 'Ended · simulated', time: 'Just now', duration: state.call.elapsed, recording: 'pending', summary: '' })
    endPreviewTeamCall(state, state.call.id)
  }
  state.notice = state.role === 'closer' ? 'You left. The rep and caller stay connected (simulated).' : 'Call ended. Demo record saved in History.'
  state.call = null
  state.minimized = true
}
export function openPreviewText(state, number, name = 'Unlinked number') {
  const id = previewNumberKey(number)
  if (!id) { state.notice = 'Enter a 10–15 digit demo phone number.'; return false }
  let thread = state.conversations.find(item => item.id === id)
  if (!thread) {
    thread = { id, name, number: number.trim(), draft: '', messages: [] }
    state.conversations.unshift(thread)
  }
  Object.assign(state, { textThread: id, tab: 'Texts', minimized: false, panelsMinimized: false, notice: '', newTextNumber: '' })
  return true
}
export const previewRecordingLabels = { ready: 'Recording ready · sample', pending: 'Recording pending', none: 'Not recorded' }
// One chronological view derived from existing call/message fixtures, never copied.
export function previewConversationEvents(state, number) {
  const id = previewNumberKey(number)
  if (!id) return []
  const thread = state.conversations.find(item => item.id === id)
  return [
    ...state.history.filter(item => previewNumberKey(item.number) === id).map(item => ({ ...item, kind: 'call' })),
    ...(thread?.messages || []).map(item => ({ ...item, id: `text-${item.sequence}`, kind: 'text' })),
  ].sort((a, b) => a.sequence - b.sequence)
}
export function sendPreviewText(state) {
  const thread = state.conversations.find(item => item.id === state.textThread)
  if (!thread?.draft.trim()) return false
  thread.messages.push({ sequence: state.nextSequence++, direction: 'out', text: thread.draft.trim(), time: 'Just now · simulated' })
  thread.draft = ''
  state.notice = 'Demo text saved in this thread. Nothing sent.'
  return true
}
export function openPreviewChat(state, name) {
  if (!previewTeammates.includes(name)) return false
  Object.assign(state, { chatUser: name, chatOpen: true })
  return true
}
export function sendPreviewChat(state) {
  const chat = state.chats[state.chatUser]
  if (!chat?.draft.trim()) return false
  chat.messages.push({ author: 'You', text: chat.draft.trim(), time: 'Just now · demo' })
  chat.draft = ''
  return true
}
