<template>
  <section ref="panel" class="comms-inbox" :style="{ left: `${left}px`, bottom: `${bottom}px` }" role="dialog" aria-label="Inbox design preview">
    <header class="inbox-heading">
      <b>Inbox</b>
      <span v-if="unread" class="unread-pill">{{ unread }} new</span>
      <span class="grow" />
      <Button variant="ghost" :icon="MarkAsDoneIcon" aria-label="Mark all as read" title="Mark all as read" @click="markAllCommsRead(c)" />
      <Button variant="ghost" icon="x" aria-label="Close inbox" @click="c.open = false" />
    </header>
    <nav class="inbox-filters" aria-label="Inbox filters">
      <button v-for="filter in inboxFilters" :key="filter" type="button" :aria-pressed="c.filter === filter" :class="{ selected: c.filter === filter }" @click="c.filter = filter">{{ filter }}<span v-if="commsUnreadCount(c, filter)" class="filter-count">{{ commsUnreadCount(c, filter) }}</span></button>
    </nav>
    <div class="inbox-list">
      <article v-for="item in items" :key="item.id" class="inbox-item" :class="[`kind-${item.kind}`, { unread: !item.read, expanded: c.expanded === item.id }]">
        <button type="button" class="item-open" :aria-expanded="c.expanded === item.id" @click="toggle(item)">
          <span class="item-dot" aria-hidden="true" />
          <span class="item-avatar" :class="{ bot: isBot(item) }"><FeatherIcon v-if="isBot(item)" :name="botIcon(item)" class="size-3.5" /><template v-else>{{ item.from.slice(0, 1) }}</template></span>
          <span class="item-body">
            <span class="item-line"><b>{{ item.from }}</b><span class="item-title">{{ item.title }}</span></span>
            <span class="item-text">{{ item.body }}</span>
            <small>{{ item.time }}<template v-if="item.replies.length"> · {{ item.replies.length }} {{ item.replies.length === 1 ? 'reply' : 'replies' }}</template></small>
          </span>
        </button>
        <div v-if="c.expanded === item.id" class="item-detail">
          <div v-if="item.kind === 'live_one'" class="live-actions">
            <Button variant="solid" iconLeft="headphones" :disabled="!!p.call" @click="join(item)">Join listening</Button>
            <Button v-if="compsPath(item)" variant="subtle" iconLeft="map" @click="openComps(item)">Open comps</Button>
            <Button variant="ghost" @click="resolveCommsLiveOne(c, item.id)">Handled</Button>
          </div>
          <p v-if="item.kind === 'live_one' && p.call" class="item-note">Finish your current call first — this stays here.</p>
          <table v-if="item.digest" class="digest"><tbody><tr v-for="row in item.digest" :key="row[0]"><th>{{ row[0] }}</th><td>{{ row[1] }}</td><td>{{ row[2] }}</td></tr></tbody></table>
          <div v-for="(reply, i) in item.replies" :key="i" class="item-reply"><b>{{ reply.author }}</b> {{ reply.text }} <small>{{ reply.time }}</small></div>
          <form v-if="item.kind !== 'standup' && item.kind !== 'refund'" class="item-compose" @submit.prevent="replyCommsItem(c, item.id)">
            <FormControl v-model="item.draft" :aria-label="`Reply to ${item.from}`" :placeholder="item.kind === 'bot' ? 'Ask the bot…' : `Reply to ${item.from}…`" />
            <Button type="submit" icon="arrow-up" variant="solid" :disabled="!item.draft.trim()" aria-label="Send reply" />
          </form>
          <button v-else-if="item.kind === 'standup'" type="button" class="item-link" @click="router.push({ name: 'Today' })">Open Today board →</button>
        </div>
      </article>
      <p v-if="!items.length" class="inbox-empty">Nothing here for {{ c.filter.toLowerCase() }}.</p>
    </div>
    <footer class="inbox-foot">Design preview · fictional alerts, replies stay in this browser.</footer>
  </section>
