<template>
  <!-- 306px, the mockup's width. The rail is a column of key/value ROWS, not a
       stack of cards: cards put their own padding between every figure and the
       one above it, which is what made this read as a pile of widgets rather
       than one calculation you can follow down the page. -->
  <div class="desk-rail">
    <!-- ARV -->
    <div class="lb">ARV</div>
    <div v-if="!picked.length" class="empty">
      Tick comps on the map to price this.
    </div>
    <template v-else>
      <div class="arvline">
        <span class="av">{{ money(arv) }}</span>
        <span class="ak">{{ money(avgPsf) }}/sf × {{ fmt(subjectSqft) }}sf</span>
      </div>
      <div class="sub">
        {{ usable.length }} of {{ picked.length }} comp{{ picked.length === 1 ? '' : 's' }}
        <span
          v-if="usable.length < picked.length"
          :title="'Comps without both a price and a size cannot produce a $/sf'"
        >· {{ picked.length - usable.length }} unusable</span>
      </div>
    </template>

    <!-- Repairs -->
    <div class="sublb2">
      Repairs<span class="band">{{ bandLabel }}</span>
    </div>
    <div class="seg">
      <button
        v-for="l in LEVELS"
        :key="l.id"
        class="sgb"
        :class="{ on: l.id === level }"
        @click="level = l.id"
      >
        {{ l.short }}<span class="sgv">{{ money(l.cost[band]) }}</span>
      </button>
    </div>

    <div
      v-for="m in MAJORS"
      :key="m"
      class="row pick"
      :class="{ on: majors.includes(m) }"
      @click="toggleMajor(m)"
    >
      <span class="chk">✓</span>
      <span class="k">{{ m }}</span>
      <span class="v mut">+{{ money(MAJOR_COST) }}</span>
    </div>

    <div class="row tot">
      <span class="k">Estimate</span>
      <span class="v">{{ money(repairs) }}</span>
    </div>

    <!-- Offer -->
    <div class="sublb2">Offer</div>
    <div class="row"><span class="k">ARV</span><span class="v mut">{{ money(arv) }}</span></div>
    <div class="row"><span class="k">× Margin</span><span class="v mut">{{ MARGIN }}%</span></div>
    <div class="row"><span class="k">= Gross</span><span class="v mut">{{ money(gross) }}</span></div>
    <div class="row">
      <span class="k" :title="DOUBLE_WHY">− Repairs × 2</span>
      <span class="v mut">{{ money(repairs * 2) }}</span>
    </div>
    <div class="row"><span class="k">− Fee</span><span class="v mut">{{ money(FEE) }}</span></div>

    <div class="row big">
      <span class="k">Max offer</span>
      <span class="v" :class="{ bad: offer <= 0 }">{{ money(offer) }}</span>
    </div>
    <div v-if="arv && offer <= 0" class="warn">
      Repairs and fee exceed {{ MARGIN }}% of ARV — there is no offer here at this repair level.
    </div>

    <!-- The 2x2, unchanged in behaviour: it writes the lead's real First-Call Read. -->
    <div class="readcard">
      <FirstCallReadCard
        v-if="lead"
        :lead="lead"
        :motivated="motivated"
        :on-price="onPrice"
        @saved="$emit('read-saved')"
      />
    </div>

    <!-- Save, in the mockup's foot band: full-bleed, its own surface, pinned. -->
    <div class="rfoot">
      <div class="savedline">
        <template v-if="!saved">Nothing saved for this lead yet.</template>
        <template v-else-if="drifted">
          Saved <b>{{ savedWhen }}</b> at <b>{{ money(saved.offer) }}</b> — changed since.
        </template>
        <template v-else>Saved <b>{{ savedWhen }}</b> · offer <b>{{ money(saved.offer) }}</b></template>
      </div>
      <div v-if="saved && !saved.stored" class="savedline amber">
        Recorded on the timeline only — the lead has nowhere to keep the current number yet.
      </div>
      <button class="go" :disabled="!canSave" @click="save">
        {{ saving ? 'Saving…' : drifted ? 'Re-save (S)' : 'Save (S)' }}
      </button>
      <div v-if="error" class="warn">{{ error }}</div>
    </div>
  </div>
</template>

<script setup>
/**
 * The offer rail, styled to `~/crm-mockups/today-leadzolo/v17.html`.
 *
 * WHY SCOPED CSS RATHER THAN TAILWIND UTILITIES. The mockup is a specification
 * with real numbers in it -- 13px/1.5 base, 10px uppercase labels at #9a9ba3,
 * 17px for the figure that gets said out loud, 6px radii, #e8e8ec hairlines --
 * and Tailwind's scale has no 11.5px, no 9.5px and a different grey ramp. The
 * first cut approximated all of it with the nearest utility class, and
 * "approximately the mockup" in twenty places is what made it look nothing like
 * the mockup.
 *
 * The arithmetic below is unchanged; this is a skin.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { call, toast } from 'frappe-ui'
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

const BANDS = ['<1,500', '1,500–2,000', '2,000–2,500', '2,500+']
const LEVELS = [
  { id: 'smooth', short: 'Smooth', cost: [20000, 30000, 40000, 50000] },
  { id: 'shiver', short: 'Shiver', cost: [35000, 45000, 65000, 85000] },
  { id: 'abandon', short: 'Abandon', cost: [50000, 70000, 85000, 110000] },
]

const level = ref('smooth')
const majors = ref([])
function toggleMajor(m) {
  majors.value = majors.value.includes(m)
    ? majors.value.filter((x) => x !== m)
    : [...majors.value, m]
}

const subjectSqft = computed(() => Number(props.subject?.sqft) || 0)

const band = computed(() => {
  const s = subjectSqft.value
  if (!s || s < 1500) return 0
  if (s < 2000) return 1
  if (s < 2500) return 2
  return 3
})
const bandLabel = computed(() => `${BANDS[band.value]} sqft`)

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

<style scoped>
/* Tokens lifted verbatim from the mockup so there is one source of truth for
   what this screen looks like. */
