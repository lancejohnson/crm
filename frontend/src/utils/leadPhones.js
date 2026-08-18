// Every distinct phone on a CRM Lead, primary first.
// Mirrors crm.api.lead_phones.iter_phones so the Call button, the Phones card
// and Send Text all agree about what numbers this lead has.

function last10(value) {
  const digits = String(value || '').replace(/\D/g, '')
  return digits.length >= 10 ? digits.slice(-10) : ''
}

function parseExtra(raw) {
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .map((item) => (typeof item === 'string' ? item : item?.number || ''))
      .filter(Boolean)
  } catch {
    return []
  }
}

export function listLeadPhones(doc) {
  if (!doc) return []
  const seen = new Set()
  const out = []
  for (const number of [
    doc.mobile_no,
    doc.phone,
    ...parseExtra(doc.extra_phones),
  ]) {
    const trimmed = String(number || '').trim()
    const digits = last10(trimmed)
    if (!trimmed || !digits || seen.has(digits)) continue
    seen.add(digits)
    out.push({
      number: trimmed,
      last10: digits,
      primary: out.length === 0,
    })
  }
  return out
}

export function primaryLeadPhone(doc) {
  return listLeadPhones(doc)[0]?.number || ''
}