</template>
<script setup>
import { Button, FeatherIcon, FormControl } from 'frappe-ui'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { onClickOutside } from '@vueuse/core'
import MarkAsDoneIcon from '@/components/Icons/MarkAsDoneIcon.vue'
import { commsPreview as c } from '@/composables/commsPreview'
import { phonePreview as p } from '@/composables/phonePreview'
import { inboxFilters, filteredInbox, commsUnreadCount, markAllCommsRead, markCommsRead, replyCommsItem, resolveCommsLiveOne } from '@/utils/commsPreview'
import { previewTeamCall, previewJoinDestination, previewJoinOutcome, startPreviewCall } from '@/utils/phonePreview'
const props = defineProps({ left: { type: Number, default: 0 }, bottom: { type: Number, default: 0 } })
const route = useRoute()
const router = useRouter()
const panel = ref(null)
const items = computed(() => filteredInbox(c))
const unread = computed(() => commsUnreadCount(c))
function isBot(item) { return ['standup', 'bot', 'refund'].includes(item.kind) }
function botIcon(item) { return item.kind === 'standup' ? 'sunrise' : item.kind === 'refund' ? 'rotate-ccw' : 'cpu' }
function toggle(item) { c.expanded = c.expanded === item.id ? null : item.id; markCommsRead(c, item.id) }
function linked(item) { return previewTeamCall(p, item.call) }
function compsPath(item) { return previewJoinDestination(linked(item)) }
function join(item) {
  const call = linked(item)
  const destination = previewJoinOutcome(p, call, () => startPreviewCall(p, 'closer', item.call), route.path)
  resolveCommsLiveOne(c, item.id)
  if (destination) { c.open = false; router.push(destination) }
}
function openComps(item) { const path = compsPath(item); if (path) { c.open = false; router.push(path) } }
// Same escape hatch as the real panel: clicking anywhere else closes it, except
// the bell that opened it (or every click on the bell would open-then-close).
onClickOutside(panel, () => { c.open = false }, { ignore: ['#notifications-btn', '.preview-bar'] })
onMounted(async () => { await nextTick(); panel.value?.querySelector('button')?.focus({ preventScroll: true }) })
onBeforeUnmount(() => { c.expanded = null })
</script>
<style scoped>
.comms-inbox { position: fixed; top: 0; z-index: 41; width: 350px; max-width: 100vw; display: flex; flex-direction: column; background: var(--surface-white, #fff); box-shadow: 8px 0 8px rgba(0,0,0,.08); color: var(--ink-gray-9, #222); }
.inbox-heading { display: flex; align-items: center; gap: 8px; padding: 9px 12px 9px 18px; border-bottom: 1px solid var(--outline-gray-2, #e5e5e5); font-size: 14px; }
.grow { flex: 1; }
.unread-pill { font-size: 10px; padding: 2px 7px; border-radius: 10px; background: #e3f1e8; color: #1f6b41; font-weight: 600; }
.inbox-filters { display: flex; gap: 4px; padding: 8px 12px; overflow-x: auto; border-bottom: 1px solid var(--outline-gray-1, #eee); }
.inbox-filters button { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; padding: 4px 9px; border-radius: 14px; font-size: 11px; color: var(--ink-gray-6, #666); }
.inbox-filters button:hover { background: var(--surface-gray-1, #f5f5f5); }
.inbox-filters button.selected { background: var(--surface-gray-7, #333); color: #fff; }
.inbox-filters button:focus-visible, .item-open:focus-visible, .item-link:focus-visible { outline: 2px solid var(--ink-gray-7, #555); outline-offset: -2px; }
.filter-count { font-size: 9px; padding: 0 5px; border-radius: 8px; background: #0002; }
.selected .filter-count { background: #fff3; }
.inbox-list { flex: 1; min-height: 0; overflow-y: auto; }
.inbox-item { border-bottom: 1px solid var(--outline-gray-1, #eee); }
.item-open { display: flex; gap: 10px; width: 100%; padding: 11px 14px; text-align: left; align-items: flex-start; }
.item-open:hover { background: var(--surface-gray-1, #fafafa); }
.item-dot { width: 5px; height: 5px; margin-top: 12px; border-radius: 50%; background: transparent; flex-shrink: 0; }
.unread .item-dot { background: var(--surface-gray-7, #333); }
.item-avatar { display: grid; place-items: center; width: 28px; height: 28px; margin-top: 2px; border-radius: 50%; flex-shrink: 0; font-size: 12px; font-weight: 600; background: var(--surface-gray-2, #eee); color: var(--ink-gray-8, #333); }
.item-avatar.bot { background: #eef3ff; color: #2d4f9e; }
.kind-live_one .item-avatar { background: #fff4d6; color: #8a6414; }
.item-body { flex: 1; min-width: 0; }
.item-line { display: flex; gap: 6px; align-items: baseline; font-size: 13px; }
.item-line b { font-weight: 600; flex-shrink: 0; }
.item-title { color: var(--ink-gray-6, #666); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.unread .item-title { color: var(--ink-gray-9, #222); }
.item-text { display: block; margin-top: 3px; font-size: 12px; line-height: 1.45; color: var(--ink-gray-7, #555); }
.unread .item-text { color: var(--ink-gray-9, #222); }
.item-body small { display: block; margin-top: 4px; font-size: 10px; color: var(--ink-gray-5, #777); }
.kind-live_one { border-left: 3px solid #d9a536; }
.item-detail { padding: 0 14px 12px 52px; }
.live-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.item-note { font-size: 11px; color: var(--ink-gray-5, #777); margin-bottom: 8px; }
.digest { width: 100%; margin: 4px 0 10px; font-size: 12px; border-collapse: collapse; }
.digest th { text-align: left; font-weight: 600; padding: 4px 0; }
.digest td { color: var(--ink-gray-6, #666); padding: 4px 0 4px 10px; }
.item-reply { font-size: 12px; margin-bottom: 6px; line-height: 1.45; }
.item-reply small { color: var(--ink-gray-5, #777); }
.item-compose { display: flex; gap: 6px; margin-top: 6px; }
.item-compose > :first-child { flex: 1; min-width: 0; }
.item-link { font-size: 12px; color: var(--ink-gray-8, #333); text-decoration: underline; text-underline-offset: 3px; }
.inbox-empty { padding: 32px 18px; font-size: 13px; color: var(--ink-gray-5, #777); }
.inbox-foot { padding: 8px 18px; border-top: 1px solid var(--outline-gray-1, #eee); font-size: 10px; color: var(--ink-gray-5, #777); }
@media (max-width: 639px) { .comms-inbox { left: 0 !important; width: 100vw; } }
</style>
