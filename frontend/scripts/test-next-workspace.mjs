// Next workspace (real, not the mockup): pure helpers, SFC compile, and the
// safety rules that must hold before anything ships — no secrets or provider
// keys in the bundle, classic never imports a Talk/PhoneDock module, and the
// preview stays out of production. Run with node.
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { talkListFrom, talkIndex, nextTalk, nextUnreadTalk, matchTalk, talkPaletteSections, shortcutFor } from '../src/utils/talkShortcuts.js'
import { mentionQuery, mentionCandidates, insertMention } from '../src/utils/talkMentions.js'
import { normalizeNumber, formatPhone } from '../src/utils/phoneFormat.js'

const src = (file) => readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8')

// --- Shortcuts over a store-shaped conversation list --------------------------
{
  const list = talkListFrom([
    { kind: 'live', id: 'CRM-CALL-1', label: 'Exe · Jordan', group: 'Live' },
    { kind: 'standup', id: 'standup', label: 'Standup', group: 'Channels', unread: 1 },
    { kind: 'channel', id: 'acquisitions', label: '#acquisitions', group: 'Channels', unread: 2 },
    { kind: 'channel', id: 'dispo', label: '#dispo', group: 'Channels' },
    { kind: 'dm', id: 'dm-exe', label: 'Exe', group: 'Direct messages', unread: 0, user: 'exe@x.com' },
  ])
  assert.equal(list[3].unread, 0, 'missing unread defaults to 0')
  assert.equal(talkIndex(list, { kind: 'channel', id: 'acquisitions' }), 2, 'slug ids match route params')
  assert.equal(nextTalk(list, null, 1).id, 'CRM-CALL-1', 'Alt+↓ from nowhere = first')
  assert.equal(nextTalk(list, null, -1).id, 'dm-exe', 'Alt+↑ from nowhere = last')
  assert.equal(nextTalk(list, { kind: 'dm', id: 'dm-exe' }, 1).id, 'CRM-CALL-1', 'wraps')
  assert.equal(nextUnreadTalk(list, { kind: 'live', id: 'CRM-CALL-1' }, 1).id, 'standup')
  assert.equal(nextUnreadTalk(list, { kind: 'channel', id: 'acquisitions' }, 1).id, 'standup', 'skips self, wraps to earlier unread')
  assert.equal(nextUnreadTalk(list.map((i) => ({ ...i, unread: 0 })), null, 1), null, 'nothing unread → no move')
  assert.deepEqual(matchTalk(list, 'acq').map((i) => i.id), ['acquisitions'])
  assert.deepEqual(matchTalk(list, '', { scope: 'dm' }).map((i) => i.id), ['dm-exe'])
  assert.equal(talkPaletteSections(list, '', 'dm')[0].title, 'Direct messages')
  assert.equal(shortcutFor({ key: 'k', metaKey: true, shiftKey: true }), 'dm-switcher')
  assert.equal(shortcutFor({ key: 'ArrowDown', altKey: true }, { typing: true }), null, 'alt+arrows stay out of fields')
  assert.equal(shortcutFor({ key: 'Escape' }, { onTalkPage: true, typing: true, inComposer: true }), 'escape')
  assert.equal(shortcutFor({ key: 'Escape' }, { onTalkPage: true, typing: true, inComposer: false }), null)
}

// --- @mentions against real user rows --------------------------------------
{
  const users = [
    { name: 'dennis.szafran@groundworkpro.com', full_name: 'Dennis Szafran', first_name: 'Dennis' },
    { name: 'exe@groundworkpro.com', full_name: 'Exe Ortiz', first_name: 'Exe' },
  ]
  assert.equal(mentionQuery('hello @de'), 'de')
  assert.equal(mentionQuery('email me@x.com'), null, 'an @ inside a word is not a mention')
  assert.equal(mentionQuery('no mention'), null)
  assert.deepEqual(mentionCandidates(users, 'de').map((u) => u.first_name), ['Dennis'])
  assert.deepEqual(mentionCandidates(users, 'ex').map((u) => u.first_name), ['Exe'])
  assert.equal(mentionCandidates(users, '').length, 2)
  assert.equal(insertMention('hey @de', users[0]), 'hey @dennis.szafran ')
}

// --- Number normalisation the dialer/history key on --------------------------
{
  assert.equal(normalizeNumber('(202) 555-0123'), '+12025550123')
  assert.equal(normalizeNumber('1 202 555 0123'), '+12025550123')
  assert.equal(normalizeNumber('+12025550123'), '+12025550123')
  assert.equal(normalizeNumber('12345'), '', 'too short is not dialable')
  assert.equal(normalizeNumber(''), '')
  assert.equal(formatPhone('+12025550123'), '(202) 555-0123')
}

