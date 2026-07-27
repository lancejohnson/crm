<template>
  <Dialog v-model="show" :options="{ title: dialogTitle, size: '4xl' }">
    <template #body-content>
      <!-- ── SOURCE: property + stage + reps + the rows ───────────────────── -->
      <div v-if="phase === 'source'" class="flex flex-col gap-4">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <div class="mb-1.5 text-xs text-ink-gray-5">
              {{ __('Add to property (optional)') }}
            </div>
            <Autocomplete
              :options="propertyOptions"
              :modelValue="property"
              :placeholder="__('No property')"
              @update:modelValue="(v) => (property = v?.value || '')"
            >
              <template #target="{ togglePopover }">
                <Button
                  variant="outline"
                  class="w-full !justify-between"
                  iconRight="chevron-down"
                  @click="togglePopover()"
                >
                  <span class="truncate">
                    {{ propertyLabel || __('No property') }}
                  </span>
                </Button>
              </template>
              <template #footer="{ close }">
                <Button
                  v-if="property"
                  variant="ghost"
                  class="w-full !justify-start"
                  :label="__('Clear')"
                  iconLeft="x"
                  @click="property = ''; close()"
                />
              </template>
            </Autocomplete>
            <div class="mt-1 text-xs text-ink-gray-5">
              {{ __('Under contract & dispo properties.') }}
            </div>
          </div>
          <div>
            <div class="mb-1.5 text-xs text-ink-gray-5">
              {{ __('Board stage') }}
            </div>
            <FormControl
              v-model="stage"
              type="select"
              :options="STAGES"
              :disabled="!property"
            />
          </div>
        </div>

        <div>
          <div class="mb-1.5 text-xs text-ink-gray-5">
            {{ __('Split between (optional)') }}
          </div>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="u in callableUsers"
              :key="u.name"
              type="button"
              class="rounded-full border px-2.5 py-1 text-xs transition"
              :class="
                assignees.includes(u.name)
                  ? 'border-outline-gray-4 bg-surface-gray-3 text-ink-gray-8'
                  : 'border-outline-gray-2 text-ink-gray-6 hover:bg-surface-gray-2'
              "
              @click="toggleAssignee(u.name)"
            >
              {{ u.full_name || u.name }}
            </button>
          </div>
          <div v-if="assignees.length" class="mt-1 text-xs text-ink-gray-5">
            {{
              __(
                'Buyers are dealt out evenly, round-robin. A buyer someone already owns is left alone.',
              )
            }}
          </div>
        </div>

        <div>
          <div class="mb-1.5 flex items-center justify-between">
            <span class="text-xs text-ink-gray-5">
              {{ __('Paste rows (incl. header) or upload a CSV') }}
            </span>
            <label
              class="cursor-pointer text-xs font-medium text-ink-gray-7 hover:text-ink-gray-9"
            >
              {{ __('Upload CSV') }}
              <input
                type="file"
                accept=".csv,text/csv,text/plain"
                class="hidden"
                @change="onFile"
              />
            </label>
          </div>
          <Textarea
            v-model="raw"
            :rows="8"
            :placeholder="
              __(
                'Name\tPhone\tEmail\tBuyer type\nManny Rivera\t+13125551234\tmanny@x.com\tCash Buyer',
              )
            "
          />
          <div class="mt-1 text-xs text-ink-gray-5">
            {{
              __(
                'Tip: in Excel/Google Sheets select the cells including the header row, copy, and paste here.',
              )
            }}
          </div>
        </div>

        <ErrorMessage v-if="error" :message="error" />
      </div>

      <!-- ── MAP: confirm each column -> field ────────────────────────────── -->
      <div v-else-if="phase === 'map'" class="flex flex-col gap-3">
        <div class="flex items-center justify-between">
          <div class="text-sm text-ink-gray-7">
            <span class="font-medium text-ink-gray-9">{{ parsed.rows.length }}</span>
            {{ __('rows detected') }}
            <span class="text-ink-gray-5">
              · {{ mappedCount }} {{ __('of') }} {{ parsed.headers.length }}
              {{ __('columns mapped') }}
            </span>
          </div>
          <Button variant="ghost" :label="__('Back')" @click="phase = 'source'" />
        </div>

        <div class="max-h-[22rem] overflow-auto rounded border border-outline-gray-2">
          <table class="w-full text-sm">
            <thead class="sticky top-0 bg-surface-gray-2">
              <tr>
                <th class="px-3 py-2 text-left font-medium text-ink-gray-7">
                  {{ __('Column in your file') }}
                </th>
                <th class="px-3 py-2 text-left font-medium text-ink-gray-7">
                  {{ __('Sample') }}
                </th>
                <th class="px-3 py-2 text-left font-medium text-ink-gray-7">
                  {{ __('Import as') }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(h, i) in parsed.headers"
                :key="i"
                class="border-t border-outline-gray-1"
              >
                <td class="px-3 py-1.5 text-ink-gray-8">
                  {{ h || __('(blank)') }}
                </td>
                <td class="max-w-[12rem] truncate px-3 py-1.5 text-ink-gray-5">
                  {{ sampleFor(i) }}
                </td>
                <td class="px-3 py-1.5">
                  <select
                    v-model="mapping[i]"
                    class="w-full rounded border-none bg-surface-gray-2 py-1 pl-2 pr-7 text-sm text-ink-gray-8 focus:ring-1 focus:ring-outline-gray-3"
                  >
                    <option value="">{{ __('— Ignore —') }}</option>
                    <option v-for="f in FIELDS" :key="f.value" :value="f.value">
                      {{ f.label }}
                    </option>
                  </select>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="text-xs text-ink-gray-5">
          {{
            __(
              'Existing buyers are matched by email, then phone — they are attached and assigned, never duplicated, and their details are left as they are.',
            )
          }}
        </div>

        <ErrorMessage v-if="error" :message="error" />
      </div>

      <!-- ── IMPORTING ────────────────────────────────────────────────────── -->
      <div v-else-if="phase === 'importing'" class="flex flex-col gap-3 py-4">
        <div class="text-sm text-ink-gray-7">
          {{ __('Importing') }} {{ done }} / {{ parsed.rows.length }}…
        </div>
        <div class="h-2 w-full overflow-hidden rounded-full bg-surface-gray-3">
          <div
            class="h-full rounded-full bg-surface-gray-7 transition-all"
            :style="{ width: pct + '%' }"
          />
        </div>
      </div>

      <!-- ── DONE ─────────────────────────────────────────────────────────── -->
      <div v-else-if="phase === 'done'" class="flex flex-col gap-4">
        <div class="flex items-start gap-2.5 rounded-md bg-surface-green-1 px-3 py-2.5">
          <CircleCheckIcon class="mt-0.5 size-4 shrink-0 text-ink-green-3" />
          <div class="text-sm">
            <div class="font-medium text-ink-gray-8">
              {{ __('Import complete') }}
            </div>
            <div class="mt-0.5 text-ink-gray-6">
              <span class="font-medium text-ink-gray-8">{{ result.created }}</span>
              {{ __('new buyers') }} ·
              <span class="font-medium text-ink-gray-8">{{ result.matched }}</span>
              {{ __('already existed') }}
              <template v-if="result.skipped">
                · {{ result.skipped }} {{ __('skipped') }}
              </template>
            </div>
            <div v-if="propertyLabel" class="mt-0.5 text-ink-gray-6">
              <span class="font-medium text-ink-gray-8">{{ result.attached }}</span>
              {{ __('added to') }} {{ propertyLabel }}
              <span class="text-ink-gray-5">({{ stage }})</span>
            </div>
          </div>
        </div>

        <div v-if="assignedTotal" class="flex flex-col gap-1">
          <div class="text-xs text-ink-gray-5">{{ __('Assigned to') }}</div>
          <div class="flex flex-wrap gap-2 text-sm">
            <span
              v-for="(n, u) in result.assigned"
              :key="u"
              class="rounded bg-surface-gray-2 px-2 py-0.5 text-ink-gray-7"
            >
              {{ userLabel(u) }}: <span class="font-medium">{{ n }}</span>
            </span>
          </div>
        </div>

        <div
          v-if="result.unmatched_metros?.length"
          class="rounded bg-surface-amber-1 px-2.5 py-1.5 text-xs text-ink-amber-3"
        >
          {{ __('Metro not recognised (left blank):') }}
          {{ result.unmatched_metros.join(', ') }}
        </div>

        <div v-if="result.error_count" class="flex flex-col gap-1">
          <div class="text-xs font-medium text-ink-red-3">
            {{ result.error_count }} {{ __('rows failed') }}
          </div>
          <div
            class="max-h-24 overflow-auto rounded bg-surface-gray-2 px-2.5 py-1.5 text-xs text-ink-gray-6"
          >
            <div v-for="(e, i) in result.errors" :key="i">
              {{ __('Row') }} {{ e.row }}: {{ e.error }}
            </div>
          </div>
        </div>
      </div>
    </template>

    <template #actions>
      <div class="flex flex-row-reverse gap-2">
        <Button
          v-if="phase === 'source'"
          variant="solid"
          :label="__('Next')"
          @click="parseAndMap"
        />
        <Button
          v-else-if="phase === 'map'"
          variant="solid"
          :label="__('Import') + ' ' + parsed.rows.length + ' ' + __('buyers')"
          :loading="importing"
          @click="runImport"
        />
        <template v-else-if="phase === 'done'">
          <Button
            v-if="property"
            variant="solid"
            :label="__('Open dispo board')"
            @click="openBoard"
          />
          <Button
            v-else
            variant="solid"
            :label="__('Open buyers')"
            @click="openBuyers"
          />
          <Button :label="__('Close')" @click="show = false" />
        </template>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import Autocomplete from '@/components/frappe-ui/Autocomplete.vue'
import CircleCheckIcon from '~icons/lucide/circle-check'
import {
  call,
  createResource,
  Dialog,
  FormControl,
  Textarea,
  Button,
  ErrorMessage,
  toast,
} from 'frappe-ui'
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usersStore } from '@/stores/users'

