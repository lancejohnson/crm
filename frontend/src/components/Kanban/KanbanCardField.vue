<template>
  <!--
    Wraps a single Kanban-card field row. The display content is passed in via
    the default slot (so each page keeps its own field rendering); this component
    layers on the hover-only affordances:
      - phone / address fields  -> a copy-to-clipboard icon
      - any other editable field -> a pencil that opens an inline editor popover

    Nothing is shown until the row is hovered, and — since gw325 — nothing is
    BUILT until then either. This component is instantiated once per field per
    card, so on a 287-card board there are ~2,000 of it. Mounting the affordance
    eagerly meant ~2,000 Tooltips, ~2,000 Popovers and ~16,000 computeds
    constructed on every board render, to draw controls that are invisible
    unless the pointer is on the row. Now the resting cost of a field row is one
    div and one boolean.
  -->
  <div
    class="group/kbf relative flex min-w-0 items-center gap-2"
    @pointerenter="hot = true"
  >
    <div class="flex min-w-0 flex-1 items-center gap-2 truncate">
      <slot />
    </div>

    <KanbanCardFieldAction
      v-if="hot"
      :doctype="doctype"
      :name="name"
      :fieldName="fieldName"
      :rawValue="rawValue"
      :copyText="copyText"
      @updated="(e) => emit('updated', e)"
    />
  </div>
</template>

<script setup>
import KanbanCardFieldAction from '@/components/Kanban/KanbanCardFieldAction.vue'
import { ref } from 'vue'

defineProps({
  doctype: { type: String, required: true },
  name: { type: String, required: true },
  fieldName: { type: String, required: true },
  // raw stored value used to seed the editor (display value may be formatted)
  rawValue: { default: '' },
  // text the copy button writes to the clipboard (the value the user sees)
  copyText: { type: String, default: '' },
})

const emit = defineEmits(['updated'])

// Latches on first hover and stays on: the editor popover must survive the
// pointer leaving the row (Popper repositions a popover whose anchor unmounts),
// and re-mounting on every pointerenter would just move the cost around.
const hot = ref(false)
</script>
