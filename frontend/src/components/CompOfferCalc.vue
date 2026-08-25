<template>
  <!-- ONE column by default; "+ Compare" adds the second. Two calculators
       side by side is the exception, not the norm, and the second column was
       costing ~5rem of width on a surface whose whole job is the map.

       The columns stay independent, like the sheet: shared-looking defaults
       (both ARVs empty, both $25k fee) but typing in one never writes the
       other — no merged cells. -->
  <div class="wrap">
  <div
    class="calc"
    :style="{ width: cols === 2 ? '30rem' : '21rem' }"
    @keydown="onKeys"
  >
    <div class="head">
      <span>{{ __('Cash offer') }}</span>
      <span class="head-r">
        <button
          v-if="cols === 1"
          type="button"
          class="link"
          :title="__('Run a second set of numbers beside this one')"
          @click="addCompare"
        >
          {{ __('+ Compare') }}
        </button>
        <button
          type="button"
          class="save"
          :disabled="!canSave || saving"
          @click="save"
        >
          {{ saving ? __('Saving…') : __('Save calcs') }}
        </button>
      </span>
    </div>

    <div
      class="grid"
      :style="{ gridTemplateColumns: cols === 2 ? '6.5rem 1fr 1fr' : '6.5rem 1fr' }"
    >
      <template v-if="cols === 2">
        <span />
        <span class="colh">{{ __('Scenario 1') }}</span>
        <span class="colh">
          {{ __('Scenario 2') }}
          <button
            type="button"
            class="drop"
            :title="__('Drop this scenario')"
            @click="cols = 1"
          >
            ×
          </button>
        </span>
      </template>

      <!-- The formula comes first because it frames every number under it.
           Per column, like everything else here: "+ Compare" then puts the two
           formulas side by side on the same house, which is the comparison a
           wholesaler actually wants. -->
      <span class="lab">{{ __('Formula') }}</span>
      <div v-for="col in visible" :key="'form' + col" class="seg">
        <button
          v-for="f in FORMULAS"
          :key="f.key"
          type="button"
          :class="{ on: multOf(col) === f.mult }"
          :title="f.why"
          @click="setFormula(col, f)"
        >
          {{ f.label }}
        </button>
      </div>

      <span class="lab">{{ __('ARV') }}</span>
      <input
        v-for="col in visible"
        :key="'arv' + col"
        :ref="(el) => setField(0, col, el)"
        :class="{ empty: !s[col].arv }"
        inputmode="numeric"
        :placeholder="arvHint"
        :value="s[col].arv ? money(s[col].arv) : ''"
        @focus="$event.target.select()"
        @input="typeMoney(col, 'arv', $event)"
      />

      <span class="lab">{{ __('% of ARV') }}</span>
      <label v-for="col in visible" :key="'pct' + col" class="pct">
        <input
          :ref="(el) => setField(1, col, el)"
          inputmode="numeric"
          :value="Math.round(s[col].pct * 100)"
          @focus="$event.target.select()"
          @change="setPct(col, $event)"
        />
        <i>%</i>
      </label>

      <span class="lab">{{ __('After %') }}</span>
      <span v-for="col in visible" :key="'after' + col" class="out">
        {{ s[col].arv ? money(run(col).after) : '—' }}
      </span>

      <!-- Repairs is a NAMED choice, not a number to invent. The rep is on the
           phone with a seller describing a house; "kitchen & baths" is a thing
           they can hear, "$30/sf" is not. Each row carries what that level
           costs on THIS house so the ladder has a felt price, not just a rate.
           "Other…" keeps the raw $/sf field one click away — the preset is a
           shortcut, never a cage. -->
      <span class="lab">{{ __('Repairs') }}</span>
      <div v-for="col in visible" :key="'rep' + col" class="rep">
        <template v-if="isCustom(col)">
          <input
            :ref="(el) => setField(2, col, el)"
            class="rep-psf"
            inputmode="numeric"
            :value="money(s[col].rehabPsf)"
            @focus="$event.target.select()"
            @input="typeMoney(col, 'rehabPsf', $event)"
          />
          <button
            type="button"
            class="rep-caret"
            :title="__('Pick a repair level')"
            @click="toggleMenu(col)"
          >
            ▾
          </button>
          <span class="rep-sf">{{ __('/sf') }}</span>
        </template>
        <button
          v-else
          type="button"
          class="rep-btn"
          :class="{ open: menuFor === col }"
          @click="toggleMenu(col)"
        >
          <span class="rep-name">{{ tierFor(col).label }}</span>
          <span class="vals">
            <i>{{ money(s[col].rehabPsf) }}/sf</i><b v-if="sqft">
              ({{ k(s[col].rehabPsf * sqft) }})</b>
          </span>
          <span class="caret">▾</span>
        </button>

        <div v-if="menuFor === col" class="menu">
          <button
            v-for="t in TIERS"
            :key="t.key"
            type="button"
            class="mrow"
            :class="{ on: s[col].rehabPsf === t.psf }"
            @click="pickTier(col, t)"
          >
            <span>{{ t.label }}</span>
            <span class="vals">
              <i>{{ money(t.psf) }}/sf</i><b v-if="sqft">
                ({{ k(t.psf * sqft) }})</b>
            </span>
          </button>
          <div class="msep" />
          <button type="button" class="mrow other" @click="pickOther(col)">
            {{ __('Other…') }}
          </button>
        </div>
      </div>

      <!-- This row is the DEDUCTION, not the repair bill: at 2× the two differ,
           and the number that hits the offer is the one that has to be on
           screen or the arithmetic above it stops adding up. The repair bill
           itself stays visible one row up, in the picker's (…k). -->
      <span class="lab">
        {{ multOf(0) === 2 || (cols === 2 &amp;&amp; multOf(1) === 2) ? __('Repairs') : __('Rehab') }}
        <i>{{ fmt(sqft) }} sf</i>
      </span>
      <div v-for="col in visible" :key="'rehab' + col" class="ded">
        <span v-if="multOf(col) === 2" class="x2" :title="DOUBLE_WHY">× 2</span>
        <input
          :ref="(el) => setField(3, col, el)"
          inputmode="numeric"
          :value="money(run(col).rehab)"
          @focus="$event.target.select()"
          @input="typeRehab(col, $event)"
        />
      </div>

      <span class="lab">{{ __('Wholesale') }}</span>
      <span v-for="col in visible" :key="'ws' + col" class="out">
        {{ s[col].arv ? money(run(col).wholesale) : '—' }}
      </span>

      <span class="lab">{{ __('Fee') }}</span>
      <input
        v-for="col in visible"
        :key="'fee' + col"
        :ref="(el) => setField(4, col, el)"
        inputmode="numeric"
        :value="money(s[col].fee)"
        @focus="$event.target.select()"
        @input="typeMoney(col, 'fee', $event)"
      />

      <span class="lab offer">{{ __('Offer') }}</span>
      <span
        v-for="col in visible"
        :key="'offer' + col"
        class="out offer"
        :class="{ bad: s[col].arv && run(col).offer <= 0, win: winner === col }"
      >
        <!-- Which one is bigger, and by how much. The gap is the whole reason
             anyone runs two of these, and eyeballing two five-figure numbers
             for a $800 difference is exactly the arithmetic this tool exists
             to stop doing in your head. -->
        <b v-if="winner === col" class="gap" :title="__('Higher of the two')">
          +{{ money(offerGap) }}
        </b>
        {{ s[col].arv ? money(run(col).offer) : '—' }}
      </span>
    </div>

    <!-- With one column the comparison cannot be on screen, so the other
         formula reports itself rather than making the rep toggle, read, and
         toggle back holding a number in their head. Its OWN percentage, since
         that is part of what is being compared. -->
    <div v-if="altOffer !== null" class="alt">
      {{
        __('{0} would offer {1}', [altFormula.label, money(altOffer)])
      }}<template v-if="altOffer !== run(0).offer">
        —
        <b :class="altOffer > run(0).offer ? 'up' : 'down'">
          {{ money(Math.abs(altOffer - run(0).offer)) }}
          {{ altOffer > run(0).offer ? __('more') : __('less') }}
        </b>
      </template>
    </div>
    <textarea
      v-model="notes"
      class="notes"
      rows="3"
      :placeholder="__('Notes — condition, access, what you told the seller…')"
    />
  </div>

    <table v-if="subjectRow || rows.length" class="tbl">
      <thead>
        <tr>
          <th>{{ __('Address') }}</th>
          <th>{{ __('Sale / list') }}</th>
          <th class="n">{{ __('Dist') }}</th>
          <th class="n">{{ __('Sq ft') }}</th>
          <th class="n">{{ __('Price') }}</th>
          <th class="n">{{ __('$/sf') }}</th>
          <th class="n">{{ __('On this') }}</th>
          <th>{{ __('Status') }}</th>
          <th />
        </tr>
      </thead>
      <tbody>
        <tr v-if="subjectRow" class="subj">
          <td class="street" :title="subjectRow.address">{{ subjectRow.street }}</td>
          <td>{{ subjectRow.date }}</td>
          <td class="n">—</td>
          <td class="n">{{ subjectRow.sqft }}</td>
          <td class="n">{{ subjectRow.price }}</td>
          <td class="n">{{ subjectRow.psf }}</td>
          <td class="n">—</td>
          <td>{{ __('Subject') }}</td>
          <td />
        </tr>
        <tr v-for="r in rows" :key="r.name">
          <td class="street" :title="r.address">
            <button type="button" @click="$emit('open', r.name)">{{ r.street }}</button>
          </td>
          <td>{{ r.date }}</td>
          <td class="n">{{ r.mi }}</td>
          <td class="n">{{ r.sqft }}</td>
          <td class="n">{{ r.price }}</td>
          <td class="n">{{ r.psf }}</td>
          <td class="n">{{ r.onThis }}</td>
          <td>{{ r.status }}</td>
          <td class="rm">
            <button
              type="button"
              :title="__('Remove from table — stays on the map')"
              @click="$emit('remove', r.name)"
            >
              ×
            </button>
          </td>
        </tr>
        <tr class="avg">
          <td colspan="5">{{ __('Average $/sf') }}</td>
          <td class="n">{{ avgPsf ? money(avgPsf) : '—' }}</td>
          <td class="n">{{ suggestedArv ? money(suggestedArv) : '—' }}</td>
          <td />
          <td />
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
/**
 * Cash Offer. Two formulas, because the desk uses both:
 *   2× repairs  ARV × 90% − 2×repairs − fee   (default; what OfferRail runs)
 *   Classic     ARV × 70% −   repairs − fee   (the 70% rule)
 * i.e. after = ARV × %, deduction = mult × $/sf × sqft, offer = after −
 * deduction − fee. Picking a formula sets its canonical %, and the % stays
 * editable afterwards — the toggle owns the SHAPE, the rep owns the number.
 *
 * `mult` is stored, unlike the repair tier, because it genuinely cannot be
 * derived: a 70% column does not imply a single deduction once the rep is free
 * to edit the percentage. Anything saved before this existed has no `mult` and
 * is read as Classic — which is what those numbers meant when they were
 * written.
 *
 * One scenario by default; "+ Compare" opens a second one carrying whatever
 * the rep is already on, and each column keeps its own toggle. Seeding it with
 * the other formula was tried and removed: it decided for them what was being
 * compared, when the far more common comparison is the same formula at two
 * percentages. Each column is its own notebook.
 *
 * Repairs are picked by NAME off a four-rung ladder. There is deliberately no
 * stored `tier` field — the tier is DERIVED from the $/sf, so there is nothing
 * to drift, an old saved calc names itself, and typing 30 into "Other…" is the
 * same thing as picking Kitchen & baths. A $/sf that matches no rung simply
 * renders as the raw input it always was.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { call, toast } from 'frappe-ui'
import { streetAddress } from '@/utils/comps'

const emit = defineEmits(['remove', 'open', 'saved'])

const props = defineProps({
  lead: { type: String, required: true },
  subject: { type: Object, default: null },
  comps: { type: Array, default: () => [] },
  address: { type: String, default: '' },
  // Snapshot from a timeline comment. When present, this is the source of
  // truth for the columns (not localStorage) so "Tweak calcs" opens on
  // the numbers that were actually saved, not a later draft.
  seed: { type: Object, default: null },
})

// Matches OfferRail.vue's rail so the two surfaces cannot name the same
// formula differently. Order is display order: the default leads.
const FORMULAS = [
  {
    key: 'double',
    label: __('2× repairs'),
    pct: 0.9,
    mult: 2,
    why: __('ARV × 90% − 2× repairs − fee'),
  },
  {
    key: 'classic',
    label: __('Classic'),
    pct: 0.7,
    mult: 1,
    why: __('ARV × 70% − repairs − fee — the 70% rule'),
  },
]
// Same reason the desk rail gives, and for the same doubling.
const DOUBLE_WHY = __(
  'Doubled on purpose: a buffer that overruns is recoverable where an offer ' +
    'that was too high is not.',
)

const TIERS = [
  { key: 'paint', label: __('Paint & carpet'), psf: 10 },
  { key: 'kitchen', label: __('Kitchen & baths'), psf: 30 },
  { key: 'full', label: __('Full rehab'), psf: 50 },
  { key: 'studs', label: __('Down to studs'), psf: 75 },
]

// Kitchen & baths — the middle-low rung, and the one the ladder opens on so
// the control reads as a named condition rather than an unnamed number.
const DEFAULT_PSF = 30
const DEFAULT_FEE = 25000

function fresh(f) {
  const g = f || FORMULAS[0]
  return { arv: 0, pct: g.pct, mult: g.mult, rehabPsf: DEFAULT_PSF, fee: DEFAULT_FEE }
}

const s = reactive([fresh(), fresh()])
const cols = ref(1)
// Only needed to hold the raw input open when the typed number happens to land
// on a rung; every other custom case falls out of `tierFor` returning nothing.
const custom = reactive([false, false])
const menuFor = ref(-1)
const notes = ref('')
const saving = ref(false)
const visible = computed(() => (cols.value === 2 ? [0, 1] : [0]))
const canSave = computed(
  () => visible.value.some((i) => s[i].arv > 0) && !saving.value,
)
const grid = [[null, null], [null, null], [null, null], [null, null], [null, null]]

function setField(row, col, el) {
  grid[row][col] = el || grid[row][col]
}

const storageKey = computed(() => `compsCalc:${props.lead}`)

function applyScene(i, row) {
  const base = fresh()
  const blank = !row || !Object.keys(row).length
  Object.assign(s[i], base, {
    arv: Number(row.arv) || 0,
    pct: Number(row.pct) || base.pct,
    rehabPsf: Number(row.rehabPsf ?? row.rehab_psf) || DEFAULT_PSF,
    fee: Number(row.fee) || DEFAULT_FEE,
    // A snapshot written before the toggle existed carries no `mult`, and its
    // numbers were computed with a single deduction — so it IS the classic
    // one. Only a genuine reset falls back to the column's default.
    mult: Number(row.mult) || (blank ? base.mult : 1),
  })
}

function loadSaved() {
  notes.value = ''
  menuFor.value = -1
  custom[0] = false
  custom[1] = false
  const seed = props.seed
  if (seed && Array.isArray(seed.scenarios) && seed.scenarios.length) {
    applyScene(0, {})
    applyScene(1, {})
    seed.scenarios.forEach((row, i) => {
      if (i < 2) applyScene(i, row)
    })
    cols.value = Math.min(2, Math.max(1, seed.scenarios.length))
    if (typeof seed.notes === 'string') notes.value = seed.notes
    return
  }
  cols.value = 1
  try {
    const raw = JSON.parse(localStorage.getItem(storageKey.value) || 'null')
    if (!raw) return
    // New shape is [{…},{…}]. The previous single-ARV blob is ignored — better
    // to start clean than to write one number into both columns.
    if (Array.isArray(raw.s) && raw.s.length === 2) {
      // Same rule as a saved snapshot: a draft with no `mult` predates the
      // toggle and is classic.
      raw.s.forEach((row, i) =>
        Object.assign(s[i], fresh(), row, { mult: Number(row.mult) || 1 }),
      )
    }
    if (raw.cols === 2) cols.value = 2
    if (typeof raw.notes === 'string') notes.value = raw.notes
  } catch {
    /* ignore */
  }
}

