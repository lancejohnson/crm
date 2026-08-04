import posthog from 'posthog-js'

// PostHog project tokens are public browser identifiers, not secrets. Keeping all
// provider-specific behavior here makes a future OpenReplay/Sentry swap isolated.
const PROJECT_TOKEN = 'phc_q4dNYTopNUy2Y7Sdr9MEAt6RkatAUbD9we4wDMjehvDN'
const API_HOST = 'https://us.i.posthog.com'
const UI_HOST = 'https://us.posthog.com'

let initialized = false

function maskText(text) {
  // Keep spacing/layout usable while names, addresses, messages, transcripts,
  // comments and every other rendered value remain unreadable outside the browser.
  return text.replace(/\S/g, '•')
}

function scrubNetworkRequest(request) {
  try {
    const url = new URL(request.name, window.location.origin)
    // Frappe query strings can contain document names, filters and auth material.
    request.name = `${url.origin}${url.pathname}`
  } catch {
    request.name = request.name.split('?')[0]?.split('#')[0] || '[redacted]'
  }
  request.requestHeaders = undefined
  request.responseHeaders = undefined
  request.requestBody = undefined
  request.responseBody = undefined
  return request
}

function sessionUser() {
  const cookies = new URLSearchParams(document.cookie.split('; ').join('&'))
  const user = cookies.get('user_id')
  return user && user !== 'Guest' ? user : null
}

function frontendBuildId() {
  // Production's git metadata is deliberately absent from the Docker build
  // context, but the entry chunk is content-hashed and uniquely identifies the
  // exact frontend users are running. Local Vite builds retain the git-derived
  // value injected by vite.config.js.
  for (const script of document.scripts) {
    const match = script.src.match(/\/assets\/crm\/frontend\/assets\/index-([^/]+)\.js$/)
    if (match) return match[1]
  }
  return import.meta.env.VITE_CRM_BUILD_ID || 'unknown'
}

/** Start privacy-first, full-session replay for authenticated CRM users. */
export function initTelemetry() {
  if (initialized || typeof window === 'undefined' || !sessionUser()) return
  initialized = true

  posthog.init(PROJECT_TOKEN, {
    api_host: API_HOST,
    ui_host: UI_HOST,
    defaults: '2026-05-30',
    autocapture: false,
    capture_pageview: false,
    capture_pageleave: false,
    capture_exceptions: {
      capture_unhandled_errors: true,
      capture_unhandled_rejections: true,
      capture_console_errors: true,
    },
    capture_performance: { network_timing: true, web_vitals: false },
    enable_recording_console_log: false,
    person_profiles: 'identified_only',
    session_recording: {
      maskAllInputs: true,
      maskTextSelector: '*',
      maskTextFn: maskText,
      blockSelector: 'img, video, audio, canvas, iframe',
      recordHeaders: false,
      recordBody: false,
      captureCanvas: { recordCanvas: false },
      recordCrossOriginIframes: false,
      maskCapturedNetworkRequestFn: scrubNetworkRequest,
    },
    loaded: (client) => {
      client.identify(sessionUser(), { application: 'frappe-crm' })
      client.register({
        application: 'frappe-crm',
        build: frontendBuildId(),
        deployment: window.location.hostname === 'crm.groundworkpro.com' ? 'production' : 'development',
      })
    },
  })
}

/** Route context attached to feedback responses and exception events. */
export function setTelemetryRoute(route) {
  if (!initialized) return
  posthog.register({
    surface: route?.name ? String(route.name) : 'unknown',
    // Drop the query/hash but keep the document route needed to diagnose navigation bugs.
    route_path: route?.path || window.location.pathname,
  })
}

export function currentReplayUrl() {
  if (!initialized) return undefined
  return posthog.get_session_replay_url({ withTimestamp: true }) || undefined
}
