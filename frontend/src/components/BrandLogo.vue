<template>
  <!-- theme-specific logos picked via CSS so 'system' theme and live
       switches need no JS (useTheme state is per-component, not shared) -->
  <!-- keep the logo's aspect ratio: contain within the caller's box (h-8
       max-w-16) instead of object-cover + w-full, which cropped/squished any
       logo that isn't ~2:1 -->
  <div v-if="lightLogo || darkLogo" class="flex items-center">
    <img v-if="lightLogo" :src="lightLogo" class="h-full w-auto max-w-full object-contain dark:hidden" />
    <img v-if="darkLogo" :src="darkLogo" class="hidden h-full w-auto max-w-full object-contain dark:block" />
  </div>
  <CRMLogo v-else class="size-8 shrink-0 rounded" />
</template>

<script setup>
import CRMLogo from '@/components/Icons/CRMLogo.vue'
import { computed } from 'vue'

const brand = defineModel({ type: Object, default: () => ({}) })

// when only one logo is set, use it in both themes
const lightLogo = computed(() => brand.value?.logo || brand.value?.logoDark)
const darkLogo = computed(() => brand.value?.logoDark || brand.value?.logo)
</script>
