import { call, createResource } from 'frappe-ui'

// Preset text messages (team list + the rep's own), shared by every composer
// so the lead page, the header Text modal and the Today card show the same
// chips. One resource, cached, refreshed after any save.
export const textPresets = createResource({
  url: 'crm.api.text_presets.get_text_presets',
  cache: 'crm:text-presets',
  auto: true,
})

// A token the lead could not fill renders as `[first name?]` and the composer
// refuses to send while one remains — "Hi , this is German" is the text a
// seller reads as a robot. Labels mirror TOKENS in crm/api/text_presets.py.
export const UNFILLED_RE = /\[(first name|street|address|city|your name)\?\]/

export function hasUnfilled(text) {
  return UNFILLED_RE.test(text || '')
}

// Fill a preset body for one lead. Rendering lives on the server so the token
// definitions exist once and the Today card needs no extra fields.
export function renderPreset(lead, body) {
  return call('crm.api.text_presets.render_text_preset', { lead, body })
}
