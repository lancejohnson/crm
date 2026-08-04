export function zillowUrl(address) {
  const slug = String(address || '')
    .replace(/[^A-Za-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return slug ? `https://www.zillow.com/homes/${slug}_rb/` : ''
}

export function mapsUrl(address) {
  return address
    ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`
    : ''
}
