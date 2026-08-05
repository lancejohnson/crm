<template>
  <Dialog v-model="show" :options="{ title: dialogTitle, size: 'xl' }">
    <template #body-content>
      <!-- ── COMPOSE: pick recipients + write the template ───────────────── -->
      <div v-if="phase === 'compose'" class="flex flex-col gap-4">
        <!-- sender line -->
        <div v-if="linkedNumber" class="text-xs text-ink-gray-5">
          {{ __('Sending from') }}
          <span class="font-medium text-ink-gray-7">{{ formatPhone(linkedNumber) }}</span>
        </div>
        <div v-else class="flex items-center justify-between gap-2">
          <span class="text-xs text-ink-gray-5">
            {{ __('No Quo number linked to your profile yet.') }}
          </span>
          <Button :label="__('Select number')" @click="showSelectNumber = true" />
        </div>

        <!-- status failsafe: pick which interest stages to text -->
        <div v-if="hasStages">
          <div class="mb-1.5 text-xs text-ink-gray-5">{{ __('Statuses to text') }}</div>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="s in stagesPresent"
              :key="s"
              type="button"
              class="flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors"
              :class="stageActive(s)
                ? 'border-outline-gray-3 bg-surface-gray-2 text-ink-gray-8'
                : 'border-outline-gray-2 text-ink-gray-4'"
              @click="toggleStage(s)"
            >
              <span
                class="size-2 rounded-full"
                :class="stageActive(s) ? '' : 'opacity-40'"
                :style="{ backgroundColor: stageColor(s) }"
              />
              {{ s }} ({{ stageCount(s) }})
            </button>
          </div>
          <div class="mt-1 text-xs text-ink-gray-4">
            {{ __('“Not Interested” is off by default so you don’t text them. Click a status to include or exclude it.') }}
          </div>
        </div>

        <!-- recipients -->
        <div>
          <div class="mb-1.5 flex items-center justify-between">
            <span class="text-xs text-ink-gray-5">
              {{ selectedCount }} {{ __('of') }} {{ visible.length }} {{ __('selected') }}
              <span v-if="noPhone.length" class="text-ink-gray-4">
                · {{ noPhone.length }} {{ __('without a phone') }}
              </span>
              <span v-if="doNotContact.length" class="text-ink-red-3">
                · {{ doNotContact.length }} {{ __('do not contact') }}
              </span>
            </span>
            <div class="flex gap-3">
              <button class="text-xs text-ink-blue-3 hover:underline" @click="selectAll">
                {{ __('Select all') }}
              </button>
              <button class="text-xs text-ink-gray-5 hover:underline" @click="selectNone">
                {{ __('Clear') }}
              </button>
            </div>
          </div>
          <div class="max-h-52 overflow-y-auto rounded border border-outline-gray-2">
            <label
              v-for="r in visible"
              :key="r.name"
              class="flex cursor-pointer items-center gap-2.5 border-b border-outline-gray-1 px-3 py-2 text-sm last:border-b-0 hover:bg-surface-gray-1"
            >
              <input
                type="checkbox"
                class="size-3.5 rounded border-outline-gray-3 accent-surface-gray-7"
                :checked="selected.has(r.name)"
                @change="toggle(r.name)"
              />
              <span class="min-w-0 flex-1 truncate text-ink-gray-8">
                {{ r.buyer_name || '—' }}
              </span>
              <span
                v-if="r.stage"
                class="flex shrink-0 items-center gap-1 text-xs text-ink-gray-4"
              >
                <span class="size-1.5 rounded-full" :style="{ backgroundColor: stageColor(r.stage) }" />
                {{ r.stage }}
              </span>
              <span class="shrink-0 text-ink-gray-5">{{ formatPhone(r.phone) }}</span>
            </label>
            <div
              v-if="!visible.length"
              class="px-3 py-4 text-center text-sm text-ink-gray-4"
            >
              <!-- The empty state has to name the RIGHT reason. Do-not-contact
                   removes people from this list, so "nobody has a phone number"
                   was actively false for a buyer who has one and simply asked to
                   be left alone (caught in verification, gw298). -->
              {{ emptyReason }}
            </div>
          </div>
          <div v-if="noPhone.length" class="mt-1 text-xs text-ink-gray-4">
            {{ noPhone.length }} {{ __('buyer(s) skipped — no phone number on file.') }}
          </div>
          <!-- Named, not just counted: "3 excluded" is easy to scroll past, and the
               whole point is that a removal request stays visible (gw296). -->
          <div
            v-if="doNotContact.length"
            class="mt-1 rounded border border-outline-red-1 bg-surface-red-1 px-2 py-1.5 text-xs text-ink-red-4"
          >
            {{ doNotContact.length }}
            {{ __('buyer(s) removed — they asked not to be contacted:') }}
            {{ doNotContact.map((r) => r.buyer_name || r.name).join(', ') }}
          </div>
        </div>

        <!-- message template -->
        <div>
          <div class="mb-1.5 text-xs text-ink-gray-5">{{ __('Message') }}</div>
          <Textarea
            v-model="template"
            :rows="4"
            :placeholder="__('Hi {{first_name}}, we just listed a property that fits your buy box…')"
          />
          <div class="mt-1 text-xs text-ink-gray-4">
            {{ __('Tip:') }} <code class="rounded bg-surface-gray-2 px-1">{{ firstNameToken }}</code>
            {{ __('inserts each buyer’s first name. You’ll confirm every message before it sends.') }}
          </div>
        </div>
        <ErrorMessage :message="error" />
      </div>

      <!-- ── REVIEW: confirm one message at a time ───────────────────────── -->
      <div v-else-if="phase === 'review'" class="flex flex-col gap-4">
        <div class="flex items-center justify-between text-xs text-ink-gray-5">
          <span>
            {{ __('Message') }} {{ idx + 1 }} {{ __('of') }} {{ queue.length }}
          </span>
          <span>
            <span class="text-ink-green-3">{{ sentCount }} {{ __('sent') }}</span>
            <span v-if="skippedCount"> · {{ skippedCount }} {{ __('skipped') }}</span>
          </span>
        </div>

        <!-- who this goes to -->
        <div class="flex items-center justify-between rounded border border-outline-gray-2 px-3 py-2">
          <div class="min-w-0">
            <div class="flex items-center gap-1.5">
              <span class="truncate font-medium text-ink-gray-9">
                {{ current.buyer_name || '—' }}
              </span>
              <span
                v-if="current.stage"
                class="flex shrink-0 items-center gap-1 text-xs text-ink-gray-5"
              >
                <span class="size-1.5 rounded-full" :style="{ backgroundColor: stageColor(current.stage) }" />
                {{ current.stage }}
              </span>
            </div>
            <div class="text-xs text-ink-gray-5">{{ formatPhone(current.phone) }}</div>
          </div>
          <div class="text-xs text-ink-gray-5">
            {{ __('from') }} {{ formatPhone(linkedNumber) }}
          </div>
        </div>

        <!-- the exact text that will be sent (editable) -->
        <div>
          <div class="mb-1.5 text-xs text-ink-gray-5">
            {{ __('Confirm this message') }}
          </div>
          <Textarea v-model="current.text" :rows="4" />
        </div>
        <ErrorMessage :message="error" />
      </div>

      <!-- ── DONE ────────────────────────────────────────────────────────── -->
      <div v-else class="flex flex-col items-center gap-3 py-6 text-center">
        <CircleCheckIcon class="size-10 text-ink-green-3" />
        <div class="text-base font-medium text-ink-gray-9">
          {{ sentCount }} {{ __('text(s) sent') }}
        </div>
        <div v-if="skippedCount || failedCount" class="text-sm text-ink-gray-5">
          <span v-if="skippedCount">{{ skippedCount }} {{ __('skipped') }}</span>
          <span v-if="skippedCount && failedCount"> · </span>
          <span v-if="failedCount" class="text-ink-red-4">{{ failedCount }} {{ __('failed') }}</span>
        </div>
      </div>
    </template>

    <template #actions>
      <!-- compose -->
      <div v-if="phase === 'compose'" class="flex justify-end">
        <Button
          variant="solid"
          :label="__('Review & send') + ' (' + selectedCount + ')'"
          :disabled="!template.trim() || !selectedCount || !linkedNumber"
          @click="startReview"
        />
      </div>
      <!-- review -->
      <div v-else-if="phase === 'review'" class="flex items-center justify-between gap-2">
        <Button variant="ghost" :label="__('Back')" :disabled="idx === 0 || sending" @click="back" />
        <div class="flex gap-2">
          <Button :label="__('Skip')" :disabled="sending" @click="skip" />
          <Button
            variant="solid"
            :label="idx === queue.length - 1 ? __('Send') : __('Send & next')"
            :loading="sending"
            :disabled="!current.text.trim()"
            @click="sendCurrent"
          />
        </div>
      </div>
      <!-- done -->
      <div v-else class="flex justify-end">
        <Button variant="solid" :label="__('Close')" @click="show = false" />
      </div>
    </template>
  </Dialog>

  <SelectQuoNumberModal v-model="showSelectNumber" @saved="onNumberSaved" />
