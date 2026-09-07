<template>
  <section ref="drawer" class="lead-drawer" :class="{ collapsed: !c.open }" :style="{ left: `${left}px`, bottom: `${bottom}px` }" aria-label="Team thread design preview">
    <header class="drawer-heading">
      <Button variant="ghost" :icon="c.open ? 'chevron-down' : 'chevron-up'" :aria-label="c.open ? 'Collapse team thread' : 'Expand team thread'" :aria-expanded="c.open" @click="c.open = !c.open" />
      <nav class="drawer-tabs" aria-label="Threads">
        <button type="button" :aria-pressed="c.thread === 'lead'" :class="{ selected: c.thread === 'lead' }" @click="pick('lead')"><FeatherIcon name="home" class="size-3.5" /> This lead<span class="tab-caption">{{ leadLabel }}</span></button>
        <button type="button" :aria-pressed="c.thread === 'standup'" :class="{ selected: c.thread === 'standup' }" @click="pick('standup')"><FeatherIcon name="sunrise" class="size-3.5" /> Standup <span class="pin" title="Pinned">📌</span></button>
        <button v-for="name in previewTeammates" :key="name" type="button" :aria-pressed="c.thread === name" :class="{ selected: c.thread === name }" @click="pick(name)"><span class="tab-avatar">{{ name.slice(0, 1) }}</span>{{ name }}<span v-if="dmUnread(name)" class="tab-badge">{{ dmUnread(name) }}</span></button>
      </nav>
      <span class="drawer-caption">Fictional thread · nothing is posted</span>
    </header>
    <div v-if="c.open" class="drawer-body">
      <template v-if="c.thread === 'lead'">
        <div ref="scroller" class="thread-scroll">
          <p class="thread-intro">Everything said about <b>{{ leadLabel }}</b>, next to the record. @mention a teammate to pull them in.</p>
          <div v-for="message in c.leadThread.messages" :key="message.sequence" class="thread-message" :class="{ mine: message.author === 'You' }"><span class="msg-avatar">{{ message.author.slice(0, 1) }}</span><div><b>{{ message.author }}</b> <small>{{ message.time }}</small><p v-html="highlight(message.text)" /></div></div>
        </div>
        <form class="thread-compose" @submit.prevent="postLeadThread(c)">
          <div class="compose-field">
            <ul v-if="mentions" class="mention-menu" role="listbox" aria-label="Mention a teammate"><li v-for="name in mentions" :key="name"><button type="button" role="option" @click="mention(name)"><span class="tab-avatar">{{ name.slice(0, 1) }}</span>{{ name }}</button></li></ul>
            <FormControl v-model="c.leadThread.draft" type="textarea" :rows="2" aria-label="Message the team about this lead" placeholder="Message the team about this lead… type @ to mention" @keydown.esc.stop="c.mentionOpen = false" />
          </div>
          <Button type="submit" icon="arrow-up" variant="solid" :disabled="!c.leadThread.draft.trim()" aria-label="Post to lead thread" />
        </form>
      </template>
      <div v-else-if="c.thread === 'standup'" class="standup-post">
        <div class="standup-head"><FeatherIcon name="sunrise" class="size-4" /><b>{{ c.standup.title }}</b><span class="pin">📌 pinned until 4pm</span></div>
        <ul><li v-for="line in c.standup.lines" :key="line">{{ line }}</li></ul>
        <Button variant="subtle" iconLeft="list" @click="router.push({ name: 'Today' })">Open Today board</Button>
      </div>
      <template v-else>
        <div ref="scroller" class="thread-scroll">
          <p class="thread-intro">Direct thread with <b>{{ c.thread }}</b> — the same conversation the phone bar opens from their status.</p>
          <div v-for="(message, i) in dm.messages" :key="i" class="thread-message" :class="{ mine: message.author === 'You' }"><span class="msg-avatar">{{ message.author.slice(0, 1) }}</span><div><b>{{ message.author }}</b> <small>{{ message.time }}</small><p>{{ message.text }}</p></div></div>
        </div>
        <form class="thread-compose" @submit.prevent="sendDm">
          <FormControl v-model="dm.draft" :aria-label="`Message ${c.thread}`" :placeholder="`Message ${c.thread}…`" />
          <Button type="submit" icon="arrow-up" variant="solid" :disabled="!dm.draft.trim()" aria-label="Send direct message" />
        </form>
      </template>
    </div>
  </section>
