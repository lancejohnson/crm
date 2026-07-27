<template>
  <Dialog v-model="show" :options="{ title: dialogTitle, size: '4xl' }">
    <template #body-content>
      <!-- ── SOURCE: name the list + paste or upload ──────────────────────── -->
      <div v-if="phase === 'source'" class="flex flex-col gap-4">
        <div>
          <div class="mb-1.5 text-xs text-ink-gray-5">
            {{ __('List name') }} <span class="text-ink-red-3">*</span>
          </div>
          <FormControl
            v-model="listName"
            type="text"
            :placeholder="__('e.g. ISTL LeadPack — Jun 2026')"
          />
          <div class="mt-1 text-xs text-ink-gray-5">
            {{
              __(
                'These leads get their own saved list + board view and stay off the main Leads view until you promote them.',
              )
            }}
          </div>
        </div>

        <div>
          <div class="mb-1.5 text-xs text-ink-gray-5">
            {{ __('Source (optional)') }}
          </div>
          <FormControl
            v-model="source"
            type="text"
            :placeholder="__('e.g. iSpeedToLead')"
          />
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
            :rows="9"
            :placeholder="
              __(
                'First Name\tLast Name\tPhone\tEmail\tProperty Address\nJane\tDoe\t+13125551234\tjane@x.com\t123 Main St',
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
          <Button
            variant="ghost"
            :label="__('Back')"
            @click="phase = 'source'"
          />
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
                    <option v-for="f in fieldOptions" :key="f.value" :value="f.value">
                      {{ f.label }}
                    </option>
                  </select>
                </td>
              </tr>
            </tbody>
          </table>
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
        <div
          class="flex items-start gap-2.5 rounded-md bg-surface-green-1 px-3 py-2.5"
        >
          <CircleCheckIcon class="mt-0.5 size-4 shrink-0 text-ink-green-3" />
          <div class="text-sm">
            <div class="font-medium text-ink-gray-8">
              {{ __('Imported into') }} “{{ result.list_name }}”
            </div>
            <div class="mt-0.5 text-ink-gray-6">
              <span class="font-medium text-ink-gray-8">{{ result.created }}</span>
              {{ __('new leads created') }} ·
              <span class="font-medium text-ink-gray-8">{{ result.matched }}</span>
              {{ __('already existed (tagged, left visible)') }}
              <template v-if="result.skipped">
                · {{ result.skipped }} {{ __('skipped') }}
              </template>
            </div>
          </div>
        </div>

        <div class="text-sm text-ink-gray-6">
          {{
            __(
              'New leads are parked out of the main Leads view. Open the list below to work them.',
            )
          }}
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
          :label="__('Import') + ' ' + parsed.rows.length + ' ' + __('leads')"
          :loading="importing"
          @click="runImport"
        />
        <template v-else-if="phase === 'done'">
          <Button
            variant="solid"
            :label="__('Open list')"
            @click="openList"
          />
          <Button :label="__('Close')" @click="show = false" />
        </template>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
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

const show = defineModel({ type: Boolean })
const emit = defineEmits(['imported'])
const router = useRouter()

const phase = ref('source')
const listName = ref('')
const source = ref('')
const raw = ref('')
const error = ref('')
const importing = ref(false)
const done = ref(0)
const result = ref({})
const parsed = ref({ headers: [], rows: [] })
const mapping = ref([])

const CHUNK = 200

const dialogTitle = computed(
  () =>
    ({
      source: __('Import leads'),
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

/* ── field list: real CRM Lead fields, so custom ones (property_address,
      bedrooms, lead_cost…) are mappable without hardcoding a list here ── */
const fields = createResource({
  url: 'crm.api.doc.get_filterable_fields',
  params: { doctype: 'CRM Lead' },
  cache: ['import-fields', 'CRM Lead'],
  auto: true,
  transform: (d) => d || [],
})

const SKIP = new Set([
  'name',
  'owner',
  'modified_by',
  'converted',
  'lead_name',
  '_assign',
  '_liked_by',
  'import_lists',
  'import_hidden',
])

const fieldOptions = computed(() =>
  (fields.data || [])
    .filter((f) => f.fieldname && !SKIP.has(f.fieldname))
    .map((f) => ({ label: f.label || f.fieldname, value: f.fieldname }))
    .sort((a, b) => a.label.localeCompare(b.label)),
)

/* ── header -> fieldname aliases. Left side is normalised (lowercase,
      alphanumeric only). Covers the iSpeedToLead LeadPack sheet plus the
      usual spreadsheet spellings. ── */
const ALIASES = {
  firstname: 'first_name',
  fname: 'first_name',
  lastname: 'last_name',
  lname: 'last_name',
  fullname: 'first_name',
  name: 'first_name',
  phone: 'mobile_no',
  phonenumber: 'mobile_no',
  mobile: 'mobile_no',
  mobileno: 'mobile_no',
  cell: 'mobile_no',
  cellphone: 'mobile_no',
  primaryphone: 'mobile_no',
  email: 'email',
  emailaddress: 'email',
  propertyaddress: 'property_address',
  address: 'property_address',
  streetaddress: 'property_address',
  street: 'property_address',
  city: 'property_city',
  propertycity: 'property_city',
  state: 'property_state',
  stateid: 'property_state',
  propertystate: 'property_state',
  zip: 'property_zip',
  zipcode: 'property_zip',
  postalcode: 'property_zip',
  propertyzip: 'property_zip',
  county: 'property_county',
  propertycounty: 'property_county',
  typeofproperty: 'property_type',
  propertytype: 'property_type',
  bedrooms: 'bedrooms',
  beds: 'bedrooms',
  bathrooms: 'bathrooms',
  baths: 'bathrooms',
  squarefootage: 'square_footage',
  sqft: 'square_footage',
  squarefeet: 'square_footage',
  yearofconstruction: 'year_built',
  yearbuilt: 'year_built',
  sellermotivation: 'property_reason_for_sell',
  reasonforselling: 'property_reason_for_sell',
  howfasttheywanttosell: 'property_duration_to_sell',
  anyonelivinginthehouse: 'property_occupied_by',
  leadcost: 'lead_cost',
  cost: 'lead_cost',
  notes: 'lead_summary',
  leadsummary: 'lead_summary',
}

function norm(s) {
  return String(s || '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '')
}

function guessField(header) {
  const n = norm(header)
  if (!n) return ''
  const opts = fieldOptions.value
  const has = (v) => opts.some((f) => f.value === v)
  // Only accept an alias the field list actually offers, otherwise the <select>
  // renders blank (value not among its options) while still importing — the
  // mapping shown wouldn't match the mapping used.
  if (ALIASES[n] && has(ALIASES[n])) return ALIASES[n]
  const exact = opts.find((f) => norm(f.value) === n || norm(f.label) === n)
  if (exact) return exact.value
  const partial = opts.find(
    (f) => norm(f.label).startsWith(n) && n.length >= 4,
  )
  return partial ? partial.value : ''
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
  if (!listName.value.trim()) {
    error.value = __('A list name is required.')
    return
  }
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
    list_name: listName.value.trim(),
    created: 0,
    matched: 0,
    skipped: 0,
    errors: [],
    error_count: 0,
    views: [],
  }

  try {
    for (let i = 0; i < rows.length; i += CHUNK) {
      const chunk = rows.slice(i, i + CHUNK)
      const res = await call('crm.api.lead_import.import_leads', {
        list_name: listName.value.trim(),
        rows: JSON.stringify(chunk),
        source: source.value.trim() || null,
      })
      totals.created += res.created || 0
      totals.matched += res.matched || 0
      totals.skipped += res.skipped || 0
      totals.error_count += res.error_count || 0
      if (res.errors?.length) totals.errors.push(...res.errors)
      if (res.views?.length) totals.views = res.views
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

function openList() {
  show.value = false
  // CRM View Settings is autoincrement-named, so ?view= wants the row's
  // integer name, not the label.
  const listView = (result.value.views || []).find((v) => v.type === 'list')
  // viewType is a route param, not a query arg — without it the URL is
  // /leads/view?view=N and no view is resolved at all.
  router.push({
    name: 'Leads',
    params: { viewType: 'list' },
    query: listView ? { view: listView.name } : {},
  })
}

watch(show, (v) => {
  if (!v) return
  phase.value = 'source'
  listName.value = ''
  source.value = ''
  raw.value = ''
  error.value = ''
  done.value = 0
  result.value = {}
  parsed.value = { headers: [], rows: [] }
  mapping.value = []
})
</script>
