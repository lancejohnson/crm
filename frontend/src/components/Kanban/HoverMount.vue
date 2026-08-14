<template>
  <div
    class="contents"
    @pointerenter="hot = true"
    @focusin="hot = true"
    @click="onClick"
  >
    <slot v-if="hot" />
    <slot v-else name="placeholder" />
  </div>
</template>

<script setup>
/*
  Defers mounting an interactive control until the pointer actually reaches it.

  Kanban cards carry controls that cost real money to construct and are useless
  until touched — a Dropdown builds a trigger, a portal, a content container and
  its own id/context plumbing. Multiplied by every card on the board that is
  hundreds of component instances built during a render, to draw a "+" button.

  The placeholder slot renders the resting appearance; the default slot is the
  real thing. `hot` latches so an open menu can't be torn out from under the
  user by the pointer leaving.
*/
import { ref, nextTick } from 'vue'

const props = defineProps({
  // Selector for the control to re-trigger when the very first interaction is a
  // click rather than a hover (touch, or a fast pointer that clicks on entry).
  triggerSelector: { type: String, default: 'button' },
})

const hot = ref(false)

function onClick(e) {
  if (hot.value) return
  hot.value = true
  // The click that woke us up landed on the placeholder, so the real control
  // never saw it. Replay it once the real control exists.
  const host = e.currentTarget
  nextTick(() => {
    host?.querySelector(props.triggerSelector)?.click()
  })
}
</script>
