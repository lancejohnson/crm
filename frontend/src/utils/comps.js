const DIMENSIONS = [
  {
    key: 'type',
    label: 'type',
    subject: (s) => s?.property_type,
    comp: (c) => c?.property_type,
    matches: (a, b) => String(a).toLowerCase() === String(b).toLowerCase(),
  },
  {
    key: 'beds',
    label: 'beds',
    subject: (s) => number(s?.beds),
    comp: (c) => number(c?.bedrooms),
    matches: (a, b) => Math.abs(a - b) <= 1,
  },
  {
    key: 'baths',
    label: 'baths',
    subject: (s) => number(s?.baths),
    comp: (c) => number(c?.bathrooms),
    matches: (a, b) => Math.abs(a - b) <= 1,
  },
  {
    key: 'sqft',
    label: 'size',
    subject: (s) => number(s?.sqft),
    comp: (c) => number(c?.square_footage),
    matches: (a, b) => Math.abs(a - b) / Math.max(a, 1) <= 0.25,
  },
  {
    key: 'year',
    label: 'age',
    subject: (s) => number(s?.year_built),
    comp: (c) => number(c?.year_built),
    matches: (a, b) => Math.abs(a - b) <= 20,
  },
]

function number(value) {
  const n = Number(value)
  return Number.isFinite(n) && n > 0 ? n : null
}

function present(value) {
  return value !== null && value !== undefined && value !== ''
}

/**
 * A transparent fit count, using the same five tolerances as the server's
 * “similar” preset. “4/5 fit” is more honest and useful than an opaque 80 score.
 */
export function compFit(comp, subject) {
  const dimensions = DIMENSIONS.map((dimension) => {
    const subjectValue = dimension.subject(subject)
    const compValue = dimension.comp(comp)
    if (!present(subjectValue) || !present(compValue)) return null
    return {
      key: dimension.key,
      label: dimension.label,
      matches: dimension.matches(subjectValue, compValue),
    }
  }).filter(Boolean)
  const matched = dimensions.filter((dimension) => dimension.matches).length
  const total = dimensions.length
  const ratio = total ? matched / total : 0
  return {
    matched,
    total,
    ratio,
    dimensions,
    theme: !total ? 'gray' : ratio >= 0.8 ? 'green' : ratio >= 0.6 ? 'blue' : 'orange',
  }
}

export function compFacts(comp) {
  return [
    number(comp?.bedrooms) ? `${formatDecimal(comp.bedrooms)} bd` : '',
    number(comp?.bathrooms) ? `${formatDecimal(comp.bathrooms)} ba` : '',
    number(comp?.square_footage)
      ? `${Math.round(Number(comp.square_footage)).toLocaleString()} sf`
      : '',
    number(comp?.year_built) ? String(Math.round(Number(comp.year_built))) : '',
  ].filter(Boolean)
}

export function subjectFacts(subject) {
  return [
    number(subject?.beds) ? `${formatDecimal(subject.beds)} bd` : '',
    number(subject?.baths) ? `${formatDecimal(subject.baths)} ba` : '',
    number(subject?.sqft) ? `${Math.round(Number(subject.sqft)).toLocaleString()} sf` : '',
    number(subject?.year_built) ? String(Math.round(Number(subject.year_built))) : '',
  ].filter(Boolean)
}

export function compDifferences(comp, subject) {
  const out = []
  const sqft = delta(comp?.square_footage, subject?.sqft)
  if (sqft !== null) out.push(`${signed(Math.round(sqft))} sf`)

  const year = delta(comp?.year_built, subject?.year_built)
  if (year !== null && year !== 0) {
    out.push(`${Math.abs(Math.round(year))} yr ${year > 0 ? 'newer' : 'older'}`)
  }
  if (number(comp?.distance_mi) !== null) {
    out.push(`${Number(comp.distance_mi).toFixed(comp.distance_mi < 1 ? 1 : 1)} mi`)
  }
  return out
}

export function formatCompMoney(value) {
  const n = number(value)
  return n === null ? '—' : '$' + Math.round(n).toLocaleString()
}

function delta(a, b) {
  const aa = number(a)
  const bb = number(b)
  return aa === null || bb === null ? null : aa - bb
}

function signed(value) {
  if (!value) return 'same'
  return value > 0 ? `+${value.toLocaleString()}` : value.toLocaleString()
}

function formatDecimal(value) {
  const n = Number(value)
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, '')
}
