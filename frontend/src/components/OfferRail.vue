<template>
  <!-- 340px wide with a 40px right gutter, which leaves the same ~288px of
       content a plain 300px rail had. The gutter is for somebody else's widget
       and it is deliberate: PostHog injects a "Report a problem" survey tab
       (button.ph-survey-widget-tab, in a shadow root, position:fixed, 35px wide,
       pinned to the right edge and vertically CENTRED) on every page of this
       app, prod included -- and it landed squarely on "Max offer", the one number
       the rep says out loud. Shadow DOM means our CSS cannot move it, and
       suppressing feedback on the screen reps work from all day is the wrong
       trade. Reserving the strip is the honest fix: the tab keeps working and
       nothing important is ever underneath it. -->
  <div class="flex w-[340px] shrink-0 flex-col gap-3 overflow-y-auto border-l p-3 pr-10"
       style="border-color: var(--surface-gray-2)">

    <!-- ARV, derived from the comps the rep actually ticked -->
    <div>
      <div class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-ink-gray-5">ARV</div>
      <div v-if="!picked.length" class="rounded border border-dashed p-2 text-xs text-ink-gray-5"
           style="border-color: var(--surface-gray-3)">
        Tick comps on the map to price this.
      </div>
      <template v-else>
        <div class="flex items-baseline justify-between">
          <span class="text-lg font-semibold text-ink-gray-9">{{ money(arv) }}</span>
          <span class="text-xs text-ink-gray-5">{{ money(avgPsf) }}/sf × {{ fmt(subjectSqft) }}sf</span>
        </div>
        <div class="mt-0.5 text-[11px] text-ink-gray-5">
          {{ usable.length }} of {{ picked.length }} comp{{ picked.length === 1 ? '' : 's' }}
          <span v-if="usable.length < picked.length" :title="'Comps without both a price and a size cannot produce a $/sf'">
            · {{ picked.length - usable.length }} unusable
          </span>
        </div>
      </template>
    </div>

    <!-- Repairs -->
    <div>
      <div class="mb-1 flex items-baseline justify-between">
        <span class="text-[10px] font-semibold uppercase tracking-wide text-ink-gray-5">Repairs</span>
        <span class="text-[10px] text-ink-gray-5">{{ bandLabel }}</span>
      </div>
      <div class="flex gap-1">
        <button
          v-for="l in LEVELS"
          :key="l.id"
          class="flex-1 rounded border px-1 py-1 text-[11px] leading-tight"
          :class="l.id === level
            ? 'border-outline-gray-4 bg-surface-gray-2 font-medium text-ink-gray-9'
            : 'border-transparent text-ink-gray-6 hover:bg-surface-gray-1'"
          @click="level = l.id"
        >
          <div>{{ l.short }}</div>
          <div class="text-ink-gray-5">{{ money(l.cost[band]) }}</div>
        </button>
      </div>

      <div class="mt-1.5 space-y-0.5">
        <label
          v-for="m in MAJORS"
          :key="m"
          class="flex cursor-pointer items-center gap-1.5 text-xs text-ink-gray-7"
        >
          <input type="checkbox" class="size-3 rounded" :value="m" v-model="majors" />
          <span class="flex-1">{{ m }}</span>
          <span class="text-ink-gray-5">+{{ money(MAJOR_COST) }}</span>
        </label>
      </div>

      <div class="mt-1.5 flex items-baseline justify-between border-t pt-1.5"
           style="border-color: var(--surface-gray-2)">
        <span class="text-xs text-ink-gray-6">Estimate</span>
        <span class="text-sm font-medium text-ink-gray-9">{{ money(repairs) }}</span>
      </div>
    </div>

    <!-- The offer, shown as the steps a rep says out loud -->
    <div>
      <div class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-ink-gray-5">Offer</div>
      <div class="space-y-0.5 text-xs">
        <div class="flex justify-between"><span class="text-ink-gray-6">ARV</span><span>{{ money(arv) }}</span></div>
        <div class="flex justify-between"><span class="text-ink-gray-6">× Margin</span><span>{{ MARGIN }}%</span></div>
        <div class="flex justify-between"><span class="text-ink-gray-6">= Gross</span><span>{{ money(gross) }}</span></div>
        <div class="flex justify-between">
          <span class="text-ink-gray-6" :title="DOUBLE_WHY">− Repairs × 2</span>
          <span>{{ money(repairs * 2) }}</span>
        </div>
        <div class="flex justify-between"><span class="text-ink-gray-6">− Fee</span><span>{{ money(FEE) }}</span></div>
      </div>
      <div class="mt-1.5 flex items-baseline justify-between border-t pt-1.5"
           style="border-color: var(--surface-gray-2)">
        <span class="text-[17px] font-semibold text-ink-gray-9">Max offer</span>
        <span class="text-[17px] font-semibold"
              :class="offer > 0 ? 'text-ink-gray-9' : 'text-ink-red-4'">{{ money(offer) }}</span>
      </div>
      <div v-if="arv && offer <= 0" class="mt-1 text-[11px] text-ink-red-4">
        Repairs and fee exceed {{ MARGIN }}% of ARV — there is no offer here at this repair level.
      </div>
    </div>

    <!-- The 2x2. Reuses the existing card rather than a second way to record it. -->
    <FirstCallReadCard
      v-if="lead"
      :lead="lead"
      :motivated="motivated"
      :on-price="onPrice"
      @saved="$emit('read-saved')"
    />

    <!-- Save. Pinned to the bottom of the rail so it is in the same place
         whatever the lead above it looks like. -->
    <div class="mt-auto border-t pt-2" style="border-color: var(--surface-gray-2)">
      <div class="mb-1.5 text-[11px] leading-snug" :class="drifted ? 'text-ink-amber-3' : 'text-ink-gray-5'">
        <template v-if="!saved">{{ __('Nothing saved for this lead yet.') }}</template>
        <template v-else-if="drifted">
          {{ __('Saved {0} at {1} — changed since.', [savedWhen, money(saved.offer)]) }}
        </template>
        <template v-else>
          {{ __('Saved {0} · offer {1}', [savedWhen, money(saved.offer)]) }}
        </template>
      </div>
      <div v-if="saved && !saved.stored" class="mb-1.5 text-[11px] text-ink-amber-3">
        {{ __('Recorded on the timeline only — the lead has nowhere to keep the current number yet.') }}
      </div>
      <Button
        class="w-full"
        variant="solid"
        :loading="saving"
        :disabled="!canSave"
        :label="drifted ? __('Re-save (S)') : __('Save (S)')"
        @click="save"
      />
      <div v-if="error" class="mt-1 text-[11px] text-ink-red-4">{{ error }}</div>
    </div>
  </div>
