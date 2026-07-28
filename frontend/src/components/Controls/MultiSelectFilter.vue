<template>
  <Popover placement="bottom-start">
    <template #target="{ togglePopover }">
      <button
        class="flex h-7 w-full items-center justify-between gap-2 rounded bg-surface-gray-2 px-2 py-1 transition-colors hover:bg-surface-gray-3"
        @click="togglePopover()"
      >
        <span
          class="truncate text-base leading-5"
          :class="selected.length ? 'text-ink-gray-8' : 'text-ink-gray-4'"
        >
          {{ summary }}
        </span>
        <FeatherIcon
          name="chevron-down"
          class="h-4 w-4 shrink-0 text-ink-gray-5"
        />
      </button>
    </template>
    <template #body>
      <div
        class="mt-1 w-[16rem] rounded-lg bg-surface-modal text-base shadow-2xl ring-1 ring-black ring-opacity-5"
      >
        <div class="p-1.5">
          <FormControl
            v-model="query"
            type="text"
            :placeholder="__('Search')"
          />
        </div>
        <div class="max-h-[13rem] overflow-y-auto px-1.5">
          <div
            v-if="!visibleOptions.length"
            class="px-2 py-1.5 text-base text-ink-gray-5"
          >
            {{ __('No results found') }}
          </div>
          <button
            v-for="option in visibleOptions"
            :key="option.value"
            class="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-surface-gray-2"
            @click="toggle(option.value)"
          >
            <span
              class="flex h-4 w-4 shrink-0 items-center justify-center rounded border"
              :class="
                isSelected(option.value)
                  ? 'border-outline-gray-5 bg-surface-gray-7'
                  : 'border-outline-gray-2'
              "
            >
              <FeatherIcon
                v-if="isSelected(option.value)"
                name="check"
                class="h-3 w-3 text-ink-white"
              />
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-ink-gray-8">
                {{ option.label }}
              </span>
              <span
                v-if="option.description"
                class="block truncate text-sm text-ink-gray-5"
              >
                {{ option.description }}
              </span>
            </span>
          </button>
        </div>
        <div class="flex items-center justify-between border-t p-1.5">
          <Button
            variant="ghost"
            :label="__('Select all')"
            @click="selectAll"
          />
          <Button variant="ghost" :label="__('Clear')" @click="clear" />
        </div>
      </div>
    </template>
  </Popover>
</template>

<script setup>
import { FormControl, Popover, FeatherIcon } from 'frappe-ui'
import { computed, ref } from 'vue'

// A checkbox-list picker for "any of these" filters. Renders as a compact
// summary button because it has to fit the filter row next to the field and
// operator selects — a chip list would blow the row's width open once you pick
// more than one or two.
//
// The stored value is always an array; each entry is whatever the field's
// backend needs (an email for `_assign`, a list name for `import_lists`, the
// raw option for a Select).
const props = defineProps({
  value: { type: [Array, String, null], default: () => [] },
  options: { type: Array, default: () => [] },
  placeholder: { type: String, default: '' },
})

const emit = defineEmits(['change'])

defineOptions({ inheritAttrs: false })

const query = ref('')

// Tolerates the legacy shapes a filter row can arrive in: a real array, the
// comma-separated string the old text control produced, or a bare value.
const selected = computed(() => {
  const value = props.value
  if (Array.isArray(value)) return value.filter((v) => v !== '' && v != null)
  if (typeof value === 'string' && value)
    return value
      .split(',')
      .map((v) => v.trim().replace(/%/g, ''))
      .filter(Boolean)
  return []
})

const visibleOptions = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return props.options
  return props.options.filter((option) =>
    [option.label, option.value, option.description].some((text) =>
      (text || '').toString().toLowerCase().includes(q),
    ),
  )
})

const summary = computed(() => {
  if (!selected.value.length) return props.placeholder || __('Select')
  if (selected.value.length === 1) return labelFor(selected.value[0])
  if (selected.value.length === props.options.length && props.options.length)
    return __('All ({0})', [selected.value.length])
  return __('{0} selected', [selected.value.length])
})

function labelFor(value) {
  return props.options.find((o) => o.value === value)?.label || value
}

function isSelected(value) {
  return selected.value.includes(value)
}

function toggle(value) {
  const next = isSelected(value)
    ? selected.value.filter((v) => v !== value)
    : [...selected.value, value]
  emit('change', next)
}

function selectAll() {
  emit(
    'change',
    props.options.map((o) => o.value),
  )
}

function clear() {
  emit('change', [])
}
</script>