function persist() {
  try {
    localStorage.setItem(
      storageKey.value,
      JSON.stringify({ s, cols: cols.value, notes: notes.value }),
    )
  } catch {
    /* quota */
  }
}

watch(storageKey, loadSaved, { immediate: true })
watch(s, persist, { deep: true })
watch([notes, cols], persist)

const sqft = computed(() => Number(props.subject?.sqft) || 0)

function tierFor(col) {
  return TIERS.find((t) => t.psf === Number(s[col].rehabPsf)) || null
}
function isCustom(col) {
  return custom[col] || !tierFor(col)
}
function toggleMenu(col) {
  menuFor.value = menuFor.value === col ? -1 : col
}
function pickTier(col, t) {
  s[col].rehabPsf = t.psf
  custom[col] = false
  menuFor.value = -1
}
function pickOther(col) {
  custom[col] = true
  menuFor.value = -1
  nextTick(() => {
    const el = grid[2][col]
    el?.focus()
    el?.select?.()
  })
}
// A click anywhere else closes the menu. Capture phase so it still fires when
// the click lands on something that stops propagation.
function onDocClick(e) {
  if (menuFor.value < 0) return
  if (!e.target?.closest?.('.rep')) menuFor.value = -1
}
onMounted(() => document.addEventListener('click', onDocClick, true))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick, true))

