<template>
  <CreateDocumentModal
    v-if="showCreateDocumentModal"
    v-model="showCreateDocumentModal"
    :doctype="createDocumentDoctype"
    :data="createDocumentData"
    @callback="(data) => createDocumentCallback(data)"
  />
  <QuickEntryModal
    v-if="showQuickEntryModal"
    v-model="showQuickEntryModal"
    v-bind="quickEntryProps"
  />
  <AddressModal
    v-if="showAddressModal"
    v-model="showAddressModal"
    v-bind="addressProps"
  />
  <ChangePasswordModal
    v-if="showChangePasswordModal"
    v-model="showChangePasswordModal"
  />
  <AboutModal v-model="showAboutModal" />
  <CommandPalette v-if="showCommandPalette" v-model="showCommandPalette" />
</template>
<script setup>
import ChangePasswordModal from '@/components/Modals/ChangePasswordModal.vue'
import CreateDocumentModal from '@/components/Modals/CreateDocumentModal.vue'
import QuickEntryModal from '@/components/Modals/QuickEntryModal.vue'
import AddressModal from '@/components/Modals/AddressModal.vue'
import AboutModal from '@/components/Modals/AboutModal.vue'
import CommandPalette from '@/components/CommandPalette.vue'
import {
  showCreateDocumentModal,
  createDocumentDoctype,
  createDocumentData,
  createDocumentCallback,
} from '@/composables/document'
import {
  showQuickEntryModal,
  quickEntryProps,
  showAddressModal,
  addressProps,
  showAboutModal,
  showChangePasswordModal,
  showCommandPalette,
} from '@/composables/modals'
import {
  isSidebarCollapsed,
  activeDetailPanel,
} from '@/composables/settings'
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'

// Cmd/Ctrl-K opens (or closes) the command palette — allowed even while a field
// is focused, so it works from anywhere. Requires the modifier, so it never
// interferes with plain typing.
useKeyboardShortcuts({
  ignoreTyping: false,
  shortcuts: [
    {
      match: (e) => (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k',
      action: () => (showCommandPalette.value = !showCommandPalette.value),
    },
  ],
})

// Bracket keys toggle the sidebars — only when NOT typing in a field (default
// ignoreTyping) so they don't swallow real "[" / "]" input.
useKeyboardShortcuts({
  shortcuts: [
    {
      keys: '[',
      action: () => (isSidebarCollapsed.value = !isSidebarCollapsed.value),
    },
    {
      keys: ']',
      action: () => activeDetailPanel.value?.toggle(),
    },
  ],
})
</script>
