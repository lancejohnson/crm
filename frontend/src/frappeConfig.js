// frappe-ui global config that MUST be in place before any other app module
// evaluates.
//
// `composables/settings.js` creates `auto: true` resources at module top level
// (is_sms_enabled / is_call_integration_enabled / is_whatsapp_installed).
// A resource resolves its fetcher at call time via getConfig('resourceFetcher')
// and falls back to frappe-ui's bare `request`, which does NOT prefix
// `/api/method/` -- so a resource that fires before setConfig runs fetches the
// RELATIVE url `crm.api.sms.is_sms_enabled`, gets index.html back and fails
// with `Unexpected token '<'`. That is exactly what happened when App.vue
// gained a static import of settings.js (bd51726e): settings.js moved into the
// eager graph, evaluated before main.js's body, and the Text button / Text
// Messages tab vanished from every lead because smsEnabled never became true.
//
// ES modules evaluate imports depth-first in source order, so importing this
// file FIRST in main.js guarantees the config exists for everything after it.
import { setConfig, frappeRequest } from 'frappe-ui'

setConfig('resourceFetcher', frappeRequest)
