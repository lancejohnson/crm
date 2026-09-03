<template>
  <div class="flex pr-3">
    <div class="z-20 ml-2 flex items-center justify-center gap-1">
      <Button
        class="size-7"
        variant="ghosted"
        @click="sidebarOpened = !sidebarOpened"
      >
        <MenuIcon class="h-4 text-ink-gray-9" />
      </Button>
      <!-- the command palette is Cmd-K on desktop; a phone has no such key,
           so this is the only way to reach search + commands there -->
      <Button
        class="size-7"
        variant="ghosted"
        :title="__('Search')"
        @click="showCommandPalette = true"
      >
        <FeatherIcon name="search" class="h-4 text-ink-gray-9" />
      </Button>
    </div>
    <div id="app-header" class="flex-1" />
  </div>
  <CallUI class="mr-3 mt-2" />
</template>

<script setup>
import MenuIcon from '@/components/Icons/MenuIcon.vue'
import CallUI from '@/components/Telephony/CallUI.vue'
import { mobileSidebarOpened as sidebarOpened } from '@/composables/settings'
import { showCommandPalette } from '@/composables/modals'
import { FeatherIcon } from 'frappe-ui'
</script>
