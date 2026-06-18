<template>
  <teleport to="body">
    <div
      class="fixed inset-0 z-[100] flex items-center justify-center bg-black/90"
      @click="$emit('close')"
    >
      <!-- close -->
      <button
        class="absolute right-3 top-3 rounded-full p-2 text-white/80 hover:bg-white/10 hover:text-white"
        @click.stop="$emit('close')"
      >
        <FeatherIcon name="x" class="size-6" />
      </button>

      <!-- previous -->
      <button
        v-if="images.length > 1"
        class="absolute left-2 rounded-full p-2 text-white/80 hover:bg-white/10 hover:text-white sm:left-5"
        @click.stop="prev"
      >
        <FeatherIcon name="chevron-left" class="size-8" />
      </button>

      <img
        :src="images[current]"
        class="max-h-[92vh] max-w-[92vw] rounded object-contain"
        @click.stop
      />

      <!-- next -->
      <button
        v-if="images.length > 1"
        class="absolute right-2 rounded-full p-2 text-white/80 hover:bg-white/10 hover:text-white sm:right-5"
        @click.stop="next"
      >
        <FeatherIcon name="chevron-right" class="size-8" />
      </button>

      <!-- counter -->
      <div
        v-if="images.length > 1"
        class="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-black/50 px-3 py-1 text-sm text-white"
      >
        {{ current + 1 }} / {{ images.length }}
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { FeatherIcon } from 'frappe-ui'
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  images: { type: Array, default: () => [] },
  startIndex: { type: Number, default: 0 },
})
const emit = defineEmits(['close'])

const current = ref(props.startIndex)
// re-opening on a different thumbnail updates the starting image
watch(() => props.startIndex, (v) => (current.value = v))

function next() {
  current.value = (current.value + 1) % props.images.length
}
function prev() {
  current.value = (current.value - 1 + props.images.length) % props.images.length
}

function onKey(e) {
  if (e.key === 'Escape') emit('close')
  else if (e.key === 'ArrowRight') next()
  else if (e.key === 'ArrowLeft') prev()
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>
