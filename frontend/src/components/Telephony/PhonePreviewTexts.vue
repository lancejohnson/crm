<template>
  <div class="text-workspace" :class="{ split, 'has-thread': !!thread }" aria-label="Demo text messages">
    <div v-if="split || !thread" class="conversation-list">
      <form class="new-conversation" @submit.prevent="openPreviewText(p, p.newTextNumber)"><FormControl v-model="p.newTextNumber" aria-label="New text number" placeholder="New number…" /><Button type="submit" icon="plus" :disabled="!previewNumberKey(p.newTextNumber)" aria-label="Open new-number text" /></form>
      <button v-for="item in p.conversations" :key="item.id" type="button" class="conversation-row" :class="{ selected: p.textThread === item.id }" :aria-label="`Open texts with ${item.name}`" @click="openPreviewText(p, item.number, item.name)"><span class="initial">{{ item.name.slice(0, 1) }}</span><span class="conversation-summary"><b>{{ item.name }}</b><small>{{ item.number }}</small><span class="snippet">{{ item.draft ? `Draft: ${item.draft}` : item.messages.at(-1)?.text || 'Start a conversation' }}</span></span></button>
    </div>
    <div v-if="thread" class="thread-panel">
      <div class="thread-heading"><Button class="back-button" variant="ghost" icon="arrow-left" aria-label="All conversations" @click="p.textThread = null" /><div><b>{{ thread.name }}</b><small>{{ thread.number }}</small></div></div>
      <div ref="messages" class="text-thread" aria-label="Demo conversation: calls and texts">
        <p v-if="!events.length" class="empty-thread">No calls or texts yet. Start the conversation.</p>
        <template v-for="event in events" :key="event.id">
          <div v-if="event.kind === 'text'" class="message-row" :class="{ outbound: event.direction === 'out' }"><div class="message-bubble"><p>{{ event.text }}</p><small>{{ event.direction === 'out' ? 'You' : thread.name }} · {{ event.time }}</small></div></div>
          <article v-else class="call-event" :class="{ connected: event.duration }" :aria-label="`${event.direction} call · ${event.result}`">
            <div class="call-event-head"><FeatherIcon :name="event.direction === 'Inbound' ? 'phone-incoming' : 'phone-outgoing'" class="size-4" /><b>{{ event.direction }} call</b><span>{{ event.result }}<template v-if="event.duration"> · {{ event.duration }}</template></span></div>
            <small class="call-event-time">{{ event.time }}<template v-if="event.duration"> · {{ previewRecordingLabels[event.recording] }}</template></small>
            <details v-if="event.summary" class="call-summary"><summary><FeatherIcon name="align-left" class="size-3" /> AI summary · sample</summary><p>{{ event.summary }}</p><small>Sample text written for this mockup — not generated from a real call.</small></details>
            <PhonePreviewRecording v-if="event.recording === 'ready'" :key="`rec-${event.id}`" />
          </article>
        </template>
      </div>
      <form class="text-compose" @submit.prevent="sendPreviewText(p)"><FormControl v-model="thread.draft" type="textarea" :aria-label="`Message ${thread.name}`" placeholder="Write a message…" /><Button type="submit" icon="arrow-up" variant="solid" :disabled="!thread.draft.trim()" aria-label="Send demo text" /></form>
    </div>
    <div v-else-if="split" class="choose-thread"><span>Messages</span><p>Pick a conversation, or start with a number.</p></div>
  </div>
