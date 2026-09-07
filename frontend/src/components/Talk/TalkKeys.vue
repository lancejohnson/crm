<template>
  <Dialog v-model="helpOpen" :options="{ title: __('Keyboard shortcuts') }">
    <template #body-content>
      <ul class="shortcut-list" :aria-label="__('Talk keyboard shortcuts')">
        <li v-for="item in talkShortcutList" :key="item.label">
          <span class="shortcut-label">{{ item.label }}</span>
          <span class="shortcut-keys"><kbd v-for="key in item.keys" :key="key">{{ key }}</kbd></span>
        </li>
      </ul>
      <p class="shortcut-note">{{ __('⌘ is Ctrl on Windows/Linux. Alt+arrows stay out of text fields; the other combos work anywhere in the new workspace.') }}</p>
    </template>
  </Dialog>
</template>
<script setup>
/**
 * Mattermost-style keyboard layer for the next workspace — the ONE place the
 * DOM is bound. Every rule (typing detection, which combos fire where,
 * prev/next/unread, fuzzy) is pure in utils/talkShortcuts.js and driven here by
 * `talkStore.conversations` (real channels / DMs / live calls).
 *
 * ⌘K is not bound: the CRM palette owns it, so this registers a "Talk" section
 * into it and ⌘⇧K opens the same palette scoped to DMs. The DM scope also
 * offers teammates with no thread yet — picking one calls talk.ensure_dm.
 */
import { Dialog, FeatherIcon, call } from 'frappe-ui'
import { h, markRaw, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { commandPaletteScope, showCommandPalette, openCommandPalette, registerPaletteExtension } from '@/composables/modals'
import { isDialogOpen } from '@/utils/dialogs'
import { talkStore } from '@/stores/talk'
import { usersStore } from '@/stores/users'
import { sessionStore } from '@/stores/session'
import { talkListFrom, nextTalk, nextUnreadTalk, talkPaletteSections, matchTalk, shortcutFor, isTypingTarget, talkShortcutList } from '@/utils/talkShortcuts'

const route = useRoute()
const router = useRouter()
const talk = talkStore()
const session = sessionStore()
const { users } = usersStore()
const helpOpen = ref(false)
const icons = { live: 'zap', standup: 'bookmark', channel: 'hash', dm: 'message-square', user: 'user-plus', lead: 'home', unreads: 'inbox', drafts: 'edit-3' }
const iconFor = (kind) => markRaw({ render: () => h(FeatherIcon, { name: icons[kind] }) })

function conversations() { return talkListFrom(talk.conversations) }
function current() { return route.name === 'Talk' ? route.params : null }
function go(item) {
  if (!item) return
  router.push({ name: 'Talk', params: { kind: item.kind, id: item.id } })
}
async function startDm(user) {
  const dm = await call('crm.api.talk.ensure_dm', { user })
  await talk.channels.reload()
  if (dm?.name) go({ kind: 'dm', id: dm.name })
}
function composerEl() { return document.querySelector('form[data-talk-composer] textarea') }

// Teammates without a DM thread yet, offered only in the DM scope.
function usersWithoutDm(query) {
  const have = new Set(talk.dmRows.map((c) => c.dm_user))
  const pool = (users.data?.crmUsers || [])
    .filter((u) => u.name !== session.user && !have.has(u.name))
    .map((u) => ({ kind: 'user', id: u.name, label: u.full_name || u.name, group: 'Start a conversation', unread: 0, keywords: `dm ${u.email || ''}` }))
  return matchTalk(pool, query)
}

const unregister = registerPaletteExtension((query, scope) => {
  const sections = talkPaletteSections(conversations(), query, scope).map((section) => ({
    title: section.title,
    items: section.items.map((item) => ({
      type: 'command', key: `talk:${item.kind}:${item.id}`, label: item.label,
      meta: item.unread ? `${item.unread} unread` : item.group, icon: iconFor(item.kind), group: 'Talk',
      run: () => go(item),
    })),
  }))
  if (scope === 'dm') {
    const extra = usersWithoutDm(query)
    if (extra.length) sections.push({ title: __('Start a conversation'), items: extra.map((u) => ({ type: 'command', key: `talk:user:${u.id}`, label: u.label, meta: u.group, icon: iconFor('user'), group: 'Talk', run: () => startDm(u.id) })) })
  }
  return sections
})

function onKey(event) {
  const target = event.target
  const onTalkPage = route.name === 'Talk'
  const inComposer = !!(target?.closest && target.closest('form[data-talk-composer]'))
  const action = shortcutFor(event, { typing: isTypingTarget(target), onTalkPage, inComposer })
  if (!action) return
  const paletteOpen = showCommandPalette.value
  if (paletteOpen && action !== 'dm-switcher') return
  if (isDialogOpen() && !(action === 'help' && helpOpen.value)) return
  event.preventDefault()
  event.stopPropagation()
  switch (action) {
    case 'dm-switcher':
      if (paletteOpen && commandPaletteScope.value === 'dm') showCommandPalette.value = false
      else openCommandPalette('dm')
      break
    case 'next': go(nextTalk(conversations(), current(), 1)); break
    case 'prev': go(nextTalk(conversations(), current(), -1)); break
    case 'next-unread': go(nextUnreadTalk(conversations(), current(), 1)); break
    case 'prev-unread': go(nextUnreadTalk(conversations(), current(), -1)); break
    case 'focus-composer': composerEl()?.focus(); break
    case 'escape': {
      const item = current()
      if (item && ['channel', 'dm', 'standup'].includes(item.kind)) {
        call('crm.api.talk.mark_read', { channel: item.id }).then((r) => talk.patchUnread(item.id, r?.unread || 0)).catch(() => {})
      }
      composerEl()?.blur()
      break
    }
    case 'help': helpOpen.value = !helpOpen.value; break
  }
}
onMounted(() => window.addEventListener('keydown', onKey, true))
onBeforeUnmount(() => { window.removeEventListener('keydown', onKey, true); unregister() })
</script>
<style scoped>
.shortcut-list { list-style: none; margin: 0; padding: 0; }
.shortcut-list li { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 8px 0; border-bottom: 1px solid var(--outline-gray-1, #eee); font-size: 13px; color: var(--ink-gray-8, #333); }
.shortcut-list li:last-child { border-bottom: 0; }
.shortcut-keys { display: flex; gap: 4px; flex-shrink: 0; }
kbd { min-width: 22px; padding: 2px 6px; border: 1px solid var(--outline-gray-2, #ddd); border-bottom-width: 2px; border-radius: 4px; background: var(--surface-gray-1, #fafafa); font: 11px ui-monospace, monospace; text-align: center; color: var(--ink-gray-7, #555); }
.shortcut-note { margin-top: 12px; font-size: 11px; line-height: 1.5; color: var(--ink-gray-5, #777); }
</style>
