<template>
  <!-- theme-specific logos picked via CSS so 'system' theme and live
       switches need no JS (useTheme state is per-component, not shared) -->
  <div v-if="lightLogo || darkLogo">
    <img v-if="lightLogo" :src="lightLogo" class="h-full w-full object-cover dark:hidden" />
    <img v-if="darkLogo" :src="darkLogo" class="hidden h-full w-full object-cover dark:block" />
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