function multOf(col) {
  return Number(s[col]?.mult) === 2 ? 2 : 1
}
function setFormula(col, f) {
  s[col].mult = f.mult
  // The percentage is part of the formula's identity, so picking one sets it.
  // It stays editable afterwards; the rep just starts from the canonical number.
  s[col].pct = f.pct
}

/** A second column starts as a copy of the one the rep is looking at — same
 *  formula, same percentage, same repair level — so the only thing different
 *  about it is what they deliberately change. An untouched column only; a
 *  dropped-then-restored one keeps whatever was in it. */
function addCompare() {
  if (!s[1].arv) {
    Object.assign(s[1], {
      pct: s[0].pct,
      mult: multOf(0),
      rehabPsf: s[0].rehabPsf,
      fee: s[0].fee,
    })
  }
  cols.value = 2
}

function run(col) {
  const x = s[col]
  const after = Math.round(x.arv * x.pct)
  const repairs = Math.round((Number(x.rehabPsf) || 0) * sqft.value)
  const rehab = repairs * multOf(col)
  const wholesale = after - rehab
  return { after, repairs, rehab, wholesale, offer: wholesale - x.fee }
}

// Only ever a comparison between two PRICED columns: an empty scenario reads
// as an offer of minus the fee, and crowning the other one for beating it
// would be noise dressed up as a finding.
const winner = computed(() => {
  if (cols.value !== 2 || !s[0].arv || !s[1].arv) return -1
  const a = run(0).offer
  const b = run(1).offer
  if (a === b) return -1
  return a > b ? 0 : 1
})
const offerGap = computed(() =>
  winner.value < 0 ? 0 : Math.abs(run(0).offer - run(1).offer),
)

