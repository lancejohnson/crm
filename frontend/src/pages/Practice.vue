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
        :loading="creating"
        @click="createSet"
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

    <div v-else-if="sets.length" class="mt-4">
      <div class="flex border-b border-outline-gray-1 py-1.5 text-xs font-medium text-ink-gray-5">
        <span class="min-w-0 flex-1">{{ __('Set') }}</span>
        <span class="w-28 shrink-0">{{ __('Properties') }}</span>
        <span class="w-24 shrink-0">{{ __('Time') }}</span>
        <span class="w-44 shrink-0">{{ __('Last run') }}</span>
      </div>
      <button
        v-for="s in sets"
        :key="s.name"
        class="flex w-full items-center border-b border-outline-gray-1 py-2.5 text-left text-sm hover:bg-surface-gray-1"
        @click="$router.push({ name: 'PracticeSet', params: { setId: s.name } })"
      >
        <span class="flex min-w-0 flex-1 items-center gap-2 truncate font-medium text-ink-gray-9">
          {{ s.title }}
          <Badge
            v-if="!s.is_active"
            :label="__('Paused')"
            variant="subtle"
            theme="gray"
          />
        </span>
        <span class="w-28 shrink-0 text-ink-gray-6">
          {{ s.property_count }}
        </span>
        <span class="w-24 shrink-0 text-ink-gray-6">
          {{ s.time_limit_min ? __('{0} min', [s.time_limit_min]) : __('Untimed') }}
        </span>
        <span class="w-44 shrink-0 text-ink-gray-5">
          {{ s.my_attempt ? lastLabel(s.my_attempt) : '—' }}
        </span>
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
        :loading="creating"
        @click="createSet"
      />
    </div>
  </div>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import {
  Badge,
  Breadcrumbs,
  Button,
  call,
  createResource,
  toast,
} from 'frappe-ui'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const creating = ref(false)

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

async function createSet() {
  creating.value = true
  try {
    const res = await call('crm.api.practice.save_set', {
      title: __('New set'),
      time_limit_min: 30,
      is_active: 1,
    })
    router.push({ name: 'PracticeSet', params: { setId: res.name } })
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not create the set.'))
  } finally {
    creating.value = false
  }
}
</script>
