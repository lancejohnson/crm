import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { newPhonePreview, previewCalls, startPreviewCall, leavePreviewCall, sendPreviewText, audiences, triggerPreviewAlert, joinPreviewAlert, endPreviewTeamCall, invitePreviewCloser, sendPreviewChat, openPreviewChat, openPreviewText, callbackPreview, previewNumberKey, phoneDesigns, selectPhoneDesign, triggerPreviewIncoming, answerPreviewIncoming, declinePreviewIncoming, previewConversationEvents, previewRecordingLabels, previewJoinDestination, previewTeamCall } from '../src/utils/phonePreview.js'
import { previewChatPosition } from '../src/utils/phonePreviewPosition.js'
const p = newPhonePreview()
const initialHistory = p.history.length
assert.equal(p.enabled, false)
assert.equal(p.minimized, true)
assert.equal(p.tab, 'History', 'design A opens on recent calls')
assert.equal(callbackPreview(p, { number: 'bad' }), false)
assert.equal(p.call, null)
assert.ok(initialHistory >= 3)
assert.ok(p.history.every(item => item.number && item.direction && item.result && item.time))
assert.ok(p.history.some(item => item.result === 'Missed' && !item.duration))
assert.equal(startPreviewCall(p, 'closer', previewCalls[1]), true)
p.mode = 'Whisper'
const liveCall = p.call
assert.equal(callbackPreview(p, p.history[0]), false, 'callback must not replace active call')
assert.equal(p.call, liveCall)
assert.equal(p.mode, 'Whisper')
triggerPreviewAlert(p)
assert.equal(joinPreviewAlert(p), false, 'join alert must not replace active call')
assert.ok(p.alert, 'blocked join keeps invitation')
leavePreviewCall(p)
assert.equal(p.history.length, initialHistory, 'closer leave does not log ended rep call')
assert.deepEqual(p.endedIds, [])
assert.match(p.notice, /stay connected/)
const alert = p.alert
p.panelsMinimized = true
triggerPreviewAlert(p)
assert.equal(p.alert, alert)
assert.equal(p.panelsMinimized, false)
assert.equal(joinPreviewAlert(p), true)
assert.equal(p.mode, 'Listen')
assert.equal(p.alert, null)
leavePreviewCall(p)
triggerPreviewAlert(p)
endPreviewTeamCall(p, 'demo-exe')
assert.equal(p.alert, null)
assert.equal(joinPreviewAlert(p), false)
startPreviewCall(p, 'rep')
invitePreviewCloser(p)
assert.equal(p.invited, true)
leavePreviewCall(p)
assert.equal(p.history.length, initialHistory + 1)
assert.equal(p.history[0].duration, '08:42')
assert.equal(p.history[0].direction, 'Outbound')
assert.equal(p.history[0].time, 'Just now')
assert.equal(p.minimized, true)
assert.equal(callbackPreview(p, p.history[1]), true)
assert.equal(p.call.name, 'Jordan Ellis')
assert.equal(p.call.number, p.history[1].number)
assert.equal(p.tab, 'Dial')
// History Text maps to the same canonical thread even when phone formatting differs.
assert.equal(openPreviewText(p, p.history[1].number, p.history[1].name), true)
assert.equal(p.tab, 'Texts')
const jordan = p.conversations.find(item => item.id === p.textThread)
assert.equal(jordan.name, 'Jordan Ellis')
const threadCount = p.conversations.length
assert.equal(openPreviewText(p, '+1 202 555 0123'), true)
assert.equal(p.conversations.length, threadCount)
assert.equal(p.textThread, jordan.id)
assert.ok(p.call, 'texting leaves active call intact')
assert.equal(sendPreviewText(p), false)
jordan.draft = '  Draft for Jordan  '
openPreviewText(p, '(202) 555-0199')
const newThread = p.conversations.find(item => item.id === p.textThread)
assert.equal(newThread.messages.length, 0)
assert.equal(newThread.name, 'Unlinked number')
assert.equal(jordan.draft, '  Draft for Jordan  ', 'draft survives changing threads')
newThread.draft = '  New number text  '
assert.equal(sendPreviewText(p), true)
assert.equal(newThread.messages[0].text, 'New number text')
assert.equal(newThread.messages[0].direction, 'out')
assert.equal(newThread.draft, '')
assert.equal(jordan.messages.length, 2, 'send goes only to selected recipient')
openPreviewText(p, jordan.number)
assert.equal(sendPreviewText(p), true)
assert.equal(jordan.messages.at(-1).text, 'Draft for Jordan')
assert.equal(p.history.length, initialHistory + 1, 'Texts have threads, not call-history rows')
assert.equal(openPreviewText(p, 'abc'), false)
assert.equal(previewNumberKey(''), '')
assert.equal(previewNumberKey('(202) 555-0123'), '+12025550123')
// Status/chat never joins or changes the active call; each person owns a draft/thread.
const callBeforeChat = p.call
assert.equal(openPreviewChat(p, 'Exe'), true)
assert.equal(p.call, callBeforeChat)
p.chats.Exe.draft = 'Only Exe sees this'
assert.equal(openPreviewChat(p, 'Germán'), true)
assert.equal(sendPreviewChat(p), false)
p.chats['Germán'].draft = '  Hello Germán  '
assert.equal(sendPreviewChat(p), true)
assert.equal(p.chats['Germán'].messages.at(-1).text, 'Hello Germán')
assert.equal(p.chats.Exe.messages.length, 1)
openPreviewChat(p, 'Exe')
assert.equal(p.chats.Exe.draft, 'Only Exe sees this')
assert.equal(sendPreviewChat(p), true)
openPreviewChat(p, 'Dennis')
assert.equal(p.chats.Dennis.messages.length, 1)
assert.equal(openPreviewChat(p, 'Unknown'), false)
assert.equal(p.chatUser, 'Dennis')
assert.match(audiences.Whisper, /Only the rep/)
assert.match(audiences.Barge, /Both people/)
assert.equal(newPhonePreview().history.length, initialHistory)
assert.equal(newPhonePreview().conversations[0].messages.length, 2, 'fresh fixture has independent arrays')
// Designs have different default workflows, without replacing an active call.
for (const design of Object.keys(phoneDesigns)) {
  assert.equal(selectPhoneDesign(p, design), true)
  assert.equal(p.design, design)
  assert.equal(p.call, callBeforeChat)
}
assert.equal(selectPhoneDesign(p, 'bad'), false)
// Incoming call handling is a real state transition, not a completed-call fiction.
const incomingState = newPhonePreview()
triggerPreviewIncoming(incomingState)
assert.equal(incomingState.incoming.direction, 'Inbound')
assert.equal(callbackPreview(incomingState, incomingState.history[0]), false)
assert.equal(answerPreviewIncoming(incomingState), true)
assert.equal(incomingState.incoming, null)
assert.equal(incomingState.call.direction, 'Inbound')
const answered = incomingState.call
triggerPreviewIncoming(incomingState, true)
assert.equal(answerPreviewIncoming(incomingState), false, 'incoming cannot replace an active call')
assert.equal(incomingState.call, answered)
assert.ok(incomingState.incoming)
assert.equal(declinePreviewIncoming(incomingState), true)
assert.equal(incomingState.history[0].result, 'Declined')
assert.equal(incomingState.history[0].duration, '')
assert.equal(incomingState.call, answered, 'declining leaves current call connected')
assert.equal(declinePreviewIncoming(incomingState), false)
leavePreviewCall(incomingState)
assert.equal(incomingState.history[0].direction, 'Inbound')
// Chat never changes phone minimized/open state, and viewport math stays bounded.
p.minimized = false
openPreviewChat(p, 'Exe')
assert.equal(p.minimized, false)
for (const width of [390, 1200]) {
  for (const left of [-100, 20, width - 30, width + 100]) {
    const pos = previewChatPosition({ left, width: 60, top: 720 }, width, 844)
    assert.ok(parseFloat(pos.left) >= 12)
    assert.ok(parseFloat(pos.left) + parseFloat(pos.width) <= width - 36)
    assert.ok(parseFloat(pos.bottom) + parseFloat(pos.maxHeight) <= 844 - 12)
  }
}
// Unified per-person conversation: calls and texts interleave oldest-first; only
// connected calls carry a summary or recording; recording state is explicit.
{
  const fresh = newPhonePreview()
  const timeline = previewConversationEvents(fresh, '202-555-0123')
  assert.ok(timeline.length >= 4, 'Jordan has both calls and texts')
  assert.deepEqual(timeline.map(e => e.kind), ['call', 'text', 'text', 'call'], 'chronological interleave by sequence')
  assert.ok(timeline.every((e, i) => i === 0 || e.sequence >= timeline[i - 1].sequence))
  assert.deepEqual(previewConversationEvents(fresh, 'nope'), [])
  for (const item of fresh.history) {
    assert.ok(Object.hasOwn(previewRecordingLabels, item.recording), `recording state labelled: ${item.recording}`)
    if (!item.duration) { assert.equal(item.summary, '', 'no summary for missed/no-answer'); assert.equal(item.recording, 'none') }
    if (item.recording === 'ready') assert.ok(item.summary, 'a ready recording has a sample summary')
  }
  triggerPreviewIncoming(fresh)
  declinePreviewIncoming(fresh)
  assert.equal(fresh.history[0].result, 'Declined')
  assert.equal(fresh.history[0].summary, '', 'declined calls never get a summary')
  assert.equal(fresh.history[0].recording, 'none')
  assert.equal(previewConversationEvents(fresh, '(202) 555-0123')[0].kind, 'call')
  assert.equal(previewConversationEvents(fresh, '(202) 555-0123').at(-1).result, 'Declined', 'declined call lands in that person\u2019s conversation')
  // Sample audio is synthetic and its real duration must be what the player shows.
  const wav = readFileSync(new URL('../src/assets/phone-preview-sample.wav', import.meta.url))
  assert.equal(wav.toString('ascii', 0, 4), 'RIFF')
  const rate = wav.readUInt32LE(24), channels = wav.readUInt16LE(22), bits = wav.readUInt16LE(34)
  const seconds = (wav.length - 44) / (rate * channels * bits / 8)
  assert.ok(Math.abs(seconds - 8) < 0.05, `sample is ~8s, got ${seconds}`)
  assert.ok(wav.length < 400_000, 'sample stays small')
}
// Joining a live-one lands on the lead's comps map; fictional calls without a lead go nowhere.
{
  const fresh = newPhonePreview()
  triggerPreviewAlert(fresh)
  assert.equal(previewJoinDestination(fresh.alert.call), null, 'no lead, no navigation')
  fresh.alert = null
  triggerPreviewAlert(fresh, 'CRM-LEAD-2026-00008')
  assert.equal(previewJoinDestination(fresh.alert.call), '/leads/CRM-LEAD-2026-00008/comps')
  assert.equal(previewJoinDestination({ lead: 'a/b c' }), '/leads/a%2Fb%20c/comps', 'lead ids are URL-encoded')
  startPreviewCall(fresh, 'rep')
  assert.equal(joinPreviewAlert(fresh), false, 'blocked join must not navigate either')
  // Headset join from the team bar: linked rep call -> comps; unlinked cold call -> stays.
  const bar = newPhonePreview()
  assert.equal(previewJoinDestination(previewTeamCall(bar, previewCalls[0])), null, 'no lead seen yet, nowhere to go')
  bar.previewLead = 'CRM-LEAD-2026-00008'
  assert.equal(previewJoinDestination(previewTeamCall(bar, previewCalls[0])), '/leads/CRM-LEAD-2026-00008/comps', 'Exe\u2019s linked call opens comps')
  assert.equal(previewJoinDestination(previewTeamCall(bar, previewCalls[1])), null, 'Germ\u00e1n\u2019s unlinked number never navigates')
  assert.equal(previewTeamCall(bar, previewCalls[0]).id, 'demo-exe', 'join still targets the same team call')
}
const settings = newPhonePreview().phoneSettings
settings.numbers[0].members['Germán'].ring = true
assert.equal(settings.numbers[0].members['Germán'].use, false, 'ring and use permissions are distinct')
settings.recordingDefault = false
assert.equal(settings.numbers[0].recording, 'inherit')
assert.equal(settings.numbers[1].recording, 'off', 'workspace changes preserve explicit overrides')
assert.equal(newPhonePreview().phoneSettings.recordingDefault, true)
for (const file of ['pages/PhonePreview.vue', 'pages/PhoneSettingsPreview.vue', 'components/Telephony/PhonePreviewWidget.vue', 'components/Telephony/PhonePreviewTexts.vue', 'components/Telephony/PhonePreviewChat.vue', 'components/Telephony/PhonePreviewCall.vue', 'components/Telephony/PhonePreviewRecording.vue']) {
  const source = readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8')
  const { descriptor, errors } = parse(source, { filename: file })
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: file })
  const template = compileTemplate({ source: descriptor.template.content, filename: file, id: file, compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(template.errors, [])
  assert.doesNotMatch(source, /\b(fetch|createResource|createDocumentResource|localStorage|sessionStorage|Notification|AudioContext)\b|crm\.integrations|@telnyx|requestPermission/)
  if (file === 'pages/PhonePreview.vue') {
    assert.equal((source.match(/await call\(/g) || []).length, 1)
    assert.match(source, /call\('frappe.client.get_list'/)
  } else {
    assert.doesNotMatch(source, /\bcall\(/, 'phone controls have no API calls')
  }
  if (file.endsWith('Widget.vue')) {
    assert.match(source, /emit\('reserve'/)
    assert.match(source, /Fictional caller, not the real lead/)
    assert.match(source, /PhonePreviewChat v-if=/)
    assert.match(source, /name: 'History'/)
    assert.doesNotMatch(source, /aria-label="Demo teammate chat"[^>]*@click/, 'generic chat entry removed')
    assert.match(source, /class="status-chat"/)
    for (const button of source.matchAll(/<button\b[^>]*>([\s\S]*?)<\/button>/g)) {
      assert.doesNotMatch(button[1], /<(button|Button)\b/, 'status-chat and headset must be sibling buttons')
    }
    assert.match(source, /aria-label="Minimize all phone panels"/)
    assert.match(source, /previewJoinOutcome\(p, call, start, route\.path\)/, 'join goes through the shared guard helper')
    const utils = readFileSync(new URL('../src/utils/phonePreview.js', import.meta.url), 'utf8')
    assert.match(utils, /export function previewJoinOutcome[\s\S]*?if \(!start\(\)\) return null/, 'navigation only after a successful join')
    assert.match(source, /\.answer-call \{[^}]*background: #167645/, 'Answer is visibly green')
    assert.match(source, /\.decline-call \{[^}]*color: #a32e2e/, 'Decline reads red')
  }
  if (file.endsWith('Texts.vue')) {
    assert.match(source, /previewConversationEvents/, 'thread is the unified calls+texts timeline')
    assert.match(source, /AI summary \u00b7 sample/)
    assert.match(source, /not generated from a real call/)
    assert.match(source, /PhonePreviewRecording v-if="event.recording === 'ready'"/)
  }
  if (file.endsWith('Recording.vue')) {
    assert.doesNotMatch(source, /autoplay/)
    assert.match(source, /Sample audio \u00b7 not this call/)
    assert.match(source, /onBeforeUnmount/, 'player tears down when the person/thread changes')
  }
}
console.log('Phone preview: three designs, incoming safety, anchored chat geometry, unified conversation timeline, sample recording/summary provenance, history/text/chat isolation, settings fixtures, no-send guards and seven Vue SFCs passed.')