// What the other formula would pay for the same house, at ITS percentage.
const altFormula = computed(
  () => FORMULAS.find((f) => f.mult !== multOf(0)) || FORMULAS[0],
)
const altOffer = computed(() => {
  if (cols.value !== 1 || !s[0].arv) return null
  const f = altFormula.value
  const after = Math.round(s[0].arv * f.pct)
  const rehab = Math.round((Number(s[0].rehabPsf) || 0) * sqft.value) * f.mult
  return after - rehab - s[0].fee
})

const usable = computed(() =>
  (props.comps || []).filter((c) => Number(c.price) > 0 && Number(c.square_footage) > 0),
)
const avgPsf = computed(() => {
  if (!usable.value.length) return 0
  const sum = usable.value.reduce((a, c) => a + Number(c.price) / Number(c.square_footage), 0)
  return Math.round(sum / usable.value.length)
})
const suggestedArv = computed(() =>
  avgPsf.value && sqft.value ? Math.round((avgPsf.value * sqft.value) / 1000) * 1000 : 0,
)
const arvHint = computed(() => (suggestedArv.value ? money(suggestedArv.value) : ''))

const subjectRow = computed(() => {
  const s = props.subject
  if (!s && !props.address) return null
  const sf = Number(s?.sqft) || 0
  const sale = s?.last_sale || {}
  const price = Number(sale.price) || 0
  const psf = price && sf ? Math.round(price / sf) : 0
  return {
    address: props.address || '',
    street: streetAddress(props.address) || props.address || __('This property'),
    date: sale.date ? fmtDate(sale.date) : '—',
    sqft: sf ? sf.toLocaleString() : '—',
    price: price ? money(price) : '—',
    psf: psf ? money(psf) : '—',
  }
})