const props = defineProps({
  // pre-select a property (the Dispo page passes the board it's showing)
  lead: { type: String, default: '' },
})
const show = defineModel({ type: Boolean })
const emit = defineEmits(['imported'])
const router = useRouter()

const phase = ref('source')
const property = ref('')
const stage = ref('New')
const raw = ref('')
const error = ref('')
const importing = ref(false)
const done = ref(0)
const result = ref({})
const parsed = ref({ headers: [], rows: [] })
const mapping = ref([])
const assignees = ref([])

const CHUNK = 200

// mirrors IMPORT_FIELDS in crm/api/buyer_import.py — the only columns an
// import may write (the IL/Quo-owned fields are deliberately absent)
const FIELDS = [
  { label: __('First name'), value: 'first_name' },
  { label: __('Last name'), value: 'last_name' },
  { label: __('Full name'), value: 'buyer_name' },
  { label: __('Phone'), value: 'phone' },
  { label: __('Email'), value: 'email' },
  { label: __('Buyer type'), value: 'buyer_type' },
  { label: __('Buybox'), value: 'buybox' },
  { label: __('Quo tags'), value: 'quo_tags' },
  { label: __('Metro area'), value: 'metro' },
]

const STAGES = [
  'New',
  'Attempted to Contact',
  'Interested',
  'Offer Made',
  'Not Interested',
]

