<template>
  <div class="flex h-full flex-col gap-6 px-6 py-8 text-ink-gray-8">
    <!-- Header -->
    <div class="flex justify-between px-2 text-ink-gray-8">
      <div class="flex flex-col gap-1">
        <h2 class="flex gap-2 text-xl font-semibold leading-none h-5">
          {{ __('Sidebar') }}
        </h2>
        <p class="text-p-base text-ink-gray-6">
          {{ __('Reorder the left sidebar and show or hide modules. Applies to everyone.') }}
        </p>
      </div>
      <div class="flex item-center space-x-2 w-3/12 justify-end">
        <Button
          v-if="dirty"
          :label="__('Update')"
          variant="solid"
          :loading="settings.save.loading"
          @click="updateSettings"
        />
      </div>
    </div>

    <!-- Module list -->
    <div class="flex flex-1 flex-col p-2 overflow-y-auto">
      <Draggable
        :list="items"
        item-key="label"
        class="flex flex-col gap-1.5"
        @end="dirty = true"
      >
        <template #item="{ element: item }">
          <div
            class="flex items-center justify-between rounded border border-outline-gray-modals px-2.5 py-2 cursor-grab"
            :class="{ 'opacity-50': item.hidden }"
          >
            <div class="flex items-center gap-2 text-base text-ink-gray-8">
              <DragVerticalIcon class="h-3.5 text-ink-gray-6" />
              <component :is="item.icon" class="h-4 w-4" />
              <div>{{ __(item.label) }}</div>
            </div>
            <div class="flex items-center gap-2 text-sm text-ink-gray-5">
              <span>{{ item.hidden ? __('Hidden') : __('Visible') }}</span>
              <Switch
                :modelValue="!item.hidden"
                @update:modelValue="
                  (v) => {
                    item.hidden = !v
                    dirty = true
                  }
                "
              />
            </div>
          </div>
        </template>
      </Draggable>
    </div>
  </div>
</template>
<script setup>
import DragVerticalIcon from '@/components/Icons/DragVerticalIcon.vue'
import { sidebarLinks, applySidebarConfig } from '@/utils/sidebarLinks'
import { getSettings } from '@/stores/settings'
import Draggable from 'vuedraggable'
import { Switch, toast } from 'frappe-ui'
import { ref } from 'vue'

const { _settings: settings, settings: settingsData } = getSettings()

const dirty = ref(false)

// start from the saved order (visible first, in order), then append hidden
// modules so they stay listed and can be re-enabled
function initialItems() {
  const visible = applySidebarConfig(settingsData.value?.custom_sidebar_items)
  const visibleLabels = new Set(visible.map((l) => l.label))
  const rows = visible.map((l) => ({ ...l, hidden: false }))
  for (const l of sidebarLinks) {
    if (!visibleLabels.has(l.label)) rows.push({ ...l, hidden: true })
  }
  return rows
}

const items = ref(initialItems())

function updateSettings() {
  settings.doc.custom_sidebar_items = JSON.stringify(
    items.value.map(({ label, hidden }) => ({ label, hidden: !!hidden })),
  )
  settings.save.submit(null, {
    onSuccess: () => {
      dirty.value = false
      toast.success(__('Sidebar updated'))
    },
  })
}
</script>
