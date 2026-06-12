<template>
  <LayoutHeader>
    <template #left-header>
      <Breadcrumbs
        :items="[
          { label: 'Sequences', route: { name: 'Sequences' } },
          { label: sequenceId, route: { name: 'Sequence', params: { sequenceId } } },
        ]"
      />
    </template>
    <template #right-header>
      <div class="flex items-center gap-3">
        <div class="flex items-center gap-2 text-sm text-ink-gray-7">
          <span>Enabled</span>
          <Switch v-model="enabled" />
        </div>
        <Button variant="solid" label="Save" :loading="saving" @click="save" />
        <Dropdown
          :options="[
            { label: 'Duplicate', icon: 'copy', onClick: duplicateSequence },
            { label: 'Delete', icon: 'trash-2', onClick: () => (showDelete = true) },
          ]"
        >
          <Button icon="more-horizontal" variant="ghosted" />
        </Dropdown>
      </div>
    </template>
  </LayoutHeader>

  <Dialog v-model="showDelete" :options="{ title: 'Delete Sequence' }">
    <template #body-content>
      <div class="text-sm text-ink-gray-7">
        Delete "{{ sequenceId }}"?
        <template v-if="enrollments.data?.length">
          This also deletes its {{ enrollments.data.length }} enrollment(s) — enrolled leads stop
          receiving steps.
        </template>
      </div>
    </template>
    <template #actions>
      <Button class="w-full" variant="solid" theme="red" label="Delete" :loading="deletingSeq" @click="deleteSequence" />
    </template>
  </Dialog>

  <div class="flex-1 overflow-y-auto px-3 pb-6 sm:px-5">
    <div class="mx-auto mt-4 flex max-w-3xl flex-col gap-4">
      <!-- Auto-enroll -->
      <FormControl
        v-model="autoEnrollSources"
        type="textarea"
        label="Auto-enroll lead sources (one per line — a lead whose source is set to a match enrolls instantly)"
        :rows="2"
      />

      <!-- Steps -->
      <div class="text-lg font-medium text-ink-gray-9">Steps</div>
      <div
        v-for="(group, i) in groups"
        :key="i"
        class="flex flex-col gap-3 rounded-lg border px-5 py-4 shadow-sm"
      >
        <div class="flex items-center justify-between">
          <div class="text-sm font-medium text-ink-gray-7">Step {{ i + 1 }}</div>
          <div class="flex items-center gap-1">
            <Button icon="arrow-up" variant="ghosted" :disabled="i === 0" @click="move(i, -1)" />
            <Button icon="arrow-down" variant="ghosted" :disabled="i === groups.length - 1" @click="move(i, 1)" />
            <Button icon="trash-2" variant="ghosted" :disabled="groups.length === 1" @click="groups.splice(i, 1)" />
          </div>
        </div>
        <FormControl
          v-model="group.step_type"
          type="select"
          label="Type"
          :options="['Email', 'Call', 'Text', 'Pushover']"
        />
        <FormControl
          v-if="group.step_type === 'Email' || group.step_type === 'Pushover'"
          v-model="group.subject"
          type="text"
          :label="group.step_type === 'Email' ? 'Email Subject' : 'Notification Title (optional — defaults to lead name)'"
          placeholder="Your property at {{ property_address }}"
        />
        <FormControl
          v-model="group.message"
          type="textarea"
          :label="messageLabel(group.step_type)"
          :rows="4"
        />
        <!-- Trigger paths: one action, fired on different timing/conditions -->
        <div class="flex flex-col gap-2">
          <div class="text-xs text-ink-gray-5">
            Trigger paths — each path fires this step on its own timing and condition. The first
            path waits after the previous step; each later path waits after the path above it.
          </div>
          <div
            v-for="(path, j) in group.paths"
            :key="j"
            class="flex items-end gap-2 rounded-md bg-surface-gray-1 px-3 py-2"
          >
            <FormControl
              v-model="path.wait_value"
              type="number"
              class="w-24 shrink-0"
              :label="j === 0 ? 'Wait' : 'Then wait'"
              :min="0"
            />
            <FormControl
              v-model="path.wait_unit"
              type="select"
              class="w-32 shrink-0"
              label="Unit"
              :options="['Seconds', 'Minutes', 'Hours', 'Days', 'Weeks', 'Months']"
            />
            <FormControl
              v-model="path.condition"
              type="text"
              class="grow"
              label="Condition (Jinja — blank = always fire)"
              placeholder="lead.source == 'PropertyLeads'"
            />
            <Button
              icon="x"
              variant="ghosted"
              :disabled="group.paths.length === 1"
              @click="group.paths.splice(j, 1)"
            />
          </div>
          <Button
            class="self-start"
            variant="ghosted"
            label="Add Trigger Path"
            iconLeft="plus"
            @click="group.paths.push({ wait_value: 0, wait_unit: 'Minutes', condition: '' })"
          />
        </div>
      </div>
      <Button variant="subtle" label="Add Step" iconLeft="plus" @click="addStep" />
      <div class="text-xs text-ink-gray-5">
        Lead variables: <span v-pre>{{ first_name }}, {{ last_name }}, {{ lead_name }}, {{ property_address }}, {{ property_city }}</span>
        — or any lead field via <span v-pre>{{ lead.field_name }}</span>.<br />
        Sender (lead owner) variables: <span v-pre>{{ owner_first_name }}, {{ owner_last_name }}, {{ owner_name }}, {{ owner_email }}, {{ owner_quo_number }}</span>
        — or any user field via <span v-pre>{{ user.field_name }}</span>.<br />
        Full Jinja works too (conditionals, filters). Emails send automatically, Calls create a task
        for the lead owner, Texts send from the lead owner's Quo number, Pushover rings the lead
        owner's phone (emergency push, re-rings until acknowledged or a Quo call touches the lead).
        Trigger paths let one step fire at different times per lead — e.g. ring immediately for
        <span v-pre>lead.source == 'Red Panda Leads'</span> but 3 minutes in for PropertyLeads.
        A path's wait always elapses even when its condition skips it, so later paths keep their timing.
      </div>

      <!-- Enrollments -->
      <div class="mt-6 flex items-center justify-between">
        <div class="text-lg font-medium text-ink-gray-9">Enrollments</div>
        <Button variant="subtle" label="Enroll Lead" iconLeft="plus" @click="showEnroll = true" />
      </div>
      <div v-if="enrollments.data?.length" class="overflow-hidden rounded-lg border">
        <table class="w-full text-sm">
          <thead class="bg-surface-gray-2 text-left text-ink-gray-5">
            <tr>
              <th class="px-4 py-2 font-medium">Lead</th>
              <th class="px-4 py-2 font-medium">Status</th>
              <th class="px-4 py-2 font-medium">Step</th>
              <th class="px-4 py-2 font-medium">Next Run</th>
              <th class="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="enr in enrollments.data" :key="enr.name" class="border-t">
              <td class="px-4 py-2">
                <router-link class="text-ink-gray-8 hover:underline" :to="{ name: 'Lead', params: { leadId: enr.lead } }">
                  {{ enr.lead_name || enr.lead }}
                </router-link>
              </td>
              <td class="px-4 py-2">
                <Badge :theme="statusTheme(enr.status)" :label="enr.status" />
              </td>
              <td class="px-4 py-2 text-ink-gray-7">{{ stepLabel(enr.current_step) }}</td>
              <td class="px-4 py-2 text-ink-gray-7">{{ enr.next_run ? dateFormat(enr.next_run) : '—' }}</td>
              <td class="px-4 py-2 text-right">
                <Dropdown :options="enrollmentActions(enr)">
                  <Button icon="more-horizontal" variant="ghosted" />
                </Dropdown>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-sm text-ink-gray-5">No leads enrolled yet.</div>
    </div>
  </div>

  <Dialog v-model="showEnroll" :options="{ title: 'Enroll Lead' }">
    <template #body-content>
      <div class="flex flex-col gap-1.5">
        <label class="block text-xs text-ink-gray-5">Lead</label>
        <Link v-model="enrollLead" doctype="CRM Lead" placeholder="Select a lead" />
      </div>
    </template>
    <template #actions>
      <Button class="w-full" variant="solid" label="Enroll" :loading="enrolling" @click="enroll" />
    </template>
  </Dialog>