const rows = computed(() =>
  (props.comps || []).map((c) => {
    const price = Number(c.price) || 0
    const sf = Number(c.square_footage) || 0
    const psf = price && sf ? Math.round(price / sf) : 0
    const active = String(c.status || '').toLowerCase().startsWith('activ')
    return {
      name: c.name,
      address: c.address || '',
      street: streetAddress(c.address) || c.address || '—',
      date: fmtDate(c.removed_date || c.listed_date),
      mi: c.distance_mi != null ? Number(c.distance_mi).toFixed(2) : '—',
      sqft: sf ? sf.toLocaleString() : '—',
      price: price ? money(price) : '—',
      psf: psf ? money(psf) : '—',
      onThis: psf && sqft.value ? money(Math.round(psf * sqft.value)) : '—',
      status: active ? __('Listed') : __('Sold'),
    }
  }),
)

function parseMoney(v) {
  const n = Number(String(v).replace(/[^0-9.]/g, ''))
  return Number.isFinite(n) ? n : 0
}
function money(n) {
  return '$' + Math.round(Number(n) || 0).toLocaleString()
}
/** Rounded to whole thousands: this is a feel for the size, not a quote. */
function k(n) {
  return '$' + Math.round((Number(n) || 0) / 1000).toLocaleString() + 'k'
}
function fmt(n) {
  return (Number(n) || 0).toLocaleString()
}
function fmtDate(v) {
  if (!v) return '—'
  const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})/)
  const d = m ? new Date(+m[1], +m[2] - 1, +m[3]) : new Date(v)
  if (isNaN(d)) return '—'
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
function setPct(col, e) {
  const n = parseMoney(e.target.value)
  s[col].pct = (n > 1 ? n / 100 : n) || (col ? 0.65 : 0.7)
}

