<template>
  <Dialog v-model="show" :options="{ title: __('Underwriting Sheet') }">
    <template #body-content>
      <div class="flex flex-col gap-4 text-base">
        <!-- Success / existing view: the sheet is ready, here's the link. -->
        <template v-if="result">
          <div
            class="flex items-start gap-2.5 rounded-md bg-surface-green-2 px-3 py-2.5 text-ink-gray-8"
          >
            <FeatherIcon name="check-circle" class="mt-0.5 size-4 shrink-0 text-ink-green-3" />
            <div>
              <div class="font-medium">
                {{ result.existing ? __('Underwriting sheet already exists.') : __('Underwriting sheet created.') }}
              </div>
              <div class="mt-0.5 text-sm text-ink-gray-6">
                {{ __('Pre-filled with the date, your name, and the Zillow link — ready to go.') }}
              </div>
            </div>
          </div>

          <div v-if="address" class="flex flex-col gap-0.5">
            <div class="text-xs text-ink-gray-5">{{ __('Property') }}</div>
            <div class="text-ink-gray-8">{{ address }}</div>
          </div>

          <div class="flex gap-2">
            <Button
              class="flex-1"
              variant="solid"
              :label="__('Open sheet')"
              icon-left="external-link"
              @click="openSheet"
            />
            <Button
              :tooltip="__('Copy link')"
              icon="link"
              @click="copyLink"
            />
          </div>
        </template>

        <!-- Confirm view: explain what the button does. -->
        <template v-else>
          <div
            class="flex items-start gap-2.5 rounded-md bg-surface-gray-2 px-3 py-2.5 text-ink-gray-6"
          >
            <SheetIcon class="mt-0.5 size-4 shrink-0 text-ink-gray-7" />
            <div>
              <div class="font-medium text-ink-gray-8">
                {{ __('Create an underwriting sheet for this lead.') }}
              </div>
              <div class="mt-0.5 text-sm">
                {{ __('Copies the template into the shared Underwriting folder, names it after the address, and fills the date, your name, and the Zillow link.') }}
              </div>
            </div>
          </div>

          <div v-if="address" class="flex flex-col gap-0.5">
            <div class="text-xs text-ink-gray-5">{{ __('Property') }}</div>
            <div class="text-ink-gray-8">{{ address }}</div>
          </div>
          <div
            v-else
            class="rounded-md bg-surface-amber-1 px-3 py-2 text-sm text-ink-amber-3"
          >
            {{ __('Set a property address first — the sheet is named after it.') }}
          </div>

          <ErrorMessage :message="error" />
        </template>
      </div>
    </template>

    <template v-if="!result" #actions>
      <Button
        class="w-full"
        variant="solid"
        :label="__('Create underwriting sheet')"
        :loading="loading"
        :disabled="!address"
        @click="createSheet"
      />
    </template>
  </Dialog>
</template>

<script setup>
import SheetIcon from '@/components/Icons/DetailsIcon.vue'
import { copyToClipboard } from '@/utils'
import {
  call,
  Dialog,
  Button,
  ErrorMessage,
  FeatherIcon,
  toast,
} from 'frappe-ui'
import { ref, computed, watch } from 'vue'

const props = defineProps({
  referenceDoc: { type: Object, default: () => ({}) },
  options: { type: Object, default: () => ({ afterCreate: () => {} }) },
})

const show = defineModel({ type: Boolean })

const loading = ref(false)
const error = ref(null)
// { sheet_url, existing } once a sheet exists or is created.
const result = ref(null)

const address = computed(() => props.referenceDoc?.property_address || '')

function leadName() {
  return props.referenceDoc?.name || ''
}

// On open, if a workbook already exists jump straight to the open view.
watch(
  show,
  async (open) => {
    if (!open) return
    error.value = null
    result.value = null
    const lead = leadName()
    if (!lead) return
    try {
      const rows = await call('crm.api.underwriting.get_underwriting_workbooks', {
        lead,
      })
      if (rows?.[0]) result.value = { ...rows[0], existing: true }
    } catch (e) {
      // non-fatal — the create path still works
    }
  },
  { immediate: true },
)

async function createSheet() {
  const lead = leadName()
  if (!lead || loading.value) return
  loading.value = true
  error.value = null
  try {
    result.value = await call(
      'crm.api.underwriting.create_underwriting_workbook',
      { lead },
    )
    toast.success(
      result.value.existing
        ? __('Opened the existing underwriting sheet')
        : __('Underwriting sheet created'),
    )
    props.options.afterCreate?.()
  } catch (e) {
    error.value =
      e.messages?.[0] || e.message || __('Failed to create underwriting sheet')
  } finally {
    loading.value = false
  }
}

function openSheet() {
  if (result.value?.sheet_url)
    window.open(result.value.sheet_url, '_blank', 'noopener')
}

function copyLink() {
  if (result.value?.sheet_url) copyToClipboard(result.value.sheet_url)
}
</script>
