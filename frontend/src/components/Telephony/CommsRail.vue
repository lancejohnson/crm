<template>
  <aside class="team-rail" :class="[`mode-${mode}`]" :style="{ bottom: `${bottom}px` }" aria-label="Team rail design preview">
    <template v-if="mode === 'strip'">
      <button type="button" class="strip-button" aria-label="Expand team rail" title="Expand team rail" @click="c.railCollapsed = false"><FeatherIcon name="chevrons-left" class="size-4" /></button>
      <button type="button" class="strip-button" :aria-label="`Channels · ${channelUnreadTotal(c)} unread`" :title="`Channels · ${channelUnreadTotal(c)} unread`" @click="show('channels')"><FeatherIcon name="hash" class="size-4" /><span v-if="channelUnreadTotal(c)" class="strip-badge">{{ channelUnreadTotal(c) }}</span></button>
      <button type="button" class="strip-button" aria-label="Direct messages" title="Direct messages" @click="show('dms')"><FeatherIcon name="message-square" class="size-4" /></button>
      <button type="button" class="strip-button live" :aria-label="`Live · ${liveCount} happening now`" :title="`Live · ${liveCount} happening now`" @click="show('live')"><FeatherIcon name="activity" class="size-4" /><span v-if="liveCount" class="strip-badge amber">{{ liveCount }}</span></button>
    </template>
    <template v-else>
      <header class="rail-heading">
        <b>Team</b>
        <span class="rail-caption">{{ mode === 'overlay' ? 'Floating · widen the window to dock it' : 'Docked' }}</span>
        <Button variant="ghost" icon="chevrons-right" aria-label="Collapse team rail" @click="c.railCollapsed = true" />
      </header>
      <nav class="rail-tabs" aria-label="Rail sections">
        <button v-for="section in sections" :key="section.id" type="button" :aria-pressed="c.railSection === section.id" :class="{ selected: c.railSection === section.id }" @click="c.railSection = section.id"><FeatherIcon :name="section.icon" class="size-3.5" />{{ section.label }}<span v-if="section.badge" class="tab-badge" :class="{ amber: section.id === 'live' }">{{ section.badge }}</span></button>
      </nav>

      <div v-if="c.railSection === 'live'" class="rail-scroll">
        <p class="rail-intro">What's happening right now. Join a call or jump to the record.</p>
        <article v-for="event in events" :key="event.id" class="event" :class="`ev-${event.kind}`">
          <span class="event-dot" aria-hidden="true" />
          <div class="event-body">
            <p>{{ event.text }}</p>
            <small>{{ event.time }}</small>
            <div class="event-actions">
              <Button v-if="event.call" size="sm" :variant="event.kind === 'live_one' ? 'solid' : 'subtle'" iconLeft="headphones" :disabled="!!p.call" :title="compsPath(event) ? 'Join listening · opens comps' : 'Join listening'" @click="join(event)">Join</Button>
              <Button v-if="event.lead || compsPath(event)" size="sm" variant="ghost" iconLeft="external-link" :disabled="!p.previewLead" @click="openLead">Open lead</Button>
            </div>
          </div>
        </article>
      </div>

      <template v-else-if="c.railSection === 'channels'">
        <ul class="rail-list" aria-label="Channels">
          <li v-for="(channel, name) in c.channels" :key="name"><button type="button" :aria-pressed="c.channel === name" :class="{ selected: c.channel === name, unread: channel.unread }" @click="openChannel(c, name)"><FeatherIcon name="hash" class="size-3.5" />{{ name.slice(1) }}<span v-if="channel.unread" class="tab-badge">{{ channel.unread }}</span></button></li>
        </ul>
        <div ref="scroller" class="rail-scroll thread">
          <div v-for="message in c.channels[c.channel].messages" :key="message.sequence" class="rail-message" :class="{ bot: message.author === 'Ops bot' }"><b>{{ message.author }}</b> <small>{{ message.time }}</small><p>{{ message.text }}</p></div>
        </div>
        <form class="rail-compose" @submit.prevent="postChannel(c)"><FormControl v-model="c.channels[c.channel].draft" :aria-label="`Message ${c.channel}`" :placeholder="`Message ${c.channel}`" /><Button type="submit" icon="arrow-up" variant="solid" :disabled="!c.channels[c.channel].draft.trim()" aria-label="Post to channel" /></form>
      </template>

      <template v-else>
        <ul class="rail-list" aria-label="Direct messages">
          <li v-for="name in previewTeammates" :key="name"><button type="button" :aria-pressed="c.dm === name" :class="{ selected: c.dm === name }" @click="c.dm = name"><span class="dm-avatar">{{ name.slice(0, 1) }}</span>{{ name }}<span class="dm-state" :class="{ busy: busy(name) }">{{ busy(name) ? 'On call' : 'Available' }}</span></button></li>
        </ul>
        <div ref="scroller" class="rail-scroll thread">
          <div v-for="(message, i) in dm.messages" :key="i" class="rail-message" :class="{ mine: message.author === 'You' }"><b>{{ message.author }}</b> <small>{{ message.time }}</small><p>{{ message.text }}</p></div>
        </div>
        <form class="rail-compose" @submit.prevent="sendDm"><FormControl v-model="dm.draft" :aria-label="`Message ${c.dm}`" :placeholder="`Message ${c.dm}`" /><Button type="submit" icon="arrow-up" variant="solid" :disabled="!dm.draft.trim()" aria-label="Send direct message" /></form>
      </template>
      <footer class="rail-foot">Design preview · fictional channels and events.</footer>
    </template>
  </aside>
