<template>
  <div class="border-t px-5 py-3">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2 text-base font-medium text-ink-gray-8">
        <FeatherIcon name="file-text" class="size-4 text-ink-gray-7" />
        {{ __('Agreements') }}
      </div>
      <Button
        :tooltip="__('Create purchase agreement')"
        icon="plus"
        variant="ghost"
        @click="emit('create')"
      />
    </div>

    <div v-if="agreements.length" class="mt-2.5 flex flex-col gap-3">
      <div
        v-for="a in agreements"
        :key="a.name"
        class="flex flex-col gap-1.5 rounded-md bg-surface-gray-2 px-3 py-2.5 text-sm"
      >
        <div class="flex items-center justify-between gap-2">
          <div class="truncate text-ink-gray-8">{{ a.template_title }}</div>
          <Badge :theme="statusTheme(a)" variant="subtle" :label="statusLabel(a)" />
        </div>

        <div class="flex items-center gap-1.5 text-xs text-ink-gray-6">
          <span>{{ a.signed_count || 0 }}/{{ a.total_signers || 0 }} {{ __('signed') }}</span>
          <span v-if="a.last_event" class="text-ink-gray-4">·</span>
          <span v-if="a.last_event" class="truncate">{{ eventLabel(a.last_event) }}</span>
        </div>

        <a
          v-if="a.is_signed"
          :href="signedUrl(a)"
          class="mt-0.5 block"
        >
          <Button class="w-full" size="sm" theme="green" :label="__('Download signed PDF')">
            <template #prefix>
              <FeatherIcon name="download" class="size-3.5" />
            </template>
          </Button>
        </a>

        <div class="mt-0.5 flex items-center gap-2">
          <Button
            class="flex-1"
            size="sm"
            :label="__('Open buyer link')"
            @click="openLink(a.buyer_link)"
          />
          <Button size="sm" icon="copy" @click="copy(a.buyer_link)" />
        </div>

        <div v-if="a.seller_links?.length" class="flex flex-col gap-1">
          <div
            v-for="sl in a.seller_links"
            :key="sl.link"
            class="flex items-center justify-between gap-2 text-xs text-ink-gray-6"
          >
            <span class="truncate">{{ sl.name }}</span>
            <div class="flex shrink-0 items-center gap-2">
              <button class="text-ink-gray-5 hover:text-ink-gray-8" @click="openLink(sl.link)">
                {{ __('open') }}
              </button>
              <button class="text-ink-gray-5 hover:text-ink-gray-8" @click="copy(sl.link)">
                {{ __('copy') }}
              </button>
            </div>
          </div>
        </div>

        <button
          class="self-start text-xs font-medium text-ink-gray-6 hover:text-ink-gray-9"
          @click="copyAll(a)"
        >
          {{ __('Copy all links') }}
        </button>

        <div class="text-xs text-ink-gray-4">
          {{ a.created_by_name || a.owner }} · {{ formatDate(a.creation, '', true) }}
        </div>
      </div>
    </div>

    <div v-else class="mt-2 text-sm text-ink-gray-5">
      {{ __('No agreements yet.') }}
    </div>
  </div>
</template>

<script setup>
import { formatDate } from '@/utils'
import { globalStore } from '@/stores/global'
import { Button, Badge, FeatherIcon, createResource, toast } from 'frappe-ui'
import { computed, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  lead: { type: String, required: true },
})
const emit = defineEmits(['create'])

const { $socket } = globalStore()

const agreementsResource = createResource({
  url: 'crm.api.agreement.get_agreements',
  cache: ['agreements', props.lead],
  params: { lead: props.lead },
  auto: true,
})

const agreements = computed(() => agreementsResource.data || [])

// Document status → a colored badge (Documenso + DocuSeal statuses).
function statusLabel(a) {
  const s = (a.agreement_status || '').toUpperCase()
  if (s === 'COMPLETED') return __('Completed')
  if (s === 'REJECTED' || s === 'DECLINED') return __('Declined')
  if (s === 'CANCELLED') return __('Cancelled')
  if (s === 'EXPIRED') return __('Expired')
  if (a.signed_count && a.total_signers && a.signed_count >= a.total_signers)
    return __('Completed')
  if (a.signed_count > 0) return __('Signing')
  return __('Awaiting')
}
function statusTheme(a) {
  const s = (a.agreement_status || '').toUpperCase()
  if (s === 'COMPLETED') return 'green'
  if (['REJECTED', 'CANCELLED', 'DECLINED', 'EXPIRED'].includes(s)) return 'red'
  if (a.signed_count > 0) return 'blue'
  return 'orange'
}
// Documenso `DOCUMENT_SIGNED` or DocuSeal `form.completed` → "Signed".
function eventLabel(ev) {
  return String(ev)
    .replace(/^DOCUMENT_/, '')
    .replace(/^(form|submission)\./, '')
    .replace(/[_.]/g, ' ')
    .toLowerCase()
    .replace(/^\w/, (c) => c.toUpperCase())
}

function copy(text) {
  if (!text) return
  navigator.clipboard?.writeText(text)
  toast.success(__('Link copied'))
}
function openLink(url) {
  if (url) window.open(url, '_blank', 'noopener,noreferrer')
}

// Proxy endpoint that streams the fully-signed PDF (the backend holds the
// Documenso token; the raw Documenso URL is an internal, expiring MinIO link).
function signedUrl(a) {
  return `/api/method/crm.api.agreement.download_signed_agreement?agreement=${encodeURIComponent(a.name)}`
}

// A labeled, paste-ready block of every link for an email/text.
function copyAll(a) {
  const lines = [`Buyer (review & sign): ${a.buyer_link}`]
  for (const sl of a.seller_links || []) {
    lines.push(`${sl.name} (sign): ${sl.link}`)
  }
  navigator.clipboard?.writeText(lines.join('\n'))
  toast.success(__('All links copied'))
}

function onEsign(data) {
  if (
    data.reference_doctype === 'CRM Lead' &&
    data.reference_docname === props.lead
  ) {
    agreementsResource.reload()
  }
}
onMounted(() => $socket.on('crm_esign', onEsign))
onBeforeUnmount(() => $socket.off('crm_esign', onEsign))
</script>
