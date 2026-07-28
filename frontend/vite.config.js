import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import path from 'path'
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
// real prod data. Log in once through the dev server itself (localhost:8080/
// login) so the session cookie is scoped to localhost.
//
// Unset, everything below behaves exactly as before.
const remoteTarget = process.env.CRM_DEV_TARGET

export default defineConfig(async ({ mode }) => {
  const isDev = mode === 'development'
  const config = {
    plugins: [
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
