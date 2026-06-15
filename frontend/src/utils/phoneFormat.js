// Display-only US phone formatting — stored values stay raw.
// Returns the input unchanged unless it looks like a bare US phone number
// (10 digits, or 11 starting with 1), so names and free text pass through.
const PHONE_LIKE = /^[\d\s()+.\-]+$/

export function formatPhone(value) {
  if (!value || typeof value !== 'string' || !PHONE_LIKE.test(value.trim())) {
    return value
  }
  let digits = value.replace(/\D/g, '')
  if (digits.length === 11 && digits[0] === '1') {
    digits = digits.slice(1)
  }
  if (digits.length !== 10) return value
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`
}

// True on iOS/Android handsets & tablets — where the Quo (OpenPhone) app lives
// and its deep link can be handled. Desktop falls through to a plain tel: link.
function isMobileDevice() {
  return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent || '')
}

// Normalize a US-ish phone string to E.164 (+1XXXXXXXXXX). Non-US digit runs
// just get a leading '+'. Returns '' when there's nothing dialable.
function toE164(value) {
  const digits = String(value || '').replace(/\D/g, '')
  if (!digits) return ''
  if (digits.length === 10) return '+1' + digits
  if (digits.length === 11 && digits[0] === '1') return '+' + digits
  return '+' + digits
}

// Build a click-to-call href for a phone number.
//   Mobile: Quo/OpenPhone deep link so the call places through the workspace,
//     with `from` setting the caller-ID number and skipping the picker prompt.
//     (openphone://dial?number=…&from=…&action=call — mobile app only.)
//   Desktop: a plain tel: link.
// Returns '' when there's no dialable number, so callers can hide the link.
export function callHref(value, from = '') {
  const e164 = toE164(value)
  if (!e164) return ''
  if (isMobileDevice()) {
    const params = new URLSearchParams({ number: e164, action: 'call' })
    if (from) params.set('from', from)
    return `openphone://dial?${params.toString()}`
  }
  return `tel:${e164}`
}