/** After Vue writes `$1,250`, put the caret after the same digit it was on. */
function putCaret(el, digitsBefore, formatted) {
  let seen = 0
  let pos = formatted.length
  for (let i = 0; i < formatted.length; i++) {
    if (/\d/.test(formatted[i])) {
      seen++
      if (seen >= digitsBefore) {
        pos = i + 1
        break
      }
    }
  }
  el.setSelectionRange(pos, pos)
}

function typeMoney(col, key, e) {
  const el = e.target
  const digitsBefore = (el.value.slice(0, el.selectionStart).match(/\d/g) || []).length
  const n = parseMoney(el.value)
  s[col][key] = n
  const formatted = n ? money(n) : ''
  nextTick(() => putCaret(el, digitsBefore, formatted))
}

/** This field is the DEDUCTION, so back-solving $/sf divides the multiplier
 *  back out — typing $75,600 at 2× is $30/sf, not $60. */
function typeRehab(col, e) {
  const el = e.target
  const digitsBefore = (el.value.slice(0, el.selectionStart).match(/\d/g) || []).length
  const n = parseMoney(el.value)
  const div = sqft.value * multOf(col)
  if (div) s[col].rehabPsf = n ? Math.round((n / div) * 100) / 100 : 0
  nextTick(() => putCaret(el, digitsBefore, n ? money(n) : ''))
}

async function save() {
  if (!canSave.value) return
  saving.value = true
  try {
    await call('crm.api.cash_offer.save_cash_offer', {
      lead: props.lead,
      scenarios: JSON.stringify(
        visible.value.map((i) => {
          const x = s[i]
          return {
            arv: x.arv,
            pct: x.pct,
            mult: multOf(i),
            rehabPsf: x.rehabPsf,
            fee: x.fee,
            ...run(i),
          }
        }),
      ),
      comps: JSON.stringify(
        (props.comps || []).map((c) => ({
          name: c.name,
          address: c.address,
          price: c.price,
          square_footage: c.square_footage,
          distance_mi: c.distance_mi,
          status: c.status,
        })),
      ),
      subject_sqft: sqft.value,
      notes: notes.value,
    })
    toast.success(__('Saved to the activity timeline'))
    emit('saved')
  } catch (e) {
    toast.error(e.messages?.[0] || __('Could not save the calc.'))
  } finally {
    saving.value = false
  }
}

function onKeys(e) {
  if (e.key === 'Escape' && menuFor.value >= 0) {
    menuFor.value = -1
    return
  }
  let r = -1
  let c = -1
  for (let i = 0; i < grid.length; i++) {
    const j = grid[i].indexOf(e.target)
    if (j >= 0) {
      r = i
      c = j
      break
    }
  }
  if (r < 0) return
  let nr = r
  let nc = c
  const step = e.key === 'ArrowDown' ? 1 : e.key === 'ArrowUp' ? -1 : 0
  if (step) nr += step
  else if (e.key === 'ArrowRight') {
    if (e.target.selectionStart < String(e.target.value || '').length) return
    nc++
  } else if (e.key === 'ArrowLeft') {
    if (e.target.selectionStart > 0) return
    nc--
  } else return
  // Walk past rows with nothing focusable in this column: the Repairs row is a
  // dropdown rather than an input unless the rep chose "Other…", and a stale
  // ref can outlive the element it pointed at.
  let next = null
  while (nr >= 0 && nr < grid.length) {
    const cand = grid[nr] && grid[nr][nc]
    if (cand && cand.isConnected) {
      next = cand
      break
    }
    if (!step) break
    nr += step
  }
  if (!next) return
  e.preventDefault()
  next.focus()
  next.select?.()
}
</script>