</template>

<script setup>
import SelectQuoNumberModal from '@/components/Modals/SelectQuoNumberModal.vue'
import { myQuoNumber, formatPhone } from '@/composables/quoSender'
import CircleCheckIcon from '~icons/lucide/circle-check'
import {
  call,
  Dialog,
  Textarea,
  Button,
  ErrorMessage,
  toast,
} from 'frappe-ui'
import { ref, computed, watch } from 'vue'

const props = defineProps({
  // [{ name (CRM Buyer id), buyer_name, phone, first_name?, stage? }]
  // `stage` = the buyer's per-property interest stage (present in property-scoped
  // contexts: Dispo board + property-filtered Buyers list). Drives the status
  // failsafe below.
  recipients: { type: Array, default: () => [] },
  // shown in the dialog title, e.g. the property address
  contextLabel: { type: String, default: '' },
})

// interest stages, canonical order + colors (mirrors the Dispo board), and the
// stage(s) excluded by default so a blast can't accidentally hit uninterested buyers
const STAGE_ORDER = ['New', 'Attempted to Contact', 'Not Interested', 'Interested', 'Offer Made']
const STAGE_COLOR = {
  New: '#3b82f6',
  'Attempted to Contact': '#f97316',
  'Not Interested': '#ef4444',
  Interested: '#22c55e',
  'Offer Made': '#a855f7',
}
const EXCLUDE_BY_DEFAULT = new Set(['Not Interested'])
function stageColor(s) {
  return STAGE_COLOR[s] || '#9ca3af'
}
const emit = defineEmits(['sent'])

