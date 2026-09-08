/**
 * Board columns for scratch properties (`/properties`). The list itself comes
 * from the server (`crm.api.properties.STAGES`) so a rename is one edit; this is
 * only the colour each stage wears, keyed by name, with a fallback for a stage
 * the palette does not know yet.
 */
const PALETTE = {
  New: { theme: 'gray', dot: 'bg-gray-400' },
  Comped: { theme: 'blue', dot: 'bg-blue-500' },
  'Offer Sent': { theme: 'orange', dot: 'bg-orange-500' },
  'Follow Up': { theme: 'purple', dot: 'bg-purple-500' },
  Dead: { theme: 'red', dot: 'bg-red-500' },
}

export function stageTheme(stage) {
  return PALETTE[stage]?.theme || 'gray'
}

export function stageDot(stage) {
  return PALETTE[stage]?.dot || 'bg-gray-400'
}
