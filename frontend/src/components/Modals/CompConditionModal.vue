<template>
  <Dialog v-model="show" :options="{ title: __('What kind of comp is this?') }">
    <template #body-content>
      <DialogDescription class="sr-only">
        {{ __('Choose the condition of the comparable property you just added.') }}
      </DialogDescription>
      <div class="flex flex-col gap-4">
        <div v-if="comp?.address" class="rounded-lg bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-7">
          {{ comp.address }}
        </div>

        <!-- One tap picks and closes. The condition is what the numbers cannot
             say — a gutted shell and a renovated flip can share a sqft — and the
             moment of adding is when the rep has just looked at the photos. -->
        <div class="flex flex-col gap-2">
          <button
            v-for="option in COMP_CONDITION_TYPES"
            :key="option"
            class="flex items-center gap-2.5 rounded-lg border px-3 py-2.5 text-left text-base"
            :class="
              current === option
                ? 'border-outline-gray-4 bg-surface-gray-2 font-medium text-ink-gray-9'
                : 'border-outline-gray-1 bg-surface-white text-ink-gray-7 hover:border-outline-gray-3 hover:bg-surface-gray-1'
            "
            @click="choose(option)"
          >
            <FeatherIcon
              :name="current === option ? 'check-circle' : 'circle'"
              class="size-4 shrink-0"
              :class="current === option ? 'text-ink-green-3' : 'text-ink-gray-4'"
            />
            {{ __(option) }}
          </button>
        </div>
      </div>
    </template>
    <template #actions>
      <div class="flex w-full items-center gap-2">
        <!-- Skipping keeps the comp picked. The tag is optional by design: a
             pick must never cost more than a click, and the chip on the card
             lets it be set later. -->
        <Button class="ml-auto" :label="__('Skip for now')" @click="show = false" />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { COMP_CONDITION_TYPES } from '@/utils/comps'
import { Button, Dialog, FeatherIcon } from 'frappe-ui'
import { DialogDescription } from 'reka-ui'
import { computed } from 'vue'

const props = defineProps({
  comp: { type: Object, default: null },
})
const emit = defineEmits(['choose'])
const show = defineModel({ type: Boolean })

const current = computed(() => props.comp?.comp_type || '')

function choose(option) {
  emit('choose', props.comp?.name, option)
  show.value = false
}
</script>
