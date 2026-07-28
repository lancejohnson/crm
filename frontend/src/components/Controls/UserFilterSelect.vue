<template>
  <Autocomplete
    :value="selected"
    :options="userOptions"
    :placeholder="__('Select a user')"
    @change="(option) => emitValue(option?.value)"
  >
    <template #item-label="{ option }">
      <div class="flex flex-col">
        <div class="truncate text-ink-gray-7">{{ option.label }}</div>
        <div v-if="option.email" class="truncate text-sm text-ink-gray-5">
          {{ option.email }}
        </div>
      </div>
    </template>
  </Autocomplete>
</template>

<script setup>
import Autocomplete from '@/components/frappe-ui/Autocomplete.vue'
import { usersStore } from '@/stores/users'
import { computed } from 'vue'

// Picks a user for a filter value, showing "First Last" instead of the raw
// login email. Two storage shapes:
//   wildcard=true   `_assign` — a JSON blob like ["a@b.com"], only reachable
//                   with LIKE, so the value has to be stored as %a@b.com%
//   wildcard=false  a plain Link-to-User field (owner, lead_owner, ...) with
//                   `equals`, stored as the bare email
// Options come from the users store, which is already loaded at app boot, so
// opening the dropdown costs no network round-trip.
const props = defineProps({
  value: { type: [String, null], default: '' },
  wildcard: { type: Boolean, default: false },
})

const emit = defineEmits(['change'])

// Filter.vue blanket-binds v-model/placeholder onto whatever control it renders;
// this one manages its own value, so don't let those leak onto the Autocomplete.
defineOptions({ inheritAttrs: false })

const usersStoreRef = usersStore()

const userOptions = computed(() => {
  const all = usersStoreRef.users?.data?.allUsers || []
  return all.map((user) => ({
    label: user.full_name || user.email || user.name,
    value: user.email || user.name,
    email: user.email,
  }))
})

// The stored value round-trips through the server as %email%; strip the
// wildcards so the dropdown can match it back to a person.
const selected = computed(() => (props.value || '').replace(/%/g, ''))

function emitValue(email) {
  if (!email) return emit('change', '')
  emit('change', props.wildcard ? `%${email}%` : email)
}
</script>