.desk-rail {
  --t1: #18181a; --t2: #62636a; --t3: #9a9ba3;
  --bg: #fff; --bg1: #fbfbfc; --bg2: #f4f4f6;
  --br: #e8e8ec; --br2: #dcdce2;
  --green: #15683c; --amber: #9a5308; --red: #b3261e;
  --rs: 5px;

  width: 306px;
  flex: none;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 12px 14px 0;
  border-left: 1px solid var(--br2);
  background: var(--bg);
  font: 13px/1.5 Inter, -apple-system, 'Segoe UI', system-ui, sans-serif;
  color: var(--t1);
}

.lb {
  font-size: 10px; font-weight: 500; letter-spacing: 0.04em;
  text-transform: uppercase; color: var(--t3);
}
.empty {
  margin-top: 6px; padding: 9px 10px; font-size: 11.5px; color: var(--t3);
  border: 1px dashed var(--br2); border-radius: var(--rs);
}
.arvline { display: flex; align-items: baseline; gap: 8px; margin-top: 3px; }
.arvline .av { font-size: 18px; font-weight: 600; letter-spacing: -0.015em; }
.arvline .ak { font-size: 11.5px; color: var(--t2); margin-left: auto; }
.sub { font-size: 11px; color: var(--t3); margin-top: 2px; }

.sublb2 {
  font-size: 10px; font-weight: 500; letter-spacing: 0.04em; text-transform: uppercase;
  color: var(--t3); margin: 18px 0 7px; padding-top: 14px; border-top: 1px solid var(--br);
  display: flex; align-items: baseline;
}
.sublb2 .band { margin-left: auto; letter-spacing: 0; text-transform: none; }

.seg { display: flex; gap: 2px; background: var(--bg2); padding: 2px; border-radius: var(--rs); }
.sgb {
  flex: 1; padding: 4px 8px; border: 0; border-radius: 4px; background: none;
  font-size: 11.5px; font-weight: 500; color: var(--t2); text-align: center;
  line-height: 1.25; cursor: pointer;
}
.sgb.on { background: var(--bg); color: var(--t1); box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06); }
.sgv { display: block; font-size: 10px; font-weight: 500; color: var(--t3); margin-top: 1px; }
.sgb.on .sgv { color: var(--t2); }

.row {
  display: flex; align-items: center; gap: 7px; height: 24px; font-size: 12px;
}
.row .k { color: var(--t2); }
.row .v { margin-left: auto; font-weight: 500; text-align: right; }
.row .v.mut { color: var(--t3); font-weight: 400; }
.row.tot { border-top: 1px solid var(--br); margin-top: 9px; padding-top: 11px; height: auto; }
.row.tot .k { color: var(--t1); font-weight: 500; }
.row.big {
  border-top: 1px solid var(--br2); margin-top: 14px; padding-top: 14px;
  height: auto; align-items: baseline;
}
/* Label and figure share a size: a 13px word beside a 24px number reads as two
   unrelated things rather than one row. */
.row.big .k { color: var(--t1); font-weight: 600; font-size: 17px; }
.row.big .v { font-size: 17px; font-weight: 600; letter-spacing: -0.015em; line-height: 1.2; }
.row.big .v.bad { color: var(--red); }

.chk {
  width: 13px; height: 13px; border: 1px solid var(--br2); border-radius: 3px; flex: none;
  display: grid; place-items: center; font-size: 8.5px; color: transparent;
}
.row.pick { cursor: pointer; border-radius: 4px; margin: 0 -5px; padding: 0 5px; }
.row.pick:hover { background: var(--bg2); }
.row.pick.on .chk { background: var(--t1); border-color: var(--t1); color: #fff; }

.warn { font-size: 11px; color: var(--red); margin-top: 6px; line-height: 1.4; }

.readcard { margin: 16px -14px 0; }

.rfoot {
  margin: auto -14px 0; padding: 10px 14px; flex: none;
  border-top: 1px solid var(--br2); background: var(--bg1);
  position: sticky; bottom: 0;
}
.savedline { font-size: 11px; color: var(--t3); margin-bottom: 7px; line-height: 1.4; min-height: 15px; }
.savedline b { color: var(--t2); font-weight: 500; }
.savedline.amber { color: var(--amber); }
.go {
  width: 100%; height: 31px; border-radius: var(--rs); background: var(--t1); color: #fff;
  font-size: 12px; font-weight: 500; border: 0; cursor: pointer;
}
.go:disabled { opacity: 0.45; cursor: default; }
</style>
