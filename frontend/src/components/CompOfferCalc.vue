<template>
  <!-- Two independent columns, like the sheet. Shared-looking defaults (both
       ARVs empty, both $35/sf, both $25k fee) but typing in one never writes
       the other — no merged cells. -->
  <div class="wrap">
  <div class="calc" @keydown="onKeys">
    <div class="head">
      <span>{{ __('Cash offer') }}</span>
      <button
        type="button"
        class="save"
        :disabled="!canSave || saving"
        @click="save"
      >
        {{ saving ? __('Saving…') : __('Save calcs') }}
      </button>
    </div>

    <div class="grid">
      <span />
      <span class="colh">{{ __('Scenario 1') }}</span>
      <span class="colh">{{ __('Scenario 2') }}</span>

      <span class="lab">{{ __('ARV') }}</span>
      <input
        v-for="col in [0, 1]"
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
      <label v-for="col in [0, 1]" :key="'pct' + col" class="pct">
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
      <span class="out">{{ s[0].arv ? money(run(0).after) : '—' }}</span>
      <span class="out">{{ s[1].arv ? money(run(1).after) : '—' }}</span>

      <span class="lab">{{ __('Rehab $/sf') }}</span>
      <input
        v-for="col in [0, 1]"
        :key="'psf' + col"
        :ref="(el) => setField(2, col, el)"
        inputmode="numeric"
        :value="money(s[col].rehabPsf)"
        @focus="$event.target.select()"
        @input="typeMoney(col, 'rehabPsf', $event)"
      />

      <span class="lab">{{ __('Rehab') }} <i>{{ fmt(sqft) }} sf</i></span>
      <input
        v-for="col in [0, 1]"
        :key="'rehab' + col"
        :ref="(el) => setField(3, col, el)"
        inputmode="numeric"
        :value="money(run(col).rehab)"
        @focus="$event.target.select()"
        @input="typeRehab(col, $event)"
      />

      <span class="lab">{{ __('Wholesale') }}</span>
      <span class="out">{{ s[0].arv ? money(run(0).wholesale) : '—' }}</span>
      <span class="out">{{ s[1].arv ? money(run(1).wholesale) : '—' }}</span>

      <span class="lab">{{ __('Fee') }}</span>
      <input
        v-for="col in [0, 1]"
        :key="'fee' + col"
        :ref="(el) => setField(4, col, el)"
        inputmode="numeric"
        :value="money(s[col].fee)"
        @focus="$event.target.select()"
        @input="typeMoney(col, 'fee', $event)"
      />

      <span class="lab offer">{{ __('Offer') }}</span>
      <span class="out offer" :class="{ bad: s[0].arv && run(0).offer <= 0 }">
        {{ s[0].arv ? money(run(0).offer) : '—' }}
      </span>
      <span class="out offer" :class="{ bad: s[1].arv && run(1).offer <= 0 }">
        {{ s[1].arv ? money(run(1).offer) : '—' }}
      </span>
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
 * Cash Offer — same arithmetic as the underwriting template, twice:
 *   after      = ARV × %
 *   rehab      = $/sf × subject sqft
 *   wholesale  = after − rehab
 *   offer      = wholesale − fee
 *
 * Scenario 1 starts at 70%, Scenario 2 at 65%. Everything else starts the same
 * ($35/sf, $25k fee, empty ARV) and then each column is its own notebook.
 */
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { call, toast } from 'frappe-ui'
import { streetAddress } from '@/utils/comps'

const emit = defineEmits(['remove', 'open', 'saved'])

const props = defineProps({
  lead: { type: String, required: true },
  subject: { type: Object, default: null },
  comps: { type: Array, default: () => [] },
  address: { type: String, default: '' },
  // Snapshot from a timeline comment. When present, this is the source of
  // truth for the two columns (not localStorage) so "Tweak calcs" opens on
  // the numbers that were actually saved, not a later draft.
  seed: { type: Object, default: null },
})

