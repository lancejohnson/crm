<template>
  <section ref="panel" class="teammate-chat" :style="position" role="dialog" :aria-label="`Chat with ${p.chatUser}`" @keydown.esc.stop="close">
    <header class="chat-heading"><Button icon="x" aria-label="Close teammate chat" @click="close" /><span class="chat-avatar">{{ p.chatUser?.slice(0, 1) }}</span><div><b>{{ p.chatUser }}</b><span class="chat-caption">Teammate chat · design preview</span></div></header>
    <div ref="messages" class="chat-messages"><div v-for="(message, i) in chat.messages" :key="i" class="chat-message" :class="{ mine: message.author === 'You' }"><p>{{ message.text }}</p><small>{{ message.author }} · {{ message.time }}</small></div></div>
    <form class="chat-compose" @submit.prevent="sendPreviewChat(p)"><FormControl v-model="chat.draft" :aria-label="`Message ${p.chatUser}`" placeholder="Write a message…" /><Button type="submit" icon="arrow-up" variant="solid" :disabled="!chat.draft.trim()" aria-label="Send demo chat message" /></form>
    <p class="chat-footnote">Fictional messages. Nothing is sent.</p>
  </section>
</template>
<script setup>
import { Button, FormControl } from 'frappe-ui'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { phonePreview as p } from '@/composables/phonePreview'
import { sendPreviewChat } from '@/utils/phonePreview'
import { previewChatPosition } from '@/utils/phonePreviewPosition'
const props = defineProps({ anchor: { type: Object, required: true } })
const emit = defineEmits(['close'])
const chat = computed(() => p.chats[p.chatUser])
const panel = ref(null)
const messages = ref(null)
const position = ref({ visibility: 'hidden' })
let observer
let frame
function measure() {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(() => {
    if (!props.anchor?.isConnected) { close(); return }
    position.value = previewChatPosition(props.anchor.getBoundingClientRect(), window.innerWidth, window.innerHeight)
  })
}
function close() { p.chatOpen = false; props.anchor?.focus({ preventScroll: true }); emit('close') }
watch(() => [props.anchor, p.chatUser], async () => {
  await nextTick(); observer?.disconnect()
  if (props.anchor) observer?.observe(props.anchor)
  measure()
  panel.value?.querySelector('input')?.focus({ preventScroll: true })
}, { flush: 'post' })
watch(() => [p.chatUser, chat.value.messages.length], async () => {
  await nextTick()
  if (messages.value) messages.value.scrollTop = messages.value.scrollHeight
}, { immediate: true })
onMounted(() => {
  observer = new ResizeObserver(measure)
  observer.observe(props.anchor)
  window.addEventListener('resize', measure)
  window.addEventListener('scroll', measure, true)
  measure()
  nextTick(() => panel.value?.querySelector('input')?.focus({ preventScroll: true }))
})
onBeforeUnmount(() => { observer?.disconnect(); cancelAnimationFrame(frame); window.removeEventListener('resize', measure); window.removeEventListener('scroll', measure, true) })
</script>
<style scoped>
.teammate-chat { position: fixed; z-index: 42; display: flex; flex-direction: column; background: var(--surface-white, white); border: 1px solid var(--outline-gray-2, #ddd); border-radius: 12px; box-shadow: 0 8px 32px #0002; overflow: hidden; color: var(--ink-gray-8, #333); }
.chat-heading { display: flex; align-items: center; gap: 9px; padding: 10px 12px; border-bottom: 1px solid var(--outline-gray-1, #eee); font-size: 13px; }
.chat-avatar { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 50%; background: var(--surface-gray-2, #eee); }
.chat-caption { display: block; margin-top: 2px; font-size: 10px; color: var(--ink-gray-5, #777); }
.chat-messages { min-height: 0; flex: 1; overflow-y: auto; padding: 12px; }
.chat-message { width: 90%; padding: 9px 11px; margin-bottom: 9px; border-radius: 9px; background: var(--surface-gray-1, #f8f8f8); font-size: 13px; line-height: 1.4; overflow-wrap: anywhere; white-space: pre-wrap; }
.chat-message.mine { margin-left: auto; background: var(--surface-gray-2, #eee); }
.chat-message small { display: block; margin-top: 5px; font-size: 10px; color: var(--ink-gray-5, #777); }
.chat-compose { display: flex; gap: 6px; padding: 0 12px; }
.chat-compose > :first-child { flex: 1; min-width: 0; }
.chat-footnote { padding: 7px 12px 10px; font-size: 10px; color: var(--ink-gray-5, #777); }
</style>
