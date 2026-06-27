<template>
  <SettingsLayoutBase
    :title="__('Notifications')"
    :description="
      __(
        'Choose how you want to be notified when activity happens on your leads’ e-sign agreements.',
      )
    "
  >
    <template #content>
      <div class="flex flex-col gap-8">
        <!-- Channels -->
        <section class="flex flex-col gap-4">
          <div class="flex items-center gap-2 h-7">
            <div class="text-base font-semibold text-ink-gray-9">
              {{ __('How to notify me') }}
            </div>
            <Badge
              v-if="isDirty"
              variant="subtle"
              theme="orange"
              size="sm"
              :label="__('Not Saved')"
            />
          </div>

          <label class="flex items-center justify-between gap-4 cursor-pointer">
            <div class="flex flex-col gap-1">
              <span class="text-base font-medium text-ink-gray-8">
                {{ __('Text me') }}
              </span>
              <span class="text-p-sm text-ink-gray-6">
                {{ __('Send a text message for agreement activity.') }}
              </span>
            </div>
            <Switch v-model="draft.text" />
          </label>

          <div v-if="draft.text" class="flex items-center justify-between gap-4 pl-0">
            <div class="flex flex-col gap-1">
              <span class="text-base font-medium text-ink-gray-8">
                {{ __('Text me at') }}
              </span>
              <span class="text-p-sm text-ink-gray-6">
                {{ __('Leave blank to use your Quo number.') }}
              </span>
            </div>
            <FormControl
              v-model="draft.text_number"
              type="text"
              class="w-44"
              :placeholder="quoNumber || __('e.g. (952) 395-3833')"
            />
          </div>

          <label class="flex items-center justify-between gap-4 cursor-pointer">
            <div class="flex flex-col gap-1">
              <span class="text-base font-medium text-ink-gray-8">
                {{ __('Email me') }}
              </span>
              <span class="text-p-sm text-ink-gray-6">
                {{ __('Send an email for agreement activity.') }}
              </span>
            </div>
            <Switch v-model="draft.email" />
          </label>
        </section>

        <!-- Events -->
        <section class="flex flex-col gap-4">
          <div class="text-base font-semibold text-ink-gray-9">
            {{ __('Notify me when an agreement is…') }}
          </div>
          <FormControl
            v-model="draft.viewed"
            type="checkbox"
            :label="__('Viewed by a signer')"
          />
          <FormControl
            v-model="draft.started"
            type="checkbox"
            :label="__('Started')"
          />
          <FormControl
            v-model="draft.signed"
            type="checkbox"
            :label="__('Signed / completed')"
          />
        </section>

        <div class="flex">
          <Button
            variant="solid"
            :label="__('Save')"
            :loading="saving"
            :disabled="!isDirty"
            @click="save"
          />
        </div>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup>
import SettingsLayoutBase from '@/components/Layouts/SettingsLayoutBase.vue'
import { usersStore } from '@/stores/users'
import { Badge, Button, FormControl, Switch, call, toast } from 'frappe-ui'
import { computed, reactive, ref } from 'vue'

const { getUser } = usersStore()

// Defaults mirror crm/api/notification_prefs.py DEFAULT_PREFS (opt-out).
const DEFAULT_PREFS = {
  text: true,
  email: true,
  viewed: true,
  started: true,
  signed: true,
  text_number: '',
}

const quoNumber = computed(() => getUser('sessionUser')?.custom_quo_number || '')

function loadPrefs() {
  const raw = getUser('sessionUser')?.custom_notification_prefs
  let stored = {}
  if (raw) {
    try {
      stored = JSON.parse(raw) || {}
    } catch {
      stored = {}
    }
  }
  return { ...DEFAULT_PREFS, ...stored }
}

const draft = reactive(loadPrefs())
const saving = ref(false)

const isDirty = computed(
  () => JSON.stringify(draft) !== JSON.stringify(loadPrefs()),
)

async function save() {
  saving.value = true
  try {
    const stored = await call(
      'crm.api.notification_prefs.set_notification_prefs',
      { prefs: JSON.stringify(draft) },
    )
    getUser('sessionUser').custom_notification_prefs = JSON.stringify(stored)
    toast.success(__('Notification preferences saved'))
  } catch (e) {
    toast.error(__('Could not save notification preferences'))
  } finally {
    saving.value = false
  }
}
</script>
