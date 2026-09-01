<template>
  <Dialog v-model="show" :options="{ size: 'xl' }">
    <template #body-title>
      <div class="flex items-center gap-3">
        <h3 class="text-2xl font-semibold leading-6 text-ink-gray-9">
          {{ editMode ? __('Edit Task') : __('Schedule a Task') }}
        </h3>
        <Button
          v-if="task?.reference_docname"
          size="sm"
          :label="
            task.reference_doctype == 'CRM Deal'
              ? __('Open Deal')
              : __('Open Lead')
          "
          :iconRight="ArrowUpRightIcon"
          @click="redirect()"
        />
      </div>
    </template>
    <template #body-content>
      <div class="flex flex-col gap-4">
        <div class="grid gap-4 sm:grid-cols-[minmax(0,1fr)_13rem]">
          <div class="space-y-1.5">
            <FormLabel :label="__('What needs to happen?')" required />
            <TextInput
              ref="title"
              v-model="_task.title"
              :placeholder="__('Call seller about offer')"
              required
            />
          </div>
          <div class="space-y-1.5">
            <FormLabel :label="__('When?')" />
            <DateTimePicker
              v-model="_task.due_date"
              class="datepicker w-full"
              :placeholder="__('No due date')"
              :format="getFormat('', '', true, true, false)"
            />
          </div>
        </div>

        <button
          type="button"
          class="flex w-fit items-center gap-1 text-sm text-ink-gray-5 hover:text-ink-gray-8"
          @click="advancedOpen = !advancedOpen"
        >
          <FeatherIcon :name="advancedOpen ? 'chevron-up' : 'chevron-down'" class="size-3.5" />
          {{ advancedOpen ? __('Fewer options') : __('More options') }}
        </button>

        <template v-if="advancedOpen">
          <div>
            <div class="mb-1.5 text-xs text-ink-gray-5">
              {{ __('Notes') }}
            </div>
            <TextEditor
              ref="description"
              variant="outline"
              editor-class="!prose-sm overflow-auto min-h-[120px] max-h-64 py-1.5 px-2 rounded border border-[--surface-gray-2] bg-surface-gray-2 placeholder-ink-gray-4 hover:border-outline-gray-modals hover:bg-surface-gray-3 hover:shadow-sm focus:bg-surface-white focus:border-outline-gray-4 focus:shadow-sm focus:ring-0 focus-visible:ring-2 focus-visible:ring-outline-gray-3 text-ink-gray-8 transition-colors"
              :bubbleMenu="true"
              :content="_task.description"
              :placeholder="__('Anything the assignee should know…')"
              @change="(val) => (_task.description = val)"
            />
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <Dropdown :options="taskStatusOptions(updateTaskStatus)">
              <Button :label="_task.status">
                <template #prefix>
                  <TaskStatusIcon :status="_task.status" />
                </template>
              </Button>
            </Dropdown>
            <Link
              class="form-control"
              :value="getUser(_task.assigned_to).full_name"
              doctype="User"
              :placeholder="__('Assign to')"
              :filters="{
                name: ['in', users.data.crmUsers?.map((user) => user.name)],
                ignore_user_type: 1,
              }"
              :hideMe="true"
              @change="(option) => (_task.assigned_to = option)"
            >
              <template #prefix>
                <UserAvatar class="mr-2 !h-4 !w-4" :user="_task.assigned_to" />
              </template>
              <template #item-prefix="{ option }">
                <UserAvatar class="mr-2" :user="option.value" size="sm" />
              </template>
              <template #item-label="{ option }">
                <Tooltip :text="option.value">
                  <div class="cursor-pointer text-ink-gray-9">
                    {{ getUser(option.value).full_name }}
                  </div>
                </Tooltip>
              </template>
            </Link>
            <Dropdown :options="taskPriorityOptions(updateTaskPriority)">
              <Button :label="_task.priority">
                <template #prefix>
                  <TaskPriorityIcon :priority="_task.priority" />
                </template>
              </Button>
            </Dropdown>
            <Dropdown :options="taskOutcomeOptions(updateTaskOutcome)">
              <Button :label="_task.call_outcome || __('Call Outcome')" />
            </Dropdown>
          </div>
        </template>
      </div>
    </template>
    <template #actions>
      <div class="flex justify-end">
        <Button
          :label="editMode ? __('Update') : __('Schedule')"
          variant="solid"
          :loading="createTaskResource.loading || updateTaskResource.loading"
          @click="updateTask"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import TaskStatusIcon from '@/components/Icons/TaskStatusIcon.vue'
