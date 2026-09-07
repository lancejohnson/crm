import { ref } from 'vue'

export const showQuickEntryModal = ref(false)
export const quickEntryProps = ref({})

export const showAddressModal = ref(false)
export const addressProps = ref({})

export const showAboutModal = ref(false)

export const showChangePasswordModal = ref(false)

export const showCommandPalette = ref(false)

// Extension point for the command palette. A registered provider returns
// `[{ title, items }]` sections for the current query; `scope` (e.g. 'dm')
// narrows the palette to extension results only, which is how a scoped
// switcher (⌘⇧K) shares the one ⌘K palette instead of a second modal.
// The palette resets `commandPaletteScope` to null when it closes.
export const commandPaletteScope = ref(null)
export const paletteExtensions = ref([])
export function registerPaletteExtension(provider) {
  paletteExtensions.value = [...paletteExtensions.value, provider]
  return () => { paletteExtensions.value = paletteExtensions.value.filter((p) => p !== provider) }
}
export function openCommandPalette(scope = null) {
  commandPaletteScope.value = scope
  showCommandPalette.value = true
}