</template>
<script setup>
import { Button, FeatherIcon, FormControl } from 'frappe-ui'
import { computed, nextTick, ref, watch } from 'vue'
import { phonePreview as p } from '@/composables/phonePreview'
import PhonePreviewRecording from '@/components/Telephony/PhonePreviewRecording.vue'
import { openPreviewText, sendPreviewText, previewNumberKey, previewConversationEvents, previewRecordingLabels } from '@/utils/phonePreview'
defineProps({ split: Boolean })
const thread = computed(() => p.conversations.find(item => item.id === p.textThread))
// One timeline per person: prior calls and texts, oldest first. Derived, never stored twice.
const events = computed(() => thread.value ? previewConversationEvents(p, thread.value.number) : [])
const messages = ref(null)
watch(() => [p.textThread, events.value.length], async () => {
  await nextTick()
  if (messages.value) messages.value.scrollTop = messages.value.scrollHeight
}, { immediate: true })
</script>
<style scoped>
.text-workspace { color: var(--ink-gray-8, #333); }
.new-conversation { display: flex; gap: 6px; padding: 12px; align-items: center; }
.new-conversation > :first-child { min-width: 0; flex: 1; }
.conversation-row { display: flex; align-items: center; gap: 10px; padding: 14px 12px; width: 100%; text-align: left; border-top: 1px solid var(--outline-gray-1, #eee); }
.conversation-row:hover, .conversation-row.selected { background: var(--surface-gray-1, #f8f8f8); }
.conversation-row:focus-visible { outline: 2px solid var(--ink-gray-7, #555); outline-offset: -2px; }
.initial { display: grid; place-items: center; flex-shrink: 0; width: 30px; height: 30px; border-radius: 50%; font-size: 12px; background: var(--surface-gray-2, #eee); }
.conversation-summary { flex: 1; min-width: 0; }
.conversation-summary b, .thread-heading b { font-size: 13px; font-weight: 600; }
.conversation-summary small, .thread-heading small { display: block; margin-top: 3px; font-size: 10px; color: var(--ink-gray-5, #777); }
.snippet { display: block; margin-top: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: var(--ink-gray-5, #777); }
.thread-heading { display: flex; align-items: center; gap: 8px; border-bottom: 1px solid var(--outline-gray-1, #eee); padding: 10px 12px; }
.text-thread { max-height: 300px; overflow-y: auto; padding: 14px 12px 0; }
.call-event { margin: 0 0 14px; padding: 10px 12px; border: 1px solid var(--outline-gray-1, #eee); border-radius: 10px; background: var(--surface-white, #fff); }
.call-event.connected { border-left: 3px solid #388452; }
.call-event-head { display: flex; align-items: center; gap: 7px; font-size: 12px; color: var(--ink-gray-8, #333); }
.call-event-head b { font-weight: 600; }
.call-event-head span { margin-left: auto; color: var(--ink-gray-5, #777); font-variant-numeric: tabular-nums; }
.call-event-time { display: block; margin-top: 5px; font-size: 10px; color: var(--ink-gray-5, #777); }
.call-summary { margin-top: 9px; font-size: 12px; }
.call-summary summary { display: flex; align-items: center; gap: 5px; cursor: pointer; font-size: 11px; font-weight: 600; color: var(--ink-gray-7, #555); list-style: none; }
.call-summary summary::-webkit-details-marker { display: none; }
.call-summary p { margin-top: 7px; line-height: 1.55; color: var(--ink-gray-8, #333); }
.call-summary small { display: block; margin-top: 6px; font-size: 10px; color: var(--ink-gray-5, #777); }
.message-row { display: flex; margin-bottom: 14px; }
.message-row.outbound { justify-content: flex-end; }
.message-bubble { max-width: 90%; padding: 9px 11px; border-radius: 10px; background: var(--surface-gray-1, #f8f8f8); overflow-wrap: anywhere; }
.outbound .message-bubble { background: var(--surface-gray-2, #eee); }
.message-bubble p { white-space: pre-wrap; font-size: 13px; line-height: 1.5; }
.message-bubble small { display: block; margin-top: 5px; font-size: 10px; color: var(--ink-gray-5, #777); }
.text-compose { display: flex; align-items: flex-end; gap: 7px; padding: 10px 12px 14px; }
.text-compose > :first-child { flex: 1; min-width: 0; }
.empty-thread { padding: 30px 5px; color: var(--ink-gray-5, #777); font-size: 13px; }
.split { display: grid; grid-template-columns: 210px minmax(0, 1fr); }
.split .conversation-list { border-right: 1px solid var(--outline-gray-1, #eee); }
.split .conversation-row { gap: 7px; }
.split .initial { display: none; }
.split .back-button { display: none; }
.choose-thread { padding: 70px 20px; text-align: center; }
.choose-thread span { font-size: 18px; }
.choose-thread p { margin-top: 10px; color: var(--ink-gray-5, #777); font-size: 12px; line-height: 1.5; }
@media (max-width: 650px) { .split { display: block; } .split.has-thread .conversation-list, .choose-thread { display: none; } .split .back-button { display: inline-flex; } .split .conversation-list { border-right: 0; } }
</style>
