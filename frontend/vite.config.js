import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import path from 'path'
import { execFileSync } from 'child_process'
import { VitePWA } from 'vite-plugin-pwa'

// https://vitejs.dev/config/
// Point `yarn dev` at a REMOTE Frappe instead of a local bench:
//
//   CRM_DEV_TARGET=https://crm.groundworkpro.com yarn dev
//
// There is no local dev mirror (removed 2026-06-19, deliberately), so the only
// way to exercise a UI change used to be a full deploy. `yarn build` is ~40s
// and irreducible -- minify off, sourcemaps off and dropping the PWA plugin
// each change it by ~2s -- so the only real speedup is not building at all.
// This proxies API/asset/auth routes to the remote site, giving HMR against
// real prod data.
//
// Unset, everything below behaves exactly as before.
const remoteTarget = process.env.CRM_DEV_TARGET

// Auth for the proxy. A Frappe API key authenticates every proxied request, so
// there is no login page and no 7-day cookie to re-enter -- API keys do not
// expire. It also sidesteps CSRF: token-authenticated writes skip the
// X-Frappe-CSRF-Token check, which matters because the dev server serves NO
// jinja boot data, so window.csrf_token is undefined here.
//
// Read from $CRM_DEV_TOKEN if set, else pulled from Infisical (groundwork/dev,
// CRM_DEV_API_TOKEN) so nothing is stored in the repo. If neither is available
// this falls back to cookie auth -- you just have to log in at localhost:8080.
//
// NOTE: while the dev server runs, anything that can reach localhost:8080 acts
// as that user. Revoke by clearing api_key/api_secret on the User in Frappe.
function devToken() {
  if (!remoteTarget) return null
  if (process.env.CRM_DEV_TOKEN) return process.env.CRM_DEV_TOKEN
  try {
    return execFileSync(
      `${process.env.HOME}/.claude/skills/api-call/scripts/inf-secret`,
      ['-e', 'dev', 'CRM_DEV_API_TOKEN'],
      { encoding: 'utf8', timeout: 20000 },
    ).trim()
  } catch {
    console.warn('[crm-dev] no API token found — falling back to cookie login')
    return null
  }
}
const devAuth = devToken()

// Who that token belongs to. Needed because the SPA decides whether you are
// logged in from the `user_id` COOKIE (stores/session.js and
// utils/sidebarLinks.js currentUser()) -- never from the API. Token auth
// authenticates the proxy's requests but leaves the browser cookie-less, so
// without this the router guard sees isLoggedIn=false, sends you to
// /login?redirect-to=/crm, which proxies to prod, and prod -- seeing a valid
// token -- redirects you to its own absolute URL. You end up on the real CRM.
function devUser() {
  if (!remoteTarget || !devAuth) return null
  try {
    const out = execFileSync(
      'curl',
      ['-s', '-H', `Authorization: token ${devAuth}`,
       `${remoteTarget}/api/method/frappe.auth.get_logged_user`],
      { encoding: 'utf8', timeout: 20000 },
    )
    return JSON.parse(out).message || null
  } catch {
    return null
  }
}
const devAuthUser = devUser()

// window.sysdefaults, the other global production's jinja boot injects (the
// full set is site_name, csrf_token, sysdefaults). Not optional: meta.js,
// utils/index.js and numberFormat.js dereference it WITHOUT optional chaining
// -- `window.sysdefaults.currency`, `.date_format`, `.float_precision` -- so
// its absence throws mid-render. That is what left the Lead activity feed
// stuck on "Loading..." forever while every request returned 200.
// csrf_token is deliberately not injected: token auth skips the CSRF check,
// and FilesUploader already guards on the global being present.
function devSysdefaults() {
  if (!remoteTarget || !devAuth) return null
  try {
    const out = execFileSync(
      'curl',
      ['-s', '-H', `Authorization: token ${devAuth}`,
       `${remoteTarget}/api/resource/System%20Settings/System%20Settings`],
      { encoding: 'utf8', timeout: 20000 },
    )
    return JSON.parse(out).data || null
  } catch {
    return null
  }
}
const devDefaults = devSysdefaults()