const show = defineModel({ type: Boolean })

// literal token (kept out of the template to avoid nested {{ }} delimiters)
const firstNameToken = '{{first_name}}'

const phase = ref('compose') // compose | review | done
const template = ref('')
const error = ref(null)
const linkedNumber = ref('')
const showSelectNumber = ref(false)

// selection (compose)
const selected = ref(new Set())
const sending = ref(false)

// review queue
const queue = ref([])
const idx = ref(0)

const dialogTitle = computed(() =>
  props.contextLabel
    ? `${__('Text buyers')} · ${props.contextLabel}`
    : __('Text buyers'),
)

// Buyers who asked not to be contacted are removed outright — not unchecked,
// removed: they must not be reachable by a stray "Select all" (gw296). The
// backend refuses them too, so this is the courteous layer, not the guard.
const doNotContact = computed(() =>
  props.recipients.filter((r) => r.do_not_contact),
)
const contactable = computed(() =>
  props.recipients.filter((r) => !r.do_not_contact),
)

// buyers we can actually text (have a phone) vs. those we can't
const textable = computed(() =>
  contactable.value.filter((r) => (r.phone || '').trim()),
)
const noPhone = computed(() =>
  contactable.value.filter((r) => !(r.phone || '').trim()),
)

// ── status failsafe ──────────────────────────────────────────────────────────
// stages present among the recipients (only property-scoped recipients carry one)
const stagesPresent = computed(() => {
  const set = new Set(contactable.value.map((r) => r.stage).filter(Boolean))
  return STAGE_ORDER.filter((s) => set.has(s))
})
const hasStages = computed(() => stagesPresent.value.length > 0)

