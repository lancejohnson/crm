import { createResource } from 'frappe-ui'
import { usersStore } from '@/stores/users'

// Available Quo (OpenPhone) workspace numbers, fetched on demand. Used by the
// Send Text "from" picker (when a user has no number yet) and the Settings ->
// Users assignment dropdown. Lazy: call quoNumbers.fetch() before reading data.
export const quoNumbers = createResource({
  url: 'list-quo-numbers',
  cache: 'Quo Numbers',
})

// The current user's linked Quo number ('' if none assigned yet).
export function myQuoNumber() {
  const { getUser } = usersStore()
  return getUser('sessionUser')?.custom_quo_number || ''
}

// +16513907073 -> "+1 (651) 390-7073"; anything else passes through.
export function formatPhone(e164) {
  if (!e164) return ''
  const m = String(e164).match(/^\+1(\d{3})(\d{3})(\d{4})$/)
  return m ? `+1 (${m[1]}) ${m[2]}-${m[3]}` : e164
}
