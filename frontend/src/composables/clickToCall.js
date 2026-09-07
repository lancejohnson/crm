import { workspaceStore } from '@/stores/workspace'
import { callHref } from '@/utils/phoneFormat'
import { myQuoNumber } from '@/composables/quoSender'

/**
 * Place a call the way the current workspace expects: Telnyx dock when the
 * user is in `next`, otherwise the existing Quo tel:/openphone: handoff.
 */
export function clickToCall(number, extra = {}) {
  if (!number) return
  const workspace = workspaceStore()
  if (workspace.isNext) {
    return import('@/composables/phone').then(({ dial }) => dial(number, extra))
  }
  const href = callHref(number, extra.from || myQuoNumber())
  if (href) window.location.href = href
}