</template>

<script setup>
import LayoutHeader from '@/components/LayoutHeader.vue'
import Link from '@/components/Controls/Link.vue'

function dateFormat(d) {
  return new Date(d).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}
import {
  Breadcrumbs,
  Button,
  Badge,
  Dialog,
  Dropdown,
  FormControl,
  Switch,
  createListResource,
  call,
  toast,
} from 'frappe-ui'
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const props = defineProps({ sequenceId: { type: String, required: true } })
const { sequenceId } = props

const enabled = ref(true)
const autoEnrollSources = ref('')
// editor model: consecutive saved steps with identical type+subject+message
// collapse into one "step" card holding multiple trigger paths (wait + unit +
// condition each); flat CRM Sequence Step rows exist only at load/save
const groups = ref([])
const saving = ref(false)
const showEnroll = ref(false)
const enrollLead = ref('')
const enrolling = ref(false)

onMounted(loadDoc)

async function loadDoc() {
  const doc = await call('frappe.client.get', { doctype: 'CRM Sequence', name: sequenceId })
  enabled.value = !!doc.enabled
  autoEnrollSources.value = doc.auto_enroll_sources || ''
  const out = []
  for (const s of doc.steps) {
    const last = out[out.length - 1]
    const path = {
      wait_value: s.wait_value || 0,
      wait_unit: s.wait_unit || 'Days',
      condition: s.condition || '',
    }
    if (
      last &&
      last.step_type === s.step_type &&
      last.subject === (s.subject || '') &&
      last.message === (s.message || '')
    ) {
      last.paths.push(path)
    } else {
      out.push({
        step_type: s.step_type,
        subject: s.subject || '',
        message: s.message || '',
        paths: [path],
      })
    }
  }
  groups.value = out
}

