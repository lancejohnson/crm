<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs
        :items="[
          { label: __('Practice'), route: { name: 'Practice' } },
          { label: set.title || setId },
        ]"
      />
    </template>
    <template #right-header>
      <div class="flex items-center gap-2">
        <Button
          v-if="canManage"
          :label="__('Save')"
          :loading="saving"
          @click="saveMeta"
        />
        <Button
          variant="solid"
          :label="resumeLabel"
          :disabled="!properties.length"
          :loading="starting"
          @click="start"
        />
      </div>
    </template>
  </LayoutHeader>

  <div class="flex min-h-0 flex-1 flex-col overflow-y-auto px-3 pb-6 sm:px-5">
    <div v-if="canManage" class="mt-3 grid max-w-3xl grid-cols-1 gap-3 sm:grid-cols-2">
      <FormControl v-model="form.title" type="text" :label="__('Name')" />
      <FormControl
        v-model="form.time_limit_min"
        type="number"
        :label="__('Time limit (minutes)')"
      />
      <FormControl
        class="sm:col-span-2"
        v-model="form.notes"
        type="textarea"
        :label="__('Notes')"
      />
      <label class="flex items-center gap-2 text-sm text-ink-gray-7">
        <FormControl type="checkbox" v-model="form.is_active" />
        {{ __('Active — setters can take this set') }}
      </label>
    </div>
    <p v-else-if="set.notes" class="mt-3 max-w-2xl text-sm text-ink-gray-5">
      {{ set.notes }}
    </p>
    <p class="mt-2 text-sm text-ink-gray-5">
      {{ __('{0} {1}', [properties.length, properties.length === 1 ? __('property') : __('properties')]) }}
      <template v-if="set.time_limit_min"> · {{ __('{0} min', [set.time_limit_min]) }}</template>
    </p>

    <div class="mt-5 max-w-3xl">
      <div class="mb-2 flex items-center justify-between">
        <h2 class="text-base font-medium text-ink-gray-8">{{ __('Properties') }}</h2>
      </div>
      <div v-if="canManage" class="mb-3">
        <Autocomplete
          :key="addKey"
          :options="leadOptions"
          :placeholder="__('Add a lead by name or address…')"
          @update:query="onLeadQuery"
          @update:modelValue="addLead"
        />
      </div>
      <div v-if="!properties.length" class="text-sm text-ink-gray-5">
        {{ canManage ? __('Add leads to build the test.') : __('Nothing in this set yet.') }}
      </div>
      <ol v-else class="divide-y divide-outline-gray-1 rounded-md border border-outline-gray-1">
        <li
          v-for="(p, i) in properties"
          :key="p.name"
          class="flex items-center gap-3 px-3 py-2"
        >
          <span class="w-6 shrink-0 text-xs text-ink-gray-5">{{ i + 1 }}</span>
          <div class="min-w-0 flex-1">
            <div class="truncate text-sm font-medium text-ink-gray-8">
              {{ p.property_address }}
            </div>
            <div class="truncate text-xs text-ink-gray-5">
              {{ p.lead_name }}
            </div>
          </div>
          <template v-if="canManage">
            <Button variant="ghost" icon="chevron-up" :disabled="i === 0" @click="move(i, -1)" />
            <Button
              variant="ghost"
              icon="chevron-down"
              :disabled="i === properties.length - 1"
              @click="move(i, 1)"
            />
            <Button variant="ghost" icon="x" @click="removeProp(p)" />
          </template>
        </li>
      </ol>
    </div>

    <div class="mt-8 max-w-4xl">
      <h2 class="mb-2 text-base font-medium text-ink-gray-8">{{ __('Times') }}</h2>
      <div v-if="!attempts.length" class="text-sm text-ink-gray-5">
        {{ __('No runs yet.') }}
      </div>
      <table v-else class="w-full text-left text-sm">
        <thead class="text-xs text-ink-gray-5">
          <tr>
            <th class="py-1.5 pr-3 font-medium">{{ __('Who') }}</th>
            <th class="py-1.5 pr-3 font-medium">{{ __('Status') }}</th>
            <th class="py-1.5 pr-3 font-medium">{{ __('Time') }}</th>
            <th class="py-1.5 pr-3 font-medium">{{ __('Done') }}</th>
            <th class="py-1.5 font-medium" />
          </tr>
        </thead>
        <tbody>
          <template v-for="a in attempts" :key="a.name">
            <tr
              class="cursor-pointer border-t border-outline-gray-1 hover:bg-surface-gray-1"
              @click="toggleRow(a.name)"
            >
              <td class="py-2 pr-3 text-ink-gray-8">{{ a.user_name }}</td>
              <td class="py-2 pr-3 text-ink-gray-6">{{ a.status }}</td>
              <td class="py-2 pr-3 tabular-nums text-ink-gray-8">
                {{ fmtDuration(a.elapsed_seconds) }}
              </td>
              <td class="py-2 pr-3 text-ink-gray-6">
                {{ a.done }}/{{ a.property_count }}
              </td>
              <td class="py-2 text-xs text-ink-gray-5">
                {{ openRow === a.name ? __('Hide') : __('Details') }}
              </td>
            </tr>
            <tr v-if="openRow === a.name">
              <td colspan="5" class="bg-surface-gray-1 px-3 py-2">
                <div
                  v-for="p in a.properties"
                  :key="p.name"
                  class="flex items-baseline justify-between gap-3 py-0.5 text-xs"
                >
                  <span class="min-w-0 truncate text-ink-gray-7">
                    {{ p.property_address }}
                  </span>
                  <span class="shrink-0 tabular-nums text-ink-gray-5">
                    <template v-if="p.duration_seconds != null">
                      {{ fmtDuration(p.duration_seconds) }}
                    </template>
                    <template v-else-if="p.opened_at">{{ __('open') }}</template>
                    <template v-else>—</template>
                    <template v-if="p.selected_count">
                      · {{ __('{0} picked', [p.selected_count]) }}
                    </template>
                    <template v-if="p.has_offer"> · {{ __('offer saved') }}</template>
                  </span>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <div v-if="canManage" class="mt-10">
      <Button theme="red" variant="subtle" :label="__('Delete set')" @click="confirmDelete = true" />
    </div>
  </div>

  <Dialog v-model="confirmDelete" :options="{ title: __('Delete this set?') }">
    <template #body-content>
      <div class="text-sm text-ink-gray-7">
        {{ __('Deletes the set, its properties, and every recorded run.') }}
      </div>
    </template>
    <template #actions>
      <Button
        class="w-full"
        variant="solid"
        theme="red"
        :label="__('Delete')"
        :loading="deleting"
        @click="removeSet"
      />
    </template>
  </Dialog>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import Autocomplete from '@/components/frappe-ui/Autocomplete.vue'