// --- SFCs compile; no secrets, no provider keys, no preview fixtures ----------
const real = [
  'stores/workspace.js', 'stores/talk.js', 'composables/phone.js',
  'components/Talk/NextWorkspaceShell.vue', 'components/Talk/TalkNav.vue', 'components/Talk/TalkKeys.vue',
  'components/Telephony/PhoneDock.vue', 'components/Telephony/PhoneDockCall.vue', 'components/Telephony/PhoneDockConversation.vue',
  'pages/Talk.vue', 'pages/PhoneDesk.vue', 'pages/PhoneSettings.vue', 'utils/talkMentions.js',
]
const SECRET = /(api[_-]?key|secret|token)\s*[:=]\s*['"][A-Za-z0-9_\-]{12,}['"]|KEY[A-Z0-9_]*\s*=\s*['"][A-Za-z0-9]{16,}|sk_live|Bearer\s+[A-Za-z0-9]{20,}/
for (const file of real) {
  const source = src(file)
  assert.doesNotMatch(source, SECRET, `${file}: looks like an embedded secret`)
  assert.doesNotMatch(source, /phonePreview\.js|commsPreview\.js|composables\/phonePreview|composables\/commsPreview/, `${file}: real code must not import mockup fixtures`)
  assert.doesNotMatch(source, /localStorage\.(get|set)Item\(['"](?!crm_next_banner_seen)/, `${file}: no local persistence beyond the banner flag`)
  if (file.endsWith('.vue')) {
    const { descriptor, errors } = parse(source, { filename: file })
    assert.deepEqual(errors, [], `${file} parse`)
    const script = compileScript(descriptor, { id: file })
    const template = compileTemplate({ source: descriptor.template.content, filename: file, id: file, compilerOptions: { bindingMetadata: script.bindings } })
    assert.deepEqual(template.errors, [], `${file} template`)
  }
}
// pages/Talk.vue is the one real file allowed to reach the preview, DEV-only.
assert.match(src('pages/Talk.vue'), /import\.meta\.env\.DEV && !workspace\.isNext[\s\S]*import\('@\/pages\/TalkPreview\.vue'\)/)

// --- Contract endpoints the frontend calls ---------------------------------
{
  const all = real.map(src).join('\n')
  for (const ep of ['crm.api.workspace.get', 'crm.api.workspace.set_version', 'crm.api.talk.list_channels', 'crm.api.talk.thread', 'crm.api.talk.post', 'crm.api.talk.mark_read', 'crm.api.talk.ensure_dm', 'crm.api.talk.presence', 'crm.api.telephony.active_calls', 'crm.api.telephony.dial', 'crm.api.telephony.join', 'crm.api.telephony.set_mode', 'crm.api.telephony.live_one', 'crm.api.telephony.history', 'crm.api.telephony.inbox', 'crm.api.telephony.send_text', 'crm.integrations.telnyx.api.webrtc_token', 'crm.integrations.api.get_recording_url']) {
    assert.ok(all.includes(ep), `frontend calls ${ep}`)
  }
  for (const ev of ['crm_talk', 'crm_talk_read', 'crm_presence', 'crm_telnyx_call', 'crm_incoming', 'crm_live_one', 'crm_transcript']) assert.ok(src('stores/talk.js').includes(`'${ev}'`), `listens for ${ev}`)
  assert.ok(src('components/Telephony/PhoneDock.vue').includes('.answer-call { background: #167645'), 'Answer is green')
}

// --- Classic stays byte-identical: nothing next is statically imported ------
{
  const app = src('App.vue')
  assert.match(app, /defineAsyncComponent\(\(\) => import\('@\/components\/Talk\/NextWorkspaceShell\.vue'\)\)/)
  assert.match(app, /<NextWorkspaceShell v-if="workspace\.isNext"/)
  assert.doesNotMatch(app, /^import .*(PhoneDock|TalkNav|TalkKeys)/m)
  const router = src('router.js')
  assert.match(router, /path: '\/talk\/:kind\/:id'[\s\S]*component: \(\) => import\('@\/pages\/Talk\.vue'\)/)
  assert.doesNotMatch(router, /import\('@\/pages\/TalkPreview\.vue'\)/, 'the preview page is reached only through pages/Talk.vue in DEV')
  const dropdown = src('components/UserDropdown.vue')
  assert.match(dropdown, /if \(workspace\.allowed\)/, 'menu item only for allowlisted users')
  assert.match(dropdown, /if \(import\.meta\.env\.DEV\)[\s\S]*import\('@\/composables\/workspaceSwitch'\)/, 'mockup toggle stays DEV-only')
  // Every real module is only reachable through dynamic imports from App/router.
  const walk = (dir) => readdirSync(dir).flatMap((f) => { const p = join(dir, f); return statSync(p).isDirectory() ? walk(p) : [p] })
  const root = new URL('../src/', import.meta.url).pathname
  const staticImporters = walk(root).filter((p) => /\.(vue|js)$/.test(p) && !real.some((r) => p.endsWith(r)) && !p.includes('/pages/Talk.vue') && !p.includes('/pages/PhoneSettings.vue'))
    .filter((p) => /^import .*(components\/Talk\/|PhoneDock|stores\/talk|composables\/phone')/m.test(readFileSync(p, 'utf8')))
  assert.deepEqual(staticImporters.map((p) => p.replace(root, '')), [], 'no classic module statically imports next-only code')
}

console.log('Next workspace: shortcuts over store lists, @mentions, E.164, 12 real modules compile, contract endpoints/events present, no secrets, classic imports nothing next-only.')
