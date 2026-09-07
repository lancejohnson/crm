<template>
  <Dialog v-model="helpOpen" :options="{ title: 'Keyboard shortcuts' }">
    <template #body-content>
      <ul class="shortcut-list" aria-label="Talk keyboard shortcuts">
        <li v-for="item in talkShortcutList" :key="item.label">
          <span class="shortcut-label">{{ item.label }}</span>
          <span class="shortcut-keys"><kbd v-for="key in item.keys" :key="key">{{ key }}</kbd></span>
        </li>
      </ul>
      <p class="shortcut-note">⌘ is Ctrl on Windows/Linux. Alt+arrows stay out of text fields; the other combos work anywhere in the new workspace.</p>
    </template>
  </Dialog>
</template>
<script setup>
/**
 * Mattermost-style keyboard layer for the D · Left nav comms mockup — the ONE
 * place the DOM is bound. Every rule (what counts as typing, which combos fire
 * where, conversation order, prev/next/unread, fuzzy) is pure in
 * utils/talkShortcuts.js and unit-tested there.
 *
 * ⌘K is not bound here: the CRM palette already owns it (GlobalModals.vue), so
 * this registers a "Talk" section INTO that palette and uses ⌘⇧K to open the
 * same palette scoped to DMs. Listens in the capture phase so ⌘⇧K can stop the
 * palette's own ⌘K toggle from firing a second time.
 */
import { Dialog, FeatherIcon } from 'frappe-ui'
import { h, markRaw, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { commsPreview as c } from '@/composables/commsPreview'
import { phonePreview as p } from '@/composables/phonePreview'
import { commandPaletteScope, showCommandPalette, openCommandPalette, registerPaletteExtension } from '@/composables/modals'
import { isDialogOpen } from '@/utils/dialogs'
import { openNavItem, talkRoute } from '@/utils/commsPreview'
import { talkConversations, nextTalk, nextUnreadTalk, talkPaletteSections, shortcutFor, isTypingTarget, talkShortcutList } from '@/utils/talkShortcuts'
const route = useRoute()
const router = useRouter()
const helpOpen = ref(false)
const icons = { live: 'zap', standup: 'bookmark', channel: 'hash', dm: 'message-square' }
const iconFor = kind => markRaw({ render: () => h(FeatherIcon, { name: icons[kind] }) })

function conversations() { return talkConversations(c, p) }
function current() { return route.name === 'Talk' ? route.params : null }
function go(item) {
  if (!item || !openNavItem(c, item.kind, item.id)) return
  router.push(talkRoute(item.kind, item.id, route.query))
}
function composerEl() { return document.querySelector('form[data-talk-composer] textarea') }

// Palette section: left-column order when the query is empty, fuzzy-ranked
// otherwise; `scope === 'dm'` is the ⌘⇧K switcher.
const unregister = registerPaletteExtension((query, scope) =>
  talkPaletteSections(conversations(), query, scope).map(section => ({
    title: section.title,
    items: section.items.map(item => ({
      type: 'command',
      key: `talk:${item.kind}:${item.id}`,
      label: item.label,
      meta: item.unread ? `${item.unread} unread` : item.group,
      icon: iconFor(item.kind),
      group: 'Talk',
      run: () => go(item),
    })),
  })),
)

function onKey(event) {
  if (!p.enabled || c.design !== 'D') return
  const target = event.target
  const onTalkPage = route.name === 'Talk'
  const inComposer = !!(target?.closest && target.closest('form[data-talk-composer]'))
  const action = shortcutFor(event, { typing: isTypingTarget(target), onTalkPage, inComposer })
  if (!action) return
  // Another modal owns the keyboard, except that our own help sheet and the
  // palette may be toggled off again by their own combo.
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
      if (item) openNavItem(c, item.kind, item.kind === 'channel' ? `#${item.id}` : item.id)
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
