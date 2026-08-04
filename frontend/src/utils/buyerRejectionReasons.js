// Canonical per-property reasons a buyer can be marked Not Interested.
// Keep the values in sync with NOT_INTERESTED_REASONS in crm/api/buyers.py.
export const BUYER_REJECTION_REASONS = [
  {
    value: 'Pricing',
    shortLabel: 'Pricing',
    icon: 'pricing',
  },
  {
    value: 'Not buying in this location',
    shortLabel: 'Location',
    icon: 'location',
  },
  {
    value: 'Not currently in the market',
    shortLabel: 'Not in market',
    icon: 'market',
  },
  {
    value: 'Daisy chainer',
    shortLabel: 'Daisy chainer',
    icon: 'daisy-chain',
  },
  {
    value: 'Does not buy deal type',
    shortLabel: 'Deal type',
    icon: 'deal-type',
  },
  {
    value: 'Property condition',
    shortLabel: 'Condition',
    icon: 'condition',
  },
  {
    value: 'No longer buying',
    shortLabel: 'No longer buying',
    icon: 'no-longer-buying',
  },
  {
    value: 'Other',
    shortLabel: 'Other',
    icon: 'other',
  },
]

const reasonByValue = new Map(
  BUYER_REJECTION_REASONS.map((reason) => [reason.value, reason]),
)

export function buyerRejectionReason(value) {
  return (
    reasonByValue.get(value) || {
      value,
      shortLabel: value,
      icon: 'other',
    }
  )
}

export function parseBuyerRejectionReasons(raw) {
  if (!raw) return []
  let values = raw
  if (typeof raw === 'string') {
    try {
      values = JSON.parse(raw)
    } catch {
      values = [raw]
    }
  }
  if (!Array.isArray(values)) return []
  return [
    ...new Set(
      values
        .filter((value) => typeof value === 'string' && value.trim())
        .map((value) => value.trim()),
    ),
  ]
}