</template>
<script setup>
import { Button, FeatherIcon, FormControl } from 'frappe-ui'
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { commsPreview as c } from '@/composables/commsPreview'
import { phonePreview as p } from '@/composables/phonePreview'
import { postLeadThread, mentionQuery, mentionCandidates, insertMention } from '@/utils/commsPreview'
import { previewTeammates, sendPreviewChat } from '@/utils/phonePreview'
defineProps({ left: { type: Number, default: 0 }, bottom: { type: Number, default: 0 } })
const route = useRoute()
const router = useRouter()
const scroller = ref(null)
const leadLabel = computed(() => route.params.leadId || p.previewLead || 'no lead open')
// DMs ARE the phone's per-person chats: one draft, one message list per teammate.
const dm = computed(() => p.chats[c.thread] || { draft: '', messages: [] })
function dmUnread(name) { return p.chats[name]?.messages.filter(m => m.author !== 'You' && m.time === 'Example').length ? 1 : 0 }
function pick(thread) { c.thread = thread; c.open = true; c.mentionOpen = false }
function sendDm() { p.chatUser = c.thread; sendPreviewChat(p) }
const mentions = computed(() => {
  if (c.thread !== 'lead') return null
  const query = mentionQuery(c.leadThread.draft)
  if (query === null) return null
  const names = mentionCandidates(query)
  return names.length ? names : null
})
function mention(name) { c.leadThread.draft = insertMention(c.leadThread.draft, name) }
function highlight(text) {
  const safe = String(text).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]))
  return safe.replace(/@([\w-]+)/g, '<mark class="mention">@$1</mark>')
}
watch(() => [c.thread, c.leadThread.messages.length, dm.value.messages.length, c.open], async () => {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
}, { immediate: true })
</script>
<style scoped>
.lead-drawer { position: fixed; right: 0; z-index: 39; display: flex; flex-direction: column; background: var(--surface-white, #fff); border-top: 1px solid var(--outline-gray-2, #e2e2e2); box-shadow: 0 -4px 18px #0000000d; color: var(--ink-gray-9, #222); height: 300px; }
.lead-drawer.collapsed { height: 40px; }
.drawer-heading { display: flex; align-items: center; gap: 6px; padding: 3px 10px 3px 4px; border-bottom: 1px solid var(--outline-gray-1, #eee); min-height: 40px; }
.drawer-tabs { display: flex; gap: 2px; min-width: 0; overflow-x: auto; }
.drawer-tabs button { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; padding: 6px 10px; border-radius: 6px; font-size: 12px; color: var(--ink-gray-6, #666); }
.drawer-tabs button:hover { background: var(--surface-gray-1, #f5f5f5); }
.drawer-tabs button.selected { background: var(--surface-gray-2, #eee); color: var(--ink-gray-9, #222); font-weight: 600; }
.drawer-tabs button:focus-visible, .mention-menu button:focus-visible { outline: 2px solid var(--ink-gray-7, #555); outline-offset: -2px; }
.tab-caption { font-size: 10px; color: var(--ink-gray-5, #777); font-weight: 400; max-width: 160px; overflow: hidden; text-overflow: ellipsis; }
.tab-avatar { display: grid; place-items: center; width: 18px; height: 18px; border-radius: 50%; font-size: 10px; background: var(--surface-gray-2, #eee); }
.tab-badge { font-size: 9px; min-width: 15px; padding: 1px 4px; border-radius: 8px; background: #d9a536; color: #fff; text-align: center; }
.pin { font-size: 10px; color: var(--ink-gray-5, #777); }
.drawer-caption { margin-left: auto; font-size: 10px; color: var(--ink-gray-5, #777); white-space: nowrap; }
.drawer-body { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.thread-scroll { flex: 1; min-height: 0; overflow-y: auto; padding: 12px 18px 4px; }
.thread-intro { font-size: 11px; color: var(--ink-gray-5, #777); margin-bottom: 12px; }
.thread-message { display: flex; gap: 10px; margin-bottom: 12px; font-size: 13px; }
.thread-message b { font-weight: 600; }
.thread-message small { font-size: 10px; color: var(--ink-gray-5, #777); }
.thread-message p { margin-top: 2px; line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere; }
.msg-avatar { display: grid; place-items: center; width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0; font-size: 11px; font-weight: 600; background: var(--surface-gray-2, #eee); }
.mine .msg-avatar { background: #dfeee5; color: #1f6b41; }
:deep(mark.mention) { background: #eef3ff; color: #2d4f9e; border-radius: 3px; padding: 0 2px; font-weight: 600; }
.thread-compose { display: flex; align-items: flex-end; gap: 8px; padding: 8px 18px 12px; border-top: 1px solid var(--outline-gray-1, #eee); }
.compose-field { flex: 1; min-width: 0; position: relative; }
.mention-menu { position: absolute; bottom: calc(100% + 6px); left: 0; z-index: 2; min-width: 180px; padding: 4px; border: 1px solid var(--outline-gray-2, #ddd); border-radius: 8px; background: #fff; box-shadow: 0 6px 20px #0002; list-style: none; }
.mention-menu button { display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px 8px; border-radius: 5px; font-size: 12px; text-align: left; }
.mention-menu button:hover { background: var(--surface-gray-1, #f5f5f5); }
.standup-post { padding: 14px 18px; overflow-y: auto; }
.standup-head { display: flex; align-items: center; gap: 8px; font-size: 13px; margin-bottom: 8px; }
.standup-head b { font-weight: 600; }
.standup-post ul { list-style: disc; padding-left: 18px; font-size: 13px; line-height: 1.7; color: var(--ink-gray-8, #333); margin-bottom: 12px; }
@media (max-width: 639px) { .lead-drawer { left: 0 !important; height: 46dvh; } .drawer-caption, .tab-caption { display: none; } }
</style>
