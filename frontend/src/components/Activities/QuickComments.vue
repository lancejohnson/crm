<template>
  <div class="px-3 pt-3 sm:px-10">
    <div
      class="overflow-hidden rounded-lg border border-outline-gray-1 bg-surface-gray-1"
    >
      <div
        class="flex items-center gap-1.5 px-3 pt-2.5 pb-1 text-sm font-medium text-ink-gray-5"
      >
        <MessageSquareTextIcon class="size-3.5" />
        <span>{{ __('Quick comment') }}</span>
        <Tooltip
          v-if="!editing"
          :text="__('Customize your quick comments')"
        >
          <button
            class="ml-auto flex shrink-0 items-center text-ink-gray-4 hover:text-ink-gray-7"
            @click="startEdit"
          >
            <LucidePencil class="size-3.5" />
          </button>
        </Tooltip>
      </div>

      <!-- chips: one tap logs the canned comment -->
      <div v-if="!editing" class="flex flex-wrap gap-1.5 px-3 pt-1 pb-2.5">
        <Tooltip
          v-for="(c, i) in comments"
          :key="i"
          :text="__('Log this comment')"
        >
          <button
            class="rounded-md border border-outline-gray-1 bg-surface-white px-2 py-0.5 text-sm text-ink-gray-7 hover:bg-surface-gray-3 disabled:opacity-50"
            :disabled="posting"
            @click="post(c)"
          >
            {{ c }}
          </button>
        </Tooltip>
        <span v-if="!comments.length" class="py-0.5 text-sm text-ink-gray-4">
          {{ __('No quick comments — click the pencil to add some.') }}
        </span>
      </div>

      <!-- inline editor: add / edit / remove the rows -->
      <div v-else class="flex flex-col gap-2 px-3 pt-1 pb-2.5">
        <div
          v-for="(c, i) in draft"
          :key="i"
          class="flex items-center gap-2"
        >
          <input
            v-model="draft[i]"
            type="text"
            class="min-w-0 flex-1 rounded-md border border-outline-gray-2 bg-surface-white px-2 py-1 text-base text-ink-gray-8 focus:outline-none focus:ring-1 focus:ring-outline-gray-3"
            @keydown.enter="addRow"
          />
          <Tooltip :text="__('Remove')">
            <button
              class="flex shrink-0 items-center text-ink-gray-4 hover:text-ink-red-3"
              @click="draft.splice(i, 1)"
            >
              <LucideTrash2 class="size-3.5" />
            </button>
          </Tooltip>
        </div>
        <div class="flex items-center gap-2">
          <LucidePlus class="size-4 shrink-0 text-ink-gray-4" />
          <input
            v-model="newOne"
            type="text"
            :placeholder="__('Add a quick comment…')"
            class="min-w-0 flex-1 bg-transparent text-base text-ink-gray-8 placeholder:text-ink-gray-4 focus:outline-none"
            @keydown.enter="addRow"
          />
        </div>
        <div class="flex items-center justify-end gap-2 pt-1">
          <Button :label="__('Cancel')" @click="editing = false" />
          <Button
            variant="solid"
            :label="__('Save')"
            :loading="saving"
            @click="save"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import MessageSquareTextIcon from '~icons/lucide/message-square-text'
import LucidePencil from '~icons/lucide/pencil'
import LucidePlus from '~icons/lucide/plus'
import LucideTrash2 from '~icons/lucide/trash-2'
import { usersStore } from '@/stores/users'
import { Button, Tooltip, call, toast } from 'frappe-ui'
import { ref, computed } from 'vue'

const props = defineProps({
  modalRef: { type: Object, default: () => ({}) },
})

const { getUser } = usersStore()

// Seeded for any user who hasn't customized their list yet.
const DEFAULT_QUICK_COMMENTS = [
  "Call 3x's, voicemail, sent text",
  'Called',
  'Voicemail',
  'Sent text',
]

// The session user's saved list (JSON string on User.custom_quick_comments),
// or null when unset → fall back to the defaults.
const savedComments = computed(() => {
  const raw = getUser('sessionUser')?.custom_quick_comments
  if (!raw) return null
  try {
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr : null
  } catch {
    return null
  }
})

const comments = computed(() => savedComments.value ?? DEFAULT_QUICK_COMMENTS)

const posting = ref(false)
async function post(c) {
  if (posting.value) return
  posting.value = true
  try {
    await props.modalRef?.addComment(c)
  } finally {
    posting.value = false
  }
}

// --- editing ---
const editing = ref(false)
const saving = ref(false)
const draft = ref([])
const newOne = ref('')

function startEdit() {
  draft.value = [...comments.value]
  newOne.value = ''
  editing.value = true
}

function addRow() {
  const t = newOne.value.trim()
  if (!t) return
  draft.value.push(t)
  newOne.value = ''
}

async function save() {
  // fold a half-typed new row in before saving
  const t = newOne.value.trim()
  if (t) draft.value.push(t)
  newOne.value = ''

  const cleaned = draft.value.map((s) => s.trim()).filter(Boolean)
  saving.value = true
  try {
    const stored = await call('crm.api.comment.set_user_quick_comments', {
      comments: JSON.stringify(cleaned),
    })
    // reflect immediately in the reactive users store
    getUser('sessionUser').custom_quick_comments = JSON.stringify(stored)
    editing.value = false
    toast.success(__('Quick comments saved'))
  } catch (e) {
    toast.error(__('Could not save quick comments'))
  } finally {
    saving.value = false
  }
}
</script>
