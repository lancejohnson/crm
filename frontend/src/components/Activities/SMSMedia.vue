<template>
  <div v-if="media?.length" class="flex flex-col gap-1.5">
    <template v-for="(m, i) in media" :key="i">
      <!-- images: inline thumbnail, click opens the pageable lightbox -->
      <img
        v-if="isImage(m)"
        :src="m.url"
        loading="lazy"
        class="max-h-64 max-w-full cursor-zoom-in rounded-md object-cover"
        @click="openAt(m)"
      />
      <!-- videos: inline player with controls -->
      <video
        v-else-if="isVideo(m)"
        :src="m.url"
        controls
        preload="metadata"
        class="max-h-64 max-w-full rounded-md"
      />
      <!-- anything else (audio, pdf, vcard…): a labeled download link -->
      <a
        v-else
        :href="m.url"
        target="_blank"
        rel="noopener noreferrer"
        class="inline-flex items-center gap-1 text-sm underline"
      >
        <AttachmentIcon class="size-3.5" />
        {{ label(m) }}
      </a>
    </template>

    <!-- full-screen viewer; arrows/keyboard page through this message's images -->
    <ImageLightbox
      v-if="viewerOpen"
      :images="imageUrls"
      :start-index="viewerIndex"
      @close="viewerOpen = false"
    />
  </div>
</template>

<script setup>
import AttachmentIcon from '@/components/Icons/AttachmentIcon.vue'
import ImageLightbox from '@/components/Activities/ImageLightbox.vue'
import { computed, ref } from 'vue'

const props = defineProps({
  // [{ url, type }] — `type` is the MMS mime type from Quo (e.g. image/jpeg)
  media: { type: Array, default: () => [] },
})

function isImage(m) {
  return (m.type || '').startsWith('image/')
}

function isVideo(m) {
  return (m.type || '').startsWith('video/')
}

function label(m) {
  return m.type || __('Attachment')
}

// only images are pageable in the lightbox (videos/files keep inline behavior)
const imageUrls = computed(() => props.media.filter(isImage).map((m) => m.url))
const viewerOpen = ref(false)
const viewerIndex = ref(0)

function openAt(m) {
  const idx = imageUrls.value.indexOf(m.url)
  viewerIndex.value = idx < 0 ? 0 : idx
  viewerOpen.value = true
}
</script>
