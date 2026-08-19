import { createResource } from 'frappe-ui'
import { computed, ref, shallowRef } from 'vue'
import { useStorage } from '@vueuse/core'

export const whatsappEnabled = ref(false)
export const isWhatsappInstalled = ref(false)
createResource({
  url: 'crm.api.whatsapp.is_whatsapp_enabled',
  cache: 'Is Whatsapp Enabled',
  auto: true,
  onSuccess: (data) => {
    whatsappEnabled.value = Boolean(data)
  },
})
createResource({
  url: 'crm.api.whatsapp.is_whatsapp_installed',
  cache: 'Is Whatsapp Installed',
  auto: true,
  onSuccess: (data) => {
    isWhatsappInstalled.value = Boolean(data)
  },
})

export const smsEnabled = ref(false)
createResource({
  url: 'crm.api.sms.is_sms_enabled',
  cache: 'Is SMS Enabled',
  auto: true,
  onSuccess: (data) => {
    smsEnabled.value = Boolean(data)
  },
})

export const callEnabled = ref(false)
export const twilioEnabled = ref(false)
export const exotelEnabled = ref(false)
export const defaultCallingMedium = ref('')
createResource({
  url: 'crm.integrations.api.is_call_integration_enabled',
  cache: 'Is Call Integration Enabled',
  auto: true,
  onSuccess: (data) => {
    twilioEnabled.value = Boolean(data.twilio_enabled)
    exotelEnabled.value = Boolean(data.exotel_enabled)
    defaultCallingMedium.value = data.default_calling_medium
    callEnabled.value = twilioEnabled.value || exotelEnabled.value
  },
})

export const mobileSidebarOpened = ref(false)

// Left navigation sidebar collapsed state (desktop). Shared here so both the
// AppSidebar and a toggle in the AppHeader drive the same persisted value.
export const isSidebarCollapsed = useStorage('isSidebarCollapsed', false)

// A page can ask for the nav to be out of the way without rewriting the user's
// own preference. Deliberately NOT persisted: the comps map opens in its own
// tab, and closing that tab must not leave every other CRM tab collapsed --
// which is exactly what writing `isSidebarCollapsed` on mount would do.
// `null` means "no opinion", so the stored preference decides.
export const sidebarCollapsedOverride = ref(null)

/**
 * What the sidebar should actually do right now.
 *
 * Reading prefers a page's override; WRITING is always a deliberate human act,
 * so it drops the override and updates the real preference -- otherwise hitting
 * Expand on a page that asked for collapsed would appear to do nothing.
 */
export const sidebarCollapsed = computed({
  get: () => sidebarCollapsedOverride.value ?? isSidebarCollapsed.value,
  set: (v) => {
    sidebarCollapsedOverride.value = null
    isSidebarCollapsed.value = v
  },
})

// The detail-panel Resizer mounted on the current record page registers a
// { toggle } here so a global shortcut (]) can collapse/expand whichever panel
// is on screen, regardless of which side it's on. Null on pages without one.
export const activeDetailPanel = shallowRef(null)

export const isMobileView = computed(() => window.innerWidth < 768)

export const showSettings = ref(false)

export const disableSettingModalOutsideClick = ref(false)

export const activeSettingsPage = ref('')
