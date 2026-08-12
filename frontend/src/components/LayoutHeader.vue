<template>
  <Teleport v-if="showHeader" to="#app-header">
    <slot>
      <!-- min-h, not h: a fixed 42px with `items-center` meant that the moment a
           page's control row wrapped (Today's does at <~1456px once a status
           badge appears) the whole cluster centred on 42px and had its TOP
           SLICED OFF by the viewport — buttons half-drawn, the badge hanging
           below the border. Where the row fits, this changes nothing. -->
      <header
        class="flex min-h-10.5 items-center justify-between py-[7px] sm:pl-5 pl-2"
      >
        <div class="flex items-center gap-2">
          <slot name="left-header" />
        </div>
        <div class="flex items-center gap-2">
          <slot name="right-header" class="flex items-center gap-2" />
        </div>
      </header>
    </slot>
  </Teleport>
</template>
<script setup>
import { ref, nextTick } from 'vue'

const showHeader = ref(false)

nextTick(() => {
  showHeader.value = true
})
</script>