const { users: allUsers } = usersStore()

const callableUsers = computed(() =>
  (allUsers.data || []).filter(
    (u) => u.name && !['Administrator', 'Guest'].includes(u.name) && u.enabled !== 0,
  ),
)

function userLabel(name) {
  const u = (allUsers.data || []).find((x) => x.name === name)
  return u?.full_name || name
}

function toggleAssignee(name) {
  const i = assignees.value.indexOf(name)
  if (i === -1) assignees.value.push(name)
  else assignees.value.splice(i, 1)
}

const assignedTotal = computed(() =>
  Object.values(result.value.assigned || {}).reduce((a, b) => a + b, 0),
)

/* ── properties: leads under contract / in dispo ── */
const properties = createResource({
  url: 'crm.api.buyer_import.get_import_properties',
  auto: true,
  transform: (d) => d || [],
})

const propertyOptions = computed(() =>
  (properties.data || []).map((p) => ({
    label: p.buyer_count ? `${p.label} (${p.buyer_count})` : p.label,
    value: p.lead,
    description: p.status,
  })),
)

const propertyLabel = computed(
  () => (properties.data || []).find((p) => p.lead === property.value)?.label || '',
)

const dialogTitle = computed(
  () =>
    ({
      source: __('Import buyers'),
      map: __('Map columns'),
      importing: __('Importing…'),
      done: __('Import complete'),
    })[phase.value],
)

const pct = computed(() =>
  parsed.value.rows.length
    ? Math.round((done.value / parsed.value.rows.length) * 100)
    : 0,
)

const mappedCount = computed(() => mapping.value.filter(Boolean).length)

/* ── header -> field aliases (normalised: lowercase, alphanumeric only) ── */
const ALIASES = {
  name: 'buyer_name',
  fullname: 'buyer_name',
  buyername: 'buyer_name',
  contact: 'buyer_name',
  contactname: 'buyer_name',
  company: 'buyer_name',
  companyname: 'buyer_name',
  firstname: 'first_name',
  fname: 'first_name',
  lastname: 'last_name',
  lname: 'last_name',
  phone: 'phone',
  phonenumber: 'phone',
  mobile: 'phone',
  mobileno: 'phone',
  cell: 'phone',
  cellphone: 'phone',
  primaryphone: 'phone',
  email: 'email',
  emailaddress: 'email',
  type: 'buyer_type',
  buyertype: 'buyer_type',
  tags: 'quo_tags',
  quotags: 'quo_tags',
  buybox: 'buybox',
  criteria: 'buybox',
  notes: 'buybox',
  metro: 'metro',
  metroarea: 'metro',
  market: 'metro',
  msa: 'metro',
}

