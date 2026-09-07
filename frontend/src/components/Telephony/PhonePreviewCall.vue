<template>
  <div v-if="p.call" class="active-call">
    <div class="call-state"><span class="connection-dot" />{{ p.held ? 'On hold' : 'Connected' }}<span class="elapsed">{{ p.call.elapsed }}</span></div>
    <h2>{{ p.call.name }}</h2><p class="number">{{ p.call.number }}</p>
    <p class="context">{{ p.role === 'closer' ? `Listening with ${p.call.rep}` : `Calling as ${p.call.rep}` }} · fictional call, not this CRM lead</p>
    <template v-if="p.role === 'closer'">
      <div class="modes" aria-label="Microphone audience"><Button v-for="mode in Object.keys(audiences)" :key="mode" :variant="p.mode === mode ? 'solid' : 'subtle'" :aria-pressed="p.mode === mode" @click="p.mode = mode">{{ mode }}</Button></div>
      <p class="audience" :class="{ speaking: p.mode === 'Barge' }" role="status">{{ audiences[p.mode] }}</p>
      <p class="context">Rep-only join tone indicator. No sound played.</p>
      <Button class="end-call" theme="red" iconLeft="phone-off" @click="leavePreviewCall(p)">Leave call</Button><p class="context">Only you leave; the other two stay connected.</p>
    </template>
    <template v-else>
      <div class="call-controls"><Button :variant="p.muted ? 'solid' : 'subtle'" :aria-pressed="p.muted" :iconLeft="p.muted ? 'mic-off' : 'mic'" @click="p.muted = !p.muted">{{ p.muted ? 'Unmute' : 'Mute' }}</Button><Button :variant="p.held ? 'solid' : 'subtle'" :aria-pressed="p.held" iconLeft="pause" @click="p.held = !p.held">{{ p.held ? 'Resume' : 'Hold' }}</Button><Button icon="grid" aria-label="Keypad" :aria-expanded="p.keypad" @click="p.keypad = !p.keypad" /></div>
      <div v-if="p.keypad" class="keypad"><output>{{ p.digits || 'Keypad' }}</output><div><Button v-for="key in '123456789*0#'" :key="key" @click="p.digits += key">{{ key }}</Button></div></div>
      <div class="invite"><FormControl v-model="p.note" aria-label="Note for Dennis" placeholder="A quick note for Dennis…" /><Button iconLeft="zap" variant="solid" :disabled="p.invited" @click="invitePreviewCloser(p)">{{ p.invited ? 'Dennis notified' : 'Got a live one' }}</Button></div>
      <div v-if="p.invited" class="invite-state"><p>{{ p.joined ? 'Dennis is listening · rep-only tone indicator' : 'Your invitation stays with Dennis until handled.' }}</p><Button v-if="!p.joined" variant="ghost" @click="p.joined = true">Preview Dennis joining</Button></div>
      <Button class="end-call" theme="red" iconLeft="phone-off" @click="leavePreviewCall(p)">End call</Button>
    </template>
  </div>
</template>
<script setup>
import { Button, FormControl } from 'frappe-ui'
import { phonePreview as p } from '@/composables/phonePreview'
import { audiences, invitePreviewCloser, leavePreviewCall } from '@/utils/phonePreview'
</script>
<style scoped>
.active-call { padding: 18px; color: var(--ink-gray-8, #333); }
.call-state { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--ink-gray-5, #777); }
.connection-dot { width: 6px; height: 6px; border-radius: 50%; background: #388452; }
.elapsed { margin-left: auto; font-variant-numeric: tabular-nums; }
h2 { margin: 15px 0 4px; font-size: 22px; font-weight: 600; letter-spacing: -.5px; }
.number { font-size: 13px; }
.context { margin-top: 10px; font-size: 11px; line-height: 1.5; color: var(--ink-gray-5, #777); }
.modes, .call-controls { display: flex; gap: 5px; margin-top: 18px; }
.modes > *, .call-controls > * { flex: 1; }
.audience { margin-top: 12px; padding: 10px 0; font-size: 13px; line-height: 1.5; border-block: 1px solid var(--outline-gray-1, #eee); }
.speaking { color: var(--ink-red-4, #ad3333); }
.invite { display: grid; gap: 8px; margin-top: 20px; }
.invite-state { font-size: 12px; padding: 10px 0; line-height: 1.5; }
.end-call { width: 100%; margin-top: 18px; }
.keypad { margin-top: 12px; }
.keypad output { display: block; text-align: center; font-size: 12px; padding: 6px; }
.keypad > div { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; }
</style>
