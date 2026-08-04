import './index.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createDialog } from './utils/dialogs'
import { initSocket } from './socket'
import router from './router'
import translationPlugin from './translation'
import App from './App.vue'
import { initTelemetry, setTelemetryRoute } from './telemetry'

import {
  FrappeUI,
  Button,
  Input,
  TextInput,
  FormControl,
  ErrorMessage,
  Dialog,
  Alert,
  Badge,
  setConfig,
  frappeRequest,
  FeatherIcon,
} from 'frappe-ui'

import { telemetryPlugin } from 'frappe-ui/frappe'

let globalComponents = {
  Button,
  TextInput,
  Input,
  FormControl,
  ErrorMessage,
  Dialog,
  Alert,
  Badge,
  FeatherIcon,
}

// create a pinia instance
let pinia = createPinia()

let app = createApp(App)

setConfig('resourceFetcher', frappeRequest)
// socketio:false because main.js creates the app's own socket below and
// overwrites $socket with it -- frappe-ui's instance was left connected but
// unreferenced (its socketio.js registers no listeners), i.e. a duplicate
// connection per user in PRODUCTION too. In dev it was worse: frappe-ui's
// version hardcodes port 9000 and uses the hostname as the site name, so it
// spammed ERR_CONNECTION_REFUSED against localhost:9000 on every reload.
app.use(FrappeUI, { socketio: false })
app.use(pinia)
app.use(router)
app.use(translationPlugin)
for (let key in globalComponents) {
  app.component(key, globalComponents[key])
}
app.use(telemetryPlugin, { app_name: 'crm' })

app.config.globalProperties.$dialog = createDialog

let socket

function mountApp() {
  // Telemetry starts only after boot/session context is available. The project is
  // configured for full-session replay; all rendered text and inputs are masked
  // in telemetry.js before anything leaves the browser.
  initTelemetry()
  setTelemetryRoute(router.currentRoute.value)
  router.afterEach((to) => setTelemetryRoute(to))

  socket = initSocket()
  app.config.globalProperties.$socket = socket
  app.mount('#app')
}

if (import.meta.env.DEV) {
  // get_context_for_dev throws unless the SERVER has developer_mode on. That is
  // fine against a local bench, but we develop against production (no local
  // mirror), where it is off -- and mounting used to live inside .then(), so
  // the promise rejected, mount() never ran and the page stayed completely
  // blank with only a ValidationError in the console. Mount regardless: when
  // the endpoint is unavailable the boot globals come from vite instead (see
  // the crm-dev-boot plugin in vite.config.js).
  //
  // Dev-only branch -- import.meta.env.DEV is false in production builds, so
  // none of this ships.
  frappeRequest({ url: '/api/method/crm.www.crm.get_context_for_dev' })
    .then((values) => {
      for (let key in values) {
        window[key] = values[key]
      }
    })
    .catch(() => {
      console.info(
        '[crm-dev] get_context_for_dev unavailable (developer_mode off on the ' +
          'target) — using boot data injected by vite',
      )
    })
    .finally(mountApp)
} else {
  mountApp()
}

if (import.meta.env.DEV) {
  window.$dialog = createDialog
}
