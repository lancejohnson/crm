<template>
  <Dialog v-model="show" :options="{ title: __('Priority order') }">
    <template #body-content>
      <p class="mb-3 text-sm text-ink-gray-6">
        {{ __('Drag the priorities into the order you want to work them. This is saved for your user.') }}
      </p>
      <Draggable
        v-model="draft"
        item-key="key"
        handle=".priority-handle"
        class="flex flex-col gap-2"
      >
        <template #item="{ element, index }">
          <div class="flex items-center gap-3 rounded-lg border border-outline-gray-1 bg-surface-white px-3 py-2.5">
            <button
              class="priority-handle cursor-grab text-ink-gray-4 active:cursor-grabbing"
              :aria-label="__('Drag priority')"
            >
              <FeatherIcon name="menu" class="size-4" />
            </button>
            <span class="flex size-6 items-center justify-center rounded-full bg-surface-gray-2 text-xs font-medium text-ink-gray-6">
              {{ index + 1 }}
            </span>
            <span class="text-sm font-medium text-ink-gray-8">{{ __(element.label) }}</span>
          </div>
        </template>
      </Draggable>
    </template>
    <template #actions>
      <div class="flex w-full justify-between gap-2">
        <Button :label="__('Reset')" @click="reset" />
        <div class="flex gap-2">
          <Button :label="__('Cancel')" @click="show = false" />
          <Button variant="solid" :label="__('Save')" :loading="saving" @click="save" />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { Button, Dialog, FeatherIcon } from 'frappe-ui'
import Draggable from 'vuedraggable'
import { ref, watch } from 'vue'

const props = defineProps({
  priorities: { type: Array, default: () => [] },
  saving: { type: Boolean, default: false },
})
const emit = defineEmits(['save'])
const show = defineModel({ type: Boolean })
const draft = ref([])

watch(
  [show, () => props.priorities],
  ([open]) => {
    if (open) draft.value = props.priorities.map((item) => ({ ...item }))
  },
  { immediate: true, deep: true },
)

function reset() {
  draft.value = props.priorities
    .slice()
    .sort((a, b) => (a.defaultOrder ?? 0) - (b.defaultOrder ?? 0))
    .map((item) => ({ ...item }))
}

function save() {
  emit('save', draft.value.map((item) => item.key))
}
</script>
