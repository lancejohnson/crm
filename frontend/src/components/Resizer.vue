<template>
  <div class="relative flex h-full shrink-0">
    <!-- Panel box: inherits the parent's classes (border/flex/width intent) and
         holds the actual sidebar content. When collapsed its width goes to 0 and
         the content is clipped (kept mounted so expanding is instant). -->
    <div
      v-bind="$attrs"
      class="relative h-full"
      :class="{ 'overflow-hidden': collapsed }"
      :style="{ width: (collapsed ? 0 : sidebarWidth) + 'px' }"
    >
      <slot v-bind="{ sidebarResizing, sidebarWidth }" />
      <!-- drag-to-resize handle (hidden while collapsed) -->
      <div
        v-show="!collapsed"
        class="absolute z-10 h-full w-1 cursor-col-resize bg-surface-gray-4 opacity-0 transition-opacity hover:opacity-100"
        :class="{
          'opacity-100': sidebarResizing,
          'left-0': side == 'right',
          'right-0': side == 'left',
        }"
        @mousedown="startResize"
      />
    </div>
    <!-- Collapse / expand toggle pinned to the panel's content-side edge; always
         reachable so a collapsed panel can be reopened. -->
    <button
      type="button"
      class="absolute top-1/2 z-30 grid size-6 -translate-y-1/2 place-items-center rounded-full border bg-surface-white text-ink-gray-6 shadow-sm transition-colors hover:bg-surface-gray-2 hover:text-ink-gray-8"
      :class="side == 'right' ? 'left-0 -translate-x-1/2' : 'right-0 translate-x-1/2'"
      :title="collapsed ? __('Expand panel') : __('Collapse panel')"
      @click="collapsed = !collapsed"
    >
      <FeatherIcon :name="toggleIcon" class="size-3.5" />
    </button>
  </div>
</template>
<script setup>
import { FeatherIcon } from 'frappe-ui'
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { useStorage } from '@vueuse/core'
import { activeDetailPanel } from '@/composables/settings'

// The parent's class/attrs are applied to the inner panel box (not the wrapper),
// so collapsing can shrink the box without disturbing the toggle button.
defineOptions({ inheritAttrs: false })

const props = defineProps({
  defaultWidth: { type: Number, default: 420 },
  minWidth: { type: Number, default: 16 * 16 },
  maxWidth: { type: Number, default: 36 * 16 },
  side: { type: String, default: 'left' },
  parent: { type: Object, default: null },
})

// Persist per side — the right detail panel (Lead/Deal/Buyer) and the left panel
// (Contact/Organization) collapse independently.
const collapsed = useStorage(`crmResizerCollapsed_${props.side}`, false)

// Chevrons point the way the panel moves: outward to collapse, inward to expand.
const toggleIcon = computed(() => {
  if (props.side === 'right')
    return collapsed.value ? 'chevrons-left' : 'chevrons-right'
  return collapsed.value ? 'chevrons-right' : 'chevrons-left'
})

// Expose this panel's toggle to the global `]` shortcut while mounted.
const panelHandle = { toggle: () => (collapsed.value = !collapsed.value) }
onMounted(() => (activeDetailPanel.value = panelHandle))
onBeforeUnmount(() => {
  if (activeDetailPanel.value === panelHandle) activeDetailPanel.value = null
})

const sidebarResizing = ref(false)
// Restore the user's last manually-set width (persisted on resize); fall back to
// the default. Clamp to the allowed range in case min/max changed.
const stored = Number(localStorage.getItem('sidebarWidth'))
const sidebarWidth = ref(
  stored
    ? Math.min(Math.max(stored, props.minWidth), props.maxWidth)
    : props.defaultWidth,
)

function startResize() {
  document.addEventListener('mousemove', resize)
  document.addEventListener('mouseup', () => {
    document.body.classList.remove('select-none')
    document.body.classList.remove('cursor-col-resize')
    document.querySelectorAll('.select-text1').forEach((el) => {
      el.classList.remove('select-text1')
      el.classList.add('select-text')
    })
    localStorage.setItem('sidebarWidth', sidebarWidth.value)
    sidebarResizing.value = false
    document.removeEventListener('mousemove', resize)
  })
}
function resize(e) {
  sidebarResizing.value = true
  document.body.classList.add('select-none')
  document.body.classList.add('cursor-col-resize')
  document.querySelectorAll('.select-text').forEach((el) => {
    el.classList.remove('select-text')
    el.classList.add('select-text1')
  })
  sidebarWidth.value =
    props.side == 'left' ? e.clientX : window.innerWidth - e.clientX

  let gap = props.parent ? distance() : 0
  sidebarWidth.value = sidebarWidth.value - gap

  // snap to props.defaultWidth
  let range = [props.defaultWidth - 10, props.defaultWidth + 10]
  if (sidebarWidth.value > range[0] && sidebarWidth.value < range[1]) {
    sidebarWidth.value = props.defaultWidth
  }

  if (sidebarWidth.value < props.minWidth) {
    sidebarWidth.value = props.minWidth
  }
  if (sidebarWidth.value > props.maxWidth) {
    sidebarWidth.value = props.maxWidth
  }
}
function distance() {
  if (!props.parent) return 0
  const rect = props.parent.getBoundingClientRect()
  return rect[props.side]
}
</script>
