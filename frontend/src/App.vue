<template>
  <FrappeUIProvider>
    <NotPermitted v-if="$route.name === 'Not Permitted'" />
    <Layout v-else-if="session.isLoggedIn" class="isolate" :style="previewWorkspaceStyle">
      <router-view :key="$route.fullPath" />
      <NextWorkspaceShell v-if="workspace.isNext" :mobile="isMobile" @reserve="nextSpace = $event" />
      <template v-else-if="PhonePreviewWidget">
        <PhonePreviewWidget @reserve="previewSpace = $event" />
        <CommsPreviewWidget :bottom="previewSpace.bottom" @reserve="commsSpace = $event" />
      </template>
    </Layout>
    <Dialogs />
  </FrappeUIProvider>
</template>

<script setup>
import NotPermitted from '@/pages/NotPermitted.vue'
import { Dialogs } from '@/utils/dialogs'
import { sessionStore } from '@/stores/session'
import { FrappeUIProvider, setConfig, useTheme } from 'frappe-ui'
import { computed, defineAsyncComponent, provide, ref } from 'vue'
import { workspaceStore } from '@/stores/workspace'
import { sidebarCollapsed } from '@/composables/settings'

// The next workspace (Telnyx phone dock + Talk left nav) mounts from ONE
// dynamically imported shell, only when the server says this user is on
// `next`. Classic users never fetch that chunk: their render is production.
const workspace = workspaceStore()
const NextWorkspaceShell = defineAsyncComponent(() => import('@/components/Talk/NextWorkspaceShell.vue'))
const nextSpace = ref({ bottom: 0, left: 0 })

// Dev-only activation: production never mounts the mockup or its fixtures.
const PhonePreviewWidget = import.meta.env.DEV
  ? defineAsyncComponent(() => import('@/components/Telephony/PhonePreviewWidget.vue'))
  : null
const CommsPreviewWidget = import.meta.env.DEV
  ? defineAsyncComponent(() => import('@/components/Telephony/CommsPreviewWidget.vue'))
  : null

// Reserve the demo's bottom status bar (+ the comms drawer / docked rail /
// docked pane), not its compact floating panels. The real CRM keeps every
// remaining pixel. `left` shifts the whole layout so the D left-nav column can
// sit exactly over the real sidebar (negative when the column is narrower).
const previewSpace = ref({ bottom: 0 })
const commsSpace = ref({ bottom: 0, right: 0, left: 0 })
const previewWorkspaceStyle = computed(() => {
  if (workspace.isNext) {
    // Real layout: the Talk column replaces the sidebar's width (220 expanded /
    // 48 collapsed in classic), the dock bar reserves its height.
    const left = nextSpace.value.left - (isSidebarCollapsedNow() ? 48 : 220)
    const bottom = nextSpace.value.bottom
    return {
      height: bottom ? `calc(100dvh - ${bottom}px)` : undefined,
      width: left ? `calc(100vw - ${left}px)` : undefined,
      marginLeft: left ? `${left}px` : undefined,
    }
  }
  const bottom = previewSpace.value.bottom + commsSpace.value.bottom
  const right = commsSpace.value.right
  const left = commsSpace.value.left || 0
  return {
    height: bottom ? `calc(100dvh - ${bottom}px)` : undefined,
    width: right || left ? `calc(100vw - ${right + left}px)` : undefined,
    marginLeft: left ? `${left}px` : undefined,
  }
})

const session = sessionStore()
provide('session', session)

const { setTheme } = useTheme()
if (!localStorage.getItem('theme')) {
  setTheme('light')
}

const MobileLayout = defineAsyncComponent(
  () => import('./components/Layouts/MobileLayout.vue'),
)
const DesktopLayout = defineAsyncComponent(
  () => import('./components/Layouts/DesktopLayout.vue'),
)
const isMobile = window.innerWidth < 640
const Layout = computed(() => (isMobile ? MobileLayout : DesktopLayout))
// The real sidebar under the Talk column: classic collapses to 48px via the
// stored preference (composables/settings sidebarCollapsed); read it so the
// shift is exact either way. Mobile has no fixed sidebar.
function isSidebarCollapsedNow() { return isMobile ? true : !!sidebarCollapsed.value }

setConfig('systemTimezone', window.timezone?.system || null)
setConfig('localTimezone', window.timezone?.user || null)
setConfig('translatedMessages', window.translated_messages || {})
</script>
