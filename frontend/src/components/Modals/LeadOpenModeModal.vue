<template>
  <Dialog
    v-model="show"
    :options="{ size: 'lg', title: __('How should leads open?') }"
  >
    <template #body-content>
      <p class="text-p-base text-ink-gray-6">
        {{
          __(
            'You just clicked a lead on the board. Opening it as a quick view keeps the board behind it, so you come back to the same place in the same column instead of scrolling to find your spot again.',
          )
        }}
      </p>

      <div class="mt-4 flex flex-col gap-2">
        <button
          v-for="option in options"
          :key="option.value"
          class="flex items-start gap-3 rounded-lg border border-outline-gray-2 p-3 text-left hover:border-outline-gray-3 hover:bg-surface-gray-1"
          @click="choose(option.value)"
        >
          <FeatherIcon
            :name="option.icon"
            class="mt-0.5 size-4 shrink-0 text-ink-gray-6"
          />
          <span class="min-w-0">
            <span class="block text-base font-medium text-ink-gray-8">
              {{ option.label }}
            </span>
            <span class="block text-p-sm text-ink-gray-5">
              {{ option.description }}
            </span>
          </span>
        </button>
      </div>

      <p class="mt-4 text-p-sm text-ink-gray-5">
        {{ __('You can change this any time in Settings → Preferences.') }}
      </p>
    </template>
  </Dialog>
</template>

<script setup>
import { Dialog, FeatherIcon } from 'frappe-ui'
import { computed } from 'vue'
import { LEAD_OPEN_MODAL, LEAD_OPEN_PAGE } from '@/composables/leadOpenMode'

const show = defineModel({ type: Boolean })
const emit = defineEmits(['choose'])

const options = computed(() => [
  {
    value: LEAD_OPEN_MODAL,
    icon: 'layers',
    label: __('Quick view over the board'),
    description: __(
      'Contact details, first-call read and the full activity timeline, without leaving the board.',
    ),
  },
  {
    value: LEAD_OPEN_PAGE,
    icon: 'external-link',
    label: __('The full lead page'),
    description: __(
      'Everything, including comps, photos, tax info and agreements. This is what clicking a card does today.',
    ),
  },
])

// There is deliberately no cancel/X-only path that resolves to a mode: the
// dialog is dismissible, but dismissing it stores NOTHING, so the user is asked
// again next time rather than being silently pinned to whichever option happened
// to be the fallback.
function choose(value) {
  show.value = false
  emit('choose', value)
}
</script>
