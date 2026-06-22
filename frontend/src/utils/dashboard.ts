import { dayjs } from 'frappe-ui'

export function getLastXDays(range: number = 30): string | null {
  const today = new Date()
  const lastXDate = new Date(today)
  lastXDate.setDate(today.getDate() - range)

  return `${dayjs(lastXDate).format('YYYY-MM-DD')},${dayjs(today).format(
    'YYYY-MM-DD',
  )}`
}

// Named calendar presets -> "from,to" (YYYY-MM-DD). Current periods (today,
// this week, this quarter) end at today so they don't trail empty future days.
export function getDateRange(preset: string): string {
  const today = dayjs()
  const fmt = (d: ReturnType<typeof dayjs>) => d.format('YYYY-MM-DD')
  const q = Math.floor(today.month() / 3) // 0-3
  const thisQuarterStart = today.startOf('month').month(q * 3)

  switch (preset) {
    case 'Yesterday': {
      const y = today.subtract(1, 'day')
      return `${fmt(y)},${fmt(y)}`
    }
    case 'This Week':
      return `${fmt(today.startOf('week'))},${fmt(today)}`
    case 'Last Week': {
      const lw = today.subtract(1, 'week')
      return `${fmt(lw.startOf('week'))},${fmt(lw.endOf('week'))}`
    }
    case 'This Quarter':
      return `${fmt(thisQuarterStart)},${fmt(today)}`
    case 'Last Quarter':
      return `${fmt(thisQuarterStart.subtract(3, 'month'))},${fmt(
        thisQuarterStart.subtract(1, 'day'),
      )}`
    case 'Today':
    default:
      return `${fmt(today)},${fmt(today)}`
  }
}

export function formatter(range: string) {
  const [from, to] = range.split(',')
  return `${formatRange(from)} to ${formatRange(to)}`
}

export function formatRange(date: string) {
  // Parse "YYYY-MM-DD" as a LOCAL date. `new Date('2026-06-19')` treats the
  // string as UTC midnight, which toLocaleDateString then renders in the local
  // timezone — shifting the displayed day back one (e.g. "Jun 18") west of UTC.
  const [y, m, d] = date.split('-').map(Number)
  const dateObj = new Date(y, m - 1, d)
  return dateObj.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year:
      dateObj.getFullYear() === new Date().getFullYear()
        ? undefined
        : 'numeric',
  })
}
