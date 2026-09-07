<template>
  <TalkNav v-if="!mobile" :bottom="dockHeight" />
  <Teleport v-else-if="mobileNavTarget" :to="mobileNavTarget"><TalkNav mobile @picked="mobileSidebarOpened = false" /></Teleport>
  <PhoneDock @reserve="dockHeight = $event" />
  <TalkKeys />
  <Transition name="fade">
    <div v-if="showBanner" class="next-banner" role="status">
      <span>
        {{ __('You are in the') }} <b>{{ __('new workspace') }}</b> — {{ __('Telnyx phone dock + team chat in the left nav. Switch back any time from your name menu →') }} <b>{{ __('Back to classic') }}</b>. {{ __('Press') }} <kbd>⌘</kbd><kbd>/</kbd> {{ __('for shortcuts.') }}
      </span>
      <button type="button" :aria-label="__('Dismiss')" @click="dismissBanner">×</button>
    </div>
  </Transition>
</template>
<script setup>
/**
 * Host for everything that only exists in the `next` workspace. App.vue
 * imports this ONE component dynamically, gated on `workspaceStore.isNext`,
 * so a classic user never loads a Talk/PhoneDock chunk. It binds the realtime
 * listeners once and reports the geometry the layout must reserve: the dock
 * bar's height and the Talk column's width (App.vue shifts the real sidebar
 * under the column, so AppSidebar/MobileSidebar stay untouched).
 *
 * On mobile the column is teleported INTO the drawer panel: a fixed overlay
 * outside it registers as a click-outside and closes the drawer on every tap.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { globalStore } from '@/stores/global'
import { talkStore } from '@/stores/talk'
import { mobileSidebarOpened } from '@/composables/settings'
import TalkNav from '@/components/Talk/TalkNav.vue'
import TalkKeys from '@/components/Talk/TalkKeys.vue'
import PhoneDock from '@/components/Telephony/PhoneDock.vue'
import { ring, dial, requestNotifyPermission, notifyLiveOne } from '@/composables/phone'
import { globalStore } from '@/stores/global'

const emit = defineEmits(['reserve'])
const props = defineProps({ mobile: Boolean })
const { $socket } = globalStore()
const talk = talkStore()
const dockHeight = ref(0)
const mobileNavTarget = ref(null)
const BANNER_KEY = 'crm_next_banner_seen'
const showBanner = ref(!localStorage.getItem(BANNER_KEY))
function dismissBanner() { showBanner.value = false; localStorage.setItem(BANNER_KEY, '1') }

const reserve = computed(() => ({ bottom: dockHeight.value, left: props.mobile ? 0 : talk.navCollapsed ? 48 : 260 }))
watch(reserve, (value) => emit('reserve', { ...value }), { immediate: true })

// The drawer panel only exists while it is open; resolve the teleport target then.
watch(mobileSidebarOpened, async (opened) => {
  mobileNavTarget.value = null
  if (!opened || !props.mobile) return
  await nextTick()
  mobileNavTarget.value = document.querySelector('.bg-surface-menu-bar') || null
}, { immediate: true })

onMounted(() => {
  requestNotifyPermission()
  globalStore().setMakeCall((number) => dial(number))
  talk.bind($socket, { onIncoming: ring, onLiveOne: notifyLiveOne })
})
onBeforeUnmount(() => {
  talk.unbind($socket)
  globalStore().setMakeCall(() => {})
  emit('reserve', { bottom: 0, left: 0 })
})
</script>
<style scoped>
.next-banner { position: fixed; top: 10px; left: 50%; transform: translateX(-50%); z-index: 45; display: flex; align-items: center; gap: 12px; max-width: 720px; padding: 10px 14px; border-radius: 8px; background: #1f2a24; color: #e9f1ec; font-size: 12px; line-height: 1.5; box-shadow: 0 8px 24px #0003; }
.next-banner kbd { margin: 0 1px; padding: 1px 5px; border: 1px solid #ffffff44; border-radius: 4px; font: 11px ui-monospace, monospace; }
.next-banner button { font-size: 16px; line-height: 1; color: #e9f1ec; opacity: .8; }
.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
