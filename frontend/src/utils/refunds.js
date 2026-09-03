// One dot per refund status, shared by the Refunds board, the lead-page card
// and (by convention) the Lead Refunds Mattermost posts: green = money back,
// red = ISTL is waiting on us, yellow = in flight. Keep in step with
// refund_mail_poll.py in the ops repo.
export const REFUND_STATUSES = [
  'To Request',
  'Requested',
  'Waiting on us',
  'Waiting on them',
  'Complete',
]

export const REFUND_STATUS_DOT = {
  'To Request': '⚪',
  Requested: '🟡',
  'Waiting on us': '🔴',
  'Waiting on them': '🔵',
  Complete: '🟢',
}

export function refundDot(status) {
  return REFUND_STATUS_DOT[status] || ''
}
