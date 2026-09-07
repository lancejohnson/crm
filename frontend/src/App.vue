<template>
  <FrappeUIProvider>
    <NotPermitted v-if="$route.name === 'Not Permitted'" />
    <Layout v-else-if="session.isLoggedIn" class="isolate" :style="previewWorkspaceStyle">
      <router-view :key="$route.fullPath" />
      <PhonePreviewWidget v-if="PhonePreviewWidget" @reserve="previewSpace = $event" />
      <CommsPreviewWidget v-if="CommsPreviewWidget" :bottom="previewSpace.bottom" @reserve="commsSpace = $event" />
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
const Layout = computed(() => {
  if (window.innerWidth < 640) {
    return MobileLayout
  } else {
    return DesktopLayout
  }
})

setConfig('systemTimezone', window.timezone?.system || null)
setConfig('localTimezone', window.timezone?.user || null)
setConfig('translatedMessages', window.translated_messages || {})
</script>