</template>

<script setup>
/**
 * The offer rail: ARV from the comps the rep ticked, repairs from Lance's Fix &
 * Flip matrix, and the offer those two produce.
 *
 * WHY REPAIRS ARE DOUBLED. The formula is 90% ARV − 2×Repairs − Fee, and the
 * doubling is deliberate rather than a fudge: the matrix is a cheat-sheet read
 * mid-call, and a buffer that overruns is recoverable where an offer that was
 * too high is not. It is shown as its own line so nobody mistakes it for the
 * repair estimate itself.
 *
 * ARV IS ROUNDED TO $1,000 because a rep says it out loud. "$117,000" is a
 * number you can defend; "$116,847" claims a precision that six comps and a
 * band-derived square footage do not have.
 *
 * Comps missing a price or a size are EXCLUDED from the average and counted out
 * loud rather than silently dropped — a $/sf built from four comps when the rep
 * ticked six is a different number than they think they are looking at.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { call, Button, toast } from 'frappe-ui'
import FirstCallReadCard from '@/components/FirstCallReadCard.vue'

const props = defineProps({
  lead: { type: String, required: true },
  picked: { type: Array, default: () => [] },
  subject: { type: Object, default: null },
  motivated: { type: String, default: '' },
  onPrice: { type: String, default: '' },
})
const emit = defineEmits(['read-saved', 'saved'])

const MARGIN = 90
const FEE = 10000
const MAJOR_COST = 10000
const MAJORS = ['Roof', 'Foundation', 'Plumbing', 'HVAC', 'Electrical']
const DOUBLE_WHY =
  'Doubled on purpose: the matrix is a mid-call cheat sheet, and a buffer that ' +
  'overruns is recoverable where an offer that was too high is not.'

// Lance's Fix & Flip matrix. Columns are square-footage bands, and the bands are
// the sheet's own — not interpolated, because the sheet is what the team quotes.
const BANDS = ['<1,500', '1,500–2,000', '2,000–2,500', '2,500+']
const LEVELS = [
  { id: 'smooth', short: 'Smooth', cost: [20000, 30000, 40000, 50000] },
  { id: 'shiver', short: 'Shiver', cost: [35000, 45000, 65000, 85000] },
  { id: 'abandon', short: 'Abandon', cost: [50000, 70000, 85000, 110000] },
]

const level = ref('smooth')
const majors = ref([])

const subjectSqft = computed(() => Number(props.subject?.sqft) || 0)

const band = computed(() => {
  const s = subjectSqft.value
  if (!s || s < 1500) return 0
  if (s < 2000) return 1
  if (s < 2500) return 2
  return 3
})
const bandLabel = computed(() => `${BANDS[band.value]} sqft`)

/** Only comps that can actually produce a $/sf. */
const usable = computed(() =>
  props.picked.filter((c) => Number(c.price) > 0 && Number(c.square_footage) > 0),
)