export default defineConfig(async ({ mode }) => {
  const isDev = mode === 'development'
  const config = {
    plugins: [
      // Production renders crm.html through jinja and injects the boot dict as
      // window[...] globals. The dev server renders index.html itself, so NONE
      // of that exists -- frappe-ui's jinjaBootData plugin is explicitly a
      // no-op when context.server is set. window.site_name being undefined is
      // not cosmetic: socket.js uses it as the socket.io NAMESPACE, so realtime
      // would silently connect to "/undefined" and never receive an event.
      // Derive it from the proxy target, which is what it is in production.
      {
        name: 'crm-dev-boot',
        apply: 'serve',
        transformIndexHtml(html) {
          if (!remoteTarget) return html
          const site = new URL(remoteTarget).hostname
          const lines = [`window.site_name = ${JSON.stringify(site)};`]
          if (devDefaults) {
            lines.push(
              `window.sysdefaults = ${JSON.stringify(devDefaults)};`,
            )
          }
          if (devAuthUser) {
            // Not real auth -- the proxy's Authorization header is what actually
            // authenticates. This only tells the SPA who it is looking at, so
            // the router guard stops bouncing to /login.
            lines.push(
              `document.cookie = "user_id=" + ${JSON.stringify(devAuthUser)} + "; path=/";`,
            )
          }
          return html.replace(
            '</body>',
            `<script>${lines.join('\n')}</script>\n</body>`,
          )
        },
      },
      vue(),
      vueJsx(),
      VitePWA({
        // The precaching service worker served stale app bundles after deploys
        // (a new SW installs but waits behind the open tab, so users kept the
        // old JS — e.g. the pre-fix SMS pane). selfDestroying ships a SW that
        // unregisters itself and clears its caches, so the CRM is always served
        // fresh from the server. We don't use offline / installable-PWA mode.
        selfDestroying: true,
        registerType: 'autoUpdate',
        devOptions: {
          enabled: true,
        },
        manifest: {
          display: 'standalone',
          name: 'Frappe CRM',
          short_name: 'Frappe CRM',
          start_url: '/crm',
          description:
            'Modern & 100% Open-source CRM tool to supercharge your sales operations',
          icons: [
            {
              src: '/assets/crm/manifest/manifest-icon-192.maskable.png',
              sizes: '192x192',
              type: 'image/png',
              purpose: 'any',
            },
            {
              src: '/assets/crm/manifest/manifest-icon-192.maskable.png',
              sizes: '192x192',
              type: 'image/png',
              purpose: 'maskable',
            },
            {
              src: '/assets/crm/manifest/manifest-icon-512.maskable.png',
              sizes: '512x512',
              type: 'image/png',
              purpose: 'any',
            },
            {
              src: '/assets/crm/manifest/manifest-icon-512.maskable.png',
              sizes: '512x512',
              type: 'image/png',
              purpose: 'maskable',
            },
          ],
        },
      }),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
    optimizeDeps: {
      include: [
        'feather-icons',
        'tailwind.config.js',
        'prosemirror-state',
        'prosemirror-view',
        'lowlight',
        'interactjs',
        // Pre-bundle reka-ui in dev: served unbundled, its TabsIndicator
        // ResizeObserver fires against a null element and crashes the Lead/Deal
        // detail pages (only under `yarn dev` — the prod Rollup build is fine).
        // optimizeDeps is dev-only, so this is inert in `vite build`.
        'reka-ui',
      ],
    },
    server: {
      fs: {
        allow: [path.resolve(__dirname, '..')],
      },
      // changeOrigin so Frappe resolves the site from the Host header (it 404s
      // "localhost does not exist" otherwise); cookieDomainRewrite so the
      // session cookie the remote sets is accepted on localhost.
      ...(remoteTarget && {
        port: 8080,
        proxy: {
          '^/(api|assets|files|private|login|app|desk|socket.io)': {
            target: remoteTarget,
            changeOrigin: true,
            secure: true,
            ws: true,
            cookieDomainRewrite: '',
            ...(devAuth && {
              headers: { Authorization: `token ${devAuth}` },
              // Token auth creates no session, so Frappe still answers with
              // `user_id=Guest; full_name=Guest; sid=Guest` on every response.
              // Those would overwrite the identity cookie injected below and
              // the router guard would bounce to /login -> prod. When the
              // Authorization header is doing the authenticating, response
              // cookies are noise: drop them.
              configure(proxy) {
                proxy.on('proxyRes', (proxyRes) => {
                  delete proxyRes.headers['set-cookie']
                })
              },
            }),
          },
        },
      }),
    },
  }

  const frappeui = await importFrappeUIPlugin(isDev, config)
  config.plugins.unshift(
    frappeui({
      // frappeProxy hardcodes a LOCAL bench (127.0.0.1:<webserver_port>), so
      // it must be off when proxying to a remote site.
      frappeProxy: !remoteTarget,
      lucideIcons: true,
      jinjaBootData: true,
      buildConfig: {
        indexHtmlPath: '../crm/www/crm.html',
        // Do NOT wipe the output dir. Every chunk is content-hashed, and a
        // deploy re-hashes nearly all of them (measured gw221 -> gw223: 124 of
        // 127 chunks changed name), so emptying the dir deletes the exact files
        // that every currently-open tab is still lazily importing. The next
        // route a rep navigated to 404'd and the SPA threw — losing whatever
        // they'd typed and not yet saved. Leaving old chunks in place lets open
        // sessions run to completion; they pick up the new bundle on reload.
        // Old assets are pruned separately rather than on every build.
        emptyOutDir: false,
        sourcemap: true,
      },
    }),
  )

  return config
})

async function importFrappeUIPlugin(isDev, config) {
  if (isDev) {
    try {
      // Check if local frappe-ui has the vite plugin file
      const fs = await import('node:fs')
      const localVitePluginPath = path.resolve(__dirname, '../frappe-ui/vite')

      if (fs.existsSync(localVitePluginPath)) {
        const module = await import('../frappe-ui/vite')
        console.info('Local frappe-ui vite plugin found, using local plugin')
        config.resolve.alias = getAliases(config)
        return module.default
      } else {
        console.warn('Local frappe-ui vite plugin not found, using npm package')
      }
    } catch (error) {
      console.warn(
        'Local frappe-ui not found, falling back to npm package:',
        error.message,
      )
    }
  }
  // Fall back to npm package if local import fails
  const module = await import('frappe-ui/vite')
  return module.default
}

function getAliases(config) {
  return {
    ...config.resolve.alias,
    'frappe-ui/tailwind': path.resolve(
      __dirname,
      '../frappe-ui/tailwind/preset.js',
    ),
    'frappe-ui/style.css': path.resolve(
      __dirname,
      '../frappe-ui/src/style.css',
    ),
    'frappe-ui/frappe': path.resolve(__dirname, '../frappe-ui/frappe/index.js'),
    'frappe-ui': path.resolve(__dirname, '../frappe-ui/src/index.ts'),
  }
}
