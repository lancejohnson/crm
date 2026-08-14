<template>
  <SettingsLayoutBase
    v-if="user.doc"
    :title="__('Preferences')"
    :description="
      __(
        'Choose how you want to use the application by setting your preferences.',
      )
    "
  >
    <template #content>
      <div>
        <div class="flex items-center justify-between">
          <div class="flex gap-2 items-center">
            <div class="text-base font-semibold text-ink-gray-9">
              {{ __('Appearance') }}
            </div>
          </div>
        </div>
        <div class="flex flex-col gap-4 my-6">
          <div class="flex flex-col gap-1">
            <span class="text-base font-medium text-ink-gray-8">
              {{ __('Theme') }}
            </span>
            <span class="text-p-sm text-ink-gray-6">
              {{ __('Switch between light, dark, or system theme') }}
            </span>
          </div>
          <ThemeSwitcher
            :logo="brand.logo || CRMLogo"
            :name="brand.name || 'CRM'"
          />
        </div>
        <div class="flex items-center justify-between">
          <div class="flex gap-2 items-center h-7">
            <div class="text-base font-semibold text-ink-gray-9">
              {{ __('Language & Time') }}
            </div>
            <Badge
              v-if="isDirty"
              :variant="'subtle'"
              :theme="'orange'"
              size="sm"
              :label="__('Not Saved')"
            />
          </div>
          <Button
            v-if="isDirty"
            :label="__('Save')"
            :loading="user.save.loading"
            @click="save()"
          />
        </div>
        <div class="flex items-center justify-between mt-6">
          <div class="flex flex-col gap-1">
            <span class="text-base font-medium text-ink-gray-8">
              {{ __('Language') }}
            </span>
            <span class="text-p-sm text-ink-gray-6">
              {{ __('Change language of the application.') }}
            </span>
          </div>
          <Link v-model="user.doc.language" doctype="Language" class="w-40" />
        </div>
        <div class="flex items-center justify-between mt-6">
          <div class="flex flex-col gap-1">
            <span class="text-base font-medium text-ink-gray-8">
              {{ __('Timezone') }}
            </span>
            <span class="text-p-sm text-ink-gray-6">
              {{ __('Change timezone of the application.') }}
            </span>
          </div>
          <Combobox
            v-model="user.doc.time_zone"
            class="w-40"
            :options="getTimezoneOptions()"
          />
        </div>

        <!--
          Saved on change, not via the Save button above. That button submits the
          User document; this preference is a Frappe user default and has nothing
          to do with that doc, so putting it behind the same button would make
          "Not Saved" lie in both directions.
        -->
        <div class="mt-8 flex items-center justify-between">
          <div class="flex gap-2 items-center h-7">
            <div class="text-base font-semibold text-ink-gray-9">
              {{ __('Leads') }}
            </div>
          </div>
        </div>
        <div class="flex items-center justify-between mt-6">
          <div class="flex flex-col gap-1 pr-4">
            <span class="text-base font-medium text-ink-gray-8">
              {{ __('Opening a lead from the board') }}
            </span>
            <span class="text-p-sm text-ink-gray-6">
              {{
                __(
                  'A quick view opens over the Kanban so you keep your place in the column. The full page has everything, including comps, photos and agreements.',
                )
              }}
            </span>
          </div>
          <!--
            The width has to be on a WRAPPER. frappe-ui's Select puts `w-full` on
            its own trigger, which beats a `w-40` passed in as a class, so the
            control grew to fill the row: it pushed past the panel's right edge,
            squeezed the label column to ~90px (wrapping the description one word
            per line) and gave the whole Preferences pane a horizontal scrollbar
            that clipped every label on the left. The Language/Timezone rows
            above get away with `class="w-40"` because Link and Combobox do not
            force their own width.
          -->
          <div class="w-40 shrink-0">
            <Select v-model="openMode" :options="openModeOptions" />
          </div>
        </div>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup>
import CRMLogo from '@/components/Icons/CRMLogo.vue'
import ThemeSwitcher from '@/components/Settings/ThemeSwitcher.vue'
import SettingsLayoutBase from '@/components/Layouts/SettingsLayoutBase.vue'
import Link from '@/components/Controls/Link.vue'
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'
import { getSettings } from '@/stores/settings'
import {
  Combobox,
  Badge,
  Select,
  toast,
  createResource,
  createDocumentResource,
} from 'frappe-ui'
import { ref, computed, inject, onMounted } from 'vue'
import {
  LEAD_OPEN_MODAL,
  LEAD_OPEN_PAGE,
  loadLeadOpenMode,
  saveLeadOpenMode,
  useLeadOpenMode,
} from '@/composables/leadOpenMode'

const refreshRequired = ref(false)

// NOTE the 'ask' sentinel is a non-empty string. reka-ui (which frappe-ui's
// Select wraps) reserves '' for its placeholder and SILENTLY DROPS any item
// declared with it, so a `value: ''` option simply never renders -- the same
// trap the comps recency filter hit. '' is still what the backend stores for
// "not asked"; it is mapped at the boundary below.
const ASK_AGAIN = 'ask'
const leadOpenMode = useLeadOpenMode()
const openMode = computed({
  get: () => leadOpenMode.value || ASK_AGAIN,
  set: (value) => saveLeadOpenMode(value === ASK_AGAIN ? '' : value),
})
const openModeOptions = [
  { label: __('Quick view'), value: LEAD_OPEN_MODAL },
  { label: __('Full page'), value: LEAD_OPEN_PAGE },
  { label: __('Ask me'), value: ASK_AGAIN },
]
onMounted(() => loadLeadOpenMode())

const { user: sessionUser } = inject('session')

const { brand } = getSettings()
const user = createDocumentResource({ doctype: 'User', name: sessionUser })

function save() {
  refreshRequired.value =
    user.doc.language !== user.originalDoc?.language ||
    user.doc.time_zone !== user.originalDoc?.time_zone

  user.save.submit(null, {
    onSuccess: () => {
      toast.success(__('Preferences Updated Successfully'))
      if (refreshRequired.value) {
        window.location.reload()
      }
    },
    onError: (err) => {
      toast.error(err.message + ': ' + err.messages[0])
    },
  })
}

const isDirty = computed(() => {
  return JSON.stringify(user.doc) !== JSON.stringify(user.originalDoc)
})

const timeZones = createResource({
  url: 'frappe.core.doctype.user.user.get_timezones',
  cache: 'TimeZones',
  auto: true,
})

function getTimezoneOptions() {
  return timeZones.data?.timezones.map((tz) => ({ label: tz, value: tz })) || []
}

useKeyboardShortcuts({
  ignoreTyping: false,
  shortcuts: [
    {
      match: (e) => (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's',
      action: () => {
        if (isDirty.value) {
          save()
        }
      },
    },
  ],
})
</script>
