export function zillowUrl(address) {
  const slug = String(address || '')
    .replace(/[^A-Za-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return slug ? `https://www.zillow.com/homes/${slug}_rb/` : ''
}

// Only observed listing URLs qualify as direct links. Old caches and an older
// Redfin service legitimately lack them; never invent a listing ID from an address.
export function providerLink(provider, address, listingUrl) {
  const host = { Redfin: 'www.redfin.com', Realtor: 'www.realtor.com' }[provider]
  if (!host) return null
  try {
    const url = new URL(listingUrl || '', `https://${host}`)
    const listingPath = provider === 'Redfin'
      ? /\/home\/\d+\/?$/.test(url.pathname)
      : url.pathname.startsWith('/realestateandhomes-detail/')
    if (listingUrl && listingPath && ['http:', 'https:'].includes(url.protocol) &&
        [host, host.slice(4)].includes(url.hostname) && !url.username && !url.password) {
      url.protocol = 'https:'
      return { label: provider, href: url.href }
    }
  } catch { /* Invalid provider URL falls back to an explicitly named Google search. */ }
  const query = String(address || '').trim()
  return query ? {
    label: `Google ${provider}`,
    href: `https://www.google.com/search?q=${encodeURIComponent(`site:${host.slice(4)} ${query}`)}`,
  } : null
}

export function propertySearchAddress(property) {
  let address = String(property?.address || '').trim()
  if (!address) return ''
  const words = (value) => ` ${value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()} `
  for (const part of [property?.city, property?.state, property?.zip]) {
    const value = String(part || '').trim()
    if (value && !words(address).includes(words(value))) address += `, ${value}`
  }
  return address
}

export function mapsUrl(address) {
  return address
    ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`
    : ''
}
