<template>
  <div class="sample-recording">
    <p>Sample audio · not this call</p>
    <audio ref="player" controls preload="metadata" :src="sampleAudio" aria-label="Play synthetic sample audio, not this call" />
    <small>8-second synthetic tones. Player time is the sample’s duration, not the call’s.</small>
  </div>
</template>
<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import sampleAudio from '@/assets/phone-preview-sample.wav'
const player = ref(null)
const route = useRoute()
function stop() {
  if (!player.value) return
  player.value.pause()
  player.value.currentTime = 0
}
watch(() => route.fullPath, stop)
// Keyed by person/call in the conversation; switching threads or closing the
// phone tears this down. Never let a detached media element keep playing.
onBeforeUnmount(() => {
  stop()
  if (player.value) { player.value.removeAttribute('src'); player.value.load() }
})
</script>
<style scoped>
.sample-recording { margin-top: 12px; }
p { font-size: 11px; font-weight: 600; margin-bottom: 7px; }
audio { display: block; width: 100%; min-width: 0; height: 38px; }
small { display: block; font-size: 10px; margin-top: 6px; line-height: 1.5; color: var(--ink-gray-5, #777); }
</style>
