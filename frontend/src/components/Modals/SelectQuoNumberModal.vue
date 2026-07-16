<template>
  <Dialog v-model="show" :options="{ title: __('Select your Quo number') }">
    <template #body-content>
      <div class="flex flex-col gap-3">
        <div class="text-base text-ink-gray-6">
          {{
            __(
              'Pick the Quo number you call and text from. It will be saved to your profile — texts you send will come from this number.',
            )
          }}
        </div>
        <div v-if="quoNumbers.loading" class="py-2 text-base text-ink-gray-5">
          {{ __('Loading numbers...') }}
        </div>
        <div v-else class="flex flex-col gap-2">
          <button
            v-for="n in quoNumbers.data || []"
            :key="n.number"
            class="flex items-center justify-between rounded-lg border px-3 py-2.5 text-left"
            :class="
              selected === n.number
                ? 'border-outline-gray-4 bg-surface-gray-2'
                : 'border-outline-gray-2 hover:bg-surface-gray-1'
            "
            @click="selected = n.number"
          >
            <div class="flex flex-col">
              <span class="text-base font-medium text-ink-gray-8">
                {{ formatPhone(n.number) }}
              </span>
              <span v-if="n.name" class="text-sm text-ink-gray-5">
                {{ n.name }}
              </span>
            </div>
            <FeatherIcon
              v-if="selected === n.number"
              name="check"
              class="h-4 w-4 text-ink-gray-8"
            />
          </button>
        </div>
        <ErrorMessage :message="error" />
      </div>
    </template>
    <template #actions>
      <Button
        class="w-full"
        variant="solid"
        :label="__('Save')"
        :loading="saving"
        :disabled="!selected"
        @click="save"
      />
    </template>
  </Dialog>
</template>

<script setup>
import { quoNumbers, formatPhone } from '@/composables/quoSender'
import { usersStore } from '@/stores/users'
import { call, Dialog, Button, ErrorMessage, FeatherIcon } from 'frappe-ui'
import { ref, watch } from 'vue'

const emit = defineEmits(['saved'])
const show = defineModel({ type: Boolean })

const selected = ref('')
const saving = ref(false)
const error = ref(null)

watch(
  show,
  (open) => {
    if (open) {
      error.value = null
      if (!quoNumbers.data && !quoNumbers.loading) quoNumbers.fetch()
    }
  },
  { immediate: true },
)

async function save() {
  if (!selected.value || saving.value) return
  saving.value = true
  error.value = null
  const { getUser } = usersStore()
  const me = getUser('sessionUser')
  try {
    await call('crm.api.sms.set_user_quo_number', {
      user: me?.name,
      number: selected.value,
    })
    // mirror into the users store so every surface sees the number immediately
    if (me) me.custom_quo_number = selected.value
    emit('saved', selected.value)
    show.value = false
  } catch (e) {
    error.value = e.messages?.[0] || __('Failed to save your Quo number')
  } finally {
    saving.value = false
  }
}
</script>
