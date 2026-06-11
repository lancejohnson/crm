<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="[{ label: 'Sequences', route: { name: 'Sequences' } }]" />
    </template>
    <template #right-header>
      <Button variant="solid" label="Create" iconLeft="plus" @click="showCreate = true" />
    </template>
  </LayoutHeader>
  <div class="flex-1 overflow-y-auto px-3 pb-2 sm:px-5 sm:pb-3">
    <div v-if="sequences.data?.length" class="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3 sm:gap-4">
      <div
        v-for="seq in sequences.data"
        :key="seq.name"
        class="group flex cursor-pointer flex-col gap-3 rounded-lg border px-5 py-4 shadow-sm hover:bg-surface-menu-bar"
        @click="$router.push({ name: 'Sequence', params: { sequenceId: seq.name } })"
      >
        <div class="flex items-center justify-between">
          <div class="truncate text-lg font-medium text-ink-gray-9">{{ seq.name }}</div>
          <Dropdown
            :options="[{ label: 'Delete', icon: 'trash-2', onClick: () => deleteSequence(seq.name) }]"
          >
            <Button icon="more-horizontal" variant="ghosted" class="hover:bg-surface-white" @click.stop />
          </Dropdown>
        </div>
        <div class="flex items-center justify-between text-sm text-ink-gray-5">
          <Badge :theme="seq.enabled ? 'green' : 'gray'" :label="seq.enabled ? 'Enabled' : 'Disabled'" />
          <div>{{ timeAgo(seq.modified) }}</div>
        </div>
      </div>
    </div>
    <div v-else-if="!sequences.loading" class="flex h-full flex-col items-center justify-center gap-2 text-ink-gray-5">
      <div class="text-lg font-medium">No sequences yet</div>
      <div class="text-sm">Create a sequence to automate emails, call tasks, and texts.</div>
      <Button class="mt-2" variant="solid" label="Create Sequence" @click="showCreate = true" />
    </div>
  </div>

  <Dialog v-model="showCreate" :options="{ title: 'New Sequence' }">
    <template #body-content>
      <FormControl v-model="newName" type="text" label="Sequence Name" placeholder="e.g. Seller Follow-up" />
    </template>
    <template #actions>
      <Button class="w-full" variant="solid" label="Create" :loading="creating" @click="createSequence" />
    </template>
  </Dialog>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import { timeAgo } from '@/utils'
import {
  Breadcrumbs,
  Button,
  Badge,
  Dialog,
  Dropdown,
  FormControl,
  createListResource,
  call,
  toast,
} from 'frappe-ui'
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const showCreate = ref(false)
const newName = ref('')
const creating = ref(false)

const sequences = createListResource({
  doctype: 'CRM Sequence',
  fields: ['name', 'enabled', 'modified'],
  orderBy: 'modified desc',
  pageLength: 99,
  auto: true,
})

async function createSequence() {
  if (!newName.value) return
  creating.value = true
  try {
    const doc = await call('frappe.client.insert', {
      doc: {
        doctype: 'CRM Sequence',
        sequence_name: newName.value,
        enabled: 1,
        steps: [{ step_type: 'Email', wait_value: 0, wait_unit: 'Days', subject: '', message: '' }],
      },
    })
    showCreate.value = false
    newName.value = ''
    router.push({ name: 'Sequence', params: { sequenceId: doc.name } })
  } catch (e) {
    toast.error(e.messages?.[0] || 'Failed to create sequence')
  } finally {
    creating.value = false
  }
}

async function deleteSequence(name) {
  try {
    await call('frappe.client.delete', { doctype: 'CRM Sequence', name })
    sequences.reload()
  } catch (e) {
    toast.error(e.messages?.[0] || 'Failed to delete (active enrollments may exist)')
  }
}
</script>
