import assert from 'node:assert/strict'
import { propertySearchAddress, providerLink, zillowUrl } from '../src/utils/propertyLinks.js'

const address = '1620 Iowa Ave E, Saint Paul, MN 55106'
const realtor = 'https://www.realtor.com/realestateandhomes-detail/1620-Iowa-Ave-E_Saint-Paul_MN_55106_M76973-83695'
const redfinPath = '/NC/Charlotte/4236-Foxcroft-Rd-28211/home/43999203'
assert.deepEqual(providerLink('Realtor', address, realtor), { label: 'Realtor', href: realtor })
assert.deepEqual(providerLink('Redfin', '4236 Foxcroft Rd, Charlotte, NC 28211', redfinPath), {
  label: 'Redfin', href: `https://www.redfin.com${redfinPath}`,
})
for (const provider of ['Redfin', 'Realtor']) {
  for (const url of [null, '', 'javascript:alert(1)', 'https://evil.com/home/1',
    'https://www.redfin.com.evil.com/home/1', 'https://user@www.redfin.com/home/1',
    '//evil.com/realestateandhomes-detail/a', 'https://www.realtor.com/']) {
    const link = providerLink(provider, address, url)
    assert.equal(link.label, `Google ${provider}`)
    assert.equal(new URL(link.href).hostname, 'www.google.com')
    assert.equal(new URL(link.href).searchParams.get('q'), `site:${provider.toLowerCase()}.com ${address}`)
  }
  assert.equal(providerLink(provider, '  ', null), null)
}
assert.equal(providerLink('Unknown', address, null), null)
assert.equal(propertySearchAddress({ address, city: 'Saint Paul', state: 'MN', zip: '55106' }), address)
assert.equal(propertySearchAddress({ address: '1620 Iowa Ave E', city: 'Saint Paul', state: 'MN', zip: '55106' }), '1620 Iowa Ave E, Saint Paul, MN, 55106')
assert.equal(propertySearchAddress({ address: '100 Main St', city: 'Indianapolis', state: 'IN' }), '100 Main St, Indianapolis, IN')
assert.equal(propertySearchAddress(null), '')
assert.equal(zillowUrl(address), 'https://www.zillow.com/homes/1620-Iowa-Ave-E-Saint-Paul-MN-55106_rb/')
console.log('propertyLinks: direct provider URLs, explicit Google fallbacks, URL safety, full address, Zillow regression passed')
