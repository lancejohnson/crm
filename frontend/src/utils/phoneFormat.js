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
