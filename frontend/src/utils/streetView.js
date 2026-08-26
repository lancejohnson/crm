/**
 * Google Maps Embed Street View. Same key as the lead-desk mockup
 * (project claude-code-486305, name "CRM Street View (Maps Embed)").
 *
 * Maps Embed keys are meant to live in the page — this one is restricted to
 * the Embed API and to crm.groundworkpro.com + localhost:8080 / :8477.
 *
 * `location=` is lat,lng only. An address string returns Invalid 'location'.
 * Use referrerpolicy="origin" on the iframe so record ids never go to Google.
 */
const MAPS_EMBED_KEY = 'AIzaSyBAIpb09ornAPq4nWMhCQqsuk46AjrErFo'

export function streetViewEmbedUrl(lat, lng) {
  if (lat == null || lng == null || Number.isNaN(Number(lat)) || Number.isNaN(Number(lng))) {
    return ''
  }
  return (
    `https://www.google.com/maps/embed/v1/streetview?key=${MAPS_EMBED_KEY}` +
    `&location=${Number(lat)},${Number(lng)}&heading=0&pitch=0&fov=90`
  )
}
