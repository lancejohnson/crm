import { ref } from 'vue'
import { call } from 'frappe-ui'

// How a lead opens when you click its Kanban card.
//
// Three states, and the third one is the point: '' means the user has never been
// asked. That is NOT the same as "wants the full page" -- it is what lets the
// board prompt once and never again. Collapsing unset into a default would mean
// either prompting forever or silently choosing for people.
export const LEAD_OPEN_MODAL = 'modal'
export const LEAD_OPEN_PAGE = 'page'

// null while we genuinely do not know yet (nothing fetched). Anything that can
// navigate must wait for this rather than assume, or the first click after a
// page load would race the preference and open the wrong thing.
const mode = ref(null)
let inflight = null

export function useLeadOpenMode() {
  return mode
}

export function loadLeadOpenMode(force = false) {
  if (!force && mode.value !== null) return Promise.resolve(mode.value)
  // Share one request. The Kanban mounts and the click handler may both ask for
  // this within the same tick.
  if (!inflight) {
    inflight = call('crm.api.ui_prefs.get_lead_open_mode')
      .then((value) => {
        mode.value = value || ''
        return mode.value
      })
      .catch(() => {
        // A preference lookup must never be able to break opening a lead. Fall
        // back to "not asked", which degrades to the prompt -- and the prompt
        // still offers both options, so the user is never stuck.
        mode.value = ''
        return ''
      })
      .finally(() => {
        inflight = null
      })
  }
  return inflight
}

export async function saveLeadOpenMode(value) {
  const next = value || ''
  // Apply locally first: the user just answered, and their answer should govern
  // this click even if the write is slow or fails.
  mode.value = next
  try {
    await call('crm.api.ui_prefs.set_lead_open_mode', { mode: next })
  } catch (e) {
    console.error('could not persist lead open mode', e)
  }
  return next
}
