<template>
  <div
    class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 px-3 py-3"
  >
    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-2 min-w-0">
        <span class="truncate text-base font-medium text-ink-gray-8">
          {{ label }}
        </span>
      </div>
      <Button
        v-if="removable"
        variant="ghost"
        icon="x"
        :label="__('Remove rule')"
        class="shrink-0"
        @click="emit('remove')"
      />
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <FormControl
        type="select"
        class="w-40 shrink-0"
        :modelValue="rule.mode"
        :options="MODES"
        @update:modelValue="setMode"
      />

      <!-- Rotate: pick the group. Searchable, because the roster is people. -->
      <MultiSelectFilter
        v-if="rule.mode === 'rotate'"
        class="w-64"
        :value="rule.users"
        :options="userOptions"
        :placeholder="__('Pick people')"
        @change="(v) => (rule.users = v)"
      />

      <!-- Fixed: one person, so a single control rather than checkboxes.
           No empty-string placeholder option: frappe-ui's Select wraps reka-ui,
           which reserves '' for the placeholder and silently DROPS any item
           declared with it — the option renders nowhere and the control just
           looks like it is missing a choice. The placeholder prop does that job. -->
      <FormControl
        v-else-if="rule.mode === 'fixed'"
        type="select"
        class="w-64"
        :placeholder="__('Select a person')"
        :modelValue="rule.users[0] || ''"
        :options="userOptions"
        @update:modelValue="(v) => (rule.users = v ? [v] : [])"
      />
    </div>

    <div class="flex items-center gap-1.5 text-p-sm text-ink-gray-5">
      <template v-if="rule.mode === 'off'">
        {{ __('Leads from here arrive with no owner.') }}
      </template>
      <template v-else-if="!rule.users.length">
        <span class="text-ink-red-3">
          {{ __('Pick at least one person, or choose “No one”.') }}
        </span>
      </template>
      <template v-else-if="nextOwner">
        {{ __('Next lead goes to') }}
        <span class="font-medium text-ink-gray-7">{{ nextOwner }}</span>
      </template>
      <template v-else-if="rule.mode === 'rotate' && rule.users.length > 1">
        {{ __('Shared evenly, day by day.') }}
      </template>
    </div>
  </div>
</template>

<script setup>
import MultiSelectFilter from '@/components/Controls/MultiSelectFilter.vue'
import { Button, FormControl } from 'frappe-ui'
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  rule: { type: Object, required: true },
  users: { type: Array, default: () => [] },
  nextOwner: { type: String, default: '' },
  removable: { type: Boolean, default: false },
})

const emit = defineEmits(['remove'])

// Mirrors crm/api/lead_assignment.MODES. Worded as the sentence a manager is
// actually writing ("Leadzolo — always — Lance"), not as an internal mode name.
const MODES = [
  { label: __('Rotate between'), value: 'rotate' },
  { label: __('Always'), value: 'fixed' },
  { label: __('No one'), value: 'off' },
]

const userOptions = computed(() =>
  props.users.map((u) => ({ label: u.full_name || u.name, value: u.name })),
)

// Switching rotate -> always must not silently keep four people and quietly use
// the first; narrow it out loud so the control shows what will be saved.
function setMode(mode) {
  props.rule.mode = mode
  if (mode === 'fixed') props.rule.users = props.rule.users.slice(0, 1)
  else if (mode === 'off') props.rule.users = []
}
</script>
