import { dayjs } from 'frappe-ui'

// Relative "in N days" chips land at 9:00 America/Chicago, not midnight and
// not "now + N×24h". Hour chips stay relative to now — a 2h follow-up at
// 3:40pm should be 5:40pm, not tomorrow morning.
export const TASK_DUE_TZ = 'America/Chicago'
export const TASK_DUE_HOUR = 9

export const DEFAULT_TASK_DUE_PRESETS = [
  { label: '2h', amount: 2, unit: 'hour' },
  { label: '3d', amount: 3, unit: 'day' },
  { label: '1wk', amount: 1, unit: 'week' },
  { label: '1mo', amount: 1, unit: 'month' },
]

export const TASK_DUE_UNITS = [
  { label: 'hours', value: 'hour' },
  { label: 'days', value: 'day' },
  { label: 'weeks', value: 'week' },
  { label: 'months', value: 'month' },
]

export function dueFromPreset(preset, now = dayjs()) {
  const amount = Number(preset?.amount)
  const unit = preset?.unit
  if (!amount || !unit) return now
  if (unit === 'hour' || unit === 'minute') {
    return now.add(amount, unit)
  }
  return now
    .tz(TASK_DUE_TZ)
    .add(amount, unit)
    .hour(TASK_DUE_HOUR)
    .minute(0)
    .second(0)
    .millisecond(0)
}

export function formatDueStamp(d) {
  return d.format('YYYY-MM-DD HH:mm:ss')
}

// DateTimePicker emits midnight when someone picks a calendar day with no
// time. Treat that as "that morning", not 12:00am.
export function snapMidnightToMorning(value) {
  if (!value) return value
  const d = dayjs(value)
  if (!d.isValid()) return value
  if (d.hour() === 0 && d.minute() === 0 && d.second() === 0) {
    return d.hour(TASK_DUE_HOUR).format('YYYY-MM-DD HH:mm:ss')
  }
  return value
}

export function dueLabel(date) {
  if (!date) return ''
  const d = dayjs(date)
  if (!d.isValid()) return ''
  const days = d.startOf('day').diff(dayjs().startOf('day'), 'day')
  const morning = d.hour() === TASK_DUE_HOUR && d.minute() === 0
  const time = d.format('h:mm a')
  if (days < 0) {
    if (days === -1) return 'yesterday'
    if (days > -7) return d.format('ddd')
    return d.format('MMM D')
  }
  if (days === 0) return morning ? 'today 9am' : time
  if (days === 1) return morning ? 'tomorrow 9am' : `tomorrow ${time}`
  if (days < 7) return morning ? `${d.format('ddd')} 9am` : `${d.format('ddd')} ${time}`
  return morning ? d.format('MMM D') : d.format('MMM D, h:mm a')
}
