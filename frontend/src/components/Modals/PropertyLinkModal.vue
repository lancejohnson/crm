<template>
  <Dialog v-model="show" :options="{ title: __('Open property address') }">
    <template #body-content>
      <div class="flex flex-col gap-4">
        <div class="rounded-lg bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-7">
          {{ address }}
        </div>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <button
            class="flex items-center gap-3 rounded-lg border border-outline-gray-1 bg-surface-white p-4 text-left hover:border-outline-gray-3 hover:bg-surface-gray-1"
            @click="open(mapsUrl(address))"
          >
            <span class="flex size-9 shrink-0 items-center justify-center rounded-full bg-surface-blue-1 text-ink-blue-3">
              <FeatherIcon name="map-pin" class="size-4" />
            </span>
            <span>
              <span class="block text-sm font-medium text-ink-gray-8">{{ __('Google Maps') }}</span>
              <span class="mt-0.5 block text-xs text-ink-gray-5">{{ __('Map and directions') }}</span>
            </span>
          </button>
          <button
            class="flex items-center gap-3 rounded-lg border border-outline-gray-1 bg-surface-white p-4 text-left hover:border-outline-gray-3 hover:bg-surface-gray-1"
            @click="open(zillowUrl(address))"
          >
            <span class="flex size-9 shrink-0 items-center justify-center rounded-full bg-surface-green-1 text-ink-green-3">
              <FeatherIcon name="home" class="size-4" />
            </span>
            <span>
              <span class="block text-sm font-medium text-ink-gray-8">{{ __('Zillow') }}</span>
              <span class="mt-0.5 block text-xs text-ink-gray-5">{{ __('Property search') }}</span>
            </span>
          </button>
        </div>
      </div>
    </template>
    <template #actions>
      <Button class="w-full" :label="__('Cancel')" @click="show = false" />
    </template>
  </Dialog>
</template>

<script setup>
import { mapsUrl, zillowUrl } from '@/utils/propertyLinks'
import { Button, Dialog, FeatherIcon } from 'frappe-ui'

defineProps({
  address: { type: String, default: '' },
})
const show = defineModel({ type: Boolean })

function open(url) {
  if (!url) return
  window.open(url, '_blank', 'noopener')
  show.value = false
}
</script>
