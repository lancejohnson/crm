<template>
  <template v-if="p.enabled">
    <PhonePreviewChat v-if="p.chatOpen && chatAnchor" :anchor="chatAnchor" />
    <aside v-if="phoneOpen" ref="rail" class="phone-surface" :class="[`design-${p.design}`, { interruption: !!p.incoming || !!p.alert }]" :style="{ bottom: `${barHeight + commsBottom + 10}px`, right: `${36 + commsRight}px`, maxHeight: `min(70dvh, calc(100dvh - ${barHeight + commsBottom + 24}px))` }" aria-label="Phone design preview">
      <header class="phone-heading"><Button icon="minus" variant="ghost" aria-label="Minimize all phone panels" @click="p.panelsMinimized = true" /><span class="phone-title">{{ p.design === 'B' ? 'Conversations' : p.design === 'C' ? 'Your line' : 'Phone' }}</span><span class="quiet-dot" /><Button icon="sliders" variant="ghost" aria-label="Preview controls" :aria-expanded="p.settingsOpen" @click="p.settingsOpen = !p.settingsOpen" /></header>

      <section v-if="p.incoming" class="incoming-call" aria-label="Incoming demo call">
        <div class="incoming-symbol"><FeatherIcon name="phone-incoming" class="size-6" /></div><p class="eyebrow">Incoming · {{ p.incoming.line }} line</p><h2>{{ p.incoming.name }}</h2><p class="caller-number">{{ p.incoming.number }}</p><p class="caller-context">{{ p.incoming.context }}</p><p class="caller-context">Fictional caller, not the real lead behind this panel.</p>
        <div class="incoming-actions"><button type="button" class="decline-call" @click="declinePreviewIncoming(p)"><FeatherIcon name="phone-off" class="size-4" />Decline</button><button type="button" class="answer-call" :disabled="!!p.call" @click="answerPreviewIncoming(p)"><FeatherIcon name="phone" class="size-4" />Answer</button></div>
        <p v-if="p.call" class="call-warning">You are already on a call with {{ p.call.name }}. Decline this incoming call to return; your call will not be replaced.</p>
        <p v-if="p.alert" class="pending-caption">A live-one invitation is also waiting.</p>
      </section>
      <section v-else-if="p.alert" class="live-invitation" aria-label="Live-one invitation">
        <span class="invitation-label"><FeatherIcon name="zap" class="size-4" /> Got a live one</span><h2>{{ p.alert.call.rep }} needs you</h2><p class="invitation-lead">{{ p.alert.call.name }} <span>· {{ p.alert.call.elapsed }}</span></p><blockquote>“{{ p.alert.note }}”</blockquote>
        <Button iconLeft="headphones" class="w-full" variant="solid" :disabled="!!p.call" @click="join(p.alert.call, () => joinPreviewAlert(p))">Join listening</Button><p class="pending-caption">{{ previewJoinDestination(p.alert.call) ? 'Joining opens this lead’s comps map so you can price while you listen.' : 'No CRM lead on this call — you stay where you are.' }}</p><p v-if="p.call" class="call-warning">Finish your current call first. This invite will stay here.</p>
        <div class="invitation-actions"><Button variant="ghost" @click="p.alert = null">Mark handled</Button><Button variant="ghost" @click="endPreviewTeamCall(p, p.alert.call.id)">Preview call ending</Button></div>
      </section>
      <section v-else-if="p.settingsOpen" class="preview-controls" aria-label="Preview scenarios">
        <p class="eyebrow">Try a moment</p><Button iconLeft="phone-incoming" @click="triggerPreviewIncoming(p)">Incoming · Jordan Ellis</Button><Button iconLeft="phone-incoming" @click="triggerPreviewIncoming(p, true)">Incoming · unknown number</Button><Button iconLeft="zap" @click="p.settingsOpen = false; triggerPreviewAlert(p, p.previewLead)">Receive a live-one alert</Button><Button iconLeft="phone" :disabled="!!p.call" @click="p.settingsOpen = false; startPreviewCall(p, 'rep')">Rep on a call · invite Dennis</Button>
        <Button iconLeft="settings" @click="p.settingsOpen = false; p.panelsMinimized = true; router.push({ name: 'Phone Settings Preview' })">Phone settings · numbers & recording</Button><details class="notification-options"><summary>Away notifications</summary><label><input v-model="p.sound" type="checkbox"> Sound</label><label><input v-model="p.browserNotice" type="checkbox"> Browser notification</label><p>Preferences only. No sound, permission prompt or notification.</p></details>
      </section>
      <template v-else>
        <div v-if="p.call && p.tab !== 'Dial'" class="active-strip"><button type="button" @click="p.tab = 'Dial'"><span class="quiet-dot" /> {{ p.call.name }} · {{ p.call.elapsed }} <span>Return to call →</span></button></div>
        <div class="phone-layout">
          <nav v-if="p.design === 'C'" class="icon-nav" aria-label="Phone sections"><button v-for="tab in sections" :key="tab.name" type="button" :aria-label="tab.name" :title="tab.name" :aria-pressed="p.tab === tab.name" :class="{ selected: p.tab === tab.name }" @click="p.tab = tab.name"><FeatherIcon :name="tab.icon" class="size-4" /><span>{{ tab.name }}</span></button></nav>
          <div class="phone-main">
            <nav v-if="p.design !== 'C'" class="section-nav" aria-label="Phone sections"><button type="button" :class="{ selected: p.tab !== 'Texts' }" :aria-pressed="p.tab !== 'Texts'" @click="p.tab = p.call ? 'Dial' : 'History'">{{ p.design === 'A' ? 'Recent calls' : 'Calls' }}</button><button type="button" :class="{ selected: p.tab === 'Texts' }" :aria-pressed="p.tab === 'Texts'" @click="p.tab = 'Texts'">{{ p.design === 'A' ? 'Conversations' : 'Messages' }}</button></nav>
            <PhonePreviewCall v-if="p.call && p.tab === 'Dial'" />
            <PhonePreviewTexts v-else-if="p.tab === 'Texts'" :split="p.design === 'B'" />
            <section v-else-if="p.design === 'C' && p.tab === 'Dial'" class="slim-dial"><p class="eyebrow">Acquisitions line</p><h2>Who’s next?</h2><FormControl v-model="p.number" aria-label="Number to dial" placeholder="Name or number" /><div class="dial-keypad"><button v-for="key in '123456789*0#'" :key="key" type="button" @click="p.number += key">{{ key }}</button></div><Button class="w-full" variant="solid" iconLeft="phone" :disabled="!previewNumberKey(p.number)" @click="dial">Call</Button></section>
            <section v-else class="call-history" aria-label="Call history">
              <p v-if="p.call" class="call-warning">Callbacks available after your current call. Texts still work.</p>
              <article v-for="item in p.history" :key="item.id" class="history-row"><button type="button" class="history-person" :aria-label="`Open conversation with ${item.name}`" @click="openPreviewText(p, item.number, item.name)"><FeatherIcon :name="item.direction === 'Inbound' ? 'arrow-down-left' : 'arrow-up-right'" class="history-direction size-4" /><span class="history-content"><span class="history-title"><b>{{ item.name }}</b><span>{{ item.duration }}</span></span><span class="history-number">{{ item.number }}</span><small>{{ item.direction }} · {{ item.result }}</small><small>{{ item.time }}</small><small class="recording-status" :class="{ ready: item.recording === 'ready' }">{{ previewRecordingLabels[item.recording] }}</small></span></button><div class="history-actions"><Button icon="phone" variant="ghost" :disabled="!!p.call || !!p.incoming" :aria-label="`Call back ${item.name}`" title="Call back" @click="callbackPreview(p, item)" /><Button icon="message-circle" variant="ghost" :aria-label="`Text ${item.name}`" title="Text" @click="openPreviewText(p, item.number, item.name)" /></div></article>
            </section>
            <form v-if="p.design !== 'C' && !p.call && p.tab !== 'Texts'" class="inline-dial" @submit.prevent="dial"><FormControl v-model="p.number" aria-label="Number to dial" placeholder="Dial a number…" /><Button type="submit" icon="phone" variant="solid" :disabled="!previewNumberKey(p.number)" aria-label="Dial demo number" /></form>
          </div>
        </div>
      </template>
      <p v-if="p.notice" class="phone-notice" role="status">{{ p.notice }}</p><footer class="preview-disclaimer">Design preview · fictional calls & messages. CRM behind is real.</footer>
    </aside>

    <footer ref="bar" class="preview-bar" aria-label="Demo team status and phone dock">
      <div class="team-strip"><span class="demo-label">TEAM</span><div v-for="call in previewCalls" :key="call.id" class="team-person"><button type="button" class="status-chat" :aria-label="`Chat with ${call.rep}`" :title="`Chat with ${call.rep}`" @click="chat(call.rep, $event)"><span class="status-dot" :class="{ available: p.endedIds.includes(call.id) }" /><span><b>{{ call.rep }}</b><span class="team-context">{{ p.endedIds.includes(call.id) ? 'Available' : call.name }}</span></span></button><Button v-if="!p.endedIds.includes(call.id)" icon="headphones" variant="ghost" :aria-label="`Join ${call.rep}'s demo call listening${previewJoinDestination(previewTeamCall(p, call)) ? ' and open the lead’s comps' : ''}`" :title="previewJoinDestination(previewTeamCall(p, call)) ? 'Join listening · opens comps' : 'Join listening'" @click="join(previewTeamCall(p, call), () => startPreviewCall(p, 'closer', call))" /></div><div class="team-person"><button type="button" class="status-chat" aria-label="Chat with Dennis" title="Chat with Dennis" @click="chat('Dennis', $event)"><span class="status-dot available" /><span><b>Dennis</b><span class="team-context">{{ p.call && (p.role === 'closer' || p.joined) ? 'On call' : 'Available' }}</span></span></button></div></div>
      <div class="dock-strip"><label class="sr-only" for="comms-design">Comms design</label><select id="comms-design" class="design-selector" :value="comms.design || ''" @change="chooseComms($event.target.value)"><option value="">Comms · off</option><option v-for="(name, key) in commsDesigns" :key="key" :value="key">{{ key }} · {{ name }}</option></select><label class="sr-only" for="phone-design">Phone design</label><select id="phone-design" class="design-selector" :value="p.design" @change="chooseDesign($event.target.value)"><option v-for="(name, key) in phoneDesigns" :key="key" :value="key">{{ key }} · {{ name }}</option></select><Button icon="sliders" variant="ghost" aria-label="Preview controls" @click="p.settingsOpen = true; p.minimized = false; p.panelsMinimized = false" /><Button class="dock-button" :variant="p.call || p.incoming || p.alert ? 'solid' : 'subtle'" iconLeft="phone" :aria-expanded="phoneOpen" @click="togglePhone">{{ p.incoming ? 'Incoming call' : p.alert ? 'Live one' : p.call ? `${p.call.name} · ${p.mode === 'Listen' && p.role === 'rep' ? 'On call' : p.mode}` : 'Phone' }}</Button><Button icon="x" variant="ghost" aria-label="Exit phone preview" title="Exit preview" @click="exit" /></div>
    </footer>
  </template>