import TaskPriorityIcon from '@/components/Icons/TaskPriorityIcon.vue'
import ArrowUpRightIcon from '@/components/Icons/ArrowUpRightIcon.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import Link from '@/components/Controls/Link.vue'
import { taskStatusOptions, taskPriorityOptions, getFormat } from '@/utils'
import { snapMidnightToMorning } from '@/utils/taskDue'
import { usersStore } from '@/stores/users'
import { useTelemetry } from 'frappe-ui/frappe'
import {
  TextEditor,
  Dropdown,
  Tooltip,
  DateTimePicker,
  createResource,
  toast,
  TextInput,
  FormLabel,
  FeatherIcon,
} from 'frappe-ui'
import { useOnboarding } from 'frappe-ui/frappe'
import { ref, watch, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  task: { type: Object, default: () => ({}) },
  doctype: { type: String, default: 'CRM Lead' },
  doc: { type: String, default: '' },
})

const show = defineModel({ type: Boolean })
const tasks = defineModel('reloadTasks', { type: Object, default: () => ({}) })

const emit = defineEmits(['updateTask', 'after', 'update:modelValue'])

function closeModal() {
  show.value = false
  emit('update:modelValue', false)
}

const router = useRouter()
const { users, getUser } = usersStore()
const { updateOnboardingStep } = useOnboarding('frappecrm')
const { capture } = useTelemetry()

const title = ref(null)
const editMode = ref(false)
const advancedOpen = ref(false)
const _task = ref({
  title: '',
  description: '',
  assigned_to: '',
  due_date: '',
  status: 'Todo',
  priority: 'Low',
  call_outcome: '',
  reference_doctype: props.doctype,
  reference_docname: null,
})

const validateTask = () => {
  if (!_task.value.title) {
    toast.error(__('Title is required'))
    return false
  }
  return true
}

const MUTABLE_FIELDS = [
  'title',
  'description',
  'assigned_to',
  'due_date',
  'status',
  'priority',
  'call_outcome',
]

function taskValues() {
  return Object.fromEntries(
    MUTABLE_FIELDS.map((field) => [field, _task.value[field] ?? '']),
  )
}

const createTaskResource = createResource({
  url: 'frappe.client.insert',
  makeParams() {
    return {
      doc: {
        doctype: 'CRM Task',
        reference_doctype: props.doctype,
        reference_docname: props.doc || null,
        ...taskValues(),
      },
    }
  },
  validate: validateTask,
  onSuccess(d) {
    if (d?.name) {
      updateOnboardingStep('create_first_task')
      capture('task_created')
      tasks.value?.reload?.()
      emit('after', d, true)
      toast.success(__('Task created'))
    }
    closeModal()
  },
})

const updateTaskResource = createResource({
  url: 'frappe.client.set_value',
  makeParams() {
    return {
      doctype: 'CRM Task',
      name: _task.value.name,
      // Activity/realtime reloads can make the modal's `modified` timestamp
      // stale while it is open. Sending the whole fetched row made Frappe treat
      // that metadata as an optimistic-lock token and reject a normal edit.
      // Only send fields a person can actually edit.
      fieldname: taskValues(),
    }
  },
  validate: validateTask,
  onSuccess(d) {
    if (d?.name) {
      tasks.value?.reload?.()
      emit('after', d)
    }
    closeModal()
  },
  onError(e) {
    toast.error(e?.messages?.[0] || __('Could not update task'))
  },
})

function updateTaskStatus(status) {
  _task.value.status = status
}

function updateTaskPriority(priority) {
  _task.value.priority = priority
}

const CALL_OUTCOMES = ['Connected', 'Left Voicemail', 'No Answer', 'Wrong Number', 'Do Not Call']
function taskOutcomeOptions(action) {
  return CALL_OUTCOMES.map((o) => ({ label: o, onClick: () => action(o) }))
}
function updateTaskOutcome(outcome) {
  _task.value.call_outcome = outcome
}

function redirect() {
  if (!props.task?.reference_docname) return
  let name = props.task.reference_doctype == 'CRM Deal' ? 'Deal' : 'Lead'
  let params = { leadId: props.task.reference_docname }
  if (name == 'Deal') {
    params = { dealId: props.task.reference_docname }
  }
  router.push({ name: name, params: params })
}

async function updateTask() {
  if (!_task.value.assigned_to) {
    _task.value.assigned_to = getUser().name
  }
  if (_task.value.due_date) {
    _task.value.due_date = snapMidnightToMorning(_task.value.due_date)
  }
  if (_task.value.name) {
    await updateTaskResource.submit()
  } else {
    await createTaskResource.submit()
  }
  // Resource callbacks vary across frappe-ui cache/realtime paths; the awaited
  // successful submit is the authoritative close point for both create/edit.
  closeModal()
}

function render() {
  editMode.value = false
  nextTick(() => {
    title.value?.el?.focus?.()
    _task.value = { ...props.task }
    if (_task.value.title) {
      editMode.value = true
      advancedOpen.value = false
    } else {
      _task.value.status = _task.value.status || 'Todo'
      advancedOpen.value = false
    }
  })
}

onMounted(() => show.value && render())

watch(show, (value) => {
  if (!value) return
  render()
})
</script>

<style scoped>
:deep(.datepicker svg) {
  width: 0.875rem;
  height: 0.875rem;
}
</style>