function flatSteps() {
  return groups.value.flatMap((g) =>
    g.paths.map((p) => ({
      step_type: g.step_type,
      subject: g.subject,
      message: g.message,
      wait_value: p.wait_value,
      wait_unit: p.wait_unit,
      condition: p.condition,
    })),
  )
}

// enrollments store the flat completed-step count — map it back to the
// grouped display ("2" for a single-path step, "2.1" for path 1 of step 2)
function stepLabel(currentStep) {
  if (!currentStep) return 0
  let flat = 0
  for (const [i, g] of groups.value.entries()) {
    for (let j = 0; j < g.paths.length; j++) {
      flat++
      if (flat === currentStep) {
        return g.paths.length === 1 ? String(i + 1) : `${i + 1}.${j + 1}`
      }
    }
  }
  return currentStep
}

function addStep() {
  groups.value.push({
    step_type: 'Email',
    subject: '',
    message: '',
    paths: [{ wait_value: 1, wait_unit: 'Days', condition: '' }],
  })
}

function move(i, dir) {
  const j = i + dir
  const arr = groups.value
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
}

function messageLabel(type) {
  if (type === 'Email') return 'Email Body'
  if (type === 'Call') return 'Call Notes (shown in the task)'
  if (type === 'Pushover') return 'Notification Body (blank = standard lead details: phone, address, condition, reason, source)'
  return 'Text Message'
}

async function save() {
  saving.value = true
  try {
    const doc = await call('frappe.client.get', { doctype: 'CRM Sequence', name: sequenceId })
    doc.enabled = enabled.value ? 1 : 0
    doc.auto_enroll_sources = autoEnrollSources.value
    doc.steps = flatSteps().map((s, i) => ({
      doctype: 'CRM Sequence Step',
      parentfield: 'steps',
      parenttype: 'CRM Sequence',
      idx: i + 1,
      ...s,
    }))
    await call('frappe.client.save', { doc })
    toast.success('Sequence saved')
  } catch (e) {
    toast.error(e.messages?.[0] || 'Failed to save')
  } finally {
    saving.value = false
  }
}

