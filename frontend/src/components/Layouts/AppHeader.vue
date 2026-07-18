<template>
  <div class="flex items-center border-b pr-5">
    <!-- Left sidebar collapse toggle (desktop). Mirrors the Collapse control at
         the bottom of the sidebar; state is shared + persisted. -->
    <button
      type="button"
      class="ml-2 mr-1 grid size-7 shrink-0 place-items-center rounded text-ink-gray-6 transition-colors hover:bg-surface-gray-3 hover:text-ink-gray-8"
      :title="isSidebarCollapsed ? __('Expand sidebar') : __('Collapse sidebar')"
      @click="isSidebarCollapsed = !isSidebarCollapsed"
    >
      <CollapseSidebar
        class="h-4 w-4 duration-300 ease-in-out"
        :class="{ '[transform:rotateY(180deg)]': isSidebarCollapsed }"
      />
    </button>
    <div id="app-header" class="flex-1"></div>
    <div class="flex items-center justify-center">
      <CallUI />
    </div>
  </div>
</template>

<script setup>
import CallUI from '@/components/Telephony/CallUI.vue'
import CollapseSidebar from '@/components/Icons/CollapseSidebar.vue'
import { isSidebarCollapsed } from '@/composables/settings'
</script>
