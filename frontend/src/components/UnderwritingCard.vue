<template>
  <div class="border-t px-5 py-3">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2 text-base font-medium text-ink-gray-8">
        <DetailsIcon class="size-4 text-ink-gray-7" />
        {{ __('Underwriting') }}
      </div>
      <Button
        :tooltip="latest ? __('Open underwriting sheet') : __('Create underwriting sheet')"
        :icon="latest ? 'external-link' : 'plus'"
        variant="ghost"
        @click="latest ? openSheet(latest) : emit('create')"
      />
    </div>

    <div v-if="latest" class="mt-2.5 flex flex-col gap-1.5 text-sm">
      <button
        class="flex items-center gap-1.5 text-left text-ink-blue-link hover:underline"
        @click="openSheet(latest)"
      >
        <FeatherIcon name="external-link" class="size-3.5 shrink-0" />
        <span class="truncate">{{ latest.address || __('Open sheet') }}</span>
      </button>

      <div class="mt-1 text-xs text-ink-gray-5">
        {{ __('Created by') }}
        <span class="text-ink-gray-7">{{
          latest.created_by_name || latest.created_by_user
        }}</span>
        · {{ formatDate(latest.workbook_created_at || latest.creation, '', true) }}
      </div>
    </div>

    <div v-else class="mt-2 text-sm text-ink-gray-5">
      {{ __('No underwriting sheet yet.') }}
    </div>
  </div>
</template>

<script setup>
import DetailsIcon from '@/components/Icons/DetailsIcon.vue'
import { formatDate } from '@/utils'
import { globalStore } from '@/stores/global'
import { Button, FeatherIcon, createResource } from 'frappe-ui'
import { computed, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  lead: { type: String, required: true },
})

const emit = defineEmits(['create'])

const { $socket } = globalStore()

const workbooks = createResource({
  url: 'crm.api.underwriting.get_underwriting_workbooks',
  cache: ['underwriting_workbooks', props.lead],
  params: { lead: props.lead },
  auto: true,
})

const latest = computed(() => workbooks.data?.[0] || null)

function openSheet(wb) {
  if (wb?.sheet_url) window.open(wb.sheet_url, '_blank', 'noopener')
}

function onUnderwriting(data) {
  if (
    data.reference_doctype === 'CRM Lead' &&
    data.reference_docname === props.lead
  ) {
    workbooks.reload()
  }
}

onMounted(() => $socket.on('crm_underwriting', onUnderwriting))
onBeforeUnmount(() => $socket.off('crm_underwriting', onUnderwriting))
</script>
