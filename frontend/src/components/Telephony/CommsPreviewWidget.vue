<template>
  <template v-if="p.enabled && c.design">
    <CommsInbox v-if="c.design === 'A' && c.open" :left="sidebarWidth" :bottom="bottom" />
    <CommsLeadThread v-else-if="c.design === 'B'" :left="sidebarWidth" :bottom="bottom" />
    <CommsRail v-else-if="c.design === 'C'" :viewportWidth="viewportWidth" :bottom="bottom" />
    <template v-else-if="c.design === 'D'">
      <TalkShortcuts />
      <!-- First-run note after "Try the new workspace": says how to get back. -->
      <div v-if="p.workspaceBanner" class="workspace-banner" role="status">
        <span>You’re in the <b>new workspace</b> — Telnyx phone dock + team chat in the left nav. Switch back any time from your name menu → <b>Back to classic</b>. Press <kbd>⌘</kbd><kbd>/</kbd> for shortcuts.</span>
        <button type="button" class="banner-close" aria-label="Dismiss" @click="p.workspaceBanner = false">×</button>
      </div>
      <CommsLeftNav v-if="!mobile" :bottom="bottom" />
      <!-- On a phone the nav lives INSIDE the real drawer panel: a fixed overlay
           outside it would count as a click-outside and close the drawer. -->
      <Teleport v-else-if="mobileNavTarget" :to="mobileNavTarget"><CommsLeftNav mobile @picked="mobileSidebarOpened = false" /></Teleport>
    </template>
  </template>
</template>
<script setup>
/**
 * Comms design mockups: what the CRM could carry instead of Mattermost.
 * DEV-only, activated with the phone preview, switched by ?commsDesign=A|B|C|D.
 *
 *   A · Inbox         the sidebar bell opens a unified inbox (alerts, digest, bots, DMs)
 *   B · Talk on the house  a record-anchored team thread drawer + pinned standup
 *   C · Team rail     a Slack-like right rail: channels, DMs, live event feed
 *   D · Left nav      the sidebar itself is the column: CRM links as a collapsible
 *                     group beside Live / Channels / DMs; a conversation is a
 *                     page in the main area (/talk/:kind/:id), nothing floats
 *
 * Nothing here touches production code paths: A intercepts the bell through
 * the notifications store's `visible` ref rather than editing AppSidebar, and
 * D overlays the real sidebar (App.vue shifts it underneath via `reserve`).
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { commsPreview as c } from '@/composables/commsPreview'
import { phonePreview as p } from '@/composables/phonePreview'
import { selectCommsDesign, railReservedWidth, navWidth } from '@/utils/commsPreview'
import { visible as realNotificationsVisible } from '@/stores/notifications'
import { mobileSidebarOpened } from '@/composables/settings'
import CommsInbox from '@/components/Telephony/CommsInbox.vue'
import CommsLeadThread from '@/components/Telephony/CommsLeadThread.vue'
import CommsRail from '@/components/Telephony/CommsRail.vue'
import CommsLeftNav from '@/components/Telephony/CommsLeftNav.vue'
import TalkShortcuts from '@/components/Telephony/TalkShortcuts.vue'
const props = defineProps({ bottom: { type: Number, default: 0 } })
const emit = defineEmits(['reserve'])
const route = useRoute()
const viewportWidth = ref(window.innerWidth)
const sidebarWidth = ref(220)
const sidebarMeasured = ref(220)
// App.vue swaps to the mobile layout under 640px; that is where the drawer lives.
const mobile = computed(() => viewportWidth.value < 640)
const mobileNavTarget = ref(null)
watch(() => route.query.commsDesign, value => { if (value && String(value) !== c.design) selectCommsDesign(c, String(value)) }, { immediate: true })
// A: the real bell opens OUR inbox. Sync flush so the real panel never paints.
watch(realNotificationsVisible, value => {
  if (!value || !p.enabled || c.design !== 'A') return
  realNotificationsVisible.value = false
  c.open = !c.open
}, { flush: 'sync' })
// B reserves its drawer height; C reserves rail width at wide viewports (or its
// strip when collapsed). D reserves nothing on the right — its conversations
// are pages — and only shifts the real sidebar under its column (left = column
// width − real sidebar width, negative when the column is the narrower of the
// two). A and overlay-mode C float and reserve nothing.
const drawerHeight = computed(() => c.design === 'B' ? (c.open ? 300 : 40) : 0)
const railWidth = computed(() => c.design === 'C' ? railReservedWidth(viewportWidth.value, c.railCollapsed) : 0)
const navShift = computed(() => c.design === 'D' && !mobile.value ? navWidth(c.navCollapsed) - sidebarMeasured.value : 0)
watch([drawerHeight, railWidth, navShift, () => p.enabled], () => {
  emit('reserve', p.enabled && c.design ? { bottom: drawerHeight.value, right: railWidth.value, left: navShift.value } : { bottom: 0, right: 0, left: 0 })
}, { immediate: true })
function measure() {
  viewportWidth.value = window.innerWidth
  const sidebar = document.querySelector('.bg-surface-menu-bar')
  sidebarMeasured.value = Math.round(sidebar?.getBoundingClientRect().width || 220)
  sidebarWidth.value = window.innerWidth < 640 ? 0 : sidebarMeasured.value + 1
}
// The drawer panel only exists while it is open; resolve the teleport target then.
watch([mobileSidebarOpened, mobile, () => c.design], async ([opened]) => {
  mobileNavTarget.value = null
  if (!opened || !mobile.value || c.design !== 'D') return
  await nextTick()
  mobileNavTarget.value = document.querySelector('.bg-surface-menu-bar') || null
}, { immediate: true })
let sidebarObserver
function onKey(event) {
  if (event.key !== 'Escape' || !c.design) return
  if (c.design === 'A' && c.open) { c.open = false; event.stopPropagation() }
  else if (c.design === 'B' && c.open) { c.open = false; event.stopPropagation() }
  else if (c.design === 'C' && !c.railCollapsed && railWidth.value === 0) { c.railCollapsed = true; event.stopPropagation() }
  // D has no overlay to close: a conversation is a page.
}
onMounted(() => {
  measure()
  window.addEventListener('resize', measure)
  window.addEventListener('keydown', onKey)
  const sidebar = document.querySelector('.bg-surface-menu-bar')
  if (sidebar) { sidebarObserver = new ResizeObserver(measure); sidebarObserver.observe(sidebar) }
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', measure)
  window.removeEventListener('keydown', onKey)
  sidebarObserver?.disconnect()
  emit('reserve', { bottom: 0, right: 0, left: 0 })
})
</script>
<style scoped>
.workspace-banner { position: fixed; top: 10px; left: 50%; transform: translateX(-50%); z-index: 41; display: flex; align-items: center; gap: 12px; max-width: min(640px, calc(100vw - 24px)); padding: 9px 12px 9px 14px; border-radius: 8px; background: var(--surface-gray-7, #2b2b2b); color: #fff; font-size: 12px; line-height: 1.45; box-shadow: 0 8px 24px #0003; }
.workspace-banner kbd { padding: 0 4px; border: 1px solid #ffffff55; border-radius: 3px; font: 11px ui-monospace, monospace; }
.banner-close { flex-shrink: 0; width: 24px; height: 24px; border-radius: 4px; font-size: 16px; line-height: 1; color: #fff; }
.banner-close:hover { background: #ffffff22; }
.banner-close:focus-visible { outline: 2px solid #fff; }
</style>