const emptyReason = computed(() => {
  if (doNotContact.value.length && !contactable.value.length)
    return doNotContact.value.length === 1
      ? __('That buyer asked not to be contacted.')
      : __('All of these buyers asked not to be contacted.')
  if (hasStages.value) return __('No buyers in the selected statuses.')
  if (doNotContact.value.length)
    return __('No one left to text — the rest asked not to be contacted.')
  return __('None of these buyers have a phone number on file.')
})
const activeStages = ref(new Set())

function stageActive(s) {
  return activeStages.value.has(s)
}
function stageCount(s) {
  return textable.value.filter((r) => r.stage === s).length
}
function toggleStage(s) {
  const set = new Set(activeStages.value)
  set.has(s) ? set.delete(s) : set.add(s)
  activeStages.value = set
  // re-sync the selection to whatever is now visible
  selected.value = new Set(visible.value.map((r) => r.name))
}

// textable buyers that pass the status filter (buyers with no stage always pass)
const visible = computed(() =>
  textable.value.filter(
    (r) => !hasStages.value || !r.stage || activeStages.value.has(r.stage),
  ),
)

const selectedCount = computed(() => selected.value.size)

function toggle(name) {
  const s = new Set(selected.value)
  s.has(name) ? s.delete(name) : s.add(name)
  selected.value = s
}
function selectAll() {
  selected.value = new Set(visible.value.map((r) => r.name))
}
function selectNone() {
  selected.value = new Set()
}

// render {{first_name}} / {{name}} for a recipient
function firstNameOf(r) {
  const fn = (r.first_name || '').trim()
  if (fn) return fn
  const parts = (r.buyer_name || '').trim().split(/\s+/)
  return parts[0] || 'there'
}
function render(text, r) {
  const fn = firstNameOf(r)
  return text
    .replaceAll('{{first_name}}', fn)
    .replaceAll('{{name}}', (r.buyer_name || '').trim() || fn)
}

const current = computed(() => queue.value[idx.value] || { text: '' })
const sentCount = computed(() => queue.value.filter((q) => q.status === 'sent').length)
const skippedCount = computed(() => queue.value.filter((q) => q.status === 'skipped').length)
const failedCount = computed(() => queue.value.filter((q) => q.status === 'failed').length)

function startReview() {
  const chosen = visible.value.filter((r) => selected.value.has(r.name))
  if (!chosen.length) return
  queue.value = chosen.map((r) => ({
    ...r,
    text: render(template.value, r),
    status: 'pending',
  }))
  idx.value = 0
  error.value = null
  phase.value = 'review'
}

function advance() {
  error.value = null
  if (idx.value < queue.value.length - 1) {
    idx.value += 1
  } else {
    phase.value = 'done'
    if (sentCount.value) emit('sent')
  }
}

function back() {
  if (idx.value > 0) {
    idx.value -= 1
    error.value = null
  }
}

function skip() {
  queue.value[idx.value].status = 'skipped'
  advance()
}

async function sendCurrent() {
  const r = queue.value[idx.value]
  const content = (r.text || '').trim()
  if (!content || sending.value) return
  sending.value = true
  error.value = null
  try {
    await call('crm.api.bulk_text.send_buyer_text', {
      buyer: r.name,
      content,
      from_number: linkedNumber.value,
    })
    r.status = 'sent'
    advance()
  } catch (e) {
    r.status = 'failed'
    error.value = e.messages?.[0] || __('Failed to send text')
  } finally {
    sending.value = false
  }
}

function onNumberSaved(number) {
  linkedNumber.value = number
}

// reset each time the modal opens
watch(show, (open) => {
  if (open) {
    phase.value = 'compose'
    template.value = ''
    error.value = null
    idx.value = 0
    queue.value = []
    linkedNumber.value = myQuoNumber()
    // status failsafe: default to every present stage EXCEPT "Not Interested"
    // (fall back to all if that would leave nothing selectable)
    let init = stagesPresent.value.filter((s) => !EXCLUDE_BY_DEFAULT.has(s))
    if (!init.length) init = [...stagesPresent.value]
    activeStages.value = new Set(init)
    selected.value = new Set(visible.value.map((r) => r.name))
    if (!linkedNumber.value) showSelectNumber.value = true
  }
})
</script>
