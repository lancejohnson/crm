<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs :items="[{ label: __('Practice') }]" />
    </template>
    <template #right-header>
      <Button
        v-if="canManage"
        variant="solid"
        :label="__('New set')"
        iconLeft="plus"
        @click="openCreate"
      />
    </template>
  </LayoutHeader>

  <div class="flex-1 overflow-y-auto px-3 pb-4 sm:px-5">
    <p class="mt-3 max-w-2xl text-sm text-ink-gray-5">
      {{ __('Same comps map as a real lead. Your picks stay on this run — they never rewrite a live deal.') }}
    </p>

    <div v-if="!available && !loading" class="mt-8 text-sm text-ink-gray-5">
      {{ __('Practice is not set up on this site yet.') }}
    </div>

    <div
      v-else-if="sets.length"
      class="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3"
    >
      <button
        v-for="s in sets"
        :key="s.name"
        class="flex flex-col gap-2 rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3 text-left shadow-sm hover:bg-surface-gray-1"
        @click="$router.push({ name: 'PracticeSet', params: { setId: s.name } })"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="truncate font-medium text-ink-gray-9">{{ s.title }}</div>
          <Badge
            v-if="!s.is_active"
            :label="__('Paused')"
            variant="subtle"
            theme="gray"
          />
        </div>
        <div class="text-sm text-ink-gray-5">
          {{ __('{0} {1}', [s.property_count, s.property_count === 1 ? __('property') : __('properties')]) }}
          <template v-if="s.time_limit_min">
            · {{ __('{0} min', [s.time_limit_min]) }}
          </template>
          <template v-else> · {{ __('Untimed') }}</template>
        </div>
        <div v-if="s.my_attempt" class="text-xs text-ink-gray-5">
          {{ lastLabel(s.my_attempt) }}
        </div>
      </button>
    </div>

    <div
      v-else-if="!loading"
      class="mt-12 flex flex-col items-center gap-2 text-ink-gray-5"
    >
      <div class="text-lg font-medium text-ink-gray-7">{{ __('No practice sets yet') }}</div>
      <div class="text-sm">
        {{ __('A set is a list of properties to comp, with an optional time limit.') }}
      </div>
      <Button
        v-if="canManage"
        class="mt-2"
        variant="solid"
        :label="__('Create a set')"
        @click="openCreate"
      />
    </div>
  </div>

  <Dialog v-model="showCreate" :options="{ title: __('New practice set') }">
    <template #body-content>
      <div class="flex flex-col gap-3">
        <FormControl v-model="draft.title" type="text" :label="__('Name')" :placeholder="__('Week-1 comps test')" />
        <FormControl
          v-model="draft.time_limit_min"
          type="number"
          :label="__('Time limit (minutes)')"
          :placeholder="__('30 — leave 0 for untimed')"
        />
        <FormControl v-model="draft.notes" type="textarea" :label="__('Notes')" />
      </div>
    </template>
    <template #actions>
      <Button
        class="w-full"
        variant="solid"
        :label="__('Create')"
        :loading="creating"
        @click="createSet"
      />
    </template>
  </Dialog>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import {
  Badge,
  Breadcrumbs,
  Button,
  Dialog,
  FormControl,
  call,
  createResource,
  toast,
} from 'frappe-ui'
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const showCreate = ref(false)
const creating = ref(false)
const draft = reactive({ title: '', time_limit_min: 30, notes: '' })

const list = createResource({
  url: 'crm.api.practice.list_sets',
  auto: true,
})

const available = computed(() => list.data?.available !== false)
const canManage = computed(() => list.data?.can_manage)
const sets = computed(() => list.data?.sets || [])
const loading = computed(() => list.loading)

function fmtDuration(sec) {
  sec = Math.max(0, Math.floor(Number(sec) || 0))
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function lastLabel(att) {
  if (att.status === 'In Progress') return __('In progress — {0}', [fmtDuration(att.elapsed_seconds)])
  if (att.status === 'Timed Out') return __('Timed out · {0}', [fmtDuration(att.elapsed_seconds)])
  return __('Last run {0}', [fmtDuration(att.elapsed_seconds)])
}

function openCreate() {
  draft.title = ''
  draft.time_limit_min = 30
  draft.notes = ''
  showCreate.value = true
}

async function createSet() {
  creating.value = true
  try {
    const res = await call('crm.api.practice.save_set', {
      title: draft.title,
      time_limit_min: Number(draft.time_limit_min) || 0,
      notes: draft.notes,
      is_active: 1,
    })
    showCreate.value = false
    router.push({ name: 'PracticeSet', params: { setId: res.name } })
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not create the set.'))
  } finally {
    creating.value = false
  }
}
</script>