function norm(s) {
  return String(s || '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '')
}

function guessField(header) {
  const n = norm(header)
  if (!n) return ''
  if (ALIASES[n]) return ALIASES[n]
  const exact = FIELDS.find((f) => norm(f.value) === n || norm(f.label) === n)
  return exact ? exact.value : ''
}

/* ── CSV / TSV parsing (quote-aware, no dependency) ── */
function detectDelim(text) {
  const line = text.split(/\r?\n/)[0] || ''
  const tabs = (line.match(/\t/g) || []).length
  const commas = (line.match(/,/g) || []).length
  return tabs > commas ? '\t' : ','
}

function parseDelimited(text, delim) {
  const rows = []
  let row = []
  let field = ''
  let inQuotes = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"'
          i++
        } else inQuotes = false
      } else field += c
    } else if (c === '"') {
      inQuotes = true
    } else if (c === delim) {
      row.push(field)
      field = ''
    } else if (c === '\n') {
      row.push(field)
      rows.push(row)
      row = []
      field = ''
    } else if (c !== '\r') {
      field += c
    }
  }
  if (field.length || row.length) {
    row.push(field)
    rows.push(row)
  }
  return rows.filter((r) => r.some((c) => String(c).trim() !== ''))
}

function parseAndMap() {
  error.value = ''
  if (!raw.value.trim()) {
    error.value = __('Paste some rows or upload a CSV first.')
    return
  }
  const all = parseDelimited(raw.value.trim(), detectDelim(raw.value))
  if (all.length < 2) {
    error.value = __('Need a header row and at least one data row.')
    return
  }
  parsed.value = { headers: all[0].map((h) => h.trim()), rows: all.slice(1) }
  mapping.value = parsed.value.headers.map((h) => guessField(h))
  phase.value = 'map'
}

function sampleFor(i) {
  const r = parsed.value.rows.find((r) => String(r[i] || '').trim())
  return r ? String(r[i]).slice(0, 40) : '—'
}

function onFile(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    raw.value = String(reader.result || '')
  }
  reader.readAsText(file)
  e.target.value = ''
}

function buildRows() {
  const map = mapping.value
  return parsed.value.rows.map((r) => {
    const obj = {}
    map.forEach((field, i) => {
      if (!field) return
      const v = String(r[i] ?? '').trim()
      if (v) obj[field] = v
    })
    return obj
  })
}

async function runImport() {
  error.value = ''
  if (!mapping.value.some(Boolean)) {
    error.value = __('Map at least one column.')
    return
  }
  const rows = buildRows()
  if (!rows.length) {
    error.value = __('Nothing to import.')
    return
  }

  importing.value = true
  phase.value = 'importing'
  done.value = 0

  const totals = {
    created: 0,
    matched: 0,
    attached: 0,
    skipped: 0,
    assigned: {},
    unmatched_metros: [],
    errors: [],
    error_count: 0,
  }

  try {
    // carries the round-robin rotation across chunks so a split doesn't
    // restart at the first person every 200 rows
    let offset = 0
    for (let i = 0; i < rows.length; i += CHUNK) {
      const res = await call('crm.api.buyer_import.import_buyers', {
        rows: JSON.stringify(rows.slice(i, i + CHUNK)),
        lead: property.value || null,
        stage: stage.value,
        assign_to: assignees.value.length ? JSON.stringify(assignees.value) : null,
        assign_offset: offset,
      })
      totals.created += res.created || 0
      totals.matched += res.matched || 0
      totals.attached += res.attached || 0
      totals.skipped += res.skipped || 0
      totals.error_count += res.error_count || 0
      if (res.errors?.length) totals.errors.push(...res.errors)
      for (const m of res.unmatched_metros || []) {
        if (!totals.unmatched_metros.includes(m)) totals.unmatched_metros.push(m)
      }
      for (const [u, n] of Object.entries(res.assigned || {})) {
        totals.assigned[u] = (totals.assigned[u] || 0) + n
      }
      offset = res.assign_offset ?? offset
      done.value = Math.min(i + CHUNK, rows.length)
    }
    totals.errors = totals.errors.slice(0, 20)
    result.value = totals
    phase.value = 'done'
    emit('imported', totals)
  } catch (e) {
    error.value = e.messages?.[0] || e.message || __('Import failed.')
    phase.value = 'map'
    toast.error(error.value)
  } finally {
    importing.value = false
  }
}

function openBoard() {
  show.value = false
  // Dispo takes the property as a route param (leadId), not a query arg
  router.push({ name: 'Dispo', params: { leadId: property.value } })
}

function openBuyers() {
  show.value = false
  router.push({ name: 'Buyers' })
}

watch(show, (v) => {
  if (!v) return
  phase.value = 'source'
  property.value = props.lead || ''
  stage.value = 'New'
  raw.value = ''
  error.value = ''
  done.value = 0
  result.value = {}
  parsed.value = { headers: [], rows: [] }
  mapping.value = []
  assignees.value = []
  properties.reload()
})
</script>
