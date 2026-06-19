<template>
  <TaskModal
    v-model="showTaskModal"
    v-model:reloadTasks="activities"
    :task="task"
    :doctype="doctype"
    :doc="doc?.name"
  />
  <NoteModal
    v-model="showNoteModal"
    v-model:reloadNotes="activities"
    :note="note"
    :doctype="doctype"
    :doc="doc?.name"
    @after="redirect('notes')"
  />
  <CallLogModal
    v-if="showCallLogModal"
    v-model="showCallLogModal"
    :data="callLog"
    :referenceDoc="referenceDoc"
    :options="{ afterInsert: () => activities.reload() }"
  />
  <SendTextModal
    v-if="showSendTextModal"
    v-model="showSendTextModal"
    :referenceDoc="referenceDoc"
    :doctype="doctype"
  />
</template>
<script setup>
import TaskModal from '@/components/Modals/TaskModal.vue'
import NoteModal from '@/components/Modals/NoteModal.vue'
import CallLogModal from '@/components/Modals/CallLogModal.vue'
import SendTextModal from '@/components/Modals/SendTextModal.vue'
import { call } from 'frappe-ui'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usersStore } from '@/stores/users'

const { getUser } = usersStore()

const props = defineProps({
  doctype: { type: String, default: '' },
})

const activities = defineModel()
const doc = defineModel('doc')

// Tasks
const showTaskModal = ref(false)
const task = ref({})

function showTask(t) {
  task.value = t || {
    title: '',
    description: '',
    assigned_to: '',
    due_date: '',
    priority: 'Low',
    status: 'Backlog',
  }
  showTaskModal.value = true
}

// Trello-style quick-add: title (+ optional due date) defaulted to the current
// user and 'Todo'. Stays on the Activity tab — no redirect to the Tasks screen.
async function addTask(title, due_date) {
  const t = (title || '').trim()
  if (!t) return
  await call('frappe.client.insert', {
    doc: {
      doctype: 'CRM Task',
      title: t,
      status: 'Todo',
      due_date: due_date || null,
      reference_doctype: props.doctype,
      reference_docname: doc.value?.name || null,
      assigned_to: getUser().name,
    },
  })
  activities.value.reload()
}

async function deleteTask(name) {
  await call('frappe.client.delete', {
    doctype: 'CRM Task',
    name,
  })
  activities.value.reload()
}

function updateTaskStatus(status, task) {
  call('frappe.client.set_value', {
    doctype: 'CRM Task',
    name: task.name,
    fieldname: 'status',
    value: status,
  }).then(() => {
    activities.value.reload()
  })
}

// Notes
const showNoteModal = ref(false)
const note = ref({})

function showNote(n) {
  note.value = n || {
    title: '',
    content: '',
  }
  showNoteModal.value = true
}

// Call Logs
const showCallLogModal = ref(false)
const callLog = ref({})
const referenceDoc = ref({})

function createCallLog() {
  let doctype = props.doctype
  let docname = props.doc?.name
  referenceDoc.value = { ...props.doc }
  callLog.value = {
    reference_doctype: doctype,
    reference_docname: docname,
  }
  showCallLogModal.value = true
}

// Send Text
const showSendTextModal = ref(false)

function sendText() {
  referenceDoc.value = { ...props.doc }
  showSendTextModal.value = true
}

// common
const route = useRoute()
const router = useRouter()

function redirect(tabName) {
  if (route.name == 'Lead' || route.name == 'Deal') {
    let hash = '#' + tabName
    if (route.hash != hash) {
      router.push({ ...route, hash })
    }
  }
}

defineExpose({
  showTask,
  addTask,
  deleteTask,
  updateTaskStatus,
  showNote,
  createCallLog,
  sendText,
})
</script>
