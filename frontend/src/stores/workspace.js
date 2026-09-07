import { defineStore } from 'pinia'
import { createResource } from 'frappe-ui'
import { computed } from 'vue'

/**
 * Which workspace this user is in: `classic` (production, byte-identical) or
 * `next` (Telnyx phone dock + Talk left nav). The server owns the answer:
 * `crm.api.workspace.get` returns `{ version, allowed }`, where `allowed` is
 * the site_config `crm_next_users` allowlist and `version` is the per-user
 * Frappe default `crm_workspace_version` (docs/next-workspace-build.md).
 *
 * Nothing "next" is imported until `isNext` is true — App.vue and the router
 * gate their dynamic imports on this store, so a classic user never fetches a
 * Talk or PhoneDock chunk. A failed/absent endpoint (older backend) resolves
 * to classic.
 */
export const workspaceStore = defineStore('crm-workspace', () => {
  const state = createResource({
    url: 'crm.api.workspace.get',
    cache: 'crm-workspace',
    initialData: { version: 'classic', allowed: false },
    auto: true,
    transform: (data) => ({
      version: data?.version === 'next' ? 'next' : 'classic',
      allowed: !!data?.allowed,
    }),
    onError: () => {},
  })

  const version = computed(() => state.data?.version || 'classic')
  const allowed = computed(() => !!state.data?.allowed)
  const isNext = computed(() => allowed.value && version.value === 'next')
  const menuLabel = computed(() =>
    isNext.value ? __('Back to classic') : __('Try the new workspace'),
  )

  const setter = createResource({
    url: 'crm.api.workspace.set_version',
    onSuccess(data) {
      state.setData({ version: data?.version === 'next' ? 'next' : 'classic', allowed: true })
    },
  })

  function setVersion(next) {
    if (!allowed.value) return Promise.resolve(false)
    return setter.submit({ version: next })
  }
  function toggle() {
    return setVersion(isNext.value ? 'classic' : 'next')
  }

  return { state, version, allowed, isNext, menuLabel, setVersion, toggle }
})