import {
  Breadcrumbs,
  Button,
  Dialog,
  FormControl,
  call,
  createResource,
  toast,
} from 'frappe-ui'
import { useDebounceFn } from '@vueuse/core'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({ setId: { type: String, required: true } })
const router = useRouter()
const saving = ref(false)
const starting = ref(false)
const deleting = ref(false)
const confirmDelete = ref(false)
const openRow = ref('')
const leadOptions = ref([])
const addKey = ref(0)
const form = reactive({ title: '', time_limit_min: 0, notes: '', is_active: true })

const detail = createResource({
  url: 'crm.api.practice.get_set',
  makeParams: () => ({ name: props.setId }),
  auto: true,
  onSuccess(d) {
    form.title = d.title || ''
    form.time_limit_min = d.time_limit_min || 0
    form.notes = d.notes || ''
    form.is_active = !!d.is_active
  },
})
const results = createResource({
  url: 'crm.api.practice.list_results',
  makeParams: () => ({ practice_set: props.setId }),
  auto: true,
})

const set = computed(() => detail.data || {})
const canManage = computed(() => set.value.can_manage)
const properties = computed(() => set.value.properties || [])
const attempts = computed(() => results.data?.attempts || [])
const resumeLabel = computed(() =>
  set.value.my_attempt?.status === 'In Progress' ? __('Resume') : __('Start'),
)

function fmtDuration(sec) {
  sec = Math.max(0, Math.floor(Number(sec) || 0))
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function toggleRow(name) {
  openRow.value = openRow.value === name ? '' : name
}

const searchLeads = useDebounceFn(async (q) => {
  try {
    const rows = await call('crm.api.practice.search_leads', { q: q || '' })
    leadOptions.value = (rows || []).map((r) => ({
      label: `${r.property_address || r.name}${r.lead_name ? ' · ' + r.lead_name : ''}`,
      value: r.name,
    }))
  } catch {
    leadOptions.value = []
  }
}, 200)

function onLeadQuery(q) {
  searchLeads(q)
}

async function addLead(opt) {
  const lead = opt?.value || opt
  if (!lead) return
  try {
    await call('crm.api.practice.add_property', {
      practice_set: props.setId,
      lead,
    })
    addKey.value += 1
    await detail.reload()
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not add that lead.'))
  }
}

async function removeProp(p) {
  try {
    await call('crm.api.practice.remove_property', { name: p.name })
    await detail.reload()
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not remove that property.'))
  }
}

async function move(i, dir) {
  const next = [...properties.value]
  const j = i + dir
  if (j < 0 || j >= next.length) return
  ;[next[i], next[j]] = [next[j], next[i]]
  try {
    await call('crm.api.practice.reorder_properties', {
      practice_set: props.setId,
      names: JSON.stringify(next.map((p) => p.name)),
    })
    await detail.reload()
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not reorder.'))
  }
}

async function saveMeta() {
  saving.value = true
  try {
    await call('crm.api.practice.save_set', {
      name: props.setId,
      title: form.title,
      time_limit_min: Number(form.time_limit_min) || 0,
      notes: form.notes,
      is_active: form.is_active ? 1 : 0,
    })
    toast.success(__('Saved'))
    await detail.reload()
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not save.'))
  } finally {
    saving.value = false
  }
}

async function start() {
  starting.value = true
  try {
    const res = await call('crm.api.practice.start_attempt', {
      practice_set: props.setId,
    })
    router.push({
      name: 'PracticeRun',
      params: { setId: props.setId, attemptId: res.name },
    })
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not start.'))
  } finally {
    starting.value = false
  }
}

async function removeSet() {
  deleting.value = true
  try {
    await call('crm.api.practice.delete_set', { name: props.setId })
    router.push({ name: 'Practice' })
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not delete.'))
  } finally {
    deleting.value = false
  }
}

onMounted(() => searchLeads(''))

watch(
  () => props.setId,
  () => {
    detail.reload()
    results.reload()
  },
)
</script>
