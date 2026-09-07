<template>
  <div class="active-call" :aria-label="__('Active call')">
    <div class="call-state"><span class="connection-dot" :class="phone.state" />{{ stateLabel }}<span class="elapsed">{{ elapsed }}</span></div>
    <h2>{{ phone.peerName || formatPhone(phone.peerNumber) || __('Call') }}</h2>
    <p class="number">{{ formatPhone(phone.peerNumber) }}<router-link v-if="phone.lead" :to="`/leads/${phone.lead}`" class="ml-2 underline">{{ __('Open lead') }}</router-link></p>

    <template v-if="phone.role === 'supervisor'">
      <div class="modes" :aria-label="__('Microphone audience')">
        <Button v-for="m in modes" :key="m.id" :variant="phone.mode === m.id ? 'solid' : 'subtle'" :aria-pressed="phone.mode === m.id" @click="setMode(m.id)">{{ m.label }}</Button>
      </div>
      <p class="audience" :class="{ speaking: phone.mode === 'barge' }" role="status">{{ audiences[phone.mode] }}</p>
      <Button class="end-call" theme="red" iconLeft="phone-off" @click="hangup">{{ __('Leave call') }}</Button>
      <p class="context">{{ __('Only you leave; the rep and caller stay connected.') }}</p>
    </template>

    <template v-else>
      <div class="call-controls">
        <Button :variant="phone.muted ? 'solid' : 'subtle'" :aria-pressed="phone.muted" :iconLeft="phone.muted ? 'mic-off' : 'mic'" @click="toggleMute">{{ phone.muted ? __('Unmute') : __('Mute') }}</Button>
        <Button :variant="phone.held ? 'solid' : 'subtle'" :aria-pressed="phone.held" iconLeft="pause" @click="toggleHold">{{ phone.held ? __('Resume') : __('Hold') }}</Button>
        <Button icon="grid" :aria-label="__('Keypad')" :aria-expanded="keypad" @click="keypad = !keypad" />
      </div>
      <div v-if="keypad" class="keypad"><output>{{ digits || __('Keypad') }}</output><div><Button v-for="key in '123456789*0#'" :key="key" @click="press(key)">{{ key }}</Button></div></div>
      <div class="invite">
        <FormControl v-model="note" :aria-label="__('Note for the closer')" :placeholder="__('A quick note for the closer…')" />
        <Button iconLeft="zap" variant="solid" :disabled="invited || !phone.lead || sending" :title="phone.lead ? '' : __('Link the call to a lead first')" @click="liveOne">{{ invited ? __('Closer notified') : __('Got a live one') }}</Button>
      </div>
      <p v-if="invited" class="context">{{ __('Your invitation is with the closer until handled.') }}</p>
      <Button class="end-call" theme="red" iconLeft="phone-off" @click="hangup">{{ __('End call') }}</Button>
    </template>
  </div>
</template>
<script setup>
import { Button, FormControl, call, toast } from 'frappe-ui'
import { computed, ref, watch } from 'vue'
import { formatPhone } from '@/utils/phoneFormat'
import { phone, elapsed, hangup, toggleMute, toggleHold, dtmf, setMode } from '@/composables/phone'

const keypad = ref(false)
const digits = ref('')
const note = ref('')
const invited = ref(false)
const sending = ref(false)
const modes = [{ id: 'monitor', label: __('Listen') }, { id: 'whisper', label: __('Whisper') }, { id: 'barge', label: __('Barge') }]
const audiences = {
  monitor: __('You hear both people. Neither hears you.'),
  whisper: __('Only the rep hears you. The caller cannot hear your coaching.'),
  barge: __('Both people hear you. You are part of the conversation.'),
}
const stateLabel = computed(() => ({
  connecting: __('Connecting…'), 'ringing-out': __('Ringing…'), 'ringing-in': __('Incoming'),
  active: phone.held ? __('On hold') : phone.role === 'supervisor' ? __('Joined') : __('Connected'),
})[phone.state] || '')
function press(key) { digits.value += key; dtmf(key) }
async function liveOne() {
  if (!phone.lead || sending.value) return
  sending.value = true
  try {
    await call('crm.api.telephony.live_one', { lead: phone.lead, note: note.value.trim(), call_log: phone.callLog })
    invited.value = true
  } catch (e) {
    toast.error(e?.messages?.[0] || __('Could not send the alert'))
  } finally { sending.value = false }
}
watch(() => phone.callLog, () => { invited.value = false; note.value = ''; digits.value = ''; keypad.value = false })
</script>
<style scoped>
.active-call { padding: 18px 16px 16px; }
.call-state { display: flex; align-items: center; gap: 7px; font-size: 11px; color: var(--ink-gray-5, #777); }
.connection-dot { width: 7px; height: 7px; border-radius: 50%; background: #d9a536; }.connection-dot.active { background: #388452; }
.elapsed { margin-left: auto; font-variant-numeric: tabular-nums; }
.active-call h2 { margin-top: 10px; font-size: 20px; font-weight: 600; letter-spacing: -.4px; }
.number { font-size: 12px; color: var(--ink-gray-5, #777); margin-top: 3px; }
.context { margin-top: 10px; font-size: 11px; line-height: 1.5; color: var(--ink-gray-5, #777); }
.call-controls, .modes { display: flex; gap: 6px; margin-top: 16px; }.call-controls > *, .modes > * { flex: 1; }
.audience { margin-top: 10px; padding: 10px; border-radius: 8px; background: var(--surface-gray-1, #f7f7f7); font-size: 12px; line-height: 1.5; }.audience.speaking { background: #fff1f0; color: #a32e2e; }
.keypad { margin-top: 12px; }.keypad output { display: block; min-height: 22px; font-size: 16px; text-align: center; letter-spacing: 2px; }.keypad > div { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-top: 8px; }
.invite { display: flex; gap: 6px; margin-top: 16px; }.invite > :first-child { flex: 1; min-width: 0; }
.end-call { width: 100%; margin-top: 14px; }
</style>
