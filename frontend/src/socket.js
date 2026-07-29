import { io } from 'socket.io-client'
import { getCachedListResource, getCachedResource } from 'frappe-ui'

export function initSocket() {
  let siteName = window.site_name

  // Connect on the CURRENT origin, whatever it is. Upstream hardcoded
  // `:${socketio_port}` whenever window.location.port was set, which is right
  // for a local bench (app on :8000, socketio on :9000) but wrong for our dev
  // proxy: on localhost:8080 it dialled localhost:9000 directly, bypassing the
  // proxy, so realtime never worked outside a deploy. Same-origin instead lets
  // vite forward /socket.io to prod (the proxy already sets ws: true).
  //
  // Identical in production: there window.location.port is '' and this builds
  // exactly the string the old code did -- https://<host>/<siteName>.
  //
  // Dropping socketio_port also removes the only BUILD-TIME import of
  // sites/common_site_config.json, which is what forced the Dockerfile to seed
  // that key before running the build.
  let url = `${window.location.protocol}//${window.location.host}/${siteName}`

  let socket = io(url, {
    withCredentials: true,
    reconnectionAttempts: 5,
  })
  socket.on('refetch_resource', (data) => {
    if (data.cache_key) {
      let resource =
        getCachedResource(data.cache_key) ||
        getCachedListResource(data.cache_key)
      if (resource) {
        resource.reload()
      }
    }
  })
  return socket
}
