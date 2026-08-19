<template>
  <!-- Two independent columns, like the sheet. Shared-looking defaults (both
       ARVs empty, both $35/sf, both $25k fee) but typing in one never writes
       the other — no merged cells. -->
  <div class="wrap">
  <div class="calc" @keydown="onKeys">
    <div class="head">{{ __('Cash offer') }}</div>

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
  </div>

    <table v-if="rows.length" class="tbl">
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
import { computed, nextTick, reactive, watch } from 'vue'
import { streetAddress } from '@/utils/comps'

defineEmits(['remove', 'open'])

const props = defineProps({
  lead: { type: String, required: true },
  subject: { type: Object, default: null },
  comps: { type: Array, default: () => [] },
})

const DEFAULT_PSF = 35
const DEFAULT_FEE = 25000

function fresh(pct) {
  return { arv: 0, pct, rehabPsf: DEFAULT_PSF, fee: DEFAULT_FEE }
}

const s = reactive([fresh(0.7), fresh(0.65)])
const grid = [[null, null], [null, null], [null, null], [null, null], [null, null]]

function setField(row, col, el) {
  grid[row][col] = el || grid[row][col]
}

const storageKey = computed(() => `compsCalc:${props.lead}`)

function loadSaved() {
  try {
    const raw = JSON.parse(localStorage.getItem(storageKey.value) || 'null')
    if (!raw) return
    // New shape is [{…},{…}]. The previous single-ARV blob is ignored — better
    // to start clean than to write one number into both columns.
    if (Array.isArray(raw.s) && raw.s.length === 2) {
      raw.s.forEach((row, i) => Object.assign(s[i], fresh(i ? 0.65 : 0.7), row))
    }
  } catch {
    /* ignore */
  }
}

watch(storageKey, loadSaved, { immediate: true })
watch(
  s,
  () => {
    try {
      localStorage.setItem(storageKey.value, JSON.stringify({ s }))
    } catch {
      /* quota */
    }
  },
  { deep: true },
)

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
  color: #44423d;
}
.calc {
  width: 26rem;
  max-width: 100%;
  border: 1px solid #e5e3de;
  border-radius: 8px;
  background: #fff;
  padding: 8px 10px 10px;
}
.head {
  color: #8a877e;
  margin-bottom: 6px;
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
  color: #161614;
  text-align: right;
}
.lab {
  color: #8a877e;
}
.lab i {
  font-style: normal;
  color: #b0aea6;
}
.lab.offer,
.out.offer {
  font-weight: 650;
  color: #161614;
}
input {
  box-sizing: border-box;
  width: 100%;
  height: 26px;
  border: 1px solid #e5e3de;
  border-radius: 5px;
  background: #f8f8f7;
  padding: 0 7px;
  text-align: right;
  font: inherit;
  font-variant-numeric: tabular-nums;
  color: #161614;
}
input:focus {
  outline: none;
  border-color: #2563c9;
  background: #fff;
}
input.empty {
  color: #8a877e;
}
.pct {
  display: flex;
  align-items: center;
  gap: 3px;
  min-width: 0;
}
.pct i {
  font-style: normal;
  color: #8a877e;
  flex: none;
}
.out {
  text-align: right;
  font-variant-numeric: tabular-nums;
  padding-right: 7px;
}
.out.bad {
  color: #b3261e;
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
  color: #8a877e;
}
.tbl td {
  border-top: 1px solid #ecece8;
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
  color: #161614;
}
.tbl .street button {
  border: 0;
  background: none;
  padding: 0;
  font: inherit;
  font-weight: inherit;
  color: #2563c9;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.tbl .avg td {
  color: #8a877e;
  border-top: 1px solid #cfccc5;
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
  color: #b0aea6;
  cursor: pointer;
  line-height: 1;
}
.tbl .rm button:hover {
  color: #b3261e;
}
</style>
