<template>
  <SettingsLayoutBase
    :title="__('Lead Assignment')"
    :description="
      __(
        'Decide who new inbound leads go to, per source. Leads created by hand already have an owner and are never touched.',
      )
    "
  >
    <template #content>
      <div v-if="loading" class="flex flex-1 items-center justify-center py-20">
        <LoadingIndicator class="size-8" />
      </div>

      <div v-else class="flex flex-col gap-8">
        <!-- Break-glass notice: site_config wins over anything on this page,
             so never let the page claim to be on while it isn't. -->
        <div
          v-if="killSwitchOff"
          class="rounded-lg bg-surface-amber-1 px-3 py-2 text-p-sm text-ink-amber-3"
        >
          {{
            __(
              'Automatic assignment is switched off in site config, so nothing on this page is in effect until that is turned back on.',
            )
          }}
        </div>

        <section class="flex flex-col gap-4">
          <div class="flex items-center gap-2 h-7">
            <div class="text-base font-semibold text-ink-gray-9">
              {{ __('Automatic assignment') }}
            </div>
            <Badge
              v-if="isDirty"
              variant="subtle"
              theme="orange"
              size="sm"
              :label="__('Not Saved')"
            />
          </div>

          <label class="flex items-center justify-between gap-4 cursor-pointer">
            <div class="flex flex-col gap-1">
              <span class="text-base font-medium text-ink-gray-8">
                {{ __('Assign new leads automatically') }}
              </span>
              <span class="text-p-sm text-ink-gray-6">
                {{
                  __(
                    'Turn off to pause. New leads then arrive with no owner until someone picks them up.',
                  )
                }}
              </span>
            </div>
            <Switch v-model="draft.enabled" />
          </label>
        </section>

        <!-- Per-source rules -->
        <section class="flex flex-col gap-4">
          <div class="flex items-center justify-between gap-2">
            <div class="flex flex-col gap-1">
              <div class="text-base font-semibold text-ink-gray-9">
                {{ __('By lead source') }}
              </div>
              <span class="text-p-sm text-ink-gray-6">
                {{ __('A source listed here follows its own rule.') }}
              </span>
            </div>
            <Autocomplete
              v-if="unusedSources.length"
              :options="unusedSources.map((s) => ({ label: s, value: s }))"
              :value="null"
              :placeholder="__('Add a source')"
              class="w-44"
              @change="(o) => o && addSource(o.value)"
            />
          </div>

          <div
            v-if="!sourceRows.length"
            class="rounded-lg border border-dashed border-outline-gray-2 px-3 py-6 text-center text-p-sm text-ink-gray-5"
          >
            {{ __('No per-source rules — every lead follows the rule below.') }}
          </div>

          <RuleRow
            v-for="row in sourceRows"
            :key="row.source"
            :label="row.source"
            :rule="row.rule"
            :users="users"
            :next-owner="nextOwnerLabel(row.source)"
            removable
            @remove="removeSource(row.source)"
          />
        </section>

        <!-- The catch-all -->
        <section class="flex flex-col gap-4">
          <div class="flex flex-col gap-1">
            <div class="text-base font-semibold text-ink-gray-9">
              {{ __('Everything else') }}
            </div>
            <span class="text-p-sm text-ink-gray-6">
              {{
                __(
                  'Any source without a rule of its own — including leads that arrive with no source at all.',
                )
              }}
            </span>
          </div>

          <RuleRow
            :label="__('All other sources')"
            :rule="draft.default"
            :users="users"
            :next-owner="nextOwnerLabel('__default__')"
          />
        </section>

        <div class="flex justify-end gap-2">
          <Button
            v-if="isDirty"
            :label="__('Discard')"
            variant="subtle"
            @click="reset"
          />
          <Button
            :label="__('Save')"
            variant="solid"
            :loading="saving"
            :disabled="!isDirty"
            @click="save"
          />
        </div>
      </div>
    </template>
  </SettingsLayoutBase>
</template>

<script setup>
import SettingsLayoutBase from '@/components/Layouts/SettingsLayoutBase.vue'
import RuleRow from '@/components/Settings/LeadAssignmentRuleRow.vue'
import {
  Autocomplete,
  Badge,
  Button,
  LoadingIndicator,
  Switch,
  call,
  toast,
} from 'frappe-ui'
import { computed, reactive, ref, onMounted } from 'vue'

const loading = ref(true)
const saving = ref(false)
const users = ref([])
const availableSources = ref([])
const nextOwner = ref({})
const killSwitchOff = ref(false)

// The server's copy of the editable part, so `isDirty` compares like with like.
const saved = ref('{}')
// ...and the untouched payload, so Discard can restore the read-only lists
// (users, sources, previews) that the snapshot doesn't carry.
const rawServer = ref('{}')

const draft = reactive({
  enabled: true,
  default: { mode: 'rotate', users: [] },
  sources: {},
})

function snapshot() {
  return JSON.stringify({
    enabled: draft.enabled,
    default: draft.default,
    sources: draft.sources,
  })
}

const isDirty = computed(() => snapshot() !== saved.value)

// Object key order is insertion order, which is the order a manager added them
// in — stable enough to render directly, and it keeps a freshly-added source at
// the bottom where the user just put it rather than jumping alphabetically.
const sourceRows = computed(() =>
  Object.keys(draft.sources).map((source) => ({
    source,
    rule: draft.sources[source],
  })),
)

const unusedSources = computed(() =>
  availableSources.value.filter((s) => !(s in draft.sources)),
)

function apply(data) {
  users.value = data.users || []
  availableSources.value = data.available_sources || []
  nextOwner.value = data.next_owner || {}
  killSwitchOff.value = !!data.kill_switch_off
  draft.enabled = data.enabled !== false
  draft.default = data.default || { mode: 'rotate', users: [] }
  draft.sources = data.sources || {}
  saved.value = snapshot()
}

function nextOwnerLabel(key) {
  const email = nextOwner.value[key]
  if (!email) return ''
  const user = users.value.find((u) => u.name === email)
  return user?.full_name || email
}

function addSource(source) {
  if (!source || source in draft.sources) return
  // Seed from the catch-all: a new rule almost always starts as "the same as
  // everyone else, but…", and an empty picker cannot be saved at all.
  draft.sources[source] = {
    mode: draft.default.mode === 'off' ? 'rotate' : draft.default.mode,
    users: [...(draft.default.users || [])],
  }
}

function removeSource(source) {
  delete draft.sources[source]
}

function reset() {
  apply(JSON.parse(rawServer.value))
}

async function load() {
  loading.value = true
  try {
    const data = await call('crm.api.lead_assignment.get_lead_assignment_settings')
    rawServer.value = JSON.stringify(data)
    apply(data)
  } catch (e) {
    toast.error(__('Could not load assignment settings'))
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const data = await call(
      'crm.api.lead_assignment.set_lead_assignment_settings',
      { settings: snapshot() },
    )
    rawServer.value = JSON.stringify(data)
    apply(data)
    toast.success(__('Lead assignment saved'))
  } catch (e) {
    // The backend refuses an empty rule by name, and that message is the whole
    // point — surface it rather than a generic failure.
    toast.error(e?.messages?.[0] || __('Could not save lead assignment'))
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>
