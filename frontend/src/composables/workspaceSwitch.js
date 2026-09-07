import { computed } from 'vue'
import { phonePreview as p } from '@/composables/phonePreview'
import { commsPreview as c } from '@/composables/commsPreview'
import { toggleWorkspace, workspaceMenuLabel, currentWorkspace, nextWorkspaceQuery, classicWorkspaceQuery } from '@/utils/workspaceVersion'

// The UserDropdown's "Try the new workspace" / "Back to classic" item. One
// composable so desktop and mobile (both mount UserDropdown) share it. Toggling
// flips the in-memory state and mirrors it into the URL query, which is the
// only thing that survives a reload until the real user default exists.
// `route`/`router` are passed in: this is created after setup (lazy import),
// where `useRoute()` cannot inject.
export function useWorkspaceSwitch({ route, router }) {
  const label = computed(() => workspaceMenuLabel(p))
  function toggle() {
    toggleWorkspace(p, c)
    const query = currentWorkspace(p) === 'next' ? nextWorkspaceQuery(route.query) : classicWorkspaceQuery(route.query)
    router.replace({ query })
  }
  return { label, toggle }
}