const DEFAULT_PSF = 35
const DEFAULT_FEE = 25000

function fresh(pct) {
  return { arv: 0, pct, rehabPsf: DEFAULT_PSF, fee: DEFAULT_FEE }
}

const s = reactive([fresh(0.7), fresh(0.65)])
const notes = ref('')
const saving = ref(false)
const canSave = computed(() => s.some((x) => x.arv > 0) && !saving.value)
const grid = [[null, null], [null, null], [null, null], [null, null], [null, null]]

function setField(row, col, el) {
  grid[row][col] = el || grid[row][col]
}

const storageKey = computed(() => `compsCalc:${props.lead}`)

function applyScene(i, row) {
  Object.assign(s[i], fresh(i ? 0.65 : 0.7), {
    arv: Number(row.arv) || 0,
    pct: Number(row.pct) || (i ? 0.65 : 0.7),
    rehabPsf: Number(row.rehabPsf ?? row.rehab_psf) || DEFAULT_PSF,
    fee: Number(row.fee) || DEFAULT_FEE,
  })
}

function loadSaved() {
  notes.value = ''
  const seed = props.seed
  if (seed && Array.isArray(seed.scenarios) && seed.scenarios.length) {
    applyScene(0, {})
    applyScene(1, {})
    seed.scenarios.forEach((row, i) => {
      if (i < 2) applyScene(i, row)
    })
    if (typeof seed.notes === 'string') notes.value = seed.notes
    return
  }
  try {
    const raw = JSON.parse(localStorage.getItem(storageKey.value) || 'null')
    if (!raw) return
    // New shape is [{…},{…}]. The previous single-ARV blob is ignored — better
    // to start clean than to write one number into both columns.
    if (Array.isArray(raw.s) && raw.s.length === 2) {
      raw.s.forEach((row, i) => Object.assign(s[i], fresh(i ? 0.65 : 0.7), row))
    }
    if (typeof raw.notes === 'string') notes.value = raw.notes
  } catch {
    /* ignore */
  }
}

function persist() {
  try {
    localStorage.setItem(storageKey.value, JSON.stringify({ s, notes: notes.value }))
  } catch {
    /* quota */
  }
}

watch(storageKey, loadSaved, { immediate: true })
watch(s, persist, { deep: true })
watch(notes, persist)

const sqft = computed(() => Number(props.subject?.sqft) || 0)

function run(col) {
  const x = s[col]
  const after = Math.round(x.arv * x.pct)
  const rehab = Math.round((Number(x.rehabPsf) || 0) * sqft.value)
  const wholesale = after - rehab
  return { after, rehab, wholesale, offer: wholesale - x.fee }
}

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

function typeRehab(col, e) {
  const el = e.target
  const digitsBefore = (el.value.slice(0, el.selectionStart).match(/\d/g) || []).length
  const n = parseMoney(el.value)
  if (sqft.value) s[col].rehabPsf = n ? Math.round((n / sqft.value) * 100) / 100 : 0
  nextTick(() => putCaret(el, digitsBefore, n ? money(n) : ''))
}

async function save() {
  if (!canSave.value) return
  saving.value = true
  try {
    await call('crm.api.cash_offer.save_cash_offer', {
      lead: props.lead,
      scenarios: JSON.stringify(
        [0, 1].map((i) => {
          const x = s[i]
          return { arv: x.arv, pct: x.pct, rehabPsf: x.rehabPsf, fee: x.fee, ...run(i) }
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
  if (e.key === 'ArrowDown') nr++
  else if (e.key === 'ArrowUp') nr--
  else if (e.key === 'ArrowRight') {
    if (e.target.selectionStart < String(e.target.value || '').length) return
    nc++
  } else if (e.key === 'ArrowLeft') {
    if (e.target.selectionStart > 0) return
    nc--
  } else return
  const next = grid[nr] && grid[nr][nc]
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
  width: 26rem;
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
  grid-template-columns: 6.5rem 1fr 1fr;
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
