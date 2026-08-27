/**
 * Screen + mic capture for a practice run, one file per property.
 *
 * getDisplayMedia needs a user gesture, so the Start click grabs the tab + mic
 * and holds those streams. Each house then gets its own MediaRecorder on that
 * same mix — no second permission prompt when they move to the next one.
 *
 * Chunks upload as they arrive so a take never becomes one POST past nginx's
 * 50 MB body limit. Bitrate is speech-over-a-map: ~160 kbps video + 48 kbps
 * mic ≈ 5 MB for a 3-minute house, ~45 MB if they sit on one for 30 minutes.
 */
const TYPES = [
  'video/webm;codecs=vp8,opus',
  'video/webm;codecs=vp9,opus',
  'video/webm',
]

let mime = ''
let mixed = null
let recorder = null
let streams = []
let queue = []
let pumping = false
let attemptId = ''
let propertyId = ''
let seq = 0
let captureOn = false
let stopping = null
const listeners = new Set()

export function watchPracticeRecording(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

function emit() {
  const on = isPracticeRecording()
  listeners.forEach((fn) => fn(on))
}

export function canPracticeRecord() {
  return (
    typeof MediaRecorder !== 'undefined' &&
    !!navigator.mediaDevices?.getDisplayMedia &&
    TYPES.some((t) => MediaRecorder.isTypeSupported(t))
  )
}

export function isPracticeRecording() {
  return captureOn && streams.length > 0
}

export function isPracticeRecorderPaused() {
  return recorder?.state === 'paused'
}

export function hasPracticeRecorder() {
  return !!recorder && recorder.state !== 'inactive'
}

export function pausePracticeRecording() {
  if (recorder?.state === 'recording') {
    try {
      recorder.pause()
    } catch {
      /* ignore */
    }
    emit()
  }
}

export function resumePracticeRecording() {
  if (recorder?.state === 'paused') {
    try {
      recorder.resume()
    } catch {
      /* ignore */
    }
    emit()
  }
}

export async function startPracticeRecording() {
  // getDisplayMedia MUST be the first await — Chrome drops the click's user
  // gesture after any yield, and then the picker never appears.
  mime = TYPES.find((t) => MediaRecorder.isTypeSupported(t))
  // selfBrowserSurface include is the one that puts THIS tab in the picker;
  // Chrome hides the calling tab otherwise. preferCurrentTab pre-selects it.
  let display
  try {
    display = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: false,
      preferCurrentTab: true,
      selfBrowserSurface: 'include',
    })
  } catch (e) {
    if (e?.name === 'NotAllowedError') throw e
    display = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: false,
    })
  }
  stopTracks()
  captureOn = true
  queue = []
  seq = 0
  attemptId = ''
  propertyId = ''
  let mic
  try {
    mic = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    })
  } catch (e) {
    display.getTracks().forEach((t) => t.stop())
    captureOn = false
    throw e
  }
  streams = [display, mic]
  mixed = new MediaStream([
    ...display.getVideoTracks(),
    ...mic.getAudioTracks(),
  ])
  display.getVideoTracks()[0]?.addEventListener('ended', () => {
    stopPracticeRecording()
  })
  emit()
}

export function setPracticeAttempt(id) {
  attemptId = id || ''
  pump()
}

export async function beginPropertyRecording(property) {
  if (!captureOn || !mixed) return null
  const prev = await endPropertyRecording()
  if (!captureOn || !mixed) return prev
  queue = []
  seq = 0
  propertyId = property
  recorder = new MediaRecorder(mixed, {
    mimeType: mime || undefined,
    videoBitsPerSecond: 160_000,
    audioBitsPerSecond: 48_000,
  })
  recorder.ondataavailable = (e) => {
    if (e.data?.size) {
      queue.push(e.data)
      pump()
    }
  }
  recorder.start(1000)
  emit()
  return prev
}

export async function endPropertyRecording() {
  if (stopping) return stopping
  if (!recorder && !queue.length) return null
  stopping = (async () => {
    const rec = recorder
    recorder = null
    if (rec && rec.state !== 'inactive') {
      await new Promise((resolve) => {
        rec.addEventListener('stop', resolve, { once: true })
        try {
          rec.stop()
        } catch {
          resolve()
        }
      })
    }
    await pump()
    const result = await finish()
    propertyId = ''
    return result
  })()
  try {
    return await stopping
  } finally {
    stopping = null
  }
}

export async function abandonPracticeRecording() {
  queue = []
  propertyId = ''
  attemptId = ''
  const rec = recorder
  recorder = null
  if (rec && rec.state !== 'inactive') {
    try {
      rec.stop()
    } catch {
      /* already stopped */
    }
  }
  stopTracks()
  captureOn = false
  emit()
}

export async function stopPracticeRecording() {
  const result = await endPropertyRecording()
  stopTracks()
  captureOn = false
  emit()
  return result
}

function stopTracks() {
  for (const s of streams) {
    s.getTracks().forEach((t) => t.stop())
  }
  streams = []
  mixed = null
}

async function pump() {
  if (pumping || !attemptId || !propertyId) return
  pumping = true
  try {
    while (queue.length) {
      const blob = queue.shift()
      const n = seq
      seq += 1
      const form = new FormData()
      form.append('attempt', attemptId)
      form.append('property', propertyId)
      form.append('seq', String(n))
      form.append('file', blob, `chunk-${n}.webm`)
      const res = await fetch('/api/method/crm.api.practice.upload_recording_chunk', {
        method: 'POST',
        credentials: 'same-origin',
        headers: window.csrf_token ? { 'X-Frappe-CSRF-Token': window.csrf_token } : {},
        body: form,
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || 'upload failed')
      }
    }
  } finally {
    pumping = false
    if (queue.length && attemptId && propertyId) pump()
  }
}

async function finish() {
  if (!attemptId || !propertyId) return null
  const form = new FormData()
  form.append('attempt', attemptId)
  form.append('property', propertyId)
  const res = await fetch('/api/method/crm.api.practice.finish_recording', {
    method: 'POST',
    credentials: 'same-origin',
    headers: window.csrf_token ? { 'X-Frappe-CSRF-Token': window.csrf_token } : {},
    body: form,
  })
  if (!res.ok) return null
  const body = await res.json()
  return body?.message || body
}