const enrollments = createListResource({
  doctype: 'CRM Sequence Enrollment',
  fields: ['name', 'lead', 'status', 'current_step', 'next_run'],
  filters: { sequence: sequenceId },
  orderBy: 'modified desc',
  pageLength: 99,
  auto: true,
})

function statusTheme(status) {
  return { Active: 'green', Paused: 'orange', Completed: 'blue', Stopped: 'gray' }[status] || 'gray'
}

function enrollmentActions(enr) {
  const actions = []
  if (enr.status === 'Active') {
    actions.push({ label: 'Pause', onClick: () => setStatus(enr.name, 'Paused') })
    actions.push({ label: 'Stop', onClick: () => setStatus(enr.name, 'Stopped') })
  } else if (enr.status === 'Paused') {
    actions.push({ label: 'Resume', onClick: () => setStatus(enr.name, 'Active') })
    actions.push({ label: 'Stop', onClick: () => setStatus(enr.name, 'Stopped') })
  }
  actions.push({ label: 'Delete', icon: 'trash-2', onClick: () => deleteEnrollment(enr.name) })
  return actions
}

async function setStatus(name, status) {
  await call('frappe.client.set_value', { doctype: 'CRM Sequence Enrollment', name, fieldname: 'status', value: status })
  enrollments.reload()
}

async function deleteEnrollment(name) {
  await call('frappe.client.delete', { doctype: 'CRM Sequence Enrollment', name })
  enrollments.reload()
}

const showDelete = ref(false)
const deletingSeq = ref(false)

async function deleteSequence() {
  deletingSeq.value = true
  try {
    // enrollments link to the sequence and block its deletion — remove them first
    for (const enr of enrollments.data || []) {
      await call('frappe.client.delete', { doctype: 'CRM Sequence Enrollment', name: enr.name })
    }
    await call('frappe.client.delete', { doctype: 'CRM Sequence', name: sequenceId })
    toast.success('Sequence deleted')
    router.push({ name: 'Sequences' })
  } catch (e) {
    toast.error(e.messages?.[0] || 'Failed to delete')
  } finally {
    deletingSeq.value = false
  }
}

async function duplicateSequence() {
  try {
    const doc = await call('frappe.client.get', { doctype: 'CRM Sequence', name: sequenceId })
    const copy = await call('frappe.client.insert', {
      doc: {
        doctype: 'CRM Sequence',
        sequence_name: sequenceId + ' (Copy)',
        // disabled + no auto-enroll: a live copy would double-send alongside the original
        enabled: 0,
        auto_enroll_sources: '',
        steps: (doc.steps || []).map((s, i) => ({
          doctype: 'CRM Sequence Step',
          parentfield: 'steps',
          parenttype: 'CRM Sequence',
          idx: i + 1,
          step_type: s.step_type,
          wait_value: s.wait_value,
          wait_unit: s.wait_unit,
          subject: s.subject,
          message: s.message,
          condition: s.condition,
        })),
      },
    })
    toast.success('Duplicated — copy is disabled with auto-enroll cleared')
    router.push({ name: 'Sequence', params: { sequenceId: copy.name } })
  } catch (e) {
    toast.error(e.messages?.[0] || 'Failed to duplicate (name may already exist)')
  }
}

async function enroll() {
  if (!enrollLead.value) return
  enrolling.value = true
  try {
    await call('frappe.client.insert', {
      doc: { doctype: 'CRM Sequence Enrollment', lead: enrollLead.value, sequence: sequenceId, status: 'Active' },
    })
    showEnroll.value = false
    enrollLead.value = ''
    enrollments.reload()
  } catch (e) {
    toast.error(e.messages?.[0] || 'Failed to enroll')
  } finally {
    enrolling.value = false
  }
}
</script>