</template>
<script setup>
import { Button, FeatherIcon, FormControl } from 'frappe-ui'
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { commsPreview as c } from '@/composables/commsPreview'
import { phonePreview as p } from '@/composables/phonePreview'
import { railMode, openChannel, postChannel, channelUnreadTotal } from '@/utils/commsPreview'
import { previewTeammates, previewCalls, previewTeamCall, previewJoinDestination, previewJoinOutcome, startPreviewCall, sendPreviewChat } from '@/utils/phonePreview'
const props = defineProps({ viewportWidth: { type: Number, required: true }, bottom: { type: Number, default: 0 } })
const route = useRoute()
const router = useRouter()
const scroller = ref(null)
const mode = computed(() => railMode(props.viewportWidth, c.railCollapsed))
const events = computed(() => [...c.events].filter(event => !event.call || !p.endedIds.includes(event.call.id)).sort((a, b) => b.sequence - a.sequence))
const liveCount = computed(() => events.value.filter(event => event.call).length)
const sections = computed(() => [
  { id: 'live', label: 'Live', icon: 'activity', badge: liveCount.value },
  { id: 'channels', label: 'Channels', icon: 'hash', badge: channelUnreadTotal(c) },
  { id: 'dms', label: 'DMs', icon: 'message-square', badge: 0 },
])
const dm = computed(() => p.chats[c.dm] || { draft: '', messages: [] })
function busy(name) { return previewCalls.some(call => call.rep === name && !p.endedIds.includes(call.id)) }
function show(section) { c.railCollapsed = false; c.railSection = section }
function compsPath(event) { return event.call ? previewJoinDestination(previewTeamCall(p, event.call)) : null }
function join(event) {
  const call = previewTeamCall(p, event.call)
  const destination = previewJoinOutcome(p, call, () => startPreviewCall(p, 'closer', event.call), route.path)
  if (destination) router.push(destination)
}
function openLead() { if (p.previewLead) router.push(`/leads/${encodeURIComponent(p.previewLead)}`) }
function sendDm() { p.chatUser = c.dm; sendPreviewChat(p) }
watch(() => [c.railSection, c.channel, c.dm, dm.value.messages.length, c.channels[c.channel]?.messages.length], async () => {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
}, { immediate: true })
</script>
<style scoped>
.team-rail { position: fixed; top: 0; right: 0; z-index: 39; display: flex; flex-direction: column; background: var(--surface-white, #fff); border-left: 1px solid var(--outline-gray-2, #e2e2e2); color: var(--ink-gray-9, #222); width: 320px; max-width: 100vw; }
.mode-overlay { box-shadow: -8px 0 24px #0001; z-index: 41; }
.mode-strip { width: 44px; align-items: center; padding-top: 8px; gap: 4px; }
.strip-button { position: relative; display: grid; place-items: center; width: 34px; height: 34px; border-radius: 8px; color: var(--ink-gray-6, #666); }
.strip-button:hover { background: var(--surface-gray-1, #f5f5f5); }
.strip-button.live { color: #8a6414; }
.strip-badge { position: absolute; top: 2px; right: 2px; min-width: 14px; height: 14px; padding: 0 3px; border-radius: 7px; background: var(--surface-gray-7, #333); color: #fff; font-size: 9px; line-height: 14px; text-align: center; }
.strip-badge.amber, .tab-badge.amber { background: #d9a536; }
.rail-heading { display: flex; align-items: center; gap: 8px; padding: 8px 6px 8px 14px; border-bottom: 1px solid var(--outline-gray-1, #eee); font-size: 14px; }
.rail-heading b { font-weight: 600; }
.rail-caption { flex: 1; font-size: 10px; color: var(--ink-gray-5, #777); }
.rail-tabs { display: flex; gap: 2px; padding: 6px 8px; border-bottom: 1px solid var(--outline-gray-1, #eee); }
.rail-tabs button { display: inline-flex; align-items: center; gap: 5px; padding: 6px 9px; border-radius: 6px; font-size: 12px; color: var(--ink-gray-6, #666); }
.rail-tabs button:hover, .rail-list button:hover { background: var(--surface-gray-1, #f5f5f5); }
.rail-tabs button.selected { background: var(--surface-gray-2, #eee); color: var(--ink-gray-9, #222); font-weight: 600; }
.rail-tabs button:focus-visible, .rail-list button:focus-visible, .strip-button:focus-visible { outline: 2px solid var(--ink-gray-7, #555); outline-offset: -2px; }
.tab-badge { min-width: 15px; padding: 1px 4px; border-radius: 8px; background: var(--surface-gray-7, #333); color: #fff; font-size: 9px; text-align: center; }
.rail-scroll { flex: 1; min-height: 0; overflow-y: auto; padding: 10px 14px; }
.rail-intro { font-size: 11px; color: var(--ink-gray-5, #777); margin-bottom: 10px; }
.event { display: flex; gap: 10px; padding: 9px 0; border-bottom: 1px solid var(--outline-gray-1, #eee); font-size: 12px; }
.event-dot { width: 8px; height: 8px; margin-top: 5px; border-radius: 50%; flex-shrink: 0; background: var(--surface-gray-4, #ccc); }
.ev-live_one .event-dot { background: #d9a536; box-shadow: 0 0 0 3px #d9a53633; }
.ev-call .event-dot { background: #388452; }
.ev-offer .event-dot { background: #2d4f9e; }
.event-body { flex: 1; min-width: 0; }
.event-body p { line-height: 1.45; }
.event-body small { display: block; margin-top: 2px; font-size: 10px; color: var(--ink-gray-5, #777); }
.event-actions { display: flex; gap: 6px; margin-top: 6px; flex-wrap: wrap; }
.rail-list { list-style: none; padding: 6px 8px 0; border-bottom: 1px solid var(--outline-gray-1, #eee); }
.rail-list button { display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px 8px; border-radius: 6px; font-size: 13px; text-align: left; color: var(--ink-gray-7, #555); }
.rail-list button.unread { font-weight: 600; color: var(--ink-gray-9, #222); }
.rail-list button.selected { background: var(--surface-gray-2, #eee); color: var(--ink-gray-9, #222); }
.rail-list .tab-badge, .dm-state { margin-left: auto; }
.dm-avatar { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; font-size: 10px; font-weight: 600; background: var(--surface-gray-2, #eee); }
.dm-state { font-size: 10px; color: #388452; }
.dm-state.busy { color: #bc8e37; }
.thread { padding-top: 12px; }
.rail-message { margin-bottom: 12px; font-size: 13px; }
.rail-message b { font-weight: 600; }
.rail-message small { font-size: 10px; color: var(--ink-gray-5, #777); }
.rail-message p { margin-top: 2px; line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere; }
.rail-message.bot b { color: #2d4f9e; }
.rail-message.mine b { color: #1f6b41; }
.rail-compose { display: flex; gap: 6px; padding: 8px 12px; border-top: 1px solid var(--outline-gray-1, #eee); }
.rail-compose > :first-child { flex: 1; min-width: 0; }
.rail-foot { padding: 7px 14px; font-size: 10px; color: var(--ink-gray-5, #777); border-top: 1px solid var(--outline-gray-1, #eee); }
</style>
