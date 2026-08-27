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
        <label
          v-if="canRecord"
          class="flex cursor-pointer items-center gap-1.5 text-sm text-ink-gray-7"
          :title="__('Capture this tab and your mic so you can talk through the comps')"
        >
          <FormControl type="checkbox" v-model="wantRecord" />
          {{ __('Record screen + mic') }}
        </label>
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
        {{ __('Active — acq reps can take this set') }}
      </label>
    </div>
    <p v-else-if="set.notes" class="mt-3 max-w-2xl text-sm text-ink-gray-5">
      {{ set.notes }}
    </p>
    <p class="mt-2 text-sm text-ink-gray-5">
      {{ __('{0} {1}', [properties.length, properties.length === 1 ? __('property') : __('properties')]) }}
      <template v-if="shownLimit"> · {{ __('{0} min', [shownLimit]) }}</template>
    </p>

    <div class="mt-5 max-w-3xl">
      <div class="mb-2 flex items-center justify-between">
        <h2 class="text-base font-medium text-ink-gray-8">{{ __('Properties') }}</h2>
      </div>
      <div v-if="canManage" class="mb-3 flex flex-col gap-2 sm:flex-row sm:items-end">
        <div class="min-w-0 flex-1">
          <Autocomplete
            :key="addKey"
            :options="leadOptions"
            :placeholder="__('Add a specific lead by name or address…')"
            @update:query="onLeadQuery"
            @update:modelValue="addLead"
          />
        </div>
        <div class="flex items-end gap-2">
          <FormControl
            v-model="randomCount"
            type="number"
            :label="__('Random')"
            class="w-20"
          />
          <Button
            :label="__('Add random')"
            :loading="addingRandom"
            :disabled="!Number(randomCount)"
            @click="addRandom"
          />
        </div>
      </div>
      <div v-if="canManage" class="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <FormControl v-model="area.states" type="text" :label="__('States')" :placeholder="__('OH, IN')" />
        <FormControl v-model="area.cities" type="text" :label="__('Cities')" :placeholder="__('Columbus')" />
        <FormControl v-model="area.counties" type="text" :label="__('Counties')" :placeholder="__('Franklin')" />
        <FormControl v-model="area.zips" type="text" :label="__('ZIPs')" :placeholder="__('43215')" />
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
                <span
                  v-if="a.properties?.some((p) => p.recording_url)"
                  class="ml-1 text-[11px] font-medium text-red-600"
                >
                  {{ __('REC') }}
                </span>
              </td>
              <td class="py-2 pr-3 text-ink-gray-6">
                {{ a.done }}/{{ a.property_count }}
              </td>
              <td class="py-2 text-xs text-ink-gray-5">
                <button class="hover:underline" @click.stop="openRun(a)">
                  {{ a.mine && a.status === 'In Progress' ? __('Resume') : __('Open') }}
                </button>
                <span class="mx-1 text-ink-gray-4">·</span>
                {{ openRow === a.name ? __('Hide') : __('Details') }}
              </td>
            </tr>
            <tr v-if="openRow === a.name">
              <td colspan="5" class="bg-surface-gray-1 px-3 py-2">
                <div
                  v-for="p in a.properties"
                  :key="p.name"
                  class="py-1"
                >
                  <div class="flex items-baseline justify-between gap-3 text-xs">
                    <span class="min-w-0 truncate text-ink-gray-7">
                      {{ p.property_address }}
                    </span>
                    <span class="shrink-0 tabular-nums text-ink-gray-5">
                      <template v-if="p.elapsed_seconds || p.duration_seconds != null">
                        {{ fmtDuration(p.elapsed_seconds || p.duration_seconds) }}
                      </template>
                      <template v-else-if="p.opened_at">{{ __('open') }}</template>
                      <template v-else>—</template>
                      <template v-if="p.selected_count">
                        · {{ __('{0} picked', [p.selected_count]) }}
                      </template>
                      <template v-if="p.offer != null"> · ${{ Number(p.offer).toLocaleString() }}</template>
                      <button
                        v-if="p.recording_url"
                        class="ml-2 font-medium text-red-600 hover:underline"
                        @click.stop="playing = playing === playKey(a, p) ? '' : playKey(a, p)"
                      >
                        {{ playing === playKey(a, p) ? __('Hide') : __('Play') }}
                      </button>
                    </span>
                  </div>
                  <div
                    v-if="p.condition"
                    class="mt-0.5 text-xs text-ink-gray-6"
                  >
                    {{ p.condition }}
                  </div>
                  <video
                    v-if="playing === playKey(a, p)"
                    class="mt-1 aspect-video w-full max-w-xl bg-black"
                    controls
                    autoplay
                    playsinline
                    preload="auto"
                    :src="streamUrl(a, p)"
                    @click.stop
                    @loadeddata="(e) => e.target.play?.().catch(() => {})"
                  />
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <div v-if="canViewLog" class="mt-8 max-w-4xl">
      <h2 class="mb-2 text-base font-medium text-ink-gray-8">{{ __('Who looked') }}</h2>
      <div v-if="!logRows.length" class="text-sm text-ink-gray-5">
        {{ __('No views logged yet.') }}
      </div>
      <table v-else class="w-full text-left text-sm">
        <thead class="text-xs text-ink-gray-5">
          <tr>
            <th class="py-1.5 pr-3 font-medium">{{ __('When') }}</th>
            <th class="py-1.5 pr-3 font-medium">{{ __('Who') }}</th>
            <th class="py-1.5 pr-3 font-medium">{{ __('Looked at') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in logRows"
            :key="row.name"
            class="border-t border-outline-gray-1"
          >
            <td class="py-1.5 pr-3 tabular-nums text-ink-gray-6">{{ prettyWhen(row.viewed_at) }}</td>
            <td class="py-1.5 pr-3 text-ink-gray-8">{{ row.viewer_name }}</td>
            <td class="py-1.5 text-ink-gray-6">
              <template v-if="row.kind === 'attempt'">
                {{ row.subject_name || row.subject_user }}'s run
              </template>
              <template v-else>
                {{ __('this set') }}
              </template>
            </td>
          </tr>
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
import {
  abandonPracticeRecording,
  canPracticeRecord,
  beginPropertyRecording,
  setPracticeAttempt,
  startPracticeRecording,
} from '@/utils/practiceRecorder'

const props = defineProps({ setId: { type: String, required: true } })
const router = useRouter()
const saving = ref(false)
const starting = ref(false)
const deleting = ref(false)
const confirmDelete = ref(false)
const openRow = ref('')
const playing = ref('')
const leadOptions = ref([])
const addKey = ref(0)
const randomCount = ref(5)
const area = reactive({ states: '', cities: '', counties: '', zips: '' })
const addingRandom = ref(false)
const wantRecord = ref(false)
const canRecord = computed(() => canPracticeRecord())
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
const viewLog = createResource({
  url: 'crm.api.practice.list_view_log',
  makeParams: () => ({ practice_set: props.setId }),
})
const results = createResource({
  url: 'crm.api.practice.list_results',
  makeParams: () => ({ practice_set: props.setId }),
  auto: true,
  onSuccess(d) {
    if (d?.can_view_log) viewLog.reload()
  },
})

const set = computed(() => detail.data || {})
const canManage = computed(() => set.value.can_manage)
const properties = computed(() => set.value.properties || [])
const attempts = computed(() => results.data?.attempts || [])
const canViewLog = computed(() => results.data?.can_view_log)
const logRows = computed(() => viewLog.data?.rows || [])
const resumeLabel = computed(() =>
  set.value.my_attempt?.status === 'In Progress' ? __('Resume') : __('Start'),
)
const shownLimit = computed(
  () => Number(canManage.value ? form.time_limit_min : set.value.time_limit_min) || 0,
)

function fmtDuration(sec) {
  sec = Math.max(0, Math.floor(Number(sec) || 0))
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function toggleRow(name) {
  openRow.value = openRow.value === name ? '' : name
  if (openRow.value !== name) playing.value = ''
}

function playKey(a, p) {
  return `${a.name}:${p.name}`
}

function streamUrl(a, p) {
  const q = new URLSearchParams({ attempt: a.name, property: p.name })
  return `/api/method/crm.api.practice.stream_recording?${q}`
}

function openRun(a) {
  if (a.status === 'In Progress' && a.mine === false) return
  router.push({
    name: 'PracticeRun',
    params: { setId: props.setId, attemptId: a.name },
  })
}

function prettyWhen(raw) {
  if (!raw) return ''
  const d = new Date(String(raw).replace(' ', 'T'))
  if (Number.isNaN(d.getTime())) return String(raw)
  return d.toLocaleString()
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

async function addRandom() {
  const n = Number(randomCount.value) || 0
  if (n <= 0) return
  addingRandom.value = true
  try {
    const res = await call('crm.api.practice.add_random_properties', {
      practice_set: props.setId,
      count: n,
      states: area.states,
      cities: area.cities,
      counties: area.counties,
      zips: area.zips,
    })
    await detail.reload()
    if (res?.added < n) {
      toast.warning(__('Only found {0} of {1} new leads with an address.', [res.added, n]))
    } else {
      toast.success(__('Added {0} leads.', [res.added]))
    }
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not add random leads.'))
  } finally {
    addingRandom.value = false
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

async function persistMeta() {
  if (!canManage.value) return
  await call('crm.api.practice.save_set', {
    name: props.setId,
    title: form.title,
    time_limit_min: Number(form.time_limit_min) || 0,
    notes: form.notes,
    is_active: form.is_active ? 1 : 0,
  })
  await detail.reload()
}

async function saveMeta() {
  saving.value = true
  try {
    await persistMeta()
    toast.success(__('Saved'))
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not save.'))
  } finally {
    saving.value = false
  }
}

async function start() {
  starting.value = true
  let recording = false
  try {
    if (wantRecord.value && canPracticeRecord()) {
      try {
        await startPracticeRecording()
        recording = true
      } catch (e) {
        toast.error(
          e?.message
            ? __('Could not start recording: {0}', [e.message])
            : __('Could not start the recording — pick this tab and allow the mic.'),
        )
      }
    }
    if (canManage.value) {
      try {
        await persistMeta()
      } catch (e) {
        if (recording) await abandonPracticeRecording()
        toast.error(e.messages?.[0] || __('Could not save the set.'))
        return
      }
    }
    const res = await call('crm.api.practice.start_attempt', {
      practice_set: props.setId,
    })
    if (recording) {
      setPracticeAttempt(res.name)
      const first = res.properties?.[0]?.name
      if (first) await beginPropertyRecording(first)
    }
    router.push({
      name: 'PracticeRun',
      params: { setId: props.setId, attemptId: res.name },
    })
  } catch (e) {
    if (recording) await abandonPracticeRecording()
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
