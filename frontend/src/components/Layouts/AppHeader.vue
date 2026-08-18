<template>
  <div class="flex items-center border-b pr-5">
    <!-- The sidebar collapse toggle used to sit here as well. Removed: the
         sidebar's own "Collapse" control at its foot does the same thing, `[`
         does it from the keyboard, and the command palette lists it -- so this
         one bought a fourth way to do it at the cost of a button sitting in the
         top-left corner of every page, which is prime real estate on a screen
         that is short of it. -->
    <div id="app-header" class="ml-2 flex-1"></div>
    <div class="flex items-center justify-center">
      <CallUI />
    </div>
  </div>
</template>

<script setup>
import CallUI from '@/components/Telephony/CallUI.vue'
</script>
