<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs
        :items="[{ label: 'Text Messages', route: { name: 'Text Messages' } }]"
      />
    </template>
    <template #right-header>
      <Button
        variant="solid"
        :label="__('New Message')"
        iconLeft="plus"
        @click="showNew = true"
      />
    </template>
  </LayoutHeader>

  <div class="flex flex-1 overflow-hidden">
    <!-- conversation list -->
    <div
      class="flex w-72 shrink-0 flex-col overflow-y-auto border-r sm:w-80"
    >
      <div
        v-if="conversations.loading && !conversations.data"
        class="p-4 text-sm text-ink-gray-5"
      >
        {{ __('Loading...') }}
      </div>
      <div
        v-else-if="!conversations.data?.length"
        class="p-4 text-sm text-ink-gray-5"
      >
        {{ __('No conversations yet.') }}
      </div>
      <button
        v-for="c in conversations.data"
        :key="c.lead"
        class="flex flex-col gap-1 border-b px-4 py-3 text-left hover:bg-surface-menu-bar"
        :class="selected === c.lead ? 'bg-surface-menu-bar' : ''"
        @click="selectConversation(c.lead)"
      >
        <div class="flex items-center justify-between gap-2">
          <div class="truncate font-medium text-ink-gray-8">
            {{ c.lead_name }}
          </div>
          <div class="shrink-0 text-xs text-ink-gray-4">
            {{ timeAgo(c.last_date) }}
          </div>
        </div>
        <div class="truncate text-sm text-ink-gray-5">
          <span v-if="c.last_direction === 'Outgoing'" class="text-ink-gray-4">
            {{ __('You:') }}
          </span>
          {{ c.last_message }}
        </div>
      </button>
    </div>

    <!-- active thread -->
    <div class="flex flex-1 flex-col overflow-hidden">
      <template v-if="selected">
        <div class="flex items-center justify-between border-b px-4 py-3">
          <div class="truncate font-medium text-ink-gray-8">
            {{ selectedName }}
          </div>
          <Button
            :label="__('Open Lead')"
            @click="
              $router.push({ name: 'Lead', params: { leadId: selected } })
            "
          />
        </div>
        <div class="flex flex-1 flex-col overflow-y-auto py-3">
          <SMSArea
            v-if="messages.data?.length"
            class="px-4"
            :messages="messages.data"
            :contactName="selectedName"
            :contactImage="selectedImage"
          />
          <div
            v-else-if="!messages.loading"
            class="flex flex-1 items-center justify-center text-sm text-ink-gray-5"
          >
            {{ __('No messages yet. Say hello!') }}
          </div>
        </div>
        <SMSBox
          v-model="threadDoc"
          v-model:sms="messages"
          doctype="CRM Lead"
          class="border-t"
        />
      </template>
      <div
        v-else
        class="flex flex-1 items-center justify-center text-sm text-ink-gray-5"
      >
        {{ __('Select a conversation or start a new message.') }}
      </div>
    </div>
  </div>

  <Dialog v-model="showNew" :options="{ title: __('New Message') }">
    <template #body-content>
      <div class="mb-1.5 text-xs text-ink-gray-5">{{ __('Lead') }}</div>
      <Link
        v-model="newLead"
        doctype="CRM Lead"
        :placeholder="__('Search leads...')"
      />
    </template>
    <template #actions>
      <Button
        class="w-full"
        variant="solid"
        :label="__('Start Conversation')"
        :disabled="!newLead"
        @click="startNew"
      />
    </template>
  </Dialog>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import SMSArea from '@/components/Activities/SMSArea.vue'
import SMSBox from '@/components/Activities/SMSBox.vue'
import Link from '@/components/Controls/Link.vue'
import { timeAgo } from '@/utils'
import { globalStore } from '@/stores/global'
import { Breadcrumbs, Button, Dialog, createResource } from 'frappe-ui'
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

const { $socket } = globalStore()

const selected = ref('')
const threadDoc = ref({ name: '' })
const showNew = ref(false)
const newLead = ref('')

const conversations = createResource({
  url: 'crm.api.sms.get_sms_conversations',
  auto: true,
})

const messages = createResource({
  url: 'crm.api.sms.get_sms_messages',
  makeParams() {
    return { reference_doctype: 'CRM Lead', reference_name: selected.value }
  },
})

const selectedName = computed(() => {
  const c = conversations.data?.find((x) => x.lead === selected.value)
  return c?.lead_name || selected.value
})

const selectedImage = computed(() => {
  const c = conversations.data?.find((x) => x.lead === selected.value)
  return c?.image || ''
})

function selectConversation(lead) {
  if (!lead) return
  selected.value = lead
  threadDoc.value = { name: lead }
  messages.reload()
}

function startNew() {
  if (!newLead.value) return
  showNew.value = false
  selectConversation(newLead.value)
  newLead.value = ''
}

onMounted(() => {
  $socket.on('quo_message', () => {
    conversations.reload()
    if (selected.value) messages.reload()
  })
})

onBeforeUnmount(() => {
  $socket.off('quo_message')
})
</script>