<style scoped>
.wrap {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 12px 20px;
  font: 13px/1.35 InterVar, Inter, -apple-system, 'Segoe UI', system-ui, sans-serif;
  color: var(--ink-gray-7);
}
.calc {
  max-width: 100%;
  border: 1px solid var(--outline-gray-2);
  border-radius: 8px;
  background: var(--surface-white);
  padding: 8px 10px 10px;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: var(--ink-gray-5);
  margin-bottom: 6px;
}
.head-r {
  display: flex;
  align-items: center;
  gap: 8px;
}
.link {
  border: 0;
  background: none;
  padding: 0;
  font: inherit;
  font-size: 12px;
  color: var(--ink-blue-3);
  cursor: pointer;
}
.link:hover {
  text-decoration: underline;
}
.drop {
  border: 0;
  background: none;
  padding: 0 0 0 3px;
  font: inherit;
  font-weight: 400;
  color: var(--ink-gray-4);
  cursor: pointer;
  line-height: 1;
}
.drop:hover {
  color: var(--ink-red-3);
}
.save {
  border: 1px solid var(--outline-gray-2);
  border-radius: 5px;
  background: var(--surface-gray-7);
  color: var(--ink-white);
  font: inherit;
  font-weight: 600;
  padding: 3px 8px;
  cursor: pointer;
}
.save:disabled {
  opacity: 0.4;
  cursor: default;
}
.notes {
  display: block;
  box-sizing: border-box;
  width: 100%;
  margin-top: 8px;
  border: 1px solid var(--outline-gray-2);
  border-radius: 5px;
  background: var(--surface-gray-2);
  padding: 6px 7px;
  font: inherit;
  color: var(--ink-gray-9);
  resize: vertical;
  min-height: 3.4em;
}
.notes:focus {
  outline: none;
  border-color: var(--ink-blue-3);
  background: var(--surface-white);
}
.grid {
  display: grid;
  column-gap: 8px;
  row-gap: 4px;
  align-items: center;
}
.colh {
  font-weight: 600;
  color: var(--ink-gray-9);
  text-align: right;
}
.lab {
  color: var(--ink-gray-5);
}
.lab i {
  font-style: normal;
  color: var(--ink-gray-4);
}
.lab.offer,
.out.offer {
  font-weight: 650;
  color: var(--ink-gray-9);
}
input {
  box-sizing: border-box;
  width: 100%;
  height: 26px;
  border: 1px solid var(--outline-gray-2);
  border-radius: 5px;
  background: var(--surface-gray-2);
  padding: 0 7px;
  text-align: right;
  font: inherit;
  font-variant-numeric: tabular-nums;
  color: var(--ink-gray-9);
}
input:focus {
  outline: none;
  border-color: var(--ink-blue-3);
  background: var(--surface-white);
}
input.empty {
  color: var(--ink-gray-5);
}
.pct {
  display: flex;
  align-items: center;
  gap: 3px;
  min-width: 0;
}
.pct i {
  font-style: normal;
  color: var(--ink-gray-5);
  flex: none;
}
.out {
  text-align: right;
  font-variant-numeric: tabular-nums;
  padding-right: 7px;
}
.out.bad {
  color: var(--ink-red-3);
}
/* The winning column keeps its number on the same right edge as the loser's —
   the badge grows leftward — or the two offers stop being comparable at a
   glance, which is the one thing this row exists for. */
.out.offer {
  display: flex;
  align-items: baseline;
  justify-content: flex-end;
  gap: 6px;
}
.gap {
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-green-3);
  background: var(--surface-green-1);
  border-radius: 4px;
  padding: 1px 4px;
  white-space: nowrap;
}
.alt {
  margin-top: 7px;
  color: var(--ink-gray-5);
  font-size: 12px;
}
.alt b {
  font-weight: 600;
}
.alt .up {
  color: var(--ink-green-3);
}
.alt .down {
  color: var(--ink-gray-7);
}

/* Formula toggle. A segmented pair rather than a dropdown: there are exactly
   two, and which one is running has to be readable without opening anything. */
.seg {
  display: flex;
  min-width: 0;
  border: 1px solid var(--outline-gray-2);
  border-radius: 5px;
  background: var(--surface-gray-2);
  padding: 1px;
  gap: 1px;
}
.seg button {
  flex: 1;
  min-width: 0;
  height: 24px;
  border: 0;
  border-radius: 4px;
  background: none;
  padding: 0 4px;
  font: inherit;
  font-size: 11.5px;
  color: var(--ink-gray-6);
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.seg button:hover {
  color: var(--ink-gray-9);
}
.seg button.on {
  background: var(--surface-white);
  color: var(--ink-gray-9);
  font-weight: 600;
  box-shadow: 0 1px 2px rgb(0 0 0 / 8%);
}

/* The deduction row wears its multiplier, so a doubled figure is never just a
   number that looks too big. */
.ded {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}
.x2 {
  flex: none;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--ink-gray-5);
  cursor: help;
}

/* Repairs picker. The trigger's value column and the menu's have to land on
   the SAME x or the selected row reads as misaligned with the list it came
   from: the trigger reserves 6px + a 10px caret inside its 7px padding (23px),
   and the menu rows carry 20px of right padding inside the 3px popover pad to
   match it exactly. */