</template>
<script setup>
import { Button, FeatherIcon, FormControl } from 'frappe-ui'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { phonePreview as p } from '@/composables/phonePreview'
import PhonePreviewTexts from '@/components/Telephony/PhonePreviewTexts.vue'
import PhonePreviewCall from '@/components/Telephony/PhonePreviewCall.vue'
import PhonePreviewChat from '@/components/Telephony/PhonePreviewChat.vue'
import { previewRecordingLabels, previewCalls, phoneDesigns, selectPhoneDesign, newPhonePreview, startPreviewCall, triggerPreviewAlert, joinPreviewAlert, endPreviewTeamCall, openPreviewChat, callbackPreview, openPreviewText, previewNumberKey, triggerPreviewIncoming, answerPreviewIncoming, declinePreviewIncoming, previewJoinDestination, previewJoinOutcome, previewTeamCall } from '@/utils/phonePreview'
import { commsPreview as comms } from '@/composables/commsPreview'
import { commsDesigns, selectCommsDesign, railReservedWidth } from '@/utils/commsPreview'
const emit = defineEmits(['reserve'])
const route = useRoute()
const router = useRouter()
const bar = ref(null)
const rail = ref(null)
const chatAnchor = shallowRef(null)
const barHeight = ref(66)
const viewportWidth = ref(window.innerWidth)
// Keep the floating phone clear of whatever the comms mockup reserves: the B
// drawer above the bar, or the docked/collapsed C rail on the right. D's
// conversations are pages in the main area, so it reserves nothing on the right.
const commsBottom = computed(() => comms.design === 'B' ? (comms.open ? 300 : 40) : 0)
const commsRight = computed(() => comms.design === 'C' ? railReservedWidth(viewportWidth.value, comms.railCollapsed) : 0)
const sections = [{ name: 'Dial', icon: 'grid' }, { name: 'History', icon: 'clock' }, { name: 'Texts', icon: 'message-circle' }]
const phoneOpen = computed(() => !p.panelsMinimized && (!p.minimized || !!p.incoming || !!p.alert || p.settingsOpen))
watch(() => route.query.phonePreview, value => { if (value === '1') p.enabled = true }, { immediate: true })
// The lead the preview last saw stands in for "the lead this call is linked to".
watch(() => route.params.leadId, value => { if (value) p.previewLead = String(value) }, { immediate: true })
watch(() => route.query.phoneDesign, value => { if (value && value !== p.design) selectPhoneDesign(p, value) }, { immediate: true })
watch(() => route.query.phoneIncoming, value => { if (value === '1' && p.enabled) triggerPreviewIncoming(p) }, { immediate: true })
let observer
let frame
function measure() {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(() => {
    if (!p.enabled) { emit('reserve', { bottom: 0 }); return }
    barHeight.value = Math.ceil(bar.value?.getBoundingClientRect().height || 66)
    viewportWidth.value = window.innerWidth
    emit('reserve', { bottom: barHeight.value })
  })
}
watch([() => p.enabled, phoneOpen], async () => { await nextTick(); observer?.disconnect(); if (bar.value) observer?.observe(bar.value); if (rail.value) observer?.observe(rail.value); measure() })
onMounted(() => { observer = new ResizeObserver(measure); if (bar.value) observer.observe(bar.value); if (rail.value) observer.observe(rail.value); window.addEventListener('resize', measure); measure() })
onBeforeUnmount(() => { observer?.disconnect(); cancelAnimationFrame(frame); window.removeEventListener('resize', measure); emit('reserve', { bottom: 0 }) })
function chat(name, event) { chatAnchor.value = event.currentTarget; openPreviewChat(p, name) }
// Accepting a join lands the closer on the lead's comps map. Only after the join
// actually succeeded (an active call blocks it), and only when there is a lead.
function join(call, start) {
  const destination = previewJoinOutcome(p, call, start, route.path)
  if (destination) router.push(destination)
}
function chooseComms(design) { selectCommsDesign(comms, design); const query = { ...route.query }; if (design) query.commsDesign = design; else delete query.commsDesign; router.replace({ query }) }
function chooseDesign(design) { selectPhoneDesign(p, design); router.replace({ query: { ...route.query, phoneDesign: design } }) }
function togglePhone() {
  const wasOpen = phoneOpen.value
  p.minimized = false
  p.panelsMinimized = wasOpen
}
function dial() { callbackPreview(p, { name: 'Unlinked number', number: p.number.trim() }) }
function exit() { Object.assign(p, newPhonePreview()); selectCommsDesign(comms, null); chatAnchor.value = null; emit('reserve', { bottom: 0 }) }
</script>
<style scoped>
.preview-bar { position: fixed; z-index: 40; bottom: 0; left: 0; right: 0; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 16px; background: var(--surface-white, white); border-top: 1px solid var(--outline-gray-2, #dedede); box-shadow: 0 -3px 14px #00000006; }
.team-strip, .dock-strip { display: flex; align-items: center; gap: 8px; min-width: 0; }
.team-strip { overflow-x: auto; }.dock-strip { flex-shrink: 0; }
.demo-label { font-size: 10px; letter-spacing: .08em; color: var(--ink-gray-5, #777); }
.team-person { display: flex; align-items: center; gap: 2px; font-size: 12px; color: var(--ink-gray-8, #333); white-space: nowrap; padding-right: 8px; }
.status-chat { display: flex; align-items: center; gap: 7px; text-align: left; border-radius: 5px; padding: 4px; }.status-chat:hover { background: var(--surface-gray-1, #f5f5f5); }
.status-chat:focus-visible, .section-nav button:focus-visible, .icon-nav button:focus-visible { outline: 2px solid var(--ink-gray-7, #555); outline-offset: -2px; }
.team-context { display: block; margin-top: 3px; font-size: 10px; color: var(--ink-gray-5, #777); }
.status-dot, .quiet-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; display: inline-block; background: #bc8e37; }.available, .quiet-dot { background: #388452; }
.dock-button { max-width: 200px; }.design-selector { max-width: 150px; font-size: 11px; padding: 5px; border: 0; background: transparent; color: var(--ink-gray-5, #777); }
.phone-surface { position: fixed; z-index: 40; right: 36px; width: 328px; display: flex; flex-direction: column; overflow-y: auto; background: var(--surface-white, white); border: 1px solid var(--outline-gray-2, #ddd); border-radius: 12px; box-shadow: 0 10px 40px #0002; color: var(--ink-gray-8, #333); }
.phone-heading { position: sticky; top: 0; z-index: 2; display: flex; align-items: center; gap: 7px; padding: 9px 10px; border-bottom: 1px solid var(--outline-gray-1, #eee); background: var(--surface-white, white); }
.phone-title { font-size: 14px; font-weight: 600; flex: 1; }.phone-heading .quiet-dot { margin-right: 4px; }
.section-nav { display: flex; gap: 22px; padding: 0 16px; border-bottom: 1px solid var(--outline-gray-1, #eee); }.section-nav button { padding: 12px 0 10px; font-size: 12px; color: var(--ink-gray-5, #777); border-bottom: 2px solid transparent; }.section-nav button.selected { border-bottom-color: var(--ink-gray-8, #333); color: var(--ink-gray-9, #222); font-weight: 600; }
.phone-main { min-width: 0; flex: 1; }.phone-layout { display: flex; }
.history-row { display: flex; gap: 9px; padding: 14px 14px; border-bottom: 1px solid var(--outline-gray-1, #eee); }.history-direction { flex-shrink: 0; margin-top: 2px; color: var(--ink-gray-5, #777); }.history-content { flex: 1; min-width: 0; }.history-title { display: flex; gap: 8px; align-items: center; justify-content: space-between; }.history-title b { font-weight: 550; font-size: 13px; }.history-title span { font-size: 10px; color: var(--ink-gray-5, #777); font-variant-numeric: tabular-nums; }.history-number { display: block; margin-top: 3px; font-size: 11px; color: var(--ink-gray-5, #777); }.history-content small { display: block; margin-top: 4px; font-size: 10px; color: var(--ink-gray-5, #777); }.history-actions { display: flex; flex-direction: column; gap: 1px; }
.history-person { display: flex; gap: 9px; min-width: 0; flex: 1; text-align: left; border-radius: 5px; }
.history-person:hover { background: var(--surface-gray-1, #fafafa); }
.history-person:focus-visible { outline: 2px solid var(--ink-gray-7, #555); outline-offset: 3px; }
.history-content .recording-status.ready { color: #167645; }
.incoming-actions button { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 11px 12px; border-radius: 8px; font-size: 13px; font-weight: 600; }
.incoming-actions .answer-call { background: #167645; color: #fff; border: 1px solid #12613a; }
.incoming-actions .answer-call:hover:not(:disabled) { background: #12613a; }
.incoming-actions .answer-call:disabled { opacity: .45; cursor: not-allowed; }
.incoming-actions .decline-call { background: #fff1f0; color: #a32e2e; border: 1px solid #e9c4c1; }
.incoming-actions button:focus-visible { outline: 2px solid var(--ink-gray-8, #333); outline-offset: 3px; }
.inline-dial { display: flex; gap: 8px; padding: 14px; background: var(--surface-gray-1, #fafafa); }.inline-dial > :first-child { min-width: 0; flex: 1; }
.preview-disclaimer { padding: 9px 14px; border-top: 1px solid var(--outline-gray-1, #eee); color: var(--ink-gray-5, #777); font-size: 10px; line-height: 1.5; }.phone-notice { margin: 0; padding: 10px 14px; font-size: 11px; line-height: 1.5; color: var(--ink-gray-6, #666); }
.design-B { width: 620px; border-radius: 12px 12px 5px 5px; }.design-B .phone-heading { padding: 10px 14px; }.design-B .section-nav { background: var(--surface-gray-1, #fafafa); }.design-B .history-actions { flex-direction: row; align-items: center; }.design-B .history-row { padding-inline: 20px; }
.design-C { width: 336px; border-radius: 9px; }.icon-nav { display: flex; flex-direction: column; gap: 8px; width: 52px; flex-shrink: 0; padding: 12px 4px; border-right: 1px solid var(--outline-gray-1, #eee); background: var(--surface-gray-1, #fafafa); }.icon-nav button { display: flex; flex-direction: column; align-items: center; gap: 5px; padding: 10px 2px; color: var(--ink-gray-5, #777); border-radius: 6px; }.icon-nav span { font-size: 9px; }.icon-nav .selected { color: var(--ink-gray-9, #222); background: var(--surface-gray-3, #eee); }.design-C .history-direction { display: none; }.design-C .history-row { padding: 12px 9px; gap: 4px; }
.slim-dial { padding: 20px 16px; }.slim-dial h2 { font-size: 21px; font-weight: 550; margin: 6px 0 20px; letter-spacing: -.5px; }.dial-keypad { display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; margin: 16px 0; }.dial-keypad button { padding: 8px; border-radius: 6px; font-size: 17px; }.dial-keypad button:hover { background: var(--surface-gray-1, #fafafa); }
.active-strip { border-bottom: 1px solid var(--outline-gray-1, #eee); padding: 9px 14px; font-size: 11px; }.active-strip button { width: 100%; text-align: left; }.active-strip span:last-child { float: right; }
.interruption { width: 344px; }.incoming-call { padding: 24px 20px 20px; text-align: center; }.incoming-symbol { width: 48px; height: 48px; border-radius: 50%; display: grid; place-items: center; margin: 0 auto 16px; background: var(--surface-gray-1, #f7f7f7); color: #388452; }.eyebrow { font-size: 10px; letter-spacing: .08em; text-transform: uppercase; color: var(--ink-gray-5, #777); }.incoming-call h2 { font-size: 25px; font-weight: 600; letter-spacing: -.6px; margin: 12px 0 6px; }.caller-number { font-size: 14px; }.caller-context { margin-top: 10px; font-size: 11px; line-height: 1.5; color: var(--ink-gray-5, #777); }.incoming-actions { display: flex; gap: 10px; margin-top: 22px; }.incoming-actions > * { flex: 1; }
.live-invitation { padding: 18px; }.invitation-label { display: flex; gap: 7px; align-items: center; color: #9b772e; font-size: 12px; }.live-invitation h2 { margin-top: 18px; font-size: 22px; font-weight: 550; letter-spacing: -.5px; }.invitation-lead { margin-top: 7px; font-size: 13px; }.invitation-lead span { color: var(--ink-gray-5, #777); }.live-invitation blockquote { padding: 14px 0 20px; font-size: 14px; line-height: 1.6; color: var(--ink-gray-6, #666); }.invitation-actions { display: flex; justify-content: space-between; gap: 4px; margin-top: 10px; }.pending-caption, .call-warning { padding: 10px 14px; font-size: 11px; line-height: 1.5; color: var(--ink-gray-5, #777); }
.preview-controls { display: grid; gap: 8px; padding: 16px; }.preview-controls .eyebrow { margin-bottom: 5px; }.notification-options { margin-top: 10px; font-size: 12px; }.notification-options summary { cursor: pointer; }.notification-options label { display: flex; gap: 7px; align-items: center; margin-top: 12px; }.notification-options p { margin-top: 10px; font-size: 10px; line-height: 1.5; color: var(--ink-gray-5, #777); }
@media (max-width: 999px) { .preview-bar { flex-direction: column; align-items: stretch; padding: 8px 12px; gap: 7px; }.dock-strip { justify-content: flex-end; flex-wrap: wrap; }.phone-surface { max-width: calc(100vw - 48px); right: 36px; max-height: 62dvh !important; }.dock-button { max-width: 160px; }.design-selector { max-width: 145px; } }
@media (max-width: 420px) { .dock-strip { gap: 3px; }.team-person { padding-right: 4px; }.dock-button { max-width: 125px; overflow: hidden; }.design-selector { max-width: 130px; } }
</style>
