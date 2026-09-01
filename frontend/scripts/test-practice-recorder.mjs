import assert from 'node:assert/strict'

const displayCalls = []
const recorderInstances = []
let activeRecorders = 0
let maxActiveRecorders = 0
let failFirstUpload = true
const uploadSequences = []
let finishCalls = 0

function track() {
  return {
    contentHint: '',
    stop() {},
    addEventListener() {},
  }
}

class FakeStream {
  constructor(tracks = [track(), track()]) {
    this.tracks = tracks
  }
  getTracks() {
    return this.tracks
  }
  getVideoTracks() {
    return [this.tracks[0]]
  }
  getAudioTracks() {
    return [this.tracks[1]]
  }
}

class FakeRecorder {
  static isTypeSupported() {
    return true
  }

  constructor() {
    this.state = 'inactive'
    this.listeners = new Map()
    recorderInstances.push(this)
  }

  addEventListener(name, fn) {
    this.listeners.set(name, fn)
  }

  start() {
    this.state = 'recording'
    activeRecorders += 1
    maxActiveRecorders = Math.max(maxActiveRecorders, activeRecorders)
  }

  stop() {
    if (this.state === 'inactive') return
    this.state = 'inactive'
    activeRecorders -= 1
    queueMicrotask(() => this.listeners.get('stop')?.())
  }

  pause() {
    this.state = 'paused'
  }

  resume() {
    this.state = 'recording'
  }

  emit(data) {
    this.ondataavailable?.({ data })
  }
}

Object.defineProperty(globalThis, 'navigator', {
  configurable: true,
  value: {
    mediaDevices: {
      async getDisplayMedia(options) {
        displayCalls.push(options)
        return new FakeStream()
      },
      async getUserMedia() {
        return new FakeStream()
      },
    },
  },
})

globalThis.window = { csrf_token: '' }
globalThis.MediaRecorder = FakeRecorder
globalThis.MediaStream = FakeStream
globalThis.fetch = async (url, options) => {
  if (String(url).includes('upload_recording_chunk')) {
    uploadSequences.push(options.body.get('seq'))
    if (failFirstUpload) {
      failFirstUpload = false
      return new Response('temporary failure', { status: 503 })
    }
    return new Response(JSON.stringify({ message: { ok: true } }), { status: 200 })
  }
  if (String(url).includes('finish_recording')) {
    finishCalls += 1
    return new Response(JSON.stringify({ message: { ok: true, url: '/recording' } }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    })
  }
  throw new Error(`Unexpected fetch: ${url}`)
}

const recorder = await import('../src/utils/practiceRecorder.js')

// Both user-facing capture choices retain distinct browser intent.
await recorder.startPracticeRecording('window')
await recorder.abandonPracticeRecording()
await recorder.startPracticeRecording('tab')
await recorder.abandonPracticeRecording()

const [windowOptions, tabOptions] = displayCalls
assert.equal(windowOptions.video.displaySurface, 'window')
assert.equal(windowOptions.selfBrowserSurface, 'exclude')
assert.equal(windowOptions.monitorTypeSurfaces, 'exclude')
assert.equal(tabOptions.video.displaySurface, 'browser')
assert.equal(tabOptions.preferCurrentTab, true)
assert.equal(tabOptions.selfBrowserSurface, 'include')

// Two rapid property transitions run through one recorder lane.
await recorder.startPracticeRecording('window')
recorder.setPracticeAttempt('ATTEMPT')
await Promise.all([
  recorder.beginPropertyRecording('PROPERTY-A'),
  recorder.beginPropertyRecording('PROPERTY-B'),
])
assert.equal(maxActiveRecorders, 1)
assert.equal(recorderInstances.at(-2).state, 'inactive')
assert.equal(recorderInstances.at(-1).state, 'recording')

// A transient upload failure retries the SAME sequence and keeps its blob until
// acknowledgement; finish waits for that retry rather than stamping a hole.
recorderInstances.at(-1).emit(new Blob(['durable chunk']))
await recorder.endPropertyRecording()
assert.deepEqual(uploadSequences, ['0', '0'])
assert.equal(finishCalls, 2) // empty A rollover + recorded B
await recorder.stopPracticeRecording()

console.log('practice recorder: capture modes, serialized rollover, durable retry PASS')