.rep {
  position: relative;
  display: flex;
  align-items: center;
  min-width: 0;
  container-type: inline-size;
}
/* The NAME is the one thing on the trigger that has to survive a narrow cell
   — it truncated to "Kitc…" in the Today modal on a phone. The rate and the
   total are both a glance away (the open menu, and the Rehab row directly
   below), so they give way first: the total, then the rate. */
@container (max-width: 230px) {
  .rep-btn .vals b {
    display: none;
  }
}
@container (max-width: 185px) {
  .rep-btn .vals {
    display: none;
  }
}
.rep-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  height: 26px;
  border: 1px solid var(--outline-gray-2);
  border-radius: 5px;
  background: var(--surface-gray-2);
  padding: 0 7px;
  font: inherit;
  color: var(--ink-gray-9);
  cursor: pointer;
}
.rep-btn:hover,
.rep-btn.open {
  border-color: var(--ink-blue-3);
  background: var(--surface-white);
}
.rep-name {
  flex: 1;
  min-width: 0;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.caret {
  flex: none;
  width: 10px;
  text-align: right;
  color: var(--ink-gray-5);
}
.vals {
  flex: none;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.vals i {
  font-style: normal;
  color: var(--ink-gray-5);
}
.vals b {
  font-weight: 400;
  color: var(--ink-gray-9);
}
.rep-psf {
  border-top-right-radius: 0;
  border-bottom-right-radius: 0;
  border-right: 0;
}
.rep-caret {
  flex: none;
  height: 26px;
  border: 1px solid var(--outline-gray-2);
  border-top-right-radius: 5px;
  border-bottom-right-radius: 5px;
  background: var(--surface-gray-3);
  color: var(--ink-gray-6);
  padding: 0 6px;
  font: inherit;
  cursor: pointer;
}
.rep-caret:hover {
  color: var(--ink-gray-9);
}
.rep-sf {
  flex: none;
  padding-left: 5px;
  color: var(--ink-gray-5);
}
/* Anchored to the RIGHT edge, never to the cell: the value column's alignment
   is a right-edge relationship, so growing leftward keeps it while letting the
   rows stay on one line. Inside the Today modal at 390px the Repairs cell is
   only 160px, which wrapped every row in half. */
.menu {
  position: absolute;
  z-index: 50;
  top: 29px;
  right: 0;
  min-width: max(260px, 100%);
  max-width: calc(100vw - 24px);
  border: 1px solid var(--outline-gray-2);
  border-radius: 6px;
  background: var(--surface-white);
  box-shadow: 0 6px 18px rgb(0 0 0 / 13%);
  padding: 3px;
  font-size: 12.5px;
}
.mrow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  width: 100%;
  border: 0;
  border-radius: 4px;
  background: none;
  padding: 5px 20px 5px 9px;
  font: inherit;
  text-align: left;
  color: var(--ink-gray-8);
  cursor: pointer;
}
.mrow.on {
  background: var(--surface-gray-2);
}
.mrow:hover {
  background: var(--surface-gray-3);
}
.mrow .vals b {
  color: var(--ink-gray-7);
}
.mrow.other {
  color: var(--ink-gray-6);
}
.msep {
  border-top: 1px solid var(--outline-gray-1);
  margin: 3px 0;
}

.tbl {
  flex: 1;
  min-width: 22rem;
  width: auto;
  border-collapse: collapse;
  margin-top: 0;
}
.tbl th,
.tbl td {
  padding: 3px 6px 3px 0;
  text-align: left;
  font-weight: 400;
}
.tbl th {
  color: var(--ink-gray-5);
}
.tbl td {
  border-top: 1px solid var(--outline-gray-1);
}
.tbl .n {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.tbl .street {
  max-width: 7.5rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ink-gray-9);
}
.tbl .street button {
  border: 0;
  background: none;
  padding: 0;
  font: inherit;
  font-weight: inherit;
  color: var(--ink-blue-3);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.tbl .subj td {
  background: var(--surface-blue-1);
  font-weight: 600;
  color: var(--ink-gray-9);
  border-bottom: 1px solid var(--outline-blue-1);
}
.tbl .avg td {
  color: var(--ink-gray-5);
  border-top: 1px solid var(--outline-gray-2);
}
.tbl .rm {
  width: 1.4rem;
  padding-right: 0;
  text-align: right;
}
.tbl .rm button {
  border: 0;
  background: none;
  padding: 0 2px;
  font: inherit;
  color: var(--ink-gray-4);
  cursor: pointer;
  line-height: 1;
}
.tbl .rm button:hover {
  color: var(--ink-red-3);
}
</style>
