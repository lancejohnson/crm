import { computed } from 'vue'
import { usersStore } from '@/stores/users'
import { DEFAULT_TASK_DUE_PRESETS } from '@/utils/taskDue'

// The rep's own due-date chips (2h / 3d / 1wk / 1mo unless customized), read
// off the session user. One definition so the lead-page to-do composer and the
// Today board's follow-up strip cannot drift: a chip a rep adds in one place
// shows up in the other on the next render.
export function useTaskDuePresets() {
  const { getUser } = usersStore()

  const savedPresets = computed(() => {
    const raw = getUser('sessionUser')?.custom_task_due_presets
    if (!raw) return null
    try {
      const arr = typeof raw === 'string' ? JSON.parse(raw) : raw
      return Array.isArray(arr) ? arr : null
    } catch {
      return null
    }
  })

  const presets = computed(() => savedPresets.value ?? DEFAULT_TASK_DUE_PRESETS)

  return { presets }
}
