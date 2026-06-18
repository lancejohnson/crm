import { defineStore } from 'pinia'
import { ref } from 'vue'

// Holds an ad-hoc set of lead names to show in the Leads list, produced by a
// dashboard drill-down (e.g. "the leads that went New -> Dead Lead this week").
// Deliberately ephemeral: it feeds the Leads list a `name in [...]` filter via
// the (never-persisted) default_filters prop, and is cleared on refresh or when
// the user dismisses the drill banner.
export const leadDrilldownStore = defineStore('lead-drilldown', () => {
  const active = ref(false)
  const names = ref([])
  const label = ref('')
  const sub = ref('')
  const truncated = ref(false)

  function set(payload) {
    names.value = payload.names || []
    label.value = payload.label || ''
    sub.value = payload.sub || ''
    truncated.value = Boolean(payload.truncated)
    active.value = true
  }

  function clear() {
    active.value = false
    names.value = []
    label.value = ''
    sub.value = ''
    truncated.value = false
  }

  return { active, names, label, sub, truncated, set, clear }
})