const avgPsf = computed(() => {
  if (!usable.value.length) return 0
  const sum = usable.value.reduce((a, c) => a + Number(c.price) / Number(c.square_footage), 0)
  return Math.round(sum / usable.value.length)
})

const arv = computed(() => {
  const v = avgPsf.value * subjectSqft.value
  return v ? Math.round(v / 1000) * 1000 : 0
})

const repairs = computed(() => {
  const base = LEVELS.find((l) => l.id === level.value).cost[band.value]
  return base + majors.value.length * MAJOR_COST
})

const gross = computed(() => Math.round((arv.value * MARGIN) / 100))
const offer = computed(() => Math.max(0, gross.value - repairs.value * 2 - FEE))

function money(n) {
  const v = Number(n) || 0
  return `$${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}
function fmt(n) {
  return (Number(n) || 0).toLocaleString('en-US')
}

/**
 * The saved determination.
 *
 * The snapshot carries the INPUTS and the CONSTANTS, not just the offer: "we
 * said $35,300" is unusable three weeks later without the comps, the $/sf and
 * the repair level that produced it, and storing `margin`/`fee` means a later
 * change to the formula cannot silently rewrite what we told a seller.
 *
 * Comps are copied, not referenced. `CRM Comp` is a projection of a feed that
 * re-syncs nightly and a BatchData fallback comp has no CRM row at all, so a
 * determination that resolved its comps by name would drift or empty out.
 */
function snapshot() {
  return {
    arv: arv.value,
    psf: avgPsf.value,
    subject_sqft: subjectSqft.value,
    level: level.value,
    majors: [...majors.value].sort(),
    repairs: repairs.value,
    margin: MARGIN,
    fee: FEE,
    offer: offer.value,
    comps: usable.value.map((c) => ({
      name: c.name,
      address: c.address,
      price: Number(c.price) || 0,
      square_footage: Number(c.square_footage) || 0,
      status: c.status || '',
      removed_date: c.removed_date || null,
      source: c.source || '',
    })),
    read: { motivated: props.motivated || '', on_price: props.onPrice || '' },
  }
}

const saved = ref(null)
const saving = ref(false)
const error = ref('')

/** The comparison that decides Save vs Re-save. Only the fields that change the
 *  number — `by`/`at`/`source` are stamped server-side and would make every
 *  saved determination look immediately stale. */
const COMPARED = [
  'arv', 'psf', 'subject_sqft', 'level', 'majors',
  'repairs', 'margin', 'fee', 'offer', 'comps', 'read',
]
function comparable(s) {
  return JSON.stringify(COMPARED.map((k) => s?.[k] ?? null))
}

const drifted = computed(
  () => !!saved.value && comparable(saved.value) !== comparable(snapshot()),
)
const canSave = computed(() => arv.value > 0 && !saving.value && (!saved.value || drifted.value))

const savedWhen = computed(() => {
  const at = saved.value?.at
  if (!at) return ''
  // Frappe hands back "YYYY-MM-DD HH:MM:SS" in SITE time with no zone, so it is
  // parsed as local rather than through Date.parse, which would read it as UTC.
  const m = String(at).match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/)
  if (!m) return String(at)
  const d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5])
  return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }).toLowerCase()
})

async function load() {
  saved.value = null
  if (!props.lead) return
  try {
    const d = await call('crm.api.price_determination.get_price_determination', {
      lead: props.lead,
    })
    if (d) saved.value = { ...d, stored: true }
  } catch (e) {
    // A determination that will not load must never stop the rep pricing the
    // deal — the rail simply reads as "nothing saved yet".
    console.error(e)
  }
}

async function save() {
  if (!canSave.value) return
  saving.value = true
  error.value = ''
  try {
    const res = await call('crm.api.price_determination.save_price_determination', {
      lead: props.lead,
      determination: snapshot(),
    })
    saved.value = { ...res.determination, stored: !!res.stored }
    toast.success(__('Price determination saved'))
    emit('saved', saved.value)
  } catch (e) {
    error.value = e?.messages?.[0] || e?.message || __('Could not save the determination.')
  } finally {
    saving.value = false
  }
}

onMounted(load)
watch(() => props.lead, load)

defineExpose({ save, canSave })
</script>
